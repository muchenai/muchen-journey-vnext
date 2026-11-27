"""Exercise the real course publishing, access and study paths with separate session cookies."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from journey_api.academy_routes import now
from journey_api.config import get_settings
from journey_api.course_learning import new_state
from journey_api.course_workspace_models import CourseRosterCode, CourseStudyRecord
from journey_api.management_access_models import CourseManagementSettings
from journey_api.db import SessionLocal
from journey_api.directory_cache_models import DirectoryMember
from journey_api.identity import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    STAFF_CSRF_COOKIE,
    STAFF_SESSION_COOKIE,
    credential_hash,
)
from journey_api.main import app
from journey_api.models import (
    CompletionCode,
    ExternalIdentity,
    IdentitySession,
    Organization,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.review_admin_routes import directory_subject

OPS = "/api/v1/ops/course-workspace"
ME = "/api/v1/me/course-workspace"


def identity(org, role, name, staff_level=None):
    uid, secret, csrf = uuid.uuid4(), uuid.uuid4().hex, uuid.uuid4().hex
    settings = get_settings()
    with SessionLocal.begin() as session:
        session.add(User(id=uid, organization_id=org, display_name=name, status=UserStatus.ACTIVE))
        session.flush()
        session.add(RoleAssignment(id=uuid.uuid4(), organization_id=org, user_id=uid, role=role))
        if staff_level:
            session.add(
                ReviewAdminAccess(
                    organization_id=org,
                    user_id=uid,
                    access_role=staff_level,
                    granted_by=uid,
                    can_grant_super_admin=staff_level == "super_admin",
                )
            )
        session.add(
            IdentitySession(
                id=uuid.uuid4(),
                organization_id=org,
                user_id=uid,
                role=role,
                token_hash=credential_hash(settings.session_secret, "session", secret),
                csrf_token_hash=credential_hash(settings.session_secret, "csrf", csrf),
                expires_at=now() + timedelta(hours=1),
            )
        )
    staff = role != Role.LEARNER
    client = TestClient(app, base_url="http://localhost")
    client.cookies.set(STAFF_SESSION_COOKIE if staff else SESSION_COOKIE, secret)
    client.cookies.set(STAFF_CSRF_COOKIE if staff else CSRF_COOKIE, csrf)
    client.headers.update({"X-CSRF-Token": csrf, "X-Journey-Session-Scope": "staff" if staff else "learner"})
    return client, uid


@pytest.fixture
def people():
    org = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=org, name="课程工作台测试"))
    owner, _ = identity(org, Role.REVIEWER, "负责人", "super_admin")
    admin, _ = identity(org, Role.REVIEWER, "发布人", "admin")
    student, uid = identity(org, Role.LEARNER, "学员")
    return owner, admin, student, uid


def data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def draft(*, title="课程", video=False):
    material = dict(
        id="m1", title="学习材料", kind="video" if video else "link", url="https://example.com/material"
    )
    if video:
        material["durationSeconds"] = 100
    return dict(
        title=title,
        summary="练习",
        minutes=12,
        tags=[],
        contentText="发布人讲义",
        rubric="正确陈述核心概念",
        materials=[material],
        chapters=[
            dict(
                id="ch",
                title="第一章",
                exam="",
                homework="写出应用步骤",
                homeworkXp=5,
                sections=[dict(id="sec", title="学习", materialIds=["m1"])],
            )
        ],
    )


def test_publish_review_live_version_and_real_learning(people, monkeypatch):
    owner, admin, student, uid = people
    course = draft()
    course["creationId"] = str(uuid.uuid4())
    pending = data(admin.post(OPS, json={"action": "saveCourse", "course": course, "intent": "publish"}))[
        "courses"
    ][0]
    assert pending["status"] == "pending" and not data(student.get(ME))["courses"]
    assert (
        len(
            data(admin.post(OPS, json={"action": "saveCourse", "course": course, "intent": "publish"}))[
                "courses"
            ]
        )
        == 1
    )
    review = dict(action="reviewCourse", id=pending["id"], revision=pending["revision"], decision="approve")
    assert admin.post(OPS, json=review).status_code == 403
    published = data(owner.post(OPS, json=review))["courses"][0]
    assert published["status"] == "published" and not student.get(OPS).is_success
    learner = data(student.get(ME))["courses"][0]
    catalog_course = data(student.get("/api/v1/me/academy"))["courses"][0]
    assert catalog_course["id"] == learner["id"]
    assert learner["updatedAt"] == catalog_course["updatedAt"] == published["updatedAt"]
    assert learner["progressUpdatedAt"] is None and catalog_course["progressUpdatedAt"] is None
    assert "rubric" not in learner and "returnReason" not in learner
    cmd = dict(id=learner["id"], revision=learner["revision"], chapterId="ch")
    assert (
        student.post(
            ME, json={**cmd, "command": "assessment", "kind": "homework", "text": "步骤"}
        ).status_code
        == 409
    )
    opened = data(student.post(ME, json={**cmd, "command": "readMaterial", "materialId": "m1"}))
    catalog_course = data(student.get("/api/v1/me/academy"))["courses"][0]
    assert opened["updatedAt"] == catalog_course["updatedAt"] == published["updatedAt"]
    study_time = opened["progressUpdatedAt"]
    assert study_time and study_time != published["updatedAt"]
    assert catalog_course["progressUpdatedAt"] == data(owner.get(OPS))["progress"][0]["updatedAt"] == study_time
    result = data(
        student.post(ME, json={**cmd, "command": "assessment", "kind": "homework", "text": "第一步"})
    )
    assert result["chapterProgress"]["ch"]["homework"]["awardedXp"] == 5
    data(student.post(ME, json={**cmd, "command": "assessment", "kind": "homework", "text": "重复"}))

    class Reviewer:
        def review(self, system, evidence):
            assert evidence["lecture"] == course["contentText"] and evidence["rubric"] == course["rubric"]
            return '{"score":94,"passed":true,"feedback":"能将概念应用于练习。"}'

    monkeypatch.setattr("journey_api.course_learning.get_reviewer", lambda: Reviewer())
    monkeypatch.setattr(
        "journey_api.course_learning.get_settings", lambda: SimpleNamespace(ai_self_check_enabled=True)
    )
    graded = data(student.post(ME, json={**cmd, "command": "reflection", "text": "我的心得"}))
    assert graded["completed"] and graded["progress"] == 100
    assert data(student.get(ME))["academyXp"] == 25
    legacy_code = "AC-" + uuid.uuid4().hex[:16].upper()
    with SessionLocal.begin() as session:
        org = session.get(User, uid).organization_id
        session.add(CourseRosterCode(user_id=uid, organization_id=org, code=legacy_code))
    current = data(owner.get(OPS))
    assert current["progress"][0]["completedChapters"] == 1
    assert [p["id"] for p in current["learners"]] == [str(uid)]
    assert "code" not in current["learners"][0]
    assert owner.post(OPS, json={"action": "issueCode", "userId": str(uid)}).status_code == 422
    assert student.post(ME, json={"command": "identify", "code": legacy_code}).status_code == 422
    edited = data(
        admin.post(
            OPS,
            json={"action": "saveCourse", "course": {**published, "title": "调整名称"}, "intent": "draft"},
        )
    )["courses"][0]
    assert (
        edited["liveRevision"] == published["revision"]
        and data(student.get(ME))["courses"][0]["title"] == "课程"
    )
    assert (
        owner.post(
            OPS, json={"action": "unpublish", "id": published["id"], "revision": published["revision"]}
        ).status_code
        == 409
    )
    retired = data(
        owner.post(OPS, json={"action": "unpublish", "id": edited["id"], "revision": edited["revision"]})
    )["courses"][0]
    assert not data(student.get(ME))["courses"]
    saved = data(
        owner.post(
            OPS,
            json={"action": "saveCourse", "course": {**retired, "title": "再次编辑标题"}, "intent": "draft"},
        )
    )["courses"][0]
    republished = data(owner.post(OPS, json={"action": "saveCourse", "course": saved, "intent": "publish"}))[
        "courses"
    ][0]
    learner = data(student.get(ME))["courses"][0]
    assert learner["revision"] == cmd["revision"] and learner["completed"]
    assert data(student.get(ME))["academyXp"] == 25
    changed = {**republished, "contentText": "更新了实际教学内容"}
    data(owner.post(OPS, json={"action": "saveCourse", "course": changed, "intent": "publish"}))
    learner = data(student.get(ME))["courses"][0]
    assert learner["revision"] != cmd["revision"] and not learner["completed"]


@pytest.mark.parametrize("camp", ["academy", "village"])
def test_progress_visible_only_to_course_author_or_organization_super_admin(people, camp):
    super_admin, course_owner, student, uid = people
    path = f"{OPS}?camp={camp}"
    access_path = "/api/v1/ops/course-access"
    assert super_admin.get(access_path).status_code == 404
    assert super_admin.post(access_path, json={"action": "saveRoles"}).status_code == 404
    course_owner_id = data(course_owner.get(path))["actorId"]
    super_id = uuid.UUID(data(super_admin.get(path))["actorId"])
    with SessionLocal.begin() as session:
        org = session.get(User, uid).organization_id
        # An ordinary super admin has full report access without grant authority or a course assignment.
        access = session.get(ReviewAdminAccess, super_id)
        access.can_grant_super_admin = False
        other_org = uuid.uuid4()
        session.add(Organization(id=other_org, name="独立测试组织"))
    publisher, publisher_id = identity(org, Role.REVIEWER, "发布人", "admin")
    reviewer_client, reviewer_id = identity(org, Role.REVIEWER, "仅负责审核", "admin")
    foreign_super, _ = identity(other_org, Role.REVIEWER, "另一组织超级管理员", "super_admin")
    with SessionLocal.begin() as session:
        # Persisted assignments from older releases must not change member certification.
        session.add(CourseManagementSettings(organization_id=org, revision=2, tags=[], issuers=[],
            assignments={"ownerId": course_owner_id, "adminIds": [str(publisher_id)],
                         "reviewers": [{"personId": str(reviewer_id), "tagNames": []}]}))
    assert data(super_admin.get(path))["isSuperAdmin"]
    assert not data(course_owner.get(path))["isSuperAdmin"]
    assert course_owner.post(path, json={"action": "saveTags", "tags": ["草稿"]}).status_code == 403
    assert data(super_admin.post(path, json={"action": "saveTags", "tags": ["测试标签"]}))["tags"] == ["测试标签"]

    def publish(client, title):
        catalog = data(client.post(path, json={
            "action": "saveCourse", "intent": "publish", "course": {**draft(title=title), "required": True},
        }))["courses"]
        return next(course for course in catalog if course["title"] == title)

    owner_course = publish(course_owner, "负责人发布")
    pending = publish(publisher, "兼任审核的发布人发布")
    foreign_course = publish(foreign_super, "另一组织课程")
    assert owner_course["status"] == pending["status"] == "pending"
    assert foreign_course["status"] == "published"
    assert data(publisher.get(path))["progress"] == []
    for item in (owner_course, pending):
        decision = {"action": "reviewCourse", "id": item["id"], "revision": item["revision"], "decision": "approve"}
        assert reviewer_client.post(path, json=decision).status_code == 403
        assert course_owner.post(path, json=decision).status_code == 403
        assert foreign_super.post(path, json=decision).status_code == 404
        data(super_admin.post(path, json=decision))
    # Other administrators can see published editions but not a pending change to someone else's course.
    visible_course = next(c for c in data(reviewer_client.get(path))["courses"] if c["id"] == pending["id"])
    assert visible_course["status"] == "published"
    revised = data(publisher.post(path, json={"action": "saveCourse", "intent": "draft",
        "course": {**visible_course, "title": "内部修订草稿"}}))["courses"]
    assert any(c["title"] == "内部修订草稿" for c in revised)
    assert all(c["title"] != "内部修订草稿" for c in data(reviewer_client.get(path))["courses"])
    for course in data(student.get(f"{ME}?camp={camp}"))["courses"]:
        data(student.post(f"{ME}?camp={camp}", json={
            "id": course["id"], "revision": course["revision"], "command": "readMaterial", "materialId": "m1",
        }))
    for client, expected in (
        (course_owner, [owner_course]), (publisher, [pending]), (reviewer_client, []),
        (super_admin, [owner_course, pending]),
    ):
        report = data(client.get(path))
        assert {course["id"]: course["title"] for course in report["progressCourses"]} == {
            course["id"]: course["title"] for course in expected
        }
        assert len(report["progress"]) == len(expected)
        assert {(row["learnerId"], row["courseId"]) for row in report["progress"]} == {
            (str(uid), course["id"]) for course in expected
        }
        assert all(row["updatedAt"] and row["percent"] > 0 for row in report["progress"])
        if client is reviewer_client:
            assert report["learners"] == []
        for course in (owner_course, pending):
            details = client.get(OPS + "/village-reflections", params={"courseId": course["id"], "learnerId": str(uid)})
            if camp == "academy":
                assert details.status_code == 404
            elif course not in expected:
                assert details.status_code == 403
            else:
                assert data(details)["chapters"][0]["text"] is None
    if camp == "village":
        endpoint = OPS + "/village-reflections"
        params = {"courseId": owner_course["id"], "learnerId": str(uid)}
        assert student.get(endpoint, params=params).status_code == 403
        assert foreign_super.get(endpoint, params=params).status_code == 404
        assert super_admin.get(endpoint, params={**params, "courseId": foreign_course["id"]}).status_code == 404
        _, foreign_learner = identity(other_org, Role.LEARNER, "同名学员")
        for ineligible in (foreign_learner, super_id):
            assert super_admin.get(endpoint, params={**params, "learnerId": str(ineligible)}).status_code == 404


@pytest.mark.parametrize("camp", ["academy", "village"])
def test_super_admin_manages_another_publishers_course(people, camp):
    manager, publisher, learner, learner_id = people
    path = f"{OPS}?camp={camp}"
    with SessionLocal.begin() as session:
        org = session.get(User, learner_id).organization_id
        foreign_org = uuid.uuid4()
        session.add(Organization(id=foreign_org, name="独立组织"))
    ordinary, _ = identity(org, Role.REVIEWER, "另一发布人", "admin")
    foreign_super, _ = identity(foreign_org, Role.REVIEWER, "管理员", "super_admin")
    created = data(publisher.post(path, json={"action": "saveCourse", "intent": "draft", "course": draft()}))["courses"][0]
    publish = {"action": "saveCourse", "intent": "publish", "course": {**created, "title": "更新后的课程"}}
    assert ordinary.post(path, json=publish).status_code == 403
    assert foreign_super.post(path, json=publish).status_code == 404
    published = data(manager.post(path, json=publish))["courses"][0]
    assert published["status"] == "published" and published["author"] == created["author"]
    retire = {"action": "unpublish", "id": created["id"], "revision": published["revision"]}
    assert ordinary.post(path, json=retire).status_code == 403
    assert foreign_super.post(path, json=retire).status_code == 404
    retired = data(manager.post(path, json=retire))["courses"][0]
    assert not data(learner.get(f"{ME}?camp={camp}"))["courses"]
    restored = data(manager.post(path, json={**publish, "course": retired}))["courses"][0]
    assert restored["status"] == "published" and restored["author"] == created["author"]
    assert data(learner.get(f"{ME}?camp={camp}"))["courses"][0]["id"] == created["id"]


@pytest.mark.parametrize("camp", ["village", "academy"])
def test_pending_course_follows_role_changes_and_records_a_required_return_reason(people, camp):
    supervisor, publisher, _, _ = people
    path = f"{OPS}?camp={camp}"
    submitted = data(publisher.post(path, json={"action": "saveCourse", "intent": "publish", "course": draft()}))
    course = submitted["courses"][0]
    command = {"action": "reviewCourse", "id": course["id"], "revision": course["revision"], "decision": "return"}
    assert publisher.post(path, json={**command, "reason": "补充讲义"}).status_code == 403
    with SessionLocal.begin() as session:
        staff = session.get(ReviewAdminAccess, uuid.UUID(submitted["actorId"]))
        staff.access_role = "super_admin"
    assert supervisor.post(path, json={**command, "reason": " "}).status_code == 422
    returned = data(publisher.post(path, json={**command, "reason": "请补充章节讲义"}))["courses"][0]
    assert returned["status"] == "returned" and returned["returnReason"] == "请补充章节讲义"
    republication = data(publisher.post(path, json={"action": "saveCourse", "intent": "publish", "course": returned}))
    assert republication["isSuperAdmin"] and republication["courses"][0]["status"] == "published"


def test_village_required_and_verified_video(people):
    owner, _, student, _ = people
    path = OPS + "?camp=village"
    data(
        owner.post(
            path, json={"action": "saveCourse", "course": {**draft(), "required": True}, "intent": "publish"}
        )
    )
    elective = data(
        owner.post(
            path,
            json={
                "action": "saveCourse",
                "course": {**draft(title="普通", video=True), "required": False},
                "intent": "publish",
            },
        )
    )
    eid = next(c["id"] for c in elective["courses"] if not c["required"])
    path = ME + "?camp=village"
    listing = data(student.get(path))
    assert (
        listing["requiredRemaining"] == 1
        and len(listing["lockedCourses"]) == 1
        and len(listing["courses"]) == 1
    )
    mandatory = listing["courses"][0]
    summary = data(student.get(ME + "/village-summary"))
    assert summary["requiredRemaining"] == 1 and summary["requiredCourses"][0]["id"] == mandatory["id"]
    assert summary["electiveCourses"][0]["id"] == eid
    assert student.post(path, json={"id": eid, "command": "favorite", "saved": True}).status_code == 403
    common = dict(id=mandatory["id"], revision=mandatory["revision"], chapterId="ch")
    for payload in (
        dict(command="readMaterial", materialId="m1"),
        dict(command="assessment", kind="homework", text="提交"),
        dict(command="reflection", text="心得"),
    ):
        data(student.post(path, json={**common, **payload}))
    unlocked = data(student.get(path))
    assert not unlocked["requiredRemaining"] and not unlocked["lockedCourses"]
    elective = next(c for c in unlocked["courses"] if c["id"] == eid)
    video = ME + f"/{eid}/watch/m1?camp=village&revision=" + str(elective["revision"])
    assert data(student.get(video))["durationSeconds"] == 100
    started = data(student.post(video, json={"action": "start", "duration": 100, "position": 0}))
    assert (
        student.post(
            video, json={"action": "complete", "sessionId": started["sessionId"], "position": 100}
        ).status_code
        == 409
    )
    assert not data(student.get(video))["completed"]


def graduation_link(source, recipient, *, used=True):
    stamp = now()
    return CompletionCode(
        id=uuid.uuid4(), organization_id=source.organization_id,
        user_id=source.id, migrated_to_user_id=recipient,
        code_hash=uuid.uuid4().hex, code_ciphertext="test", code_hint="test",
        created_at=stamp - timedelta(days=3), expires_at=stamp - timedelta(days=1),
        used_at=stamp - timedelta(days=2) if used else None,
    )


def test_village_reflections_show_exact_submissions_for_current_course_and_inherited_learner(people):
    owner, _, source, source_id = people
    staff_path = OPS + "?camp=village"
    learner_path = ME + "?camp=village"
    endpoint = OPS + "/village-reflections"
    course = draft()
    course["materials"].append({**course["materials"][0], "id": "m2"})
    course["chapters"].append({
        "id": "second", "title": "第二章", "sections": [{"id": "sec2", "title": "学习", "materialIds": ["m2"]}],
    })

    def save(version, intent):
        return data(owner.post(staff_path, json={"action": "saveCourse", "intent": intent, "course": version}))["courses"][0]

    published = save(course, "publish")
    command = {"id": published["id"], "revision": published["revision"], "chapterId": "ch"}
    answer = "第一行 <示例> & 观察\n  第二行保留缩进。"
    data(source.post(learner_path, json={**command, "command": "readMaterial", "materialId": "m1"}))
    saved = data(source.post(learner_path, json={**command, "command": "reflection", "text": answer}))
    submitted = saved["chapterProgress"]["ch"]["reflection"]
    with SessionLocal() as session:
        org = session.get(User, source_id).organization_id
    _, current_id = identity(org, Role.LEARNER, "飞书学员")
    _, namesake_id = identity(org, Role.LEARNER, "飞书学员")
    with SessionLocal.begin() as session:
        original = session.get(User, source_id)
        original.status = UserStatus.DISABLED
        session.add(graduation_link(original, current_id))

    params = {"courseId": published["id"], "learnerId": str(current_id), "courseRevision": published["revision"]}
    expected_chapters = [
        {"id": "ch", "title": "第一章", "text": answer, "submittedAt": submitted["time"]},
        {"id": "second", "title": "第二章", "text": None, "submittedAt": None},
    ]
    draft_change = save({**published, "title": "修订中的标题"}, "draft")
    assert data(owner.get(endpoint, params=params)) == {
        "courseTitle": published["title"], "learnerName": "飞书学员", "chapters": expected_chapters,
    }
    assert owner.get(endpoint, params={**params, "learnerId": str(source_id)}).status_code == 404
    namesake = data(owner.get(endpoint, params={**params, "learnerId": str(namesake_id)}))
    assert all(ch["text"] is None for ch in namesake["chapters"])

    renamed = save(draft_change, "publish")
    assert owner.get(endpoint, params=params).status_code == 409
    params["courseRevision"] = renamed["revision"]
    assert data(owner.get(endpoint, params=params))["chapters"] == expected_chapters
    updated = save({**renamed, "materials": [{**item, "url": "https://example.com/new"} for item in renamed["materials"]]}, "publish")
    params["courseRevision"] = updated["revision"]
    assert all(ch["text"] is None for ch in data(owner.get(endpoint, params=params))["chapters"])
    data(owner.post(staff_path, json={"action": "unpublish", "id": updated["id"], "revision": updated["revision"]}))
    assert owner.get(endpoint, params=params).status_code == 404


@pytest.mark.parametrize("camp", ["village", "academy"])
def test_staff_reports_migrated_video_progress_under_the_current_learner(people, monkeypatch, camp):
    owner, _, _, source_id = people
    staff_path = f"{OPS}?camp={camp}"
    learner_path = f"{ME}?camp={camp}"
    published = data(owner.post(staff_path, json={
        "action": "saveCourse", "intent": "publish", "course": {**draft(video=True), "required": True},
    }))["courses"][0]
    with SessionLocal() as session:
        org = session.get(User, source_id).organization_id
    monkeypatch.setattr(get_settings(), "feishu_learner_organization_id", org)
    open_id = "ou_" + uuid.uuid4().hex
    directory_member = dict(name="飞书通讯录姓名", employee_no="MCE123", job_title="工程师",
                            departments=["开发部"], department_paths=["研发中心 / 开发部"],
                            avatar="https://example.com/avatar.jpg", open_id=open_id)
    learner, current_id = identity(org, Role.LEARNER, "迁移后的飞书学员")
    _, namesake = identity(org, Role.LEARNER, "迁移后的飞书学员")
    course = data(learner.get(learner_path))["courses"][0]
    video = f"{ME}/{course['id']}/watch/m1?camp={camp}&revision={course['revision']}"
    # The recipient may already have a record. Matching the learner view must select its inherited one.
    stamp = now()
    monkeypatch.setattr("journey_api.course_watch.now", lambda: stamp)
    previous = data(learner.post(video, json={"action": "start", "duration": 100, "position": 0}))
    stamp += timedelta(seconds=14)
    data(learner.post(video, json={"action": "pause", "sessionId": previous["sessionId"], "position": 14}))
    with SessionLocal.begin() as session:
        source = session.get(User, source_id)
        source.status = UserStatus.DISABLED
        session.add(graduation_link(source, current_id))
        feishu = ExternalIdentity(
            id=uuid.uuid4(), organization_id=org, user_id=current_id, provider="FEISHU", subject=directory_subject(open_id),
        )
        session.add(DirectoryMember(organization_id=org, app_id=get_settings().feishu_app_id,
                                    open_id=open_id, search_name=directory_member["name"], profile=directory_member))
        session.add(feishu)
        session.flush()
        login = session.scalar(select(IdentitySession).where(IdentitySession.user_id == current_id))
        login.external_identity_id, login.external_identity_revision = feishu.id, feishu.revision

    started = data(learner.post(video, json={"action": "start", "duration": 100, "position": 0}))
    stamp += timedelta(seconds=12)
    data(learner.post(video, json={"action": "pause", "sessionId": started["sessionId"], "position": 12}))
    learned = data(learner.get(learner_path))["courses"][0]
    snapshot = data(owner.get(staff_path))
    rows = {row["learnerId"]: row for row in snapshot["progress"]}
    assert len(snapshot["progress"]) == 2 and set(rows) == {str(current_id), str(namesake)}
    members = {person["id"]: person for person in snapshot["learners"]}
    if camp == "village":
        assert members[str(current_id)]["memberProfile"] == {
            "name": "飞书通讯录姓名", "employeeNo": "MCE123", "jobTitle": "工程师",
            "departments": ["开发部"], "departmentPaths": ["研发中心 / 开发部"],
            "avatar": "https://example.com/avatar.jpg",
        }
        assert members[str(namesake)]["memberProfile"] is None
    else:
        assert all("memberProfile" not in person for person in members.values())
    current = rows[str(current_id)]
    assert current["learnerName"] == "迁移后的飞书学员" and current["status"] == "learning"
    assert current["watchedSeconds"] == learned["seconds"] == 12
    assert current["percent"] == learned["progress"] > 0
    assert current["updatedAt"] == learned["progressUpdatedAt"] == stamp.isoformat()
    assert rows[str(namesake)]["watchedSeconds"] == 0

    changed = {**published, "materials": [{**published["materials"][0], "durationSeconds": 120}]}
    updated = data(owner.post(staff_path, json={"action": "saveCourse", "intent": "publish", "course": changed}))
    new_row = next(r for r in updated["progress"] if r["learnerId"] == str(current_id))
    assert new_row["courseRevision"] != current["courseRevision"]
    assert new_row["watchedSeconds"] == new_row["percent"] == 0
    assert new_row["status"] == "not_started" and new_row["updatedAt"] is None


@pytest.mark.parametrize("link", ["unused", "foreign_org", "staff_only"])
def test_staff_report_does_not_inherit_from_ineligible_links(people, link):
    owner, _, learner, current_id = people
    publish = dict(action="saveCourse", intent="publish", course=draft(video=True))
    course = data(owner.post(OPS, json=publish))["courses"][0]
    with SessionLocal.begin() as session:
        org = session.get(User, current_id).organization_id
        if link == "foreign_org":
            org = uuid.uuid4()
            session.add(Organization(id=org, name="其他组织"))
            session.flush()
        source = User(id=uuid.uuid4(), organization_id=org, display_name="学员", status=UserStatus.DISABLED)
        session.add(source)
        session.flush()
        recipient = current_id
        if link == "staff_only":
            recipient = session.scalar(
                select(User.id).where(User.organization_id == org, User.display_name == "负责人")
            )
        session.add(graduation_link(source, recipient, used=link != "unused"))
        state = {**new_state(), "watches": {"m1": {"watchedSeconds": 75}}, "updatedAt": now().isoformat()}
        session.add(CourseStudyRecord(
            course_id=uuid.UUID(course["id"]), user_id=source.id, revision=course["revision"], state=state,
        ))
    rows = data(owner.get(OPS))["progress"]
    assert [r["learnerId"] for r in rows] == [str(current_id)]
    assert rows[0]["watchedSeconds"] == data(learner.get(ME))["courses"][0]["seconds"] == 0
    assert rows[0]["updatedAt"] is None and rows[0]["status"] == "not_started"


def test_private_course_attachment_reaches_only_a_live_course(people):
    owner, admin, learner, _ = people
    endpoint = "/api/v1/review-admin/content-assets"
    source = "课程附件中的正文与核心概念。".encode()
    upload = data(
        owner.post(endpoint, json={"name": "chapter.txt", "size": len(source), "purpose": "course"})
    )
    asset = upload["id"]
    data(
        owner.put(
            f"{endpoint}/{asset}/chunks/0",
            content=source,
            headers={"Content-Type": "application/octet-stream"},
        )
    )
    data(owner.post(f"{endpoint}/{asset}/complete"))
    private_url = f"/api/v1/me/course-assets/{asset}"
    assert learner.get(private_url).status_code == 404
    course = draft()
    course["contentText"] = ""
    course["materials"] = [
        {"id": "m1", "title": "讲义", "assetId": asset, "url": "https://example.com/replaced"}
    ]
    assert (
        admin.post(OPS, json={"action": "saveCourse", "intent": "publish", "course": course}).status_code
        == 403
    )
    row = data(owner.post(OPS, json={"action": "saveCourse", "intent": "publish", "course": course}))[
        "courses"
    ][0]
    item = data(learner.get(ME))["courses"][0]
    assert item["materials"][0]["url"] == f"/api/learner/course-assets/{asset}"
    assert "核心概念" in item["contentText"]
    assert learner.get(private_url).content == source
    data(owner.post(OPS, json={"action": "unpublish", "id": row["id"], "revision": row["revision"]}))
    assert learner.get(private_url).status_code == 404


def test_reflection_keeps_concurrently_submitted_chapter_work(people, monkeypatch):
    owner, _, student, _ = people
    course = draft()
    data(owner.post(OPS, json={"action": "saveCourse", "course": course, "intent": "publish"}))
    published = data(student.get(ME))["courses"][0]
    cmd = dict(id=published["id"], revision=published["revision"], chapterId="ch")
    data(student.post(ME, json={**cmd, "command": "readMaterial", "materialId": "m1"}))

    class Reviewer:
        def review(self, system, evidence):
            # Another request commits to the same learner record while the model is running.
            submission = data(
                student.post(
                    ME, json={**cmd, "command": "assessment", "kind": "homework", "text": "并行提交的作业"}
                )
            )
            assert submission["chapterProgress"]["ch"]["homework"]["awardedXp"] == 5
            return '{"score":90,"passed":true,"feedback":"通过"}'

    monkeypatch.setattr("journey_api.course_learning.get_reviewer", lambda: Reviewer())
    monkeypatch.setattr(
        "journey_api.course_learning.get_settings", lambda: SimpleNamespace(ai_self_check_enabled=True)
    )
    done = data(student.post(ME, json={**cmd, "command": "reflection", "text": "学习心得"}))
    assert done["completed"]
    assert done["chapterProgress"]["ch"]["homework"]["text"] == "并行提交的作业"
    assert data(student.get(ME))["academyXp"] == 25
