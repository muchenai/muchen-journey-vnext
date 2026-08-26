from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.controlled_task_authorization import task_version_contract_sha256
from journey_api.controlled_task_runtime import (
    ControlledTaskContractError,
    authorization_scope_sha256,
    policy_snapshot_sha256,
)
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    AuditEntry,
    ControlledTaskAuthorization,
    ControlledTaskAuthorizationApproval,
    ControlledTaskAuthorizationApprovalDecision,
    ControlledTaskAuthorizationApprovalRole,
    ControlledTaskAuthorizationStatus,
    JourneyStageVersion,
    JourneyVersion,
    Role,
    TaskVersion,
    User,
)
from journey_api.outcome_service import add_scoped_outbox_event
from journey_api.schemas import (
    ActivateControlledTaskAuthorizationCommand,
    ControlledTaskAuthorizationApprovalCommand,
    ControlledTaskAuthorizationApprovalOut,
    ControlledTaskAuthorizationApprovalResponse,
    ControlledTaskAuthorizationOut,
    ControlledTaskAuthorizationResponse,
    ControlledTaskAuthorizationRevisionCommand,
    CreateControlledTaskAuthorizationCommand,
    RevokeControlledTaskAuthorizationCommand,
)


router = APIRouter(prefix="/api/v1")


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def authorization_out(
    item: ControlledTaskAuthorization, *, idempotency_replay: bool = False
) -> ControlledTaskAuthorizationOut:
    return ControlledTaskAuthorizationOut(
        id=item.id,
        authorization_scope="NEWCOMER_CONTROLLED_TRAINING",
        authorized_project_ref=item.authorized_project_ref,
        target_journey_version_id=item.target_journey_version_id,
        target_journey_stage_version_id=item.target_journey_stage_version_id,
        target_task_version_id=item.task_version_id,
        task_version_sha256=item.task_version_sha256,
        authorization_version=item.authorization_version,
        scope_sha256=item.scope_sha256,
        project_owner_user_id=item.project_owner_user_id,
        newcomer_operations_owner_user_id=item.newcomer_operations_owner_user_id,
        data_security_owner_user_id=item.data_security_owner_user_id,
        reviewer_owner_user_id=item.reviewer_owner_user_id,
        primary_reviewer_user_id=item.primary_reviewer_user_id,
        backup_reviewer_user_id=item.backup_reviewer_user_id,
        policy_snapshot_ref=item.policy_snapshot_ref,
        policy_snapshot_version=item.policy_snapshot_version,
        policy_snapshot_sha256=item.policy_snapshot_sha256,
        policy_evidence_ref=item.policy_evidence_ref,
        policy_evidence_sha256=item.policy_evidence_sha256,
        valid_from=item.valid_from,
        expires_at=item.expires_at,
        status=item.status.value,
        revision=item.revision,
        activated_at=item.activated_at,
        revoked_at=item.revoked_at,
        expired_at=item.expired_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        idempotency_replay=idempotency_replay,
    )


def approval_out(
    item: ControlledTaskAuthorizationApproval, *, idempotency_replay: bool = False
) -> ControlledTaskAuthorizationApprovalOut:
    return ControlledTaskAuthorizationApprovalOut(
        id=item.id,
        authorization_id=item.authorization_id,
        approval_role=item.approval_role.value,
        signer_user_id=item.signer_user_id,
        decision=item.decision.value,
        signed_scope_sha256=item.signed_scope_sha256,
        signature_evidence_ref=item.signature_evidence_ref,
        signature_evidence_sha256=item.signature_evidence_sha256,
        signed_at=item.signed_at,
        created_at=item.created_at,
        idempotency_replay=idempotency_replay,
    )


def _lock_idempotency(
    session: Session, *, actor: Actor, command: str, key: str
) -> None:
    if not 8 <= len(key) <= 120:
        raise ApiError(400, "INVALID_REQUEST", "Idempotency-Key 长度必须为 8–120。")
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{command}:{actor.organization_id}:{actor.id}:{key}"},
    )


def _ensure_revision(item: ControlledTaskAuthorization, expected: int) -> None:
    if item.revision != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "受控任务授权已变化，请刷新后重试。",
            details={"current_revision": item.revision},
        )


def _add_lifecycle_evidence(
    session: Session,
    *,
    item: ControlledTaskAuthorization,
    actor: Actor,
    request: Request,
    action: str,
    db_now,
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=f"controlled_task_authorization.{action}",
            resource_type="controlled_task_authorization",
            resource_id=item.id,
            result=item.status.value,
            request_id=request.state.request_id,
            details={"revision": item.revision, "scope_sha256": item.scope_sha256},
            occurred_at=db_now,
        )
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type=f"controlled_task_authorization.{action}.v1",
        aggregate_type="controlled_task_authorization",
        aggregate_id=item.id,
        organization_id=actor.organization_id,
        owner_id=actor.id,
        actor_id=actor.id,
        request_id=request.state.request_id,
        dedupe_key=f"cta:{item.id}:{action}:{item.revision}",
        payload={"authorization_id": str(item.id), "revision": item.revision},
        occurred_at=db_now,
    )


@router.get(
    "/ops/controlled-task-authorizations/{authorization_id}",
    response_model=ControlledTaskAuthorizationResponse,
)
def get_controlled_task_authorization(
    authorization_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    item = session.scalar(
        select(ControlledTaskAuthorization).where(
            ControlledTaskAuthorization.id == authorization_id,
            ControlledTaskAuthorization.organization_id == actor.organization_id,
        )
    )
    if item is None:
        raise ApiError(404, "NOT_FOUND", "受控任务授权不存在。")
    return envelope(request, authorization_out(item))


@router.post(
    "/ops/controlled-task-authorizations",
    response_model=ControlledTaskAuthorizationResponse,
)
def create_controlled_task_authorization(
    command: CreateControlledTaskAuthorizationCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    _lock_idempotency(
        session, actor=actor, command="controlled-task-authorization.create", key=idempotency_key
    )
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="controlled-task-authorization.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, ControlledTaskAuthorizationOut(**replay))
    if command.valid_from.tzinfo is None or command.expires_at.tzinfo is None:
        raise ApiError(400, "INVALID_REQUEST", "授权有效期必须包含时区。")
    if command.valid_from >= command.expires_at:
        raise ApiError(400, "INVALID_REQUEST", "授权失效时间必须晚于生效时间。")
    journey = session.scalar(
        select(JourneyVersion).where(
            JourneyVersion.id == command.target_journey_version_id,
            JourneyVersion.organization_id == actor.organization_id,
        )
    )
    stage = session.scalar(
        select(JourneyStageVersion).where(
            JourneyStageVersion.id == command.target_journey_stage_version_id,
            JourneyStageVersion.organization_id == actor.organization_id,
            JourneyStageVersion.journey_version_id
            == command.target_journey_version_id,
            JourneyStageVersion.task_version_id == command.target_task_version_id,
        )
    )
    task = session.scalar(
        select(TaskVersion).where(
            TaskVersion.id == command.target_task_version_id,
            TaskVersion.organization_id == actor.organization_id,
        )
    )
    if journey is None or stage is None or task is None:
        raise ApiError(409, "AUTHORIZATION_LINEAGE_INVALID", "目标 Journey、Stage 与 Task 谱系不一致。")
    responsibility_ids = {
        command.project_owner_user_id,
        command.newcomer_operations_owner_user_id,
        command.data_security_owner_user_id,
        command.reviewer_owner_user_id,
        command.primary_reviewer_user_id,
        command.backup_reviewer_user_id,
    }
    users = set(
        session.scalars(
            select(User.id).where(
                User.organization_id == actor.organization_id,
                User.id.in_(responsibility_ids),
            )
        ).all()
    )
    if users != responsibility_ids:
        raise ApiError(409, "AUTHORIZATION_RESPONSIBILITY_INVALID", "授权责任人未完整就位。")
    try:
        policy_hash = policy_snapshot_sha256(
            command.policy_snapshot.model_dump(mode="python")
        )
    except ControlledTaskContractError as exc:
        raise ApiError(400, "POLICY_SNAPSHOT_INVALID", "治理条款快照不符合冻结合同。") from exc
    task_hash = task_version_contract_sha256(task)
    scope_values = {
        "organization_id": actor.organization_id,
        "authorized_project_ref": command.authorized_project_ref,
        "target_journey_version_id": command.target_journey_version_id,
        "target_journey_stage_version_id": command.target_journey_stage_version_id,
        "task_version_id": command.target_task_version_id,
        "task_version_sha256": task_hash,
        "authorization_version": command.authorization_version,
        "project_owner_user_id": command.project_owner_user_id,
        "newcomer_operations_owner_user_id": command.newcomer_operations_owner_user_id,
        "data_security_owner_user_id": command.data_security_owner_user_id,
        "reviewer_owner_user_id": command.reviewer_owner_user_id,
        "primary_reviewer_user_id": command.primary_reviewer_user_id,
        "backup_reviewer_user_id": command.backup_reviewer_user_id,
        "policy_snapshot_ref": command.policy_snapshot_ref,
        "policy_snapshot_version": command.policy_snapshot.policy_version,
        "policy_snapshot_sha256": policy_hash,
        "policy_evidence_ref": command.policy_evidence_ref,
        "policy_evidence_sha256": command.policy_evidence_sha256,
        "valid_from": command.valid_from,
        "expires_at": command.expires_at,
    }
    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "数据库时间不可用。")
    item = ControlledTaskAuthorization(
        id=uuid.uuid4(),
        authorization_scope="NEWCOMER_CONTROLLED_TRAINING",
        scope_sha256=authorization_scope_sha256(**scope_values),
        status=ControlledTaskAuthorizationStatus.DRAFT,
        revision=1,
        created_by_user_id=actor.id,
        created_at=db_now,
        updated_at=db_now,
        **scope_values,
    )
    session.add(item)
    session.flush()
    _add_lifecycle_evidence(
        session, item=item, actor=actor, request=request, action="created", db_now=db_now
    )
    response = authorization_out(item)
    store_result(
        session,
        actor_id=actor.id,
        command="controlled-task-authorization.create",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.post(
    "/ops/controlled-task-authorizations/{authorization_id}/submit-for-approvals",
    response_model=ControlledTaskAuthorizationResponse,
)
def submit_controlled_task_authorization_for_approvals(
    authorization_id: uuid.UUID,
    command: ControlledTaskAuthorizationRevisionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "authorization_id": str(authorization_id)}
    _lock_idempotency(session, actor=actor, command="cta.submit", key=idempotency_key)
    replay = find_replay(
        session, actor_id=actor.id, command="cta.submit", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, ControlledTaskAuthorizationOut(**replay))
    item = session.scalar(
        select(ControlledTaskAuthorization)
        .where(
            ControlledTaskAuthorization.id == authorization_id,
            ControlledTaskAuthorization.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ApiError(404, "NOT_FOUND", "受控任务授权不存在。")
    _ensure_revision(item, command.expected_revision)
    if item.status != ControlledTaskAuthorizationStatus.DRAFT:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "只有 DRAFT 可提交签署。")
    db_now = session.scalar(select(func.clock_timestamp()))
    item.status = ControlledTaskAuthorizationStatus.PENDING_APPROVALS
    item.revision += 1
    item.updated_at = db_now
    session.flush()
    _add_lifecycle_evidence(
        session, item=item, actor=actor, request=request, action="submitted", db_now=db_now
    )
    response = authorization_out(item)
    store_result(
        session,
        actor_id=actor.id,
        command="cta.submit",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.post(
    "/ops/controlled-task-authorizations/{authorization_id}/approvals",
    response_model=ControlledTaskAuthorizationApprovalResponse,
)
def approve_controlled_task_authorization(
    authorization_id: uuid.UUID,
    command: ControlledTaskAuthorizationApprovalCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "authorization_id": str(authorization_id)}
    _lock_idempotency(session, actor=actor, command="cta.approve", key=idempotency_key)
    replay = find_replay(
        session, actor_id=actor.id, command="cta.approve", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, ControlledTaskAuthorizationApprovalOut(**replay))
    item = session.scalar(
        select(ControlledTaskAuthorization)
        .where(
            ControlledTaskAuthorization.id == authorization_id,
            ControlledTaskAuthorization.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ApiError(404, "NOT_FOUND", "受控任务授权不存在。")
    _ensure_revision(item, command.expected_authorization_revision)
    if item.status != ControlledTaskAuthorizationStatus.PENDING_APPROVALS:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "授权当前不接收签署。")
    role = ControlledTaskAuthorizationApprovalRole(command.approval_role)
    expected_signer = {
        ControlledTaskAuthorizationApprovalRole.PROJECT_OWNER: item.project_owner_user_id,
        ControlledTaskAuthorizationApprovalRole.NEWCOMER_OPERATIONS_OWNER: item.newcomer_operations_owner_user_id,
        ControlledTaskAuthorizationApprovalRole.DATA_SECURITY_OWNER: item.data_security_owner_user_id,
        ControlledTaskAuthorizationApprovalRole.REVIEWER_OWNER: item.reviewer_owner_user_id,
    }[role]
    if actor.id != expected_signer:
        raise ApiError(403, "FORBIDDEN", "只有该责任角色本人可以签署。")
    if command.expected_scope_sha256 != item.scope_sha256:
        raise ApiError(409, "AUTHORIZATION_SCOPE_CHANGED", "授权 scope 已变化。")
    db_now = session.scalar(select(func.clock_timestamp()))
    if command.signed_at.tzinfo is None or command.signed_at > db_now:
        raise ApiError(400, "INVALID_REQUEST", "签署时间必须是已发生的带时区时间。")
    approval = ControlledTaskAuthorizationApproval(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        authorization_id=item.id,
        approval_role=role,
        signer_user_id=actor.id,
        decision=ControlledTaskAuthorizationApprovalDecision(command.decision),
        signed_scope_sha256=item.scope_sha256,
        signature_evidence_ref=command.signature_evidence_ref,
        signature_evidence_sha256=command.signature_evidence_sha256,
        signed_at=command.signed_at,
        created_at=db_now,
    )
    session.add(approval)
    session.flush()
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action="controlled_task_authorization.approval_recorded",
            resource_type="controlled_task_authorization_approval",
            resource_id=approval.id,
            result=approval.decision.value,
            request_id=request.state.request_id,
            details={"authorization_id": str(item.id), "approval_role": role.value},
            occurred_at=db_now,
        )
    )
    response = approval_out(approval)
    store_result(
        session,
        actor_id=actor.id,
        command="cta.approve",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.post(
    "/ops/controlled-task-authorizations/{authorization_id}/activate",
    response_model=ControlledTaskAuthorizationResponse,
)
def activate_controlled_task_authorization(
    authorization_id: uuid.UUID,
    command: ActivateControlledTaskAuthorizationCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "authorization_id": str(authorization_id)}
    _lock_idempotency(session, actor=actor, command="cta.activate", key=idempotency_key)
    initial = session.scalar(
        select(ControlledTaskAuthorization).where(
            ControlledTaskAuthorization.id == authorization_id,
            ControlledTaskAuthorization.organization_id == actor.organization_id,
        )
    )
    if initial is None:
        raise ApiError(404, "NOT_FOUND", "受控任务授权不存在。")
    scope_lock = ":".join(
        str(value)
        for value in (
            actor.organization_id,
            initial.target_journey_version_id,
            initial.target_journey_stage_version_id,
            initial.task_version_id,
        )
    )
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope_lock, 0))"),
        {"scope_lock": f"cta.scope:{scope_lock}"},
    )
    replay = find_replay(
        session, actor_id=actor.id, command="cta.activate", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, ControlledTaskAuthorizationOut(**replay))
    scoped = list(
        session.scalars(
            select(ControlledTaskAuthorization)
            .where(
                ControlledTaskAuthorization.organization_id == actor.organization_id,
                ControlledTaskAuthorization.target_journey_version_id
                == initial.target_journey_version_id,
                ControlledTaskAuthorization.target_journey_stage_version_id
                == initial.target_journey_stage_version_id,
                ControlledTaskAuthorization.task_version_id == initial.task_version_id,
            )
            .order_by(ControlledTaskAuthorization.id)
            .with_for_update()
        ).all()
    )
    item = next((candidate for candidate in scoped if candidate.id == authorization_id), None)
    if item is None:
        raise ApiError(409, "AUTHORIZATION_SCOPE_CHANGED", "授权 scope 已变化。")
    _ensure_revision(item, command.expected_revision)
    if item.status != ControlledTaskAuthorizationStatus.PENDING_APPROVALS:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "只有完成签署收集的授权可激活。")
    if actor.id not in {
        item.project_owner_user_id,
        item.newcomer_operations_owner_user_id,
        item.data_security_owner_user_id,
        item.reviewer_owner_user_id,
    }:
        raise ApiError(403, "FORBIDDEN", "只有授权责任人可以激活。")
    if (
        command.expected_scope_sha256 != item.scope_sha256
        or command.expected_task_version_sha256 != item.task_version_sha256
        or command.expected_policy_snapshot_sha256 != item.policy_snapshot_sha256
    ):
        raise ApiError(409, "AUTHORIZATION_SCOPE_CHANGED", "授权 hash 已变化。")
    db_now = session.scalar(select(func.clock_timestamp()))
    if not (item.valid_from <= db_now < item.expires_at):
        raise ApiError(409, "AUTHORIZATION_NOT_EFFECTIVE", "候选授权不在有效期内。")
    for old in scoped:
        if old.id == item.id or old.status != ControlledTaskAuthorizationStatus.ACTIVE:
            continue
        if db_now < old.expires_at:
            raise ApiError(409, "ACTIVE_AUTHORIZATION_EXISTS", "同一 scope 已有未过期授权。")
        old.status = ControlledTaskAuthorizationStatus.EXPIRED
        old.revision += 1
        old.expired_by_user_id = actor.id
        old.expired_at = db_now
        old.updated_at = db_now
        session.flush()
        _add_lifecycle_evidence(
            session, item=old, actor=actor, request=request, action="expired", db_now=db_now
        )
    approvals = list(
        session.scalars(
            select(ControlledTaskAuthorizationApproval).where(
                ControlledTaskAuthorizationApproval.authorization_id == item.id,
                ControlledTaskAuthorizationApproval.organization_id == actor.organization_id,
            )
        ).all()
    )
    expected = {
        ControlledTaskAuthorizationApprovalRole.PROJECT_OWNER: item.project_owner_user_id,
        ControlledTaskAuthorizationApprovalRole.NEWCOMER_OPERATIONS_OWNER: item.newcomer_operations_owner_user_id,
        ControlledTaskAuthorizationApprovalRole.DATA_SECURITY_OWNER: item.data_security_owner_user_id,
        ControlledTaskAuthorizationApprovalRole.REVIEWER_OWNER: item.reviewer_owner_user_id,
    }
    approved = {
        approval.approval_role: approval.signer_user_id
        for approval in approvals
        if approval.decision == ControlledTaskAuthorizationApprovalDecision.APPROVE
        and approval.signed_scope_sha256 == item.scope_sha256
    }
    if approved != expected or any(
        approval.decision == ControlledTaskAuthorizationApprovalDecision.REJECT
        for approval in approvals
    ):
        raise ApiError(409, "HUMAN_APPROVALS_INCOMPLETE", "四个准确责任角色尚未全部批准。")
    item.status = ControlledTaskAuthorizationStatus.ACTIVE
    item.revision += 1
    item.activated_by_user_id = actor.id
    item.activated_at = db_now
    item.updated_at = db_now
    session.flush()
    _add_lifecycle_evidence(
        session, item=item, actor=actor, request=request, action="activated", db_now=db_now
    )
    response = authorization_out(item)
    store_result(
        session,
        actor_id=actor.id,
        command="cta.activate",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


def _lock_active_authorization(
    session: Session, *, actor: Actor, authorization_id: uuid.UUID, expected_revision: int
) -> tuple[ControlledTaskAuthorization, object]:
    item = session.scalar(
        select(ControlledTaskAuthorization)
        .where(
            ControlledTaskAuthorization.id == authorization_id,
            ControlledTaskAuthorization.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ApiError(404, "NOT_FOUND", "受控任务授权不存在。")
    _ensure_revision(item, expected_revision)
    if item.status != ControlledTaskAuthorizationStatus.ACTIVE:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "只有 ACTIVE 授权可结束。")
    db_now = session.scalar(select(func.clock_timestamp()))
    return item, db_now


@router.post(
    "/ops/controlled-task-authorizations/{authorization_id}/expire",
    response_model=ControlledTaskAuthorizationResponse,
)
def expire_controlled_task_authorization(
    authorization_id: uuid.UUID,
    command: ControlledTaskAuthorizationRevisionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "authorization_id": str(authorization_id)}
    _lock_idempotency(session, actor=actor, command="cta.expire", key=idempotency_key)
    replay = find_replay(
        session, actor_id=actor.id, command="cta.expire", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, ControlledTaskAuthorizationOut(**replay))
    item, db_now = _lock_active_authorization(
        session,
        actor=actor,
        authorization_id=authorization_id,
        expected_revision=command.expected_revision,
    )
    if db_now < item.expires_at:
        raise ApiError(409, "AUTHORIZATION_NOT_YET_EXPIRED", "数据库时间尚未到授权失效点。")
    item.status = ControlledTaskAuthorizationStatus.EXPIRED
    item.revision += 1
    item.expired_by_user_id = actor.id
    item.expired_at = db_now
    item.updated_at = db_now
    session.flush()
    _add_lifecycle_evidence(
        session, item=item, actor=actor, request=request, action="expired", db_now=db_now
    )
    response = authorization_out(item)
    store_result(
        session,
        actor_id=actor.id,
        command="cta.expire",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.post(
    "/ops/controlled-task-authorizations/{authorization_id}/revoke",
    response_model=ControlledTaskAuthorizationResponse,
)
def revoke_controlled_task_authorization(
    authorization_id: uuid.UUID,
    command: RevokeControlledTaskAuthorizationCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "authorization_id": str(authorization_id)}
    _lock_idempotency(session, actor=actor, command="cta.revoke", key=idempotency_key)
    replay = find_replay(
        session, actor_id=actor.id, command="cta.revoke", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, ControlledTaskAuthorizationOut(**replay))
    item, db_now = _lock_active_authorization(
        session,
        actor=actor,
        authorization_id=authorization_id,
        expected_revision=command.expected_revision,
    )
    if actor.id not in {
        item.project_owner_user_id,
        item.newcomer_operations_owner_user_id,
        item.data_security_owner_user_id,
        item.reviewer_owner_user_id,
    }:
        raise ApiError(403, "FORBIDDEN", "只有授权责任人可以撤销。")
    item.status = ControlledTaskAuthorizationStatus.REVOKED
    item.revision += 1
    item.revoked_by_user_id = actor.id
    item.revoked_at = db_now
    item.revocation_reason = command.reason.strip()
    item.updated_at = db_now
    session.flush()
    _add_lifecycle_evidence(
        session, item=item, actor=actor, request=request, action="revoked", db_now=db_now
    )
    response = authorization_out(item)
    store_result(
        session,
        actor_id=actor.id,
        command="cta.revoke",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)
