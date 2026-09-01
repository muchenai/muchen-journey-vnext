import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.formal_assignment_workflow import (
    FormalAssignmentEvent,
    FormalAssignmentTransitionError,
    WorkflowActorKind,
    transition_formal_assignment,
)
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    DataRightsRequest,
    DataRightsRequestStatus,
    DataRightsRequestType,
    Enrollment,
    EnrollmentStatus,
    ExternalIdentity,
    Invite,
    InviteStatus,
    JoinContext,
    JoinContextStatus,
    ExternalNotificationReceipt,
    NotificationChannel,
    NotificationDelivery,
    NotificationEndpoint,
    NotificationEndpointStatus,
    NotificationStatus,
    ModuleContentPackageBinding,
    OutboxEvent,
    OutboxStatus,
    Review,
    ReviewDelegation,
    ReviewStatus,
    Role,
    RoleAssignment,
    User,
    UserStatus,
    WorkerHeartbeat,
)
from journey_api.schemas import (
    AssignEnrollmentReviewerCommand,
    AuditEntryOut,
    AuditListOut,
    AuditListResponse,
    CancelEnrollmentCommand,
    ConfigureNotificationEndpointCommand,
    CreateDataRightsRequestCommand,
    DataRightsRequestListOut,
    DataRightsRequestListResponse,
    DataRightsRequestOut,
    DataRightsRequestResponse,
    EnrollmentMutationOut,
    EnrollmentMutationResponse,
    EnrollmentOpsListOut,
    EnrollmentOpsListResponse,
    EnrollmentOpsOut,
    HandoffAssignedReviewCommand,
    NotificationEndpointListOut,
    NotificationEndpointListResponse,
    NotificationEndpointOut,
    NotificationEndpointResponse,
    NotificationOpsDeliveryListOut,
    NotificationOpsDeliveryListResponse,
    NotificationOpsDeliveryOut,
    NotificationOpsDeliveryResponse,
    RedriveNotificationCommand,
    RejectDataRightsRequestCommand,
    RevokeNotificationEndpointCommand,
    RuntimeComponentOut,
    RuntimeMetricsOut,
    RuntimeStatusOut,
    RuntimeStatusResponse,
    ReviewerWorkloadListOut,
    ReviewerWorkloadListResponse,
    ReviewerWorkloadOut,
    SetDataRightsLegalHoldCommand,
)
from journey_api.notification_recipients import encrypt_open_id


router = APIRouter(prefix="/api/v1/ops")
FILTER_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,120}$")
SAFE_AUDIT_KEYS = {
    "attachment_count",
    "audience",
    "content_source_count",
    "decision",
    "feedback_character_count",
    "flow",
    "reference_material_count",
    "role",
    "rotated_session_count",
    "rubric_dimension_count",
    "rubric_version",
    "sensitivity",
    "stable_key",
    "status",
    "version",
    "channel",
    "endpoint_status",
    "redrive_count",
    "request_type",
    "legal_hold",
    "resolution_code",
}


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def scoped_enrollment(
    session: Session, actor: Actor, enrollment_id: uuid.UUID, *, for_update: bool
) -> Enrollment:
    query = select(Enrollment).where(
        Enrollment.id == enrollment_id,
        Enrollment.organization_id == actor.organization_id,
    )
    if for_update:
        query = query.with_for_update()
    enrollment = session.scalar(query)
    if enrollment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的 Enrollment。")
    return enrollment


def open_review_for_enrollment(
    session: Session, enrollment: Enrollment, *, for_update: bool
) -> Review | None:
    query = (
        select(Review)
        .join(Assignment, Assignment.id == Review.assignment_id)
        .where(
            Assignment.enrollment_id == enrollment.id,
            Review.organization_id == enrollment.organization_id,
            Review.status.in_([ReviewStatus.ASSIGNED, ReviewStatus.IN_REVIEW]),
        )
        .order_by(Review.assigned_at.desc(), Review.id)
    )
    if for_update:
        query = query.with_for_update()
    reviews = session.scalars(query).all()
    if len(reviews) > 1:
        raise ApiError(409, "VERSION_CONFLICT", "Enrollment 存在多个开放评审，需要先隔离处理。")
    return reviews[0] if reviews else None


def reviewer_in_scope(session: Session, actor: Actor, reviewer_id: uuid.UUID) -> User:
    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == reviewer_id,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "新主管必须是同组织的有效 Reviewer。")
    return reviewer


def add_ops_facts(
    session: Session,
    *,
    request: Request,
    actor: Actor,
    action: str,
    event_type: str,
    resource_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type="enrollment",
            resource_id=resource_id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )
    session.add(
        OutboxEvent(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            owner_id=actor.id,
            actor_id=actor.id,
            request_id=request.state.request_id,
            payload_version=1,
            event_type=event_type,
            aggregate_type="enrollment",
            aggregate_id=resource_id,
            payload={"enrollment_id": str(resource_id)},
            status=OutboxStatus.PENDING,
        )
    )


def data_rights_request_out(
    request: DataRightsRequest, *, idempotency_replay: bool = False
) -> DataRightsRequestOut:
    allowed_commands: list[str] = []
    if request.status == DataRightsRequestStatus.OPEN:
        allowed_commands.append(
            "release_legal_hold" if request.legal_hold else "set_legal_hold"
        )
        if not request.legal_hold:
            allowed_commands.append("reject_request")
    return DataRightsRequestOut(
        id=request.id,
        subject_user_id=request.subject_user_id,
        request_type=request.request_type.value,
        status=request.status.value,
        requested_at=request.requested_at,
        due_at=request.due_at,
        legal_hold=request.legal_hold,
        resolution_code=request.resolution_code,
        resolved_at=request.completed_at,
        revision=request.revision,
        allowed_commands=allowed_commands,  # type: ignore[arg-type]
        idempotency_replay=idempotency_replay,
    )


def add_data_rights_audit(
    session: Session,
    *,
    request: Request,
    actor: Actor,
    action: str,
    resource_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type="data_rights_request",
            resource_id=resource_id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )


@router.post("/data-rights-requests", response_model=DataRightsRequestResponse)
def create_data_rights_request(
    command: CreateDataRightsRequestCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="data_rights_request.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        existing = session.scalar(
            select(DataRightsRequest).where(
                DataRightsRequest.id == uuid.UUID(str(replay["id"])),
                DataRightsRequest.organization_id == actor.organization_id,
            )
        )
        if existing is None:
            raise ApiError(
                409, "VERSION_CONFLICT", "幂等结果引用的数据权利请求已不可用。"
            )
        return envelope(
            request, data_rights_request_out(existing, idempotency_replay=True)
        )
    subject = session.scalar(
        select(User).where(
            User.id == command.subject_user_id,
            User.organization_id == actor.organization_id,
        )
    )
    if subject is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的数据主体。")
    now = datetime.now(UTC)
    rights_request = DataRightsRequest(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        subject_user_id=subject.id,
        request_type=DataRightsRequestType(command.request_type),
        status=DataRightsRequestStatus.OPEN,
        requested_by=actor.id,
        requested_at=now,
        due_at=now + timedelta(days=30),
        legal_hold=False,
        revision=1,
    )
    session.add(rights_request)
    result = {"id": str(rights_request.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="data_rights_request.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_data_rights_audit(
        session,
        request=request,
        actor=actor,
        action="data_rights_request.created",
        resource_id=rights_request.id,
        details={
            "request_type": command.request_type,
            "status": "OPEN",
            "reason": command.reason,
        },
    )
    session.commit()
    session.refresh(rights_request)
    return envelope(request, data_rights_request_out(rights_request))


@router.get("/data-rights-requests", response_model=DataRightsRequestListResponse)
def list_data_rights_requests(
    request: Request,
    status: DataRightsRequestStatus | None = None,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    query = select(DataRightsRequest).where(
        DataRightsRequest.organization_id == actor.organization_id
    )
    if status is not None:
        query = query.where(DataRightsRequest.status == status)
    requests = session.scalars(
        query.order_by(DataRightsRequest.due_at, DataRightsRequest.id).limit(100)
    ).all()
    return envelope(
        request,
        DataRightsRequestListOut(
            items=[data_rights_request_out(item) for item in requests]
        ),
    )


def scoped_data_rights_request(
    session: Session, actor: Actor, request_id: uuid.UUID
) -> DataRightsRequest:
    rights_request = session.scalar(
        select(DataRightsRequest)
        .where(
            DataRightsRequest.id == request_id,
            DataRightsRequest.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if rights_request is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的数据权利请求。")
    return rights_request


@router.put(
    "/data-rights-requests/{request_id}/legal-hold",
    response_model=DataRightsRequestResponse,
)
def set_data_rights_legal_hold(
    request_id: uuid.UUID,
    command: SetDataRightsLegalHoldCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "request_id": str(request_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="data_rights_request.legal_hold",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        existing = session.scalar(
            select(DataRightsRequest).where(
                DataRightsRequest.id == request_id,
                DataRightsRequest.organization_id == actor.organization_id,
            )
        )
        if existing is None:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的数据权利请求已不可用。")
        return envelope(
            request, data_rights_request_out(existing, idempotency_replay=True)
        )
    rights_request = scoped_data_rights_request(session, actor, request_id)
    ensure_revision(rights_request.revision, command.expected_revision)
    if rights_request.status != DataRightsRequestStatus.OPEN:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已关闭的请求不能更改 legal hold。")
    if rights_request.legal_hold == command.legal_hold:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "legal hold 已处于目标状态。")
    rights_request.legal_hold = command.legal_hold
    rights_request.legal_hold_reason = command.reason if command.legal_hold else None
    rights_request.revision += 1
    result = {"id": str(rights_request.id), "revision": rights_request.revision}
    store_result(
        session,
        actor_id=actor.id,
        command="data_rights_request.legal_hold",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_data_rights_audit(
        session,
        request=request,
        actor=actor,
        action=(
            "data_rights_request.legal_hold_set"
            if command.legal_hold
            else "data_rights_request.legal_hold_released"
        ),
        resource_id=rights_request.id,
        details={
            "legal_hold": command.legal_hold,
            "status": "OPEN",
            "reason": command.reason,
        },
    )
    session.commit()
    session.refresh(rights_request)
    return envelope(request, data_rights_request_out(rights_request))


@router.post(
    "/data-rights-requests/{request_id}/reject",
    response_model=DataRightsRequestResponse,
)
def reject_data_rights_request(
    request_id: uuid.UUID,
    command: RejectDataRightsRequestCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "request_id": str(request_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="data_rights_request.reject",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        existing = session.scalar(
            select(DataRightsRequest).where(
                DataRightsRequest.id == request_id,
                DataRightsRequest.organization_id == actor.organization_id,
            )
        )
        if existing is None:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的数据权利请求已不可用。")
        return envelope(
            request, data_rights_request_out(existing, idempotency_replay=True)
        )
    rights_request = scoped_data_rights_request(session, actor, request_id)
    ensure_revision(rights_request.revision, command.expected_revision)
    if rights_request.status != DataRightsRequestStatus.OPEN:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "数据权利请求已经关闭。")
    if rights_request.legal_hold:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "legal hold 未解除，不能拒绝请求。")
    now = datetime.now(UTC)
    rights_request.status = DataRightsRequestStatus.REJECTED
    rights_request.resolution_code = command.resolution_code
    rights_request.completed_at = now
    rights_request.completed_by = actor.id
    rights_request.revision += 1
    result = {"id": str(rights_request.id), "revision": rights_request.revision}
    store_result(
        session,
        actor_id=actor.id,
        command="data_rights_request.reject",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_data_rights_audit(
        session,
        request=request,
        actor=actor,
        action="data_rights_request.rejected",
        resource_id=rights_request.id,
        details={
            "request_type": rights_request.request_type.value,
            "status": "REJECTED",
            "resolution_code": command.resolution_code,
            "reason": command.reason,
        },
    )
    session.commit()
    session.refresh(rights_request)
    return envelope(request, data_rights_request_out(rights_request))


@router.get("/enrollments", response_model=EnrollmentOpsListResponse)
def list_enrollments(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    enrollments = session.scalars(
        select(Enrollment)
        .where(Enrollment.organization_id == actor.organization_id)
        .order_by(Enrollment.status, Enrollment.id)
        .limit(100)
    ).all()
    items: list[EnrollmentOpsOut] = []
    for enrollment in enrollments:
        learner = session.get(User, enrollment.learner_id)
        reviewer = session.get(User, enrollment.reviewer_id)
        assignments = session.scalars(
            select(Assignment)
            .where(
                Assignment.enrollment_id == enrollment.id,
                Assignment.organization_id == actor.organization_id,
            )
            .order_by(Assignment.position)
        ).all()
        open_review = open_review_for_enrollment(session, enrollment, for_update=False)
        allowed: list[str] = []
        if enrollment.status in {EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE}:
            if open_review is None:
                allowed = ["assign_reviewer", "cancel_enrollment"]
            elif open_review.status == ReviewStatus.ASSIGNED:
                allowed = ["handoff_assigned_review"]
        if enrollment.status == EnrollmentStatus.ACTIVE:
            allowed.append("create_learner_reentry")
        items.append(
            EnrollmentOpsOut(
                id=enrollment.id,
                learner_id=enrollment.learner_id,
                learner_display_name=learner.display_name if learner else "已停用身份",
                reviewer_id=enrollment.reviewer_id,
                reviewer_display_name=reviewer.display_name if reviewer else "已停用主管",
                status=enrollment.status.value,
                revision=enrollment.revision,
                journey_version_id=enrollment.journey_version_id,
                assignment_statuses=[item.status.value for item in assignments],
                open_review_status=open_review.status.value if open_review else None,
                open_review_revision=open_review.revision if open_review else None,
                allowed_commands=allowed,
            )
        )
    return envelope(request, EnrollmentOpsListOut(items=items))


@router.put(
    "/enrollments/{enrollment_id}/reviewer",
    response_model=EnrollmentMutationResponse,
)
def assign_reviewer(
    enrollment_id: uuid.UUID,
    command: AssignEnrollmentReviewerCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "enrollment_id": str(enrollment_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="enrollment.assign_reviewer",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, EnrollmentMutationOut(**replay))
    enrollment = scoped_enrollment(session, actor, enrollment_id, for_update=True)
    ensure_revision(enrollment.revision, command.expected_revision)
    if enrollment.status not in {EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前 Enrollment 不能更换主管。")
    if enrollment.reviewer_id == command.reviewer_id:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "新主管必须与当前主管不同。")
    reviewer_in_scope(session, actor, command.reviewer_id)
    module_binding = (
        session.scalar(
            select(ModuleContentPackageBinding).where(
                ModuleContentPackageBinding.organization_id == actor.organization_id,
                ModuleContentPackageBinding.journey_version_id
                == enrollment.journey_version_id,
            )
        )
        if enrollment.journey_version_id is not None
        else None
    )
    if module_binding is not None and command.reviewer_id not in {
        module_binding.primary_reviewer_user_id,
        module_binding.backup_reviewer_user_id,
    }:
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "模块 Enrollment 只能在 Owner 内容包具名的主备 Reviewer 间替换。",
        )
    open_review = open_review_for_enrollment(session, enrollment, for_update=True)
    if open_review is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已生成评审记录，不能更换主管或改写评审历史。")
    previous_reviewer_id = enrollment.reviewer_id
    enrollment.reviewer_id = command.reviewer_id
    enrollment.revision += 1
    result = {
        "resource_id": str(enrollment.id),
        "status": enrollment.status.value,
        "revision": enrollment.revision,
        "reviewer_id": str(enrollment.reviewer_id),
    }
    store_result(
        session,
        actor_id=actor.id,
        command="enrollment.assign_reviewer",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_ops_facts(
        session,
        request=request,
        actor=actor,
        action="enrollment.reviewer_assigned",
        event_type="enrollment.reviewer_assigned.v1",
        resource_id=enrollment.id,
        details={
            "previous_reviewer_id": str(previous_reviewer_id),
            "reviewer_id": str(command.reviewer_id),
            "reason": command.reason,
            "review_replaced": False,
        },
    )
    session.commit()
    return envelope(request, EnrollmentMutationOut(**result))


@router.get("/reviewer-workload", response_model=ReviewerWorkloadListResponse)
def reviewer_workload(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    db_now = session.scalar(select(func.clock_timestamp()))
    bindings = session.scalars(
        select(ModuleContentPackageBinding)
        .where(ModuleContentPackageBinding.organization_id == actor.organization_id)
        .order_by(
            ModuleContentPackageBinding.module_key,
            ModuleContentPackageBinding.created_at.desc(),
            ModuleContentPackageBinding.id,
        )
    ).all()
    items: list[ReviewerWorkloadOut] = []
    for binding in bindings:
        primary = session.get(User, binding.primary_reviewer_user_id)
        backup = session.get(User, binding.backup_reviewer_user_id)
        if (
            primary is None
            or backup is None
            or primary.organization_id != actor.organization_id
            or backup.organization_id != actor.organization_id
        ):
            raise ApiError(409, "VERSION_CONFLICT", "内容包 Reviewer 谱系已不可用。")
        enrollments = session.scalars(
            select(Enrollment).where(
                Enrollment.organization_id == actor.organization_id,
                Enrollment.journey_version_id == binding.journey_version_id,
                Enrollment.status.in_(
                    [EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE]
                ),
            )
        ).all()
        enrollment_ids = [item.id for item in enrollments]
        reviews = (
            session.scalars(
                select(Review)
                .join(Assignment, Assignment.id == Review.assignment_id)
                .where(
                    Review.organization_id == actor.organization_id,
                    Assignment.organization_id == actor.organization_id,
                    Assignment.enrollment_id.in_(enrollment_ids),
                    Review.status.in_([ReviewStatus.ASSIGNED, ReviewStatus.IN_REVIEW]),
                )
            ).all()
            if enrollment_ids
            else []
        )
        overdue = sum(
            db_now is not None
            and review.assigned_at
            + timedelta(minutes=binding.completion_sla_minutes)
            <= db_now
            for review in reviews
        )
        items.append(
            ReviewerWorkloadOut(
                binding_id=binding.id,
                module_key=binding.module_key,
                package_id=binding.package_id,
                package_version=binding.package_version,
                primary_reviewer_id=primary.id,
                primary_reviewer_display_name=primary.display_name,
                backup_reviewer_id=backup.id,
                backup_reviewer_display_name=backup.display_name,
                first_response_sla_minutes=binding.first_response_sla_minutes,
                completion_sla_minutes=binding.completion_sla_minutes,
                active_enrollment_count=len(enrollments),
                open_review_count=len(reviews),
                overdue_review_count=overdue,
                capacity_limit=None,
                capacity_status="PENDING_OWNER_CONTENT",
                replacement_scope="PRIMARY_OR_NAMED_BACKUP_ONLY",
            )
        )
    return envelope(request, ReviewerWorkloadListOut(items=items))


@router.post(
    "/enrollments/{enrollment_id}/assigned-review/handoff",
    response_model=EnrollmentMutationResponse,
)
def handoff_assigned_review(
    enrollment_id: uuid.UUID,
    command: HandoffAssignedReviewCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "enrollment_id": str(enrollment_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="review.handoff_assigned",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, EnrollmentMutationOut(**replay))
    enrollment = scoped_enrollment(session, actor, enrollment_id, for_update=True)
    ensure_revision(enrollment.revision, command.expected_revision)
    review = open_review_for_enrollment(session, enrollment, for_update=True)
    if review is None or review.status != ReviewStatus.ASSIGNED:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "仅允许移交尚未开始的待评审记录。")
    ensure_revision(review.revision, command.review_revision)
    if enrollment.reviewer_id == command.reviewer_id or review.reviewer_id == command.reviewer_id:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "新 Reviewer 必须与当前 Reviewer 不同。")
    reviewer_in_scope(session, actor, command.reviewer_id)
    linked_identity = session.scalar(
        select(ExternalIdentity.id).where(
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.user_id == command.reviewer_id,
            ExternalIdentity.provider == "FEISHU",
            ExternalIdentity.revoked_at.is_(None),
        )
    )
    if linked_identity is None:
        raise ApiError(409, "IDENTITY_NOT_LINKED", "新 Reviewer 尚未绑定有效飞书身份。")
    previous_reviewer_id = review.reviewer_id
    enrollment.reviewer_id = command.reviewer_id
    enrollment.revision += 1
    delegation = ReviewDelegation(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        review_id=review.id,
        reviewer_id=command.reviewer_id,
        delegated_by=actor.id,
        reason=command.reason,
        revision=1,
    )
    session.add(delegation)
    result = {
        "resource_id": str(enrollment.id),
        "status": enrollment.status.value,
        "revision": enrollment.revision,
        "reviewer_id": str(command.reviewer_id),
    }
    store_result(
        session,
        actor_id=actor.id,
        command="review.handoff_assigned",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_ops_facts(
        session,
        request=request,
        actor=actor,
        action="review.assigned_handoff",
        event_type="review.assigned_handoff.v1",
        resource_id=enrollment.id,
        details={
            "previous_reviewer_id": str(previous_reviewer_id),
            "reviewer_id": str(command.reviewer_id),
            "review_id": str(review.id),
            "reason": command.reason,
            "review_status": review.status.value,
            "delegation_id": str(delegation.id),
        },
    )
    session.commit()
    return envelope(request, EnrollmentMutationOut(**result))


@router.post(
    "/enrollments/{enrollment_id}/cancel",
    response_model=EnrollmentMutationResponse,
)
def cancel_enrollment(
    enrollment_id: uuid.UUID,
    command: CancelEnrollmentCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "enrollment_id": str(enrollment_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="enrollment.cancel",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, EnrollmentMutationOut(**replay))
    enrollment = scoped_enrollment(session, actor, enrollment_id, for_update=True)
    ensure_revision(enrollment.revision, command.expected_revision)
    if enrollment.status not in {EnrollmentStatus.PENDING_IDENTITY, EnrollmentStatus.ACTIVE}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前 Enrollment 不能取消。")
    open_review = open_review_for_enrollment(session, enrollment, for_update=True)
    if open_review is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已生成评审记录，不能取消 Enrollment 或改写评审历史。")
    assignments = session.scalars(
        select(Assignment)
        .where(
            Assignment.enrollment_id == enrollment.id,
            Assignment.organization_id == actor.organization_id,
        )
        .with_for_update()
    ).all()
    for assignment in assignments:
        if assignment.status in {
            AssignmentStatus.AVAILABLE,
            AssignmentStatus.IN_PROGRESS,
        }:
            try:
                assignment.status = transition_formal_assignment(
                    current=assignment.status,
                    event=FormalAssignmentEvent.CANCEL,
                    actor_kind=WorkflowActorKind.MODULE_OPERATOR,
                    actor_id=actor.id,
                    learner_id=enrollment.learner_id,
                    assigned_reviewer_id=enrollment.reviewer_id,
                    reason=command.reason,
                )
            except FormalAssignmentTransitionError as exc:
                raise ApiError(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "当前任务状态不能随 Enrollment 取消。",
                ) from exc
            assignment.revision += 1
        elif assignment.status in {
            AssignmentStatus.SUBMITTED,
            AssignmentStatus.IN_REVIEW,
            AssignmentStatus.NEEDS_REVISION,
        }:
            raise ApiError(
                409,
                "INVALID_STATE_TRANSITION",
                "已进入提交或评审历史的任务不能通过取消 Enrollment 覆盖。",
            )
    join_context = session.scalar(
        select(JoinContext).where(JoinContext.enrollment_id == enrollment.id).with_for_update()
    )
    if join_context is not None and join_context.status == JoinContextStatus.PENDING:
        join_context.status = JoinContextStatus.REVOKED
        invite = session.scalar(
            select(Invite).where(Invite.id == join_context.invite_id).with_for_update()
        )
        if invite is not None and invite.status == InviteStatus.ACTIVE:
            invite.status = InviteStatus.REVOKED
            invite.revoked_at = datetime.now(UTC)
            invite.revoke_reason = command.reason
            invite.revision += 1
    enrollment.status = EnrollmentStatus.CANCELLED
    enrollment.revision += 1
    result = {
        "resource_id": str(enrollment.id),
        "status": enrollment.status.value,
        "revision": enrollment.revision,
        "reviewer_id": str(enrollment.reviewer_id),
    }
    store_result(
        session,
        actor_id=actor.id,
        command="enrollment.cancel",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_ops_facts(
        session,
        request=request,
        actor=actor,
        action="enrollment.cancelled",
        event_type="enrollment.cancelled.v1",
        resource_id=enrollment.id,
        details={"reason": command.reason, "cancelled_assignment_count": len(assignments)},
    )
    session.commit()
    return envelope(request, EnrollmentMutationOut(**result))


def notification_endpoint_out(
    endpoint: NotificationEndpoint, *, idempotency_replay: bool = False
) -> NotificationEndpointOut:
    return NotificationEndpointOut(
        id=endpoint.id,
        user_id=endpoint.user_id,
        channel="FEISHU",
        receive_id_type="open_id",
        status=endpoint.status.value,
        source="OPERATOR_CONFIG",
        revision=endpoint.revision,
        updated_at=endpoint.updated_at,
        idempotency_replay=idempotency_replay,
    )


def require_recipient_configuration() -> str:
    settings = get_settings()
    if not settings.notification_recipients_enabled:
        raise ApiError(409, "FEATURE_DISABLED", "通知接收人配置尚未启用。")
    return settings.notification_recipient_key


def scoped_notification_learner(
    session: Session, actor: Actor, user_id: uuid.UUID
) -> User:
    learner = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(
            Enrollment,
            (Enrollment.learner_id == User.id)
            & (Enrollment.organization_id == User.organization_id),
        )
        .where(
            User.id == user_id,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.LEARNER,
            Enrollment.status != EnrollmentStatus.CANCELLED,
        )
    )
    if learner is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可配置通知的有效学员。")
    return learner


def add_notification_audit(
    session: Session,
    *,
    request: Request,
    actor: Actor,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )


@router.get(
    "/notification-endpoints", response_model=NotificationEndpointListResponse
)
def list_notification_endpoints(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    endpoints = session.scalars(
        select(NotificationEndpoint)
        .where(NotificationEndpoint.organization_id == actor.organization_id)
        .order_by(NotificationEndpoint.updated_at.desc(), NotificationEndpoint.id)
        .limit(100)
    ).all()
    return envelope(
        request,
        NotificationEndpointListOut(
            items=[notification_endpoint_out(endpoint) for endpoint in endpoints]
        ),
    )


@router.put(
    "/users/{user_id}/notification-endpoint",
    response_model=NotificationEndpointResponse,
)
def configure_notification_endpoint(
    user_id: uuid.UUID,
    command: ConfigureNotificationEndpointCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    recipient_key = require_recipient_configuration()
    scoped_notification_learner(session, actor, user_id)
    encrypted_receive_id, fingerprint = encrypt_open_id(
        command.receive_id,
        key_value=recipient_key,
        organization_id=actor.organization_id,
        user_id=user_id,
    )
    payload = {
        "expected_revision": command.expected_revision,
        "reason": command.reason,
        "recipient_fingerprint": fingerprint,
        "user_id": str(user_id),
    }
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="notification.endpoint.configure",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, NotificationEndpointOut(**replay))
    endpoint = session.scalar(
        select(NotificationEndpoint)
        .where(
            NotificationEndpoint.organization_id == actor.organization_id,
            NotificationEndpoint.user_id == user_id,
            NotificationEndpoint.channel == NotificationChannel.FEISHU,
        )
        .with_for_update()
    )
    actual_revision = endpoint.revision if endpoint is not None else 0
    if actual_revision != command.expected_revision:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "通知接收人配置已更新，请确认最新状态后重试。",
            details={"current_revision": actual_revision},
        )
    now = datetime.now(UTC)
    if endpoint is None:
        endpoint = NotificationEndpoint(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            user_id=user_id,
            channel=NotificationChannel.FEISHU,
            receive_id_type="open_id",
            encrypted_receive_id=encrypted_receive_id,
            recipient_fingerprint=fingerprint,
            key_version=1,
            status=NotificationEndpointStatus.ACTIVE,
            source="OPERATOR_CONFIG",
            revision=1,
            created_by=actor.id,
            created_at=now,
            updated_at=now,
        )
        session.add(endpoint)
    else:
        endpoint.encrypted_receive_id = encrypted_receive_id
        endpoint.recipient_fingerprint = fingerprint
        endpoint.status = NotificationEndpointStatus.ACTIVE
        endpoint.revision += 1
        endpoint.updated_at = now
        endpoint.revoked_at = None
    result = notification_endpoint_out(endpoint).model_dump(mode="json")
    store_result(
        session,
        actor_id=actor.id,
        command="notification.endpoint.configure",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_notification_audit(
        session,
        request=request,
        actor=actor,
        action="notification.endpoint.configured",
        resource_type="notification_endpoint",
        resource_id=endpoint.id,
        details={
            "channel": "FEISHU",
            "endpoint_status": "ACTIVE",
            "reason": command.reason,
        },
    )
    session.commit()
    session.refresh(endpoint)
    return envelope(request, notification_endpoint_out(endpoint))


@router.post(
    "/notification-endpoints/{endpoint_id}/revoke",
    response_model=NotificationEndpointResponse,
)
def revoke_notification_endpoint(
    endpoint_id: uuid.UUID,
    command: RevokeNotificationEndpointCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "endpoint_id": str(endpoint_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="notification.endpoint.revoke",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, NotificationEndpointOut(**replay))
    endpoint = session.scalar(
        select(NotificationEndpoint)
        .where(
            NotificationEndpoint.id == endpoint_id,
            NotificationEndpoint.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if endpoint is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的通知接收人配置。")
    ensure_revision(endpoint.revision, command.expected_revision)
    if endpoint.status != NotificationEndpointStatus.ACTIVE:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "通知接收人配置已经撤销。")
    endpoint.status = NotificationEndpointStatus.REVOKED
    endpoint.revision += 1
    endpoint.encrypted_receive_id = f"v1.{secrets.token_urlsafe(48)}"
    endpoint.recipient_fingerprint = secrets.token_hex(32)
    endpoint.revoked_at = datetime.now(UTC)
    endpoint.updated_at = endpoint.revoked_at
    result = notification_endpoint_out(endpoint).model_dump(mode="json")
    store_result(
        session,
        actor_id=actor.id,
        command="notification.endpoint.revoke",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_notification_audit(
        session,
        request=request,
        actor=actor,
        action="notification.endpoint.revoked",
        resource_type="notification_endpoint",
        resource_id=endpoint.id,
        details={
            "channel": "FEISHU",
            "endpoint_status": "REVOKED",
            "reason": command.reason,
        },
    )
    session.commit()
    session.refresh(endpoint)
    return envelope(request, notification_endpoint_out(endpoint))


def notification_delivery_out(
    delivery: NotificationDelivery, *, receipt: bool
) -> NotificationOpsDeliveryOut:
    return NotificationOpsDeliveryOut(
        id=delivery.id,
        recipient_user_id=delivery.recipient_user_id,
        channel=delivery.channel.value,
        status=delivery.status.value,
        attempt_count=delivery.attempt_count,
        redrive_count=delivery.redrive_count,
        revision=delivery.revision,
        last_error_code=delivery.last_error_code,
        next_attempt_at=delivery.next_attempt_at,
        delivered_at=delivery.delivered_at,
        external_receipt_recorded=receipt,
    )


@router.get(
    "/notification-deliveries", response_model=NotificationOpsDeliveryListResponse
)
def list_notification_deliveries(
    request: Request,
    status: NotificationStatus | None = None,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    query = select(NotificationDelivery).where(
        NotificationDelivery.organization_id == actor.organization_id
    )
    if status is not None:
        query = query.where(NotificationDelivery.status == status)
    deliveries = session.scalars(
        query.order_by(NotificationDelivery.updated_at.desc()).limit(100)
    ).all()
    receipt_ids = set(
        session.scalars(
            select(ExternalNotificationReceipt.delivery_id).where(
                ExternalNotificationReceipt.delivery_id.in_(
                    [delivery.id for delivery in deliveries]
                )
            )
        ).all()
    ) if deliveries else set()
    return envelope(
        request,
        NotificationOpsDeliveryListOut(
            items=[
                notification_delivery_out(
                    delivery, receipt=delivery.id in receipt_ids
                )
                for delivery in deliveries
            ]
        ),
    )


@router.post(
    "/notification-deliveries/{delivery_id}/redrive",
    response_model=NotificationOpsDeliveryResponse,
)
def redrive_notification_delivery(
    delivery_id: uuid.UUID,
    command: RedriveNotificationCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "delivery_id": str(delivery_id)}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="notification.delivery.redrive",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, NotificationOpsDeliveryOut(**replay))
    delivery = session.scalar(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if delivery is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的通知投递。")
    ensure_revision(delivery.revision, command.expected_revision)
    if delivery.status != NotificationStatus.DEAD:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "只有 DEAD 通知可以人工重驱。")
    if delivery.redrive_count >= 3:
        raise ApiError(409, "REDRIVE_LIMIT_REACHED", "通知已达到人工重驱上限。")
    if session.scalar(
        select(ExternalNotificationReceipt.id).where(
            ExternalNotificationReceipt.delivery_id == delivery.id
        )
    ) is not None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已记录外部回执，不能再次投递。")
    if delivery.channel == NotificationChannel.FEISHU:
        active_endpoint = session.scalar(
            select(NotificationEndpoint.id).where(
                NotificationEndpoint.organization_id == actor.organization_id,
                NotificationEndpoint.user_id == delivery.recipient_user_id,
                NotificationEndpoint.channel == NotificationChannel.FEISHU,
                NotificationEndpoint.status == NotificationEndpointStatus.ACTIVE,
            )
        )
        if active_endpoint is None:
            raise ApiError(409, "RECIPIENT_UNAVAILABLE", "接收人尚无有效飞书通知配置。")
    event = session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.id == delivery.event_id,
            OutboxEvent.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if event is None or event.status != OutboxStatus.FAILED:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "通知 Outbox 状态不允许重驱。")
    now = datetime.now(UTC)
    delivery.status = NotificationStatus.PENDING
    delivery.attempt_offset = event.attempt_count
    delivery.redrive_count += 1
    delivery.revision += 1
    delivery.next_attempt_at = now
    delivery.last_error_code = None
    delivery.updated_at = now
    event.status = OutboxStatus.PENDING
    event.processed_at = None
    event.next_attempt_at = now
    event.last_error_code = None
    event.locked_at = None
    event.lock_token = None
    result = notification_delivery_out(delivery, receipt=False).model_dump(mode="json")
    store_result(
        session,
        actor_id=actor.id,
        command="notification.delivery.redrive",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_notification_audit(
        session,
        request=request,
        actor=actor,
        action="notification.delivery.redriven",
        resource_type="notification_delivery",
        resource_id=delivery.id,
        details={"redrive_count": delivery.redrive_count, "reason": command.reason},
    )
    session.commit()
    return envelope(request, NotificationOpsDeliveryOut(**result))


def safe_audit_details(details: dict[str, object]) -> tuple[dict[str, str | int | bool], list[str]]:
    safe: dict[str, str | int | bool] = {}
    redacted: list[str] = []
    for key, value in sorted(details.items()):
        if key in SAFE_AUDIT_KEYS and isinstance(value, (str, int, bool)):
            safe[key] = value
        else:
            redacted.append(key)
    return safe, redacted


@router.get("/audit", response_model=AuditListResponse)
def list_audit(
    request: Request,
    action: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=80),
    result: str | None = Query(default=None, max_length=32),
    resource_id: uuid.UUID | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    for value in (action, resource_type, result):
        if value is not None and not FILTER_PATTERN.fullmatch(value):
            raise ApiError(400, "INVALID_REQUEST", "审计筛选值无效。")
    now = datetime.now(UTC)
    after = occurred_after or (now - timedelta(days=7))
    before = occurred_before or now
    if after.tzinfo is None or before.tzinfo is None or after >= before:
        raise ApiError(400, "INVALID_REQUEST", "审计时间范围无效。")
    if before - after > timedelta(days=31):
        raise ApiError(400, "INVALID_REQUEST", "单次审计查询不能超过 31 天。")
    query = select(AuditEntry).where(
        AuditEntry.organization_id == actor.organization_id,
        AuditEntry.occurred_at >= after,
        AuditEntry.occurred_at < before,
    )
    if action is not None:
        query = query.where(AuditEntry.action == action)
    if resource_type is not None:
        query = query.where(AuditEntry.resource_type == resource_type)
    if result is not None:
        query = query.where(AuditEntry.result == result)
    if resource_id is not None:
        query = query.where(AuditEntry.resource_id == resource_id)
    rows = session.scalars(query.order_by(AuditEntry.occurred_at.desc(), AuditEntry.id).limit(limit)).all()
    items: list[AuditEntryOut] = []
    for row in rows:
        safe, redacted = safe_audit_details(row.details)
        items.append(
            AuditEntryOut(
                id=row.id,
                actor_id=row.actor_id,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                result=row.result,
                request_id=row.request_id,
                safe_details=safe,
                redacted_fields=redacted,
                occurred_at=row.occurred_at,
            )
        )
    return envelope(request, AuditListOut(items=items))


@router.get("/runtime-status", response_model=RuntimeStatusResponse)
def runtime_status(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    settings = get_settings()
    migration_revision = session.scalar(text("SELECT version_num FROM alembic_version")) or "unknown"
    heartbeat = session.get(WorkerHeartbeat, "notification-worker")
    now = datetime.now(UTC)
    stale = heartbeat is None or heartbeat.last_seen_at < now - timedelta(seconds=15)
    backlog = session.scalar(
        select(func.count(OutboxEvent.id)).where(
            OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.PROCESSING, OutboxStatus.FAILED]),
            OutboxEvent.processed_at.is_(None),
        )
    ) or 0
    dead = session.scalar(
        select(func.count(NotificationDelivery.id)).where(
            NotificationDelivery.status == NotificationStatus.DEAD
        )
    ) or 0
    retry_wait = session.scalar(
        select(func.count(NotificationDelivery.id)).where(
            NotificationDelivery.status == NotificationStatus.RETRY_WAIT
        )
    ) or 0
    oldest_pending_at = session.scalar(
        select(func.min(OutboxEvent.occurred_at)).where(
            OutboxEvent.status.in_(
                [OutboxStatus.PENDING, OutboxStatus.PROCESSING, OutboxStatus.FAILED]
            ),
            OutboxEvent.processed_at.is_(None),
        )
    )
    oldest_pending_seconds = (
        max(0, int((now - oldest_pending_at).total_seconds()))
        if oldest_pending_at is not None
        else 0
    )
    denied = session.scalar(
        select(func.count(AuditEntry.id)).where(
            AuditEntry.organization_id == actor.organization_id,
            AuditEntry.result == "DENIED",
            AuditEntry.occurred_at >= now - timedelta(hours=24),
        )
    ) or 0
    data = RuntimeStatusOut(
        environment=settings.app_env,
        release=settings.app_release,
        config_schema_version=settings.config_schema_version,
        migration_revision=str(migration_revision),
        api=RuntimeComponentOut(status="READY", release=settings.app_release),
        database=RuntimeComponentOut(status="READY"),
        worker=RuntimeComponentOut(
            status="STALE" if stale else heartbeat.status,
            release=heartbeat.release if heartbeat else None,
            last_seen_at=heartbeat.last_seen_at if heartbeat else None,
            stale=stale,
        ),
        observability_mode="STRUCTURED_STDOUT",
        metrics=RuntimeMetricsOut(
            outbox_backlog=backlog,
            notification_retry_wait=retry_wait,
            notification_dead=dead,
            oldest_pending_seconds=oldest_pending_seconds,
            permission_denials_24h=denied,
        ),
    )
    return envelope(request, data)
