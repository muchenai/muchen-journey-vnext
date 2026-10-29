"""Learner catalog and claims; drafts, submissions and reviews stay canonical."""
import uuid
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, aliased
from journey_api.auth import Actor, get_learner_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import (Assignment, AssignmentStatus, Enrollment, EnrollmentStatus,
    TaskDefinition, TaskDefinitionStatus, TaskVersion, User, UserStatus, Role, RoleAssignment,
    Submission, SubmissionVersion, SubmissionDraft, Evaluation)
from journey_api.review_admin_models import ReviewAdminTask, PublishedTaskContent
from journey_api.review_admin_routes import DOMAINS, BADGES, PRESETS, envelope, audit
from journey_api.novice_economy import rewards, unlock_cost, wallet
from journey_api.review_admin_models import NoviceUnlockDebit

router = APIRouter(prefix="/api/v1/me/novice")


@router.get("/assignments/{assignment_id}")
def assignment_task(assignment_id: uuid.UUID, request: Request,
                    actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    task_id = session.scalar(select(Enrollment.novice_task_id).join(Assignment,
        Assignment.enrollment_id == Enrollment.id).where(Assignment.id == assignment_id,
            Enrollment.learner_id == actor.id, Enrollment.organization_id == actor.organization_id,
            Assignment.organization_id == actor.organization_id))
    return envelope(request, {"taskId":str(task_id) if task_id else None})


def owned_claim(session, actor, task_id):
    return session.scalar(select(Enrollment).where(Enrollment.organization_id == actor.organization_id,
        Enrollment.learner_id == actor.id, Enrollment.novice_task_id == task_id))


def published(session, actor, task_id):
    latest = select(func.max(TaskVersion.version)).where(TaskVersion.task_definition_id == task_id).scalar_subquery()
    row = session.execute(select(TaskVersion, PublishedTaskContent)
        .join(PublishedTaskContent, PublishedTaskContent.task_version_id == TaskVersion.id)
        .join(ReviewAdminTask, ReviewAdminTask.task_definition_id == TaskVersion.task_definition_id)
        .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
        .where(TaskVersion.organization_id == actor.organization_id,
            TaskVersion.task_definition_id == task_id, TaskVersion.version == latest,
            PublishedTaskContent.organization_id == actor.organization_id,
            PublishedTaskContent.content["camp"].as_string() == "novice",
            ReviewAdminTask.status == "published", TaskDefinition.status == TaskDefinitionStatus.PUBLISHED)
        .order_by(TaskVersion.version.desc()).limit(1)).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "任务尚未发布或已下架。")
    return row


def context(session, actor, task_id):
    enrollment = owned_claim(session, actor, task_id)
    if enrollment is not None:
        assignment = session.scalar(select(Assignment).where(Assignment.enrollment_id == enrollment.id,
            Assignment.task_definition_id == task_id, Assignment.organization_id == actor.organization_id))
        if assignment is None:
            raise ApiError(409, "INVALID_STATE", "领取记录不完整，请联系管理员。")
        version = session.get(TaskVersion, assignment.task_version_id)
        snapshot = session.get(PublishedTaskContent, assignment.task_version_id)
        if not version or not snapshot or snapshot.organization_id != actor.organization_id:
            raise ApiError(409, "INVALID_STATE", "任务发布版本不可用。")
        return version, snapshot, assignment
    version, snapshot = published(session, actor, task_id)
    return version, snapshot, None


def task_view(session, actor, task_id):
    version, snapshot, assignment = context(session, actor, task_id)
    content = snapshot.content
    reward = rewards(content)
    minutes, xp, points = reward["minutes"], reward["xp"], reward["taskPoints"]
    author = session.get(User, version.published_by)
    materials = []
    for index, material in enumerate(content.get("materials", [])):
        materials.append({"name": material.get("name", "学习材料"), "type": material["type"],
            "text": material.get("text", ""), "url": material.get("url", "") if material["type"] == "link"
            else f"/api/learner/village?task={task_id}&material={index}" if material["type"] in {"file", "image"} else ""})
    result = dict(id=str(task_id), title=version.title, description=version.purpose,
        category=content.get("domain", "产品开发"), level=content.get("difficulty", "入门"),
        minutes=minutes, experience=xp, points=points, mentor=author.display_name if author else "任务发布者",
        badges=[[BADGES[b["id"]], b["weight"]] for b in content.get("badges", []) if b.get("id") in BADGES],
        requirements=version.instructions, criteria=version.completion_criteria, materials=materials,
        rubric=content.get("rubric", []) if content.get("reviewMode") == "ai" else [],
        passScore=content.get("passScore", 60), review="人工审核", reviewMode=content.get("reviewMode", "manual"),
        publishedAt=version.published_at.isoformat(), versionId=str(version.id),
        status="available", assignmentId=None, revision=None, answer="", feedback=None,
        unlockTaskPoints=unlock_cost(content), rewardAllocations=reward["allocations"])
    if assignment:
        draft = session.scalar(select(SubmissionDraft).where(SubmissionDraft.assignment_id == assignment.id,
            SubmissionDraft.owner_id == actor.id))
        submission = session.scalar(select(SubmissionVersion).join(Submission, Submission.id == SubmissionVersion.submission_id)
            .where(Submission.assignment_id == assignment.id).order_by(SubmissionVersion.version_no.desc()).limit(1))
        evaluation = session.scalar(select(Evaluation).where(Evaluation.assignment_id == assignment.id)
            .order_by(Evaluation.created_at.desc()).limit(1))
        result.update(assignmentId=str(assignment.id), revision=assignment.revision,
            status={"IN_PROGRESS":"active", "SUBMITTED":"pending", "IN_REVIEW":"pending",
                "NEEDS_REVISION":"returned", "COMPLETED":"completed", "PASSED":"completed",
                "CANCELLED":"unavailable"}.get(assignment.status.value, "active"),
            answer=draft.body if draft else submission.body if submission else "",
            feedback={"text":evaluation.feedback, "at":evaluation.created_at.isoformat(),
                "decision":evaluation.decision.value} if evaluation else None)
    return result


@router.get("/tasks")
def list_tasks(request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    visible = select(PublishedTaskContent.task_version_id).where(
        PublishedTaskContent.organization_id == actor.organization_id,
        PublishedTaskContent.content["camp"].as_string() == "novice")
    newer = aliased(TaskVersion)
    latest = ~select(newer.id).where(newer.task_definition_id == TaskVersion.task_definition_id,
        newer.version > TaskVersion.version).exists()
    available = select(TaskVersion.task_definition_id).join(ReviewAdminTask,
        ReviewAdminTask.task_definition_id == TaskVersion.task_definition_id).where(
            TaskVersion.id.in_(visible), latest, ReviewAdminTask.status == "published")
    mine = select(Enrollment.novice_task_id).where(Enrollment.organization_id == actor.organization_id,
        Enrollment.learner_id == actor.id, Enrollment.novice_task_id.is_not(None))
    ids = session.scalars(select(TaskDefinition.id).where(TaskDefinition.organization_id == actor.organization_id,
        or_((TaskDefinition.id.in_(available)) & (TaskDefinition.status == TaskDefinitionStatus.PUBLISHED),
            TaskDefinition.id.in_(mine))).order_by(TaskDefinition.id)).all()
    return envelope(request, {"directions":DOMAINS, "items":[task_view(session, actor, task_id) for task_id in ids], "wallet":wallet(session,actor)})


@router.get("/tasks/{task_id}")
def detail(task_id: uuid.UUID, request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    return envelope(request, task_view(session, actor, task_id))


class ClaimCommand(BaseModel):
    version_id: uuid.UUID


@router.post("/tasks/{task_id}/claim")
def claim(task_id: uuid.UUID, command: ClaimCommand, request: Request,
          actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    # Serialize claims per learner; the unique owner/task constraint is the final guard.
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    existing = owned_claim(session, actor, task_id)
    if existing is None:
        definition = session.scalar(select(TaskDefinition).where(TaskDefinition.id == task_id,
            TaskDefinition.organization_id == actor.organization_id).with_for_update())
        if definition is None:
            raise ApiError(404, "NOT_FOUND", "没有找到该任务。")
        version, snapshot = published(session, actor, task_id)
        if command.version_id != version.id:
            raise ApiError(409, "VERSION_CONFLICT", "任务已更新，请重新查看后领取。")
        reviewer = session.scalar(select(User.id).join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(User.id == definition.created_by, User.organization_id == actor.organization_id,
                User.status == UserStatus.ACTIVE, RoleAssignment.role == Role.REVIEWER,
                RoleAssignment.organization_id == actor.organization_id))
        if reviewer is None:
            raise ApiError(409, "REVIEWER_UNAVAILABLE", "任务发布者暂不可审核，请联系管理员。")
        cost = unlock_cost(snapshot.content)
        if cost and wallet(session, actor)["taskPoints"] < cost:
            raise ApiError(409, "INSUFFICIENT_POINTS", f"任务点不足，解锁此任务需要 {cost} 任务点。")
        enrollment = Enrollment(id=uuid.uuid4(), organization_id=actor.organization_id, learner_id=actor.id,
            reviewer_id=reviewer, novice_task_id=task_id, status=EnrollmentStatus.ACTIVE, revision=1)
        session.add(enrollment)
        session.flush()
        if cost:
            session.add(NoviceUnlockDebit(enrollment_id=enrollment.id, organization_id=actor.organization_id,
                user_id=actor.id, amount=cost))
        assignment = Assignment(id=uuid.uuid4(), organization_id=actor.organization_id,
            enrollment_id=enrollment.id, task_definition_id=task_id, task_version_id=version.id,
            position=1, status=AssignmentStatus.IN_PROGRESS, revision=1)
        session.add(assignment)
        audit(session, request, actor, "novice.claim", assignment.id, {"task_id":str(task_id)})
        session.commit()
    return envelope(request, task_view(session, actor, task_id))


@router.get("/tasks/{task_id}/materials/{index}")
def material(task_id: uuid.UUID, index: int, request: Request,
             actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    _, snapshot, _ = context(session, actor, task_id)
    materials = snapshot.content.get("materials", [])
    if index < 0 or index >= len(materials) or materials[index]["type"] not in {"file", "image"}:
        raise ApiError(404, "NOT_FOUND", "没有找到学习文件。")
    from journey_api.review_admin_routes import Material
    data = Material.model_validate(materials[index])
    return envelope(request, {"name":data.name, "mime":data.mime, "data":data.url.split(",",1)[1]})
