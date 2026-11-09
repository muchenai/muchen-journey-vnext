"""Guild-scoped practice and administrator review, with legacy history intact."""
import uuid
import hashlib
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, get_learner_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.guild_catalog import HALLS, HALL_BY_ID, TASKS, TASK_VERSIONS
from journey_api.guild_models import GuildCertificationRequest, GuildMembership, GuildSelection, GuildTaskSubmission
from journey_api.models import CompletionCode, ExternalIdentity, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_access import permissions, require_publisher
from journey_api.review_admin_models import MedalRedemption
from journey_api.review_admin_routes import audit, envelope

router = APIRouter(prefix="/api/v1")
LEVEL_NAMES = ("未认证", "基础实践者", "进阶协作者", "综合交付者")


def fail(message, status=409, code="GUILD_CONFLICT"):
    raise ApiError(status, code, message)


def lock_guild(session, organization_id, user_id):
    # Staff authentication already locks the reviewing administrator's User row.
    # A separate account-scoped lock avoids deadlocks between two administrators
    # reviewing each other's applications. It serializes both apply and review.
    key = int.from_bytes(hashlib.sha256(f"guild-certification:{organization_id}:{user_id}".encode()).digest()[:8],
                         "big", signed=True)
    session.execute(select(func.pg_advisory_xact_lock(key)))


def request_rows(session, organization_id, user_id):
    return list(session.scalars(select(GuildCertificationRequest).where(
        GuildCertificationRequest.organization_id == organization_id,
        GuildCertificationRequest.user_id == user_id,
    ).order_by(GuildCertificationRequest.submitted_at.desc(), GuildCertificationRequest.id)))


def current_level(rows):
    approved = {row.level for row in rows if row.status == "approved"}
    level = 0
    for candidate in (1, 2, 3):
        if candidate not in approved:
            break
        level = candidate
    return level


def owned_evidence(session, organization_id, user_id):
    """Use immutable redemption snapshots, never today's edited publication or balance."""
    redemptions = session.scalars(select(MedalRedemption).where(
        MedalRedemption.organization_id == organization_id, MedalRedemption.user_id == user_id,
    ).order_by(MedalRedemption.created_at, MedalRedemption.id))
    evidence = []
    for row in redemptions:
        content = row.content
        # Legacy snapshots predate artworkLevel; green retains the same grade-one
        # compatibility used by the learner badge catalog.
        grade = content.get("artworkLevel")
        if type(grade) is not int or grade not in (1, 2, 3):
            grade = {"blue": 1, "cyan": 1, "green": 1, "purple": 2, "violet": 2, "gold": 3}.get(content.get("style"))
        if grade is None:
            continue
        evidence.append(dict(id=str(row.medal_id), redemptionId=str(row.id),
                             name=content.get("medalName", "徽章"), grade=grade,
                             artworkId=content.get("artworkId", ""), image=content.get("image", "")))
    return evidence


def serialize(row, *, admin=False):
    result = dict(id=str(row.id), level=row.level, status=row.status, evidence=row.evidence,
                  submittedAt=row.submitted_at.isoformat(),
                  reviewedAt=row.reviewed_at.isoformat() if row.reviewed_at else None,
                  reviewerName=row.reviewer_name, reason=row.reason, guildId=row.guild_id,
                  guildTitle=HALL_BY_ID[row.guild_id]["title"] if row.guild_id else "旧版全局认证",
                  task=row.task_snapshot)
    if admin:
        result.update(studentId=str(row.user_id), studentName=row.student_name)
    return result


def scoped_rows(rows, guild_id):
    return [row for row in rows if row.guild_id == guild_id]


def submission_key(actor, guild_id, level):
    return (actor.organization_id, actor.id, guild_id, level)


def valid_submission(row):
    if row is None or row.status != "submitted" or row.submitted_at is None:
        return False
    definition = TASK_VERSIONS.get((row.task_id, row.task_version))
    return bool(definition and definition["level"] == row.level and 60 <= len(row.artifact.strip()) <= 6000 and
                len(row.checks) == len(definition["checks"]) and set(row.checks) == set(definition["checks"]))


def serialize_submission(row):
    return dict(guildId=row.guild_id, level=row.level, taskId=row.task_id, version=row.task_version,
                artifact=row.artifact, checks=row.checks, submittedAt=row.submitted_at.isoformat() if row.submitted_at else None,
                status=row.status, revision=row.revision)


def learner_snapshot(session, actor):
    all_rows = request_rows(session, actor.organization_id, actor.id)
    selection = session.get(GuildSelection, (actor.organization_id, actor.id))
    guild_id = selection.guild_id if selection else None
    rows = scoped_rows(all_rows, guild_id) if guild_id else []
    memberships = set(session.scalars(select(GuildMembership.guild_id).where(
        GuildMembership.organization_id == actor.organization_id, GuildMembership.user_id == actor.id)))
    submissions = list(session.scalars(select(GuildTaskSubmission).where(
        GuildTaskSubmission.organization_id == actor.organization_id, GuildTaskSubmission.user_id == actor.id
    ).order_by(GuildTaskSubmission.guild_id, GuildTaskSubmission.level)))
    level = current_level(rows)
    owned = owned_evidence(session, actor.organization_id, actor.id)
    pending = any(row.status == "pending" for row in rows)
    requirements = []
    for target in (1, 2, 3):
        grades = list(range(1, target + 1))
        counts = [dict(grade=grade, count=sum(item["grade"] == grade for item in owned)) for grade in grades]
        fulfilled = sum(item["count"] > 0 for item in counts)
        entry = bool(guild_id and level + 1 == target and fulfilled == target and not pending)
        submitted = valid_submission(next((row for row in submissions if row.guild_id == guild_id and row.level == target), None))
        requirements.append(dict(level=target, grades=grades, counts=counts, previousMet=bool(guild_id and level >= target - 1),
                                 entryEligible=entry, taskSubmitted=submitted, eligible=entry and submitted,
                                 fulfilled=fulfilled, required=target))
    return dict(level=level, levelName=LEVEL_NAMES[level], requirements=requirements,
                requests=[serialize(row) for row in rows], joinedGuild=guild_id,
                halls=[dict(hall, joined=hall["id"] in memberships, level=current_level(scoped_rows(all_rows, hall["id"]))) for hall in HALLS],
                tasks=TASKS, submissions=[serialize_submission(row) for row in submissions],
                legacyRequests=[serialize(row) for row in scoped_rows(all_rows, None)])


def admin_snapshot(session, actor):
    rows = list(session.scalars(select(GuildCertificationRequest).where(
        GuildCertificationRequest.organization_id == actor.organization_id,
    ).order_by(GuildCertificationRequest.submitted_at.desc(), GuildCertificationRequest.id)))
    return dict(requests=[serialize(row, admin=True) for row in rows],
                counts={status: sum(row.status == status for row in rows) for status in ("pending", "approved", "returned")},
                actorId=str(actor.id))


@router.get("/me/guild")
def learner_guild(request: Request, actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    require_role(actor, Role.LEARNER)
    return envelope(request, learner_snapshot(session, actor))


class GuildApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: int = Field(strict=True, ge=1, le=3)
    guildId: str | None = Field(default=None, max_length=40)
    expectedRevision: int = Field(strict=True, ge=1)


class GuildJoin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guildId: str = Field(min_length=1, max_length=40)


class GuildTaskSave(GuildJoin):
    level: int = Field(strict=True, ge=1, le=3)
    artifact: str = Field(max_length=6000)
    checks: list[str] = Field(max_length=3)
    submit: bool = Field(strict=True)
    expectedRevision: int | None = Field(default=None, strict=True, ge=0)


def require_membership(session, actor, guild_id):
    if guild_id not in HALL_BY_ID:
        fail("请选择有效的工会。", 422, "GUILD_INVALID")
    if not session.get(GuildMembership, (actor.organization_id, actor.id, guild_id)):
        fail("请先加入该工会。")


def require_entry(session, actor, rows, level):
    if current_level(rows) + 1 != level:
        fail("请先完成上一等级认证，已通过的等级无需重复申请。")
    owned = owned_evidence(session, actor.organization_id, actor.id)
    evidence = [next((item for item in owned if item["grade"] == grade), None) for grade in range(1, level + 1)]
    if not all(evidence):
        fail("尚未获得认证所需等级的徽章，请先补齐徽章凭证。")
    return evidence


@router.post("/me/guild/join")
def join(command: GuildJoin, request: Request, actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    require_role(actor, Role.LEARNER)
    if command.guildId not in HALL_BY_ID:
        fail("请选择有效的工会。", 422, "GUILD_INVALID")
    lock_guild(session, actor.organization_id, actor.id)
    if not session.get(GuildMembership, (actor.organization_id, actor.id, command.guildId)):
        session.add(GuildMembership(organization_id=actor.organization_id, user_id=actor.id, guild_id=command.guildId))
    selection = session.get(GuildSelection, (actor.organization_id, actor.id))
    if selection:
        selection.guild_id = command.guildId
    else:
        session.add(GuildSelection(organization_id=actor.organization_id, user_id=actor.id, guild_id=command.guildId))
    session.flush()
    result = learner_snapshot(session, actor)
    session.commit()
    return envelope(request, result)


@router.post("/me/guild/tasks")
def save_task(command: GuildTaskSave, request: Request, actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    require_role(actor, Role.LEARNER)
    lock_guild(session, actor.organization_id, actor.id)
    require_membership(session, actor, command.guildId)
    rows = scoped_rows(request_rows(session, actor.organization_id, actor.id), command.guildId)
    if any(row.status == "pending" for row in rows):
        fail("认证审核期间不能修改成果，请等待审核结果。")
    require_entry(session, actor, rows, command.level)
    definition = TASKS[command.level - 1]
    if len(set(command.checks)) != len(command.checks) or not set(command.checks).issubset(definition["checks"]):
        fail("自查项不正确，请重新勾选。", 422, "GUILD_INVALID")
    if command.submit and (len(command.artifact.strip()) < 60 or set(command.checks) != set(definition["checks"])):
        fail("请填写 60 至 6000 字的成果，并完成全部三项自查。", 422, "GUILD_INVALID")
    row = session.get(GuildTaskSubmission, submission_key(actor, command.guildId, command.level))
    if (row and command.expectedRevision != row.revision) or (not row and command.expectedRevision not in (None, 0)):
        fail("成果已在其他页面更新，请刷新后再保存。", 409, "GUILD_REVISION_CONFLICT")
    if row is None:
        row = GuildTaskSubmission(organization_id=actor.organization_id, user_id=actor.id,
            guild_id=command.guildId, level=command.level, revision=0)
        session.add(row)
    row.task_id, row.task_version = definition["id"], definition["version"]
    row.artifact, row.checks = command.artifact.strip(), list(command.checks)
    row.status = "submitted" if command.submit else "draft"
    row.submitted_at = datetime.now(UTC) if command.submit else None
    row.revision += 1
    session.flush()
    result = learner_snapshot(session, actor)
    session.commit()
    return envelope(request, result)


@router.post("/me/guild/requests")
def apply(command: GuildApply, request: Request, actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    require_role(actor, Role.LEARNER)
    lock_guild(session, actor.organization_id, actor.id)
    rows = scoped_rows(request_rows(session, actor.organization_id, actor.id), command.guildId)
    if command.guildId is None:
        # Old clients may safely retry their existing global application; new
        # certifications must never be ambiguously assigned to a guild.
        if any(row.status == "pending" and row.level == command.level for row in rows):
            return envelope(request, learner_snapshot(session, actor))
        fail("请先选择工会，再提交认证申请。")
    require_membership(session, actor, command.guildId)
    pending = next((row for row in rows if row.status == "pending"), None)
    if pending:
        if pending.level != command.level:
            fail("已有待审核的认证申请，请等待审核结果。")
        if (pending.task_snapshot or {}).get("revision") != command.expectedRevision:
            fail("成果已在其他页面更新，请重新载入并核对成果后再申请认证。", 409, "GUILD_REVISION_CONFLICT")
        return envelope(request, learner_snapshot(session, actor))
    evidence = require_entry(session, actor, rows, command.level)
    submission = session.get(GuildTaskSubmission, submission_key(actor, command.guildId, command.level))
    if not valid_submission(submission):
        fail("请先提交该阶段的任务成果并完成自查。")
    if submission.revision != command.expectedRevision:
        fail("成果已在其他页面更新，请重新载入并核对成果后再申请认证。", 409, "GUILD_REVISION_CONFLICT")
    definition = TASK_VERSIONS[(submission.task_id, submission.task_version)]
    task_snapshot = {key: definition[key] for key in ("id", "version", "source", "title", "level", "brief", "deliverable")}
    task_snapshot.update(artifact=submission.artifact, checks=list(submission.checks),
        submittedAt=submission.submitted_at.isoformat(), revision=submission.revision)
    row = GuildCertificationRequest(id=uuid.uuid4(), organization_id=actor.organization_id, user_id=actor.id,
                                    student_name=actor.display_name, level=command.level, status="pending", evidence=evidence,
                                    reviewer_name="", reason="", guild_id=command.guildId, task_snapshot=task_snapshot)
    session.add(row)
    session.flush()
    audit(session, request, actor, "guild.certification.request", row.id, {"level": row.level, "guild_id": row.guild_id})
    result = learner_snapshot(session, actor)
    session.commit()
    return envelope(request, result)


@router.get("/review-admin/guild-requests")
def admin_guild(request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_publisher(session, actor)
    return envelope(request, admin_snapshot(session, actor))


class GuildReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "returned"]
    reason: str = Field(default="", max_length=1000)


def certification_account_active(session, organization_id, learner_id):
    """Keep facts on their original owner, but honor a completed Feishu migration.

    Migration disables the temporary phone user deliberately. Only its consumed
    same-organization code and an active Feishu learner can keep that history
    eligible; an unused code or a disabled/revoked corporate account cannot.
    """
    learner = session.scalar(select(User).where(User.id == learner_id,
        User.organization_id == organization_id, select(RoleAssignment.id).where(
            RoleAssignment.user_id == User.id, RoleAssignment.organization_id == organization_id,
            RoleAssignment.role == Role.LEARNER).exists()))
    if learner is None:
        return False
    if learner.status == UserStatus.ACTIVE:
        return True
    return session.scalar(select(User.id).join(CompletionCode, CompletionCode.migrated_to_user_id == User.id)
        .join(ExternalIdentity, ExternalIdentity.user_id == User.id).where(
            CompletionCode.organization_id == organization_id, CompletionCode.user_id == learner_id,
            CompletionCode.used_at.is_not(None), CompletionCode.migrated_to_user_id != learner_id,
            User.organization_id == organization_id, User.status == UserStatus.ACTIVE,
            ExternalIdentity.organization_id == organization_id, ExternalIdentity.provider == "FEISHU",
            ExternalIdentity.revoked_at.is_(None), select(RoleAssignment.id).where(
                RoleAssignment.user_id == User.id, RoleAssignment.organization_id == organization_id,
                RoleAssignment.role == Role.LEARNER).exists()).limit(1)) is not None


@router.post("/review-admin/guild-requests/{request_id}/review")
def review(request_id: uuid.UUID, command: GuildReview, request: Request,
           actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    if not permissions(session, actor)["canPublish"]:
        fail("当前账号没有认证审核权限。", 403, "FORBIDDEN")
    row = session.scalar(select(GuildCertificationRequest).where(
        GuildCertificationRequest.id == request_id, GuildCertificationRequest.organization_id == actor.organization_id))
    if row is None:
        fail("认证申请不存在。", 404, "NOT_FOUND")
    if row.user_id in {actor.id, actor.inherited_learner_id}:
        fail("不能审核自己的认证申请，请由其他管理员处理。", 403, "FORBIDDEN")
    require_publisher(session, actor)
    lock_guild(session, actor.organization_id, row.user_id)
    row = session.scalar(select(GuildCertificationRequest).where(GuildCertificationRequest.id == request_id,
        GuildCertificationRequest.organization_id == actor.organization_id).with_for_update().execution_options(populate_existing=True))
    if row.status != "pending":
        if row.status != command.decision:
            fail("该申请已由管理员处理，请刷新后查看结果。")
        return envelope(request, admin_snapshot(session, actor))
    reason = command.reason.strip()
    if command.decision == "returned" and not reason:
        fail("请填写退回原因，帮助学员补齐认证条件。", 422, "GUILD_INVALID")
    if command.decision == "approved":
        if not certification_account_active(session, actor.organization_id, row.user_id):
            fail("学员账号当前不可用，不能通过认证。")
        rows = scoped_rows(request_rows(session, actor.organization_id, row.user_id), row.guild_id)
        if current_level(rows) + 1 != row.level:
            fail("上一等级认证状态已变化，请刷新后重新核对。")
        owned = {item["redemptionId"]: item for item in owned_evidence(session, actor.organization_id, row.user_id)}
        if any(item["redemptionId"] not in owned or owned[item["redemptionId"]]["id"] != item["id"] or
               owned[item["redemptionId"]]["grade"] != item["grade"] for item in row.evidence):
            fail("申请时的徽章凭证已变化，请退回申请后重新提交。")
        if {item["grade"] for item in row.evidence} != set(range(1, row.level + 1)):
            fail("认证凭证不完整，请退回申请后重新提交。")
        if row.guild_id:
            submission = session.get(GuildTaskSubmission, (actor.organization_id, row.user_id, row.guild_id, row.level))
            task = row.task_snapshot or {}
            if not valid_submission(submission) or any(task.get(key) != value for key, value in {
                "id": submission.task_id, "version": submission.task_version, "artifact": submission.artifact,
                "checks": submission.checks, "revision": submission.revision,
                "submittedAt": submission.submitted_at.isoformat(),
            }.items()):
                fail("阶段成果状态已变化，请退回申请后重新提交。")
    if command.decision == "returned" and row.guild_id:
        submission = session.get(GuildTaskSubmission, (actor.organization_id, row.user_id, row.guild_id, row.level))
        if submission:
            submission.status, submission.submitted_at = "draft", None
            submission.revision += 1
    row.status = command.decision
    row.reviewer_id = actor.id
    row.reviewer_name = actor.display_name
    row.reviewed_at = datetime.now(UTC)
    row.reason = reason
    session.flush()
    audit(session, request, actor, "guild.certification.review", row.id,
          {"level": row.level, "guild_id": row.guild_id, "decision": row.status, "learner_id": str(row.user_id)})
    result = admin_snapshot(session, actor)
    session.commit()
    return envelope(request, result)
