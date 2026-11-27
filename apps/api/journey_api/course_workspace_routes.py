"""Staff course publishing and authenticated learner delivery for Academy and village."""

import uuid
from copy import deepcopy
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.academy_routes import TAGS, audit, fail, now, require_staff_entry
from journey_api.auth import Actor, get_actor, get_company_learner_actor, inherited_learner_ids
from journey_api.course_learning import access, course_view, edit_command, live_list, progress, records_for
from journey_api.course_watch import watch
from journey_api.course_workspace_content import (
    asset_ids,
    edition,
    identifier,
    obj,
    presented,
    publish_edition,
    retired_learning,
    text,
)
from journey_api.course_workspace_models import (
    CourseStudyAward,
    CourseStudyPreference,
    CourseStudyRecord,
    WorkspaceCourse,
)
from journey_api.db import get_db
from journey_api.idempotency import find_replay, store_result
from journey_api.management_access import course_scope, set_course_tags
from journey_api.management_access_models import CourseManagementSettings
from journey_api.models import Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_routes import cached_directory_profiles, envelope

router = APIRouter()
Scope = Literal["academy", "village"]
staff = APIRouter(prefix="/api/v1/ops/course-workspace", dependencies=[Depends(require_staff_entry)])
learner = APIRouter(prefix="/api/v1/me")


def learner_directory(actor):
    return (
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.LEARNER,
        )
        .order_by(User.display_name, User.id)
    )


def can_view_staff_asset(session, actor, asset_id):
    rights = course_scope(session, actor)
    rows = session.scalars(
        select(WorkspaceCourse).where(WorkspaceCourse.organization_id == actor.organization_id)
    )
    for row in rows:
        editions = (row.draft, row.live) if rights["isSuperAdmin"] or row.author_id == actor.id else (row.live,)
        if any(course and str(asset_id) in asset_ids(course) for course in editions):
            return True
    return False


def lookup(session, actor, scope, course_id, *, live=False, lock=False):
    query = select(WorkspaceCourse).where(
        WorkspaceCourse.id == identifier(course_id),
        WorkspaceCourse.organization_id == actor.organization_id,
        WorkspaceCourse.scope == scope,
    )
    if live:
        query = query.where(WorkspaceCourse.live.is_not(None))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(query)
    if not row:
        fail("课程不存在或已下架。", 404)
    return row


def check_revision(expected, actual):
    if type(expected) is not int or expected != actual:
        fail("课程版本已更新，请刷新后重试。", 409)


def can_view_course_report(course, actor, staff_access):
    return course.live is not None and (staff_access["isSuperAdmin"] or course.author_id == actor.id)


def staff_snapshot(session, actor, scope):
    rights = course_scope(session, actor)
    rows = session.scalars(
        select(WorkspaceCourse)
        .where(WorkspaceCourse.organization_id == actor.organization_id, WorkspaceCourse.scope == scope)
        .order_by(WorkspaceCourse.id)
    ).all()
    # Approving or administering a course does not make the reviewer its publisher.
    report_courses = [r for r in rows if can_view_course_report(r, actor, rights)]
    records = {
        (r.course_id, r.user_id, r.revision): r.state
        for r in session.scalars(
            select(CourseStudyRecord).where(CourseStudyRecord.course_id.in_([r.id for r in report_courses]))
        )
    }
    people = session.scalars(learner_directory(actor)).all() if report_courses else []
    person_ids = [p.id for p in people]
    inherited = inherited_learner_ids(session, actor.organization_id, person_ids) if report_courses else {}
    roster = [{"id": str(p.id), "name": p.display_name} for p in people]
    if scope == "village" and report_courses and people:
        # Personnel belong to the current corporate account, even when study records are inherited.
        profiles = cached_directory_profiles(session, actor, person_ids)
        for person, entry in zip(people, roster, strict=True):
            profile = profiles.get(person.id)
            entry["memberProfile"] = {
                "name": profile.get("name") or person.display_name,
                "avatar": profile.get("avatar") or "",
                "employeeNo": profile.get("employee_no") or "",
                "jobTitle": profile.get("job_title") or "",
                "departmentPaths": profile.get("department_paths") or [],
                "departments": profile.get("departments") or [],
            } if profile else None
    progress_rows = []
    for course in report_courses:
        for person in people:
            record_owner = inherited.get(person.id, person.id)
            state = records.get((course.id, record_owner, course.live["learningRevision"]))
            learning = progress(course.live, state)
            progress_rows.append(
                {
                    **{
                        k: learning[k]
                        for k in (
                            "percent",
                            "watchedSeconds",
                            "updatedAt",
                            "status",
                            "completedChapters",
                            "chapterCount",
                        )
                    },
                    "learnerId": str(person.id),
                    "learnerName": person.display_name,
                    "courseId": str(course.id),
                    "courseTitle": course.live["title"],
                    "courseRevision": course.live["revision"],
                }
            )
    catalog = [
        {
            **presented(version, staff=True),
            "liveRevision": row.live["revision"] if row.live else None,
            "liveTitle": row.live["title"] if row.live else None,
        }
        for row in rows
        if (version := row.draft if rights["isSuperAdmin"] or row.author_id == actor.id else row.live)
    ]
    return {
        **rights,
        "courses": sorted(catalog, key=lambda c: c["updatedAt"], reverse=True),
        "learners": roster,
        "progressCourses": [{"id": str(r.id), "title": r.live["title"]} for r in report_courses],
        "progress": progress_rows,
        "shares": [],
        "canManageLegacy": rights["isSuperAdmin"],
    }


@staff.get("")
def admin_catalog(
    request: Request,
    camp: Scope = "academy",
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
):
    return envelope(request, staff_snapshot(session, actor, camp))


@staff.get("/village-reflections")
def village_reflections(
    request: Request,
    course_id: uuid.UUID = Query(alias="courseId"),
    learner_id: uuid.UUID = Query(alias="learnerId"),
    course_revision: int | None = Query(default=None, alias="courseRevision"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
):
    rights = course_scope(session, actor)
    course = lookup(session, actor, "village", course_id, live=True)
    if not can_view_course_report(course, actor, rights):
        fail("无权查看这门课程的学习情况。", 403)
    if course_revision is not None:
        check_revision(course_revision, course.live["revision"])
    person = session.scalar(learner_directory(actor).where(User.id == learner_id))
    if person is None:
        fail("学习情况中没有这位学员。", 404)

    inherited = inherited_learner_ids(session, actor.organization_id, [person.id])
    record = session.get(CourseStudyRecord, (course.id, inherited.get(person.id, person.id), course.live["learningRevision"]))
    states = record.state.get("chapters", {}) if record else {}
    chapters = []
    for chapter in course.live["chapters"]:
        reflection = states.get(chapter["id"], {}).get("reflection") or {}
        chapters.append({
            "id": chapter["id"],
            "title": chapter["title"],
            "text": reflection.get("text"),
            "submittedAt": reflection.get("time"),
        })
    return envelope(request, {"courseTitle": course.live["title"], "learnerName": person.display_name, "chapters": chapters})


@staff.post("")
def admin_command(
    request: Request,
    body: dict,
    camp: Scope = "academy",
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
):
    rights = course_scope(session, actor, lock=True)
    action = body.get("action")
    resource = actor.organization_id
    if action == "saveTags":
        if not rights["isSuperAdmin"]:
            fail("仅超级管理员可以管理课程标签。", 403)
        tags = body.get("tags")
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            fail("课程标签列表格式无效。")
        rows = session.scalars(
            select(WorkspaceCourse).where(WorkspaceCourse.organization_id == actor.organization_id)
        )
        if any(t not in tags for row in rows for c in (row.draft, row.live) if c for t in c["tags"]):
            fail("标签已被课程引用，请先编辑引用该标签的课程。", 409)
        set_course_tags(session, actor, tags)
    elif action == "saveCourse":
        data = obj(body.get("course"))
        create_key = (
            str(identifier(data["creationId"])) if not data.get("id") and data.get("creationId") else None
        )
        action_key = "course.workspace.create." + camp
        if create_key and find_replay(
            session, actor_id=actor.id, command=action_key, key=create_key, payload=body
        ):
            return envelope(request, staff_snapshot(session, actor, camp))
        if data.get("id"):
            row = lookup(session, actor, camp, data["id"], lock=True)
            if not rights["isSuperAdmin"] and row.author_id != actor.id:
                fail("只能编辑自己负责的课程。", 403)
            if row.draft["status"] == "pending":
                fail("课程正在审核中。", 409)
            check_revision(data.get("revision"), row.draft["revision"])
        else:
            row = WorkspaceCourse(
                id=uuid.uuid4(), organization_id=actor.organization_id, author_id=actor.id, scope=camp
            )
        if body.get("intent") not in ("draft", "publish"):
            fail("请选择保存草稿或发布课程。")
        draft = edition(session, actor, row, data, rights, body["intent"] == "publish")
        if draft["status"] == "published":
            publish_edition(row, draft)
        row.draft = draft
        session.add(row)
        resource = row.id
        if create_key:
            store_result(
                session,
                actor_id=actor.id,
                command=action_key,
                key=create_key,
                payload=body,
                response={"id": str(row.id)},
            )
    elif action in ("reviewCourse", "unpublish"):
        row = lookup(session, actor, camp, body.get("id"), lock=True)
        c = deepcopy(row.draft)
        check_revision(body.get("revision"), c["revision"])
        c["revision"] += 1
        if action == "unpublish":
            if not rights["isSuperAdmin"] and row.author_id != actor.id:
                fail("无课程下架权限。", 403)
            if not row.live:
                fail("课程已经下架。", 409)
            if c["status"] == "published":
                c["status"] = "unpublished"
            c["_retiredLearning"] = retired_learning(row.live)
            row.live = None
        else:
            if not rights["isSuperAdmin"]:
                fail("仅超级管理员可以审核课程。", 403)
            if c["status"] != "pending":
                fail("课程未处于待审核状态。", 409)
            if body.get("decision") == "return":
                c.update(status="returned", returnReason=text(body.get("reason"), 1200, True))
            elif body.get("decision") == "approve":
                c.update(status="published", returnReason="")
                publish_edition(row, c)
            else:
                fail("审核操作无效。")
        c["updatedAt"] = now().isoformat()
        if c["status"] == "published":
            row.live = deepcopy(c)
        row.draft = c
        resource = row.id
    else:
        fail("未知课程管理操作。")
    audit(session, request, actor, "course.workspace." + action, resource)
    session.commit()
    return envelope(request, staff_snapshot(session, actor, camp))


@learner.get("/course-workspace/village-summary")
def village_summary(
    request: Request, actor: Actor = Depends(get_company_learner_actor), session: Session = Depends(get_db)
):
    rows = live_list(session, actor, "village")
    records = records_for(session, actor, rows)
    required, elective = [], []
    for row in rows:
        course = row.live
        study = progress(course, records.get((row.id, course["learningRevision"])))
        summary = dict(
            id=str(row.id),
            title=course["title"],
            summary=course["summary"],
            chapters=len(course["chapters"]),
            completed=study["status"] == "passed",
            progress=study["percent"],
        )
        (required if course["required"] else elective).append(summary)
    return envelope(
        request,
        dict(
            requiredCourses=required,
            electiveCourses=elective,
            requiredTotal=len(required),
            requiredRemaining=sum(not c["completed"] for c in required),
        ),
    )


@learner.get("/course-workspace")
def catalog(
    request: Request,
    camp: Scope = "academy",
    actor: Actor = Depends(get_company_learner_actor),
    session: Session = Depends(get_db),
):
    return envelope(request, learner_catalog(session, actor, camp))


def learner_catalog(session, actor, camp):
    rows = live_list(session, actor, camp)
    records = records_for(session, actor, rows)
    ids = [r.id for r in rows]
    prefs = {
        r.course_id
        for r in session.scalars(
            select(CourseStudyPreference).where(
                CourseStudyPreference.course_id.in_(ids),
                CourseStudyPreference.user_id == actor.id,
                CourseStudyPreference.saved.is_(True),
            )
        )
    }
    awards = session.scalars(
        select(CourseStudyAward).where(
            CourseStudyAward.organization_id == actor.organization_id,
            CourseStudyAward.user_id == actor.id,
            CourseStudyAward.scope == camp,
        )
    ).all()
    settled = {a.course_id for a in awards if a.award_key == "series-completion"}
    courses = [
        course_view(
            r, records.get((r.id, r.live["learningRevision"])), favorite=r.id in prefs, settled=r.id in settled
        )
        for r in rows
    ]
    remaining = sum(c["required"] and not c["completed"] for c in courses)
    locked = [
        c for c in courses if camp == "village" and remaining and not c["required"] and not c["completed"]
    ]
    locked_ids = {c["id"] for c in locked}
    config = session.get(CourseManagementSettings, actor.organization_id)
    return {
        "courses": sorted(
            (c for c in courses if c["id"] not in locked_ids), key=lambda c: c["createdAt"], reverse=True
        ),
        "lockedCourses": [{"id": c["id"], "title": c["title"]} for c in locked],
        "requiredRemaining": remaining,
        "tags": config.tags if config else list(TAGS),
        "learner": {"id": str(actor.id), "name": actor.display_name},
        "academyXp": sum(a.xp for a in awards),
    }


@learner.post("/course-workspace")
def learn(
    request: Request,
    body: dict,
    camp: Scope = "academy",
    actor: Actor = Depends(get_company_learner_actor),
    session: Session = Depends(get_db),
):
    if body.get("command") not in ("favorite", "readMaterial", "assessment", "reflection"):
        fail("课程学习操作无效。")
    row = lookup(session, actor, camp, body.get("id"), live=True, lock=True)
    access(session, actor, row)
    return envelope(request, edit_command(session, actor, row, body))


@learner.get("/course-workspace/{course_id}/watch/{material_id}")
@learner.post("/course-workspace/{course_id}/watch/{material_id}")
def media_watch(
    course_id: uuid.UUID,
    material_id: str,
    revision: int,
    request: Request,
    body: dict | None = None,
    camp: Scope = "academy",
    actor: Actor = Depends(get_company_learner_actor),
    session: Session = Depends(get_db),
):
    row = lookup(session, actor, camp, course_id, live=True, lock=request.method == "POST")
    access(session, actor, row)
    if request.method == "POST" and not body:
        fail("视频请求无效。")
    return envelope(
        request, watch(session, actor, row, material_id, revision, body if request.method == "POST" else None)
    )


@learner.get("/course-assets/{asset_id}")
@learner.head("/course-assets/{asset_id}")
def learner_asset(
    asset_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_company_learner_actor),
    session: Session = Depends(get_db),
):
    from journey_api.content_assets import material_response, require_course_asset

    # Streams can be referenced in more than one course. Any accessible live edition grants access.
    for scope in ("academy", "village"):
        for row in live_list(session, actor, scope):
            if str(asset_id) in asset_ids(row.live):
                if scope == "village" and not row.live["required"]:
                    from journey_api.course_learning import remaining_courses

                    rec = session.get(CourseStudyRecord, (row.id, actor.id, row.live["learningRevision"]))
                    if (
                        remaining_courses(session, actor)
                        and progress(row.live, rec.state if rec else None)["status"] != "passed"
                    ):
                        continue
                return material_response(
                    request, session, require_course_asset(session, actor, asset_id), inline=True
                )
    fail("未找到可访问的课程文件。", 404)


router.include_router(staff)
router.include_router(learner)
