"""Learner catalog and claims; drafts, submissions and reviews stay canonical."""
import uuid
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, aliased
from journey_api.auth import Actor, get_learner_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import (Assignment, AssignmentStatus, Enrollment, EnrollmentStatus,
    TaskDefinition, TaskDefinitionStatus, TaskVersion, User, UserStatus, Role, RoleAssignment,
    Submission, SubmissionVersion, SubmissionDraft, Evaluation, AuditEntry)
from journey_api.idempotency import find_replay, store_result
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


def learner_cancelled(session, actor, assignment):
    """Only this learner's explicit cancellation of the current revision can reopen."""
    if assignment.status != AssignmentStatus.CANCELLED:
        return False
    enrollment = session.get(Enrollment, assignment.enrollment_id)
    return bool(enrollment and enrollment.status == EnrollmentStatus.ACTIVE and
        enrollment.organization_id == actor.organization_id and enrollment.learner_id == actor.id and
        session.scalar(select(AuditEntry.id).where(AuditEntry.organization_id == actor.organization_id,
            AuditEntry.actor_id == actor.id, AuditEntry.resource_id == assignment.id,
            AuditEntry.action == "novice.cancel", AuditEntry.result == "SUCCESS",
            AuditEntry.details["revision"].as_integer() == assignment.revision).limit(1)))


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
        publishingDepartment=content.get("publishingDepartment", ""),
        minutes=minutes, experience=xp, points=points, mentor=author.display_name if author else "任务发布者",
        badges=[[BADGES[b["id"]], b["weight"]] for b in content.get("badges", []) if b.get("id") in BADGES],
        requirements=version.instructions, criteria=version.completion_criteria, materials=materials,
        rubric=content.get("rubric", []) if content.get("reviewMode") == "ai" else [],
        passScore=content.get("passScore", 60), review="AI 自测" if content.get("reviewMode") == "ai" else "人工审核", reviewMode=content.get("reviewMode", "manual"),
        publishedAt=version.published_at.isoformat(), versionId=str(version.id),
        status="available", claimed=False, assignmentId=None, revision=None, answer="", feedback=None,
        unlockTaskPoints=unlock_cost(content), rewardAllocations=reward["allocations"])
    if assignment:
        draft = session.scalar(select(SubmissionDraft).where(SubmissionDraft.assignment_id == assignment.id,
            SubmissionDraft.owner_id == actor.id))
        submission = session.scalar(select(SubmissionVersion).join(Submission, Submission.id == SubmissionVersion.submission_id)
            .where(Submission.assignment_id == assignment.id).order_by(SubmissionVersion.version_no.desc()).limit(1))
        evaluation = session.scalar(select(Evaluation).where(Evaluation.assignment_id == assignment.id)
            .order_by(Evaluation.created_at.desc()).limit(1))
        result.update(assignmentId=str(assignment.id), revision=assignment.revision,
            claimed=assignment.status != AssignmentStatus.CANCELLED,
            status={"IN_PROGRESS":"active", "SUBMITTED":"pending", "IN_REVIEW":"pending",
                "NEEDS_REVISION":"returned", "COMPLETED":"completed", "PASSED":"completed",
                "CANCELLED":"unavailable"}.get(assignment.status.value, "active"),
            answer=draft.body if draft else submission.body if submission else "",
            feedback={"text":evaluation.feedback, "at":evaluation.created_at.isoformat(),
                "decision":evaluation.decision.value} if evaluation else None)
        if learner_cancelled(session, actor, assignment):
            # Keep the saved draft and its fixed task version; an archived task cannot
            # be reclaimed even though its learner-owned history is still visible.
            try:
                published(session, actor, task_id)
                result["status"] = "available"
            except ApiError as error:
                if error.status_code != 404:
                    raise
            result["unlockTaskPoints"] = 0
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
    expected_revision: int | None = Field(default=None, strict=True, ge=1)


class CancelClaimCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(strict=True, ge=1)


@router.post("/tasks/{task_id}/cancel")
def cancel_claim(task_id: uuid.UUID, command: CancelClaimCommand, request: Request,
                 idempotency_key: str = Header(alias="Idempotency-Key"),
                 actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    # Serializes this learner's claim commands without blocking FK KEY SHARE
    # locks taken by a concurrent draft/submission that already owns Enrollment.
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update(key_share=True))
    payload = {**command.model_dump(mode="json"), "task_id": str(task_id)}
    replay = find_replay(session, actor_id=actor.id, command="novice.cancel", key=idempotency_key, payload=payload)
    if replay is not None:
        return envelope(request, replay)
    enrollment = session.scalar(select(Enrollment).where(Enrollment.organization_id == actor.organization_id,
        Enrollment.learner_id == actor.id, Enrollment.novice_task_id == task_id,
        Enrollment.status == EnrollmentStatus.ACTIVE).with_for_update())
    if enrollment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可取消的已接取任务。")
    assignment = session.scalar(select(Assignment).where(Assignment.enrollment_id == enrollment.id,
        Assignment.organization_id == actor.organization_id, Assignment.task_definition_id == task_id).with_for_update())
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可取消的已接取任务。")
    if assignment.revision != command.expected_revision:
        raise ApiError(409, "VERSION_CONFLICT", "任务状态已更新，请重新查看后操作。")
    if assignment.status != AssignmentStatus.IN_PROGRESS:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "只有进行中的任务可以取消接取。")
    assignment.status = AssignmentStatus.CANCELLED
    assignment.revision += 1
    audit(session, request, actor, "novice.cancel", assignment.id,
        {"task_id": str(task_id), "revision": assignment.revision, "draft_preserved": True})
    session.flush()
    result = task_view(session, actor, task_id)
    store_result(session, actor_id=actor.id, command="novice.cancel", key=idempotency_key, payload=payload, response=result)
    session.commit()
    return envelope(request, result)


@router.post("/tasks/{task_id}/claim")
def claim(task_id: uuid.UUID, command: ClaimCommand, request: Request,
          actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    require_role(actor, Role.LEARNER)
    # Serialize claims per learner; the unique owner/task constraint is the final guard.
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update(key_share=True))
    existing = owned_claim(session, actor, task_id)
    if existing is not None:
        enrollment = session.scalar(select(Enrollment).where(Enrollment.id == existing.id,
            Enrollment.organization_id == actor.organization_id).with_for_update())
        assignment = session.scalar(select(Assignment).where(Assignment.enrollment_id == enrollment.id,
            Assignment.task_definition_id == task_id, Assignment.organization_id == actor.organization_id).with_for_update())
        if assignment is None:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能重新接取。")
        if assignment.status == AssignmentStatus.CANCELLED:
            if not learner_cancelled(session, actor, assignment):
                raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能重新接取。")
            if command.expected_revision != assignment.revision or command.version_id != assignment.task_version_id:
                raise ApiError(409, "VERSION_CONFLICT", "任务状态或版本已更新，请重新查看后接取。")
            session.scalar(select(TaskDefinition.id).where(TaskDefinition.id == task_id,
                TaskDefinition.organization_id == actor.organization_id).with_for_update())
            published(session, actor, task_id)
            assignment.status = AssignmentStatus.IN_PROGRESS
            assignment.revision += 1
            audit(session, request, actor, "novice.reclaim", assignment.id,
                {"task_id": str(task_id), "revision": assignment.revision, "draft_preserved": True})
            session.commit()
    else:
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
