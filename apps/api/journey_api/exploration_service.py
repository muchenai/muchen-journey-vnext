"""Dynamic exploration uses pinned tasks and explicit human or AI provenance."""
import copy
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pydantic import Field
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from journey_api.errors import ApiError
from journey_api.exploration_models import ExplorationCatalogTask, ExplorationMaterial, ExplorationProgress, ExplorationWork
from journey_api.models import (Assignment, AssignmentStatus, CompletionCode, Decision, Enrollment,
    EnrollmentStatus, Evaluation, Organization, Role, RoleAssignment, Submission, SubmissionDraft,
    SubmissionVersion, TaskDefinition, TaskVersion, User, UserStatus)
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask
from journey_api.schemas import LearningMaterialInput, PublishTaskVersionCommand

TREASURES = ("compass", "crystal", "starmap", "key")
# This imported course is the sign-out boundary. Other check-in courses remain
# ordinary tasks, and editing this course's title does not change its identity.
TRAINING_CHECKOUT_TASK_KEY = "EXPLORATION-DYNAMIC-20261117-08"
MAX_MATERIAL_BYTES = 100 * 1024 * 1024
DEFAULT_REQUIREMENTS = {
    "learning": ["打开并学习全部有效学习材料。", "学完后点击进入下一板块，无需文字作业或人工审核。"],
    "checkin": ["完成培训签退，并成功进入项目培训群。", "确认已经进入项目培训群后完成本任务，无需文字作业。"],
    "assessment": ["打开测试文档，按文档要求完成测试。", "提交测试结果、结果链接或简短说明，等待审核。"],
}
SEED_REQUIREMENTS = {
    "learning": ["逐项打开并学习本任务的学习材料。", "学完后进入下一板块，无需提交文字作业或等待人工审核。"],
    "checkin": ["扫码签退，填写的手机号须与招聘时预留号码一致。",
        "签退后查看入项邀请、项目信息和负责人，并加入项目培训群；看不到项目请在培训群反馈。",
        "确认已经成功进入项目培训群后，完成培训签退。"],
    "assessment": ["阅读福利与实用信息学习材料。", "打开培训测试文档，按文档要求完成测试。",
        "提交测试结果、结果截图链接或简短说明，等待审核。"],
}
AI_ASSESSMENT_REQUIREMENTS = [
    "打开测试文档，按文档要求完成测试。",
    "按发布人员配置的评分标准进行 AI 评测，达到通过分数后自动完成任务。",
]


def default_requirements(mode, *, seed=False):
    return list((SEED_REQUIREMENTS if seed else DEFAULT_REQUIREMENTS)[mode])


def assessment_requirements(content, supplied):
    """Update generated instructions without replacing publisher-authored ones."""
    if ((content.get("completionMode") or "assessment") == "assessment"
            and content.get("reviewMode") == "ai"
            and supplied in (DEFAULT_REQUIREMENTS["assessment"], SEED_REQUIREMENTS["assessment"],
                AI_ASSESSMENT_REQUIREMENTS)):
        return list(AI_ASSESSMENT_REQUIREMENTS)
    if ((content.get("completionMode") or "assessment") == "assessment"
            and content.get("reviewMode") != "ai" and supplied == AI_ASSESSMENT_REQUIREMENTS):
        return default_requirements("assessment")
    return list(supplied)


def requirements_for_save(content, previous, *, seed=False):
    mode = content.get("completionMode") or "assessment"
    previous = previous if previous.get("camp") == "exploration" else {}
    previous_mode = previous.get("completionMode") or "assessment"
    inherited = previous.get("requirements") or default_requirements(previous_mode, seed=seed)
    supplied = content.get("requirements") or []
    if previous and mode == previous_mode:
        return assessment_requirements(content, supplied or inherited)
    if supplied and supplied != inherited:
        return assessment_requirements(content, supplied)
    return assessment_requirements(content, default_requirements(mode))


class ExplorationPublicationCommand(PublishTaskVersionCommand):
    title: str = Field(min_length=1, max_length=60)
    purpose: str = Field(min_length=1, max_length=2000)
    learner_outcome: str = Field(min_length=1, max_length=2000)
    # Twenty learning materials, twenty task files, and one legacy test link.
    learning_materials: list[LearningMaterialInput] = Field(default_factory=list, max_length=41)


def publication_command(content, **values):
    schema = ExplorationPublicationCommand if content.get("camp") == "exploration" else PublishTaskVersionCommand
    return schema(**values)


def ensure_published_camp(session, definition, requested_camp):
    version = session.scalar(select(TaskVersion).where(TaskVersion.task_definition_id == definition.id,
        TaskVersion.organization_id == definition.organization_id).order_by(TaskVersion.version.desc()).limit(1))
    if not version:
        return
    published = session.get(PublishedTaskContent, version.id)
    from journey_api.review_camps import task_camp
    original = published.content.get("camp", "novice") if published else task_camp(definition, None)
    if requested_camp != original:
        raise ApiError(409, "CAMP_FIXED", "已发布的任务不能更换营地，请复制为新任务。")


def validate_material_references(session, organization_id, content):
    for material in [*content.get("materials", []), *content.get("taskFiles", [])]:
        url = material.get("url", "")
        if not url.startswith("exploration-material:"):
            continue
        stored = session.get(ExplorationMaterial, uuid.UUID(url.split(":", 1)[1]))
        if (not stored or not stored.complete or stored.organization_id != organization_id
                or stored.purpose != content.get("camp", "exploration")
                or stored.purpose == "novice" and not stored.mime.startswith("video/")):
            raise ApiError(422, "INVALID_MATERIAL", "学习材料或任务文件不存在，或无权使用。")
        material.update(name=material["name"].strip(), mime=stored.mime, size=stored.size)


def _catalog_rows(session, organization_id, *, user_id=None):
    """Return published rows, optionally including this learner's retained work."""
    visible = ReviewAdminTask.status == "published"
    if user_id is not None:
        owned = select(ExplorationWork.task_id).where(ExplorationWork.organization_id == organization_id,
            ExplorationWork.user_id == user_id)
        visible = or_(visible, and_(ReviewAdminTask.status != "deleted", ExplorationCatalogTask.task_id.in_(owned)))
    return list(session.scalars(select(ExplorationCatalogTask).join(ReviewAdminTask,
        ReviewAdminTask.task_definition_id == ExplorationCatalogTask.task_id).where(
        ExplorationCatalogTask.organization_id == organization_id,
        ReviewAdminTask.organization_id == organization_id,
        ReviewAdminTask.content["camp"].as_string() == "exploration",
        visible).order_by(ExplorationCatalogTask.position, ExplorationCatalogTask.task_id)
        .execution_options(populate_existing=True)))


def _checkout_last(session, organization_id, rows):
    checkout_id = session.scalar(select(TaskDefinition.id).where(
        TaskDefinition.organization_id == organization_id, TaskDefinition.stable_key == TRAINING_CHECKOUT_TASK_KEY))
    # A stable partition preserves the requested relative order of normal tasks.
    return sorted(rows, key=lambda row: row.task_id == checkout_id)


def normalize_catalog_order(session, organization_id, *, rows=None):
    """Persist only catalog positions; caller owns the transaction.

    Publications and an explicit local repair use this same boundary rule. Reads
    use the projection below so old catalogs are correct before any repair runs.
    """
    session.scalar(select(Organization.id).where(Organization.id == organization_id).with_for_update())
    rows = _checkout_last(session, organization_id, _catalog_rows(session, organization_id) if rows is None else rows)
    for position, row in enumerate(rows, 1):
        row.position = position
    return rows


def publish_catalog(session, definition, profile, *, move=True, requested_position=None):
    """The organization row serializes order changes by different publishers."""
    session.scalar(select(Organization.id).where(Organization.id == definition.organization_id).with_for_update())
    rows = _checkout_last(session, definition.organization_id, _catalog_rows(session, definition.organization_id))
    moving = session.get(ExplorationCatalogTask, definition.id)
    if moving is None and profile.status == "published":
        moving = ExplorationCatalogTask(task_id=definition.id, organization_id=definition.organization_id, position=len(rows) + 1)
        session.add(moving)
    if moving is not None and move and profile.status == "published":
        rows = [row for row in rows if row.task_id != definition.id]
        position = min(len(rows), max(0, int(requested_position or profile.content.get("order") or len(rows) + 1) - 1))
        rows.insert(position, moving)
    normalize_catalog_order(session, definition.organization_id, rows=rows)


@dataclass(frozen=True)
class CatalogEntry:
    task_id: uuid.UUID
    position: int


def effective_catalog_positions(session, organization_id, *, user_id=None):
    """Contiguous public order without modifying legacy rows or retained work.

    Owned archived courses remain available for review before the sign-out card.
    They do not become predecessors in the published-course unlock sequence.
    """
    rows = _checkout_last(session, organization_id, _catalog_rows(session, organization_id, user_id=user_id))
    return {row.task_id: position for position, row in enumerate(rows, 1)}


def catalog(session, actor):
    return [CatalogEntry(task_id, position)
        for task_id, position in effective_catalog_positions(session, actor.organization_id).items()]


def lock_catalog(session, actor):
    """Read gates share the organization lock used by catalog publications."""
    session.scalar(select(Organization.id).where(Organization.id == actor.organization_id).with_for_update(read=True))


def unlocked_task_ids(session, actor):
    """Keep submitted milestones and previously owned work accessible.

    This matches the original journey's durable submission rule. Returning a
    submission for revision does not remove its milestone. Learning/check-in
    courses require actual completion instead of a text submission.
    """
    rows = session.execute(select(ExplorationWork.task_id, Assignment.id, Assignment.status, PublishedTaskContent.content)
        .join(Assignment, Assignment.id == ExplorationWork.assignment_id)
        .join(PublishedTaskContent, PublishedTaskContent.task_version_id == Assignment.task_version_id)
        .where(ExplorationWork.organization_id == actor.organization_id, ExplorationWork.user_id == actor.id,
            Assignment.organization_id == actor.organization_id,
            PublishedTaskContent.organization_id == actor.organization_id)).all()
    submitted = set(session.scalars(select(Submission.assignment_id)
        .join(ExplorationWork, ExplorationWork.assignment_id == Submission.assignment_id)
        .where(ExplorationWork.organization_id == actor.organization_id, ExplorationWork.user_id == actor.id,
            Submission.organization_id == actor.organization_id, Submission.current_version_no > 0)))
    milestones = {task_id for task_id, assignment_id, status, content in rows
        if status == AssignmentStatus.COMPLETED or
        ((content.get("completionMode") or "assessment") == "assessment" and assignment_id in submitted)}
    unlocked = {task_id for task_id, *_ in rows}
    for entry in catalog(session, actor):
        unlocked.add(entry.task_id)
        if entry.task_id not in milestones:
            break
    return unlocked


def ensure_task_unlocked(session, actor, task_id, *, unlocked_ids=None):
    if task_id not in (unlocked_ids if unlocked_ids is not None else unlocked_task_ids(session, actor)):
        raise ApiError(409, "JOURNEY_STAGE_LOCKED", "请先提交或完成前面的任务，后续任务尚未解锁。")


def ensure_assessment_submission(session, assignment):
    work = session.scalar(select(ExplorationWork.task_id).where(ExplorationWork.assignment_id == assignment.id,
        ExplorationWork.organization_id == assignment.organization_id))
    if work is None:
        return
    published = session.get(PublishedTaskContent, assignment.task_version_id)
    if published and (published.content.get("completionMode") or "assessment") != "assessment":
        raise ApiError(409, "INVALID_STATE_TRANSITION", "本任务请完成材料学习或培训签退，无需提交文字作业。")


def work_for(session, actor, task_id):
    return session.get(ExplorationWork, (actor.organization_id, actor.id, task_id))


def context(session, actor, task_id, *, allow_locked=False, unlocked_ids=None):
    profile = session.get(ReviewAdminTask, task_id)
    entry = session.get(ExplorationCatalogTask, task_id)
    if not profile or profile.organization_id != actor.organization_id or profile.content.get("camp") != "exploration" or not entry or profile.status == "deleted":
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的探索任务。")
    work = work_for(session, actor, task_id)
    assignment = session.get(Assignment, work.assignment_id) if work else None
    version = session.get(TaskVersion, assignment.task_version_id) if assignment else session.scalar(select(TaskVersion).where(
        TaskVersion.task_definition_id == task_id, TaskVersion.organization_id == actor.organization_id).order_by(TaskVersion.version.desc()).limit(1))
    snapshot = session.get(PublishedTaskContent, version.id) if version else None
    if not snapshot or (profile.status != "published" and not work):
        raise ApiError(404, "NOT_FOUND", "任务尚未发布或已归档。")
    if not allow_locked:
        ensure_task_unlocked(session, actor, task_id, unlocked_ids=unlocked_ids)
    return entry, profile, work, assignment, version, snapshot


def claim(session, actor, task_id, version_id):
    entry, profile, work, assignment, version, snapshot = context(session, actor, task_id)
    if assignment is None:
        definition = session.get(TaskDefinition, task_id)
        # Publishers lock their user before the task definition. Acquire this
        # reviewer FK key-share first to keep the same order while claiming.
        session.scalar(select(User.id).where(User.id == definition.created_by).with_for_update(read=True, key_share=True))
        session.scalar(select(TaskDefinition.id).where(TaskDefinition.id == task_id,
            TaskDefinition.organization_id == actor.organization_id).with_for_update(key_share=True))
        lock_catalog(session, actor)
        session.refresh(profile)
        entry, profile, work, assignment, version, snapshot = context(session, actor, task_id)
    if str(version.id) != str(version_id):
        raise ApiError(409, "VERSION_CONFLICT", "任务版本已更新，请刷新后重试。")
    if assignment:
        return work, assignment
    if profile.status != "published":
        raise ApiError(409, "INVALID_STATE_TRANSITION", "归档任务暂不可领取。")
    definition = session.get(TaskDefinition, task_id)
    reviewer = session.scalar(select(User.id).join(RoleAssignment, RoleAssignment.user_id == User.id).where(
        User.id == definition.created_by, User.organization_id == actor.organization_id,
        User.status == UserStatus.ACTIVE, RoleAssignment.organization_id == actor.organization_id,
        RoleAssignment.role == Role.REVIEWER))
    if reviewer is None:
        raise ApiError(409, "REVIEWER_UNAVAILABLE", "任务发布者暂不可审核，请联系管理员。")
    enrollment = Enrollment(id=uuid.uuid4(), organization_id=actor.organization_id, learner_id=actor.id,
        reviewer_id=reviewer, novice_task_id=task_id, status=EnrollmentStatus.ACTIVE, revision=1)
    session.add(enrollment)
    session.flush()
    assignment = Assignment(id=uuid.uuid4(), organization_id=actor.organization_id, enrollment_id=enrollment.id,
        task_definition_id=task_id, task_version_id=version.id, position=1,
        status=AssignmentStatus.IN_PROGRESS, revision=1)
    session.add(assignment)
    session.flush()
    work = ExplorationWork(organization_id=actor.organization_id, user_id=actor.id, task_id=task_id,
        assignment_id=assignment.id, opened_materials=[], checkin_confirmed=False)
    session.add(work)
    session.flush()
    return work, assignment


def learner_material(material):
    result = {key: value for key, value in material.items() if key != "url" or material.get("type") in {"link", "text"}}
    if material.get("url", "").startswith("exploration-material:"):
        result["url"] = material["url"]
    return result


def task_view(session, actor, task_id, *, allow_locked=False, unlocked_ids=None, catalog_positions=None):
    unlocked_ids = unlocked_ids if unlocked_ids is not None else unlocked_task_ids(session, actor)
    entry, profile, work, assignment, version, snapshot = context(session, actor, task_id,
        allow_locked=allow_locked, unlocked_ids=unlocked_ids)
    unlocked = task_id in unlocked_ids
    content = snapshot.content
    mode = content.get("completionMode") or "assessment"
    submission = session.scalar(select(Submission).where(Submission.assignment_id == assignment.id)) if assignment else None
    versions = list(session.scalars(select(SubmissionVersion).where(SubmissionVersion.submission_id == submission.id)
        .order_by(SubmissionVersion.version_no))) if submission else []
    draft = session.scalar(select(SubmissionDraft).where(SubmissionDraft.assignment_id == assignment.id)) if assignment else None
    decisions = list(session.scalars(select(Evaluation).where(Evaluation.assignment_id == assignment.id)
        .order_by(Evaluation.created_at))) if assignment else []
    evaluation = decisions[-1] if decisions else None
    decisions_by_version = {decision.submission_version_id: decision for decision in decisions}
    status = {"IN_PROGRESS": "active", "SUBMITTED": "pending", "IN_REVIEW": "pending",
        "NEEDS_REVISION": "returned", "COMPLETED": "completed", "CANCELLED": "active"}.get(assignment.status.value, "active") if assignment else "active"
    if not unlocked:
        status = "locked"
    if assignment and assignment.status == AssignmentStatus.CANCELLED and profile.status != "published":
        status = "unavailable"
    history = []
    ai_feedback_records = []
    for row in versions:
        decision = decisions_by_version.get(row.id)
        proof = (row.ai_use or {}).get("exploration_ai_evaluation") or {}
        ai_completed = (proof.get("source") == "AI" and proof.get("kind") == "EXPLORATION_AI"
            and proof.get("validated") is True and proof.get("passed") is True
            and proof.get("assignmentId") == str(assignment.id)
            and proof.get("taskVersionId") == str(version.id))
        history.append({"id": str(decision.review_id) if decision else str(row.id),
            "body": proof.get("originalInput", row.body) if ai_completed else row.body,
            "submittedAt": row.created_at.isoformat(),
            "status": "COMPLETED" if ai_completed or decision and decision.decision == Decision.PASS
            else "NEEDS_REVISION" if decision else "SUBMITTED", "version": row.version_no,
            **({"source": "AI"} if ai_completed else {})})
        if ai_completed:
            ai_feedback_records.append({"id": str(row.id), "text": proof["feedback"], "source": "AI",
                "decision": "PASS", "reviewedAt": row.created_at.isoformat(),
                "score": proof["score"], "maxScore": proof["maxScore"],
                "dimensions": [{key: item[key] for key in ("id", "name", "score", "maxScore", "evidence", "feedback")}
                    for item in proof["dimensions"]]})
    feedback_records = [{"id": str(decision.review_id), "text": decision.feedback or "审核已通过，继续探索吧。",
        "decision": decision.decision.value, "reviewedAt": decision.created_at.isoformat()} for decision in decisions]
    feedback_records.extend(ai_feedback_records)
    feedback_records.sort(key=lambda item: item["reviewedAt"])
    latest_feedback = feedback_records[-1] if feedback_records else None
    if work and work.completed_at and mode != "assessment":
        history.append({"id": str(assignment.id) + ":learning-completed", "body": "已完成培训签退并确认进入项目培训群。" if mode == "checkin" else "已完成学习。",
            "submittedAt": work.completed_at.isoformat(), "status": "CHECKIN_COMPLETED" if mode == "checkin" else "LEARNING_COMPLETED"})
    definition = session.get(TaskDefinition, task_id)
    owner = session.get(User, definition.created_by)
    requirements = assessment_requirements(content, content.get("requirements") or default_requirements(mode,
        seed=definition.stable_key.startswith("EXPLORATION-DYNAMIC-20261117-")))
    rubric = content.get("rubric") or []
    if mode == "assessment" and content.get("reviewMode") == "ai" and not rubric:
        # The publisher can use a private answer document without manual rows.
        # Only its server-generated dimension labels/points enter this view.
        rubric = (content.get("aiRubricSnapshot") or {}).get("dimensions") or []
    criteria = requirements
    if mode == "assessment":
        criteria = ([row["name"] for row in rubric]
            or ["按本任务配置的标准完成 AI 评测，达标后自动完成。"]
            if content.get("reviewMode") == "ai" else ["完成测试并提交结果，由审核人确认。"])
    result = dict(id=str(task_id), title=content["title"], description=content["summary"], category="", level="", minutes=0,
        review="材料学习" if mode == "learning" else "培训签退" if mode == "checkin" else "AI 自测" if content.get("reviewMode") == "ai" else "人工审核",
        experience=0, points=0, mentor=owner.display_name if owner else "", badges=[], requirements=requirements,
        status=status, versionId=str(version.id), assignmentId=str(assignment.id) if assignment else None,
        revision=assignment.revision if assignment else None, claimed=bool(assignment and assignment.status != AssignmentStatus.CANCELLED),
        answer=draft.body if draft else history[-1]["body"] if versions else "", publishedAt=version.published_at.isoformat(),
        criteria=criteria, reviewMode="NONE" if mode != "assessment" else "AI" if content.get("reviewMode") == "ai" else "HUMAN",
        passScore=content.get("passScore", 60), unlockTaskPoints=0, publishingDepartment="", rewardAllocations=[],
        materials=[learner_material(material) for material in content.get("materials", [])],
        taskFiles=[learner_material(material) for material in content.get("taskFiles", [])] if mode == "assessment" else [],
        rubric=[{key: item.get(key) for key in ("id", "name", "points")} | {"description": ""}
            for item in rubric] if content.get("reviewMode") == "ai" else [],
        feedback={**latest_feedback, "at": latest_feedback["reviewedAt"]} if latest_feedback else None,
        order=(catalog_positions if catalog_positions is not None else effective_catalog_positions(session, actor.organization_id, user_id=actor.id)).get(task_id, entry.position),
        pinnedLast=definition.stable_key == TRAINING_CHECKOUT_TASK_KEY,
        completionMode=mode, assessmentUrl=content.get("assessmentUrl") if mode == "assessment" else None,
        openedMaterials=work.opened_materials if work else [], completedAt=work.completed_at.isoformat() if work and work.completed_at else None,
        checkinConfirmed=bool(work and work.checkin_confirmed), minimumAnswerLength=1 if mode == "assessment" else 0,
        submittedAt=versions[-1].created_at.isoformat() if versions else None, feedbackRecords=feedback_records,
        activityRecords=history, submissionHistory=history, submissionCount=len(versions))
    if status == "locked":
        result.update(materials=[], taskFiles=[], assessmentUrl=None, requirements=[], criteria=[], rubric=[],
            answer="", feedback=None, feedbackRecords=[], activityRecords=[], submissionHistory=[],
            materialCount=len(content.get("materials", [])),
            taskFileCount=len(content.get("taskFiles", [])) if mode == "assessment" else 0)
    return result


def progress_for(session, actor):
    row = session.scalar(select(ExplorationProgress).where(ExplorationProgress.organization_id == actor.organization_id,
        ExplorationProgress.user_id == actor.id).with_for_update())
    if row is None:
        session.execute(insert(ExplorationProgress).values(organization_id=actor.organization_id, user_id=actor.id,
            treasures={"attempts": [], "drops": [], "ruleVersion": 2}).on_conflict_do_nothing())
        row = session.scalar(select(ExplorationProgress).where(ExplorationProgress.organization_id == actor.organization_id,
            ExplorationProgress.user_id == actor.id).with_for_update())
    return row


def settle_treasures(game, entries, completed):
    """One settled draw per task, with slots reserved for both boundary tasks."""
    ids = [str(entry.task_id) for entry in entries]
    guaranteed = set(ids[:1] + ids[-1:])
    for task_id, completed_at, title in completed:
        if any(attempt["taskId"] == task_id for attempt in game["attempts"]):
            continue
        attempt = dict(taskId=task_id, completedAt=completed_at, guaranteed=task_id in guaranteed, outcome="empty", dropId=None)
        reserved = len(guaranteed - {drop["taskId"] for drop in game["drops"]})
        unsettled = set(ids) - guaranteed - {item["taskId"] for item in game["attempts"]}
        remaining = [item for item in TREASURES if item not in {drop["treasureId"] for drop in game["drops"]}]
        slots = max(0, 4 - len(game["drops"]) - reserved)
        probability = min(1, slots / max(1, len(unsettled)))
        if remaining and (task_id in guaranteed or secrets.randbelow(10**9) < int(probability * 10**9)):
            drop = dict(id=str(uuid.uuid4()), treasureId=secrets.choice(remaining), taskId=task_id,
                taskTitle=title, discoveredAt=completed_at, acknowledgedAt=None)
            game["drops"].append(drop)
            attempt.update(outcome="discovered", dropId=drop["id"])
        elif not remaining:
            attempt["outcome"] = "collection-full"
        game["attempts"].append(attempt)
    # An administrator can legitimately shorten the catalog. Graduation stays
    # achievable even for one-to-three courses, while preserving existing drops.
    if ids and set(ids).issubset({task_id for task_id, _, _ in completed}):
        remaining = [item for item in TREASURES if item not in {drop["treasureId"] for drop in game["drops"]}]
        for treasure_id in remaining:
            task_id, completed_at, title = completed[-1]
            game["drops"].append(dict(id=str(uuid.uuid4()), treasureId=treasure_id, taskId=task_id,
                taskTitle=title, discoveredAt=completed_at, acknowledgedAt=None, catchUp=True))


def treasure_view(session, actor, *, settle=True):
    progress = progress_for(session, actor)
    entries = catalog(session, actor)
    completed = []
    for entry in entries:
        work = work_for(session, actor, entry.task_id)
        assignment = session.get(Assignment, work.assignment_id) if work else None
        if not assignment or assignment.status != AssignmentStatus.COMPLETED:
            continue
        decision = session.scalar(select(Evaluation).where(Evaluation.assignment_id == assignment.id,
            Evaluation.decision == Decision.PASS).order_by(Evaluation.created_at).limit(1))
        stamp = work.completed_at or (decision.created_at if decision else None)
        if stamp:
            title = session.get(TaskVersion, assignment.task_version_id).title
            completed.append((str(entry.task_id), stamp.isoformat(), title))
    completed.sort(key=lambda item: (item[1], item[0]))
    game = copy.deepcopy(progress.treasures)
    if settle:
        settle_treasures(game, entries, completed)
        progress.treasures = game
    total, done = len(entries), len(completed)
    missing = total - done
    block = "暂无已发布的探索任务。" if not total else f"还需完成 {missing} 项学习任务。" if missing else "还需集齐 4 件探索宝藏。" if len(game["drops"]) < 4 else None
    graduation = dict(status="LOCKED" if block else "AVAILABLE", code=None, unlockedAt=None,
        completedTasks=done, totalTasks=total, remainingTasks=missing, blockReason=block)
    code = session.scalar(select(CompletionCode).where(CompletionCode.user_id == actor.id,
        CompletionCode.organization_id == actor.organization_id))
    if code:
        from journey_api.phone_auth_routes import decrypt_completion_code
        graduation.update(status="MIGRATED" if code.used_at else "READY", code=None if code.used_at else decrypt_completion_code(code.code_ciphertext),
            unlockedAt=progress.unlocked_at.isoformat() if progress.unlocked_at else None, blockReason=None)
    elif not block:
        from journey_api.models import ExternalIdentity
        from journey_api.phone_auth_routes import TEMPORARY_IDENTITY_PROVIDERS
        temporary = session.scalar(select(ExternalIdentity.id).where(ExternalIdentity.user_id == actor.id,
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.provider.in_(TEMPORARY_IDENTITY_PROVIDERS), ExternalIdentity.revoked_at.is_(None)))
        if temporary is None:
            graduation.update(status="NOT_REQUIRED", code=None, blockReason=None)
    return dict(total=4, count=len(game["drops"]), items=game["drops"],
        pendingDrops=[drop for drop in game["drops"] if not drop.get("acknowledgedAt")], graduation=graduation)


def unlock_graduation(session, actor):
    view = treasure_view(session, actor)
    if view["graduation"]["status"] == "LOCKED":
        raise ApiError(409, "GRADUATION_LOCKED", view["graduation"]["blockReason"])
    progress = progress_for(session, actor)
    if view["graduation"]["status"] == "NOT_REQUIRED":
        progress.unlocked_at = progress.unlocked_at or datetime.now(UTC)
        return treasure_view(session, actor)
    row = session.scalar(select(CompletionCode).where(CompletionCode.user_id == actor.id).with_for_update())
    if row is None:
        from journey_api.config import get_settings
        from journey_api.identity import credential_hash
        from journey_api.phone_auth_routes import encrypt_completion_code
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        code = "MJ-" + "".join(secrets.choice(alphabet) for _ in range(8))
        row = CompletionCode(id=uuid.uuid4(), organization_id=actor.organization_id, user_id=actor.id,
            code_hash=credential_hash(get_settings().session_secret, "completion-code", code),
            code_ciphertext=encrypt_completion_code(code), code_hint=code[-4:], expires_at=datetime.now(UTC) + timedelta(days=60))
        session.add(row)
    progress.unlocked_at = progress.unlocked_at or datetime.now(UTC)
    session.flush()
    return treasure_view(session, actor)


def material_metadata(session, actor, task_id, index, group="learning"):
    *_, snapshot = context(session, actor, task_id)
    assessment = (snapshot.content.get("completionMode") or "assessment") == "assessment"
    if group == "task":
        materials = snapshot.content.get("taskFiles", []) if assessment else []
    else:
        materials = snapshot.content.get("materials", [])
    if index < 0 or index >= len(materials):
        raise ApiError(404, "NOT_FOUND", "没有找到该任务文件。" if group == "task" else "没有找到该学习材料。")
    result = dict(materials[index])
    if result.get("url", "").startswith("data:"):
        result["data"] = result.pop("url").split(",", 1)[1]
        result.pop("id", None)
    elif result.get("url", "").startswith("exploration-material:"):
        result["id"] = result["url"].split(":", 1)[1]
    return result
