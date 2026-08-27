from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    ControlledTaskAuthorization,
    ControlledTaskAuthorizationStatus,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    ExternalNotificationReceipt,
    Handoff,
    HandoffAcceptance,
    IncentiveLedgerEntry,
    IncentiveType,
    JourneyOutcomeEvidence,
    JourneyStageVersion,
    JourneyVersion,
    NotificationAttempt,
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    NextTrainingStageDecision,
    NextTrainingStageDecisionValue,
    NextTrainingStageReviewRequest,
    NextTrainingStageReviewAssignment,
    NextTrainingStageReviewResolution,
    NextTrainingStageReviewRequestStatus,
    Outcome,
    OutboxEvent,
    Review,
    Role,
    Submission,
    SubmissionVersion,
    TaskVersion,
    User,
)
from journey_api.outcome_service import add_scoped_outbox_event
from journey_api.schemas import (
    AiSummaryOut,
    HandoffOut,
    IncentiveLedgerEntryOut,
    IncentiveLedgerOut,
    IncentiveLedgerResponse,
    JourneyResultEvaluationOut,
    NotificationDeliveryOut,
    NextTrainingStageReviewRequestCommand,
    NextTrainingStageReviewRequestListOut,
    NextTrainingStageReviewRequestListResponse,
    NextTrainingStageReviewRequestOut,
    NextTrainingStageReviewRequestResponse,
    ResultEvaluationOut,
    ResultLearningCompletionOut,
    ResultNextTrainingStageOut,
    ResultOut,
    ResultReviewerConclusionOut,
    ResultResponse,
    ResultRubricFeedbackOut,
    TimelineItemOut,
    TimelineOut,
    TimelineResponse,
    HandoffAcceptanceCommand,
    HandoffAcceptanceOut,
    HandoffAcceptanceResponse,
    HandoffControlledTaskAuthorizationOut,
    HandoffDetailOut,
    HandoffDetailResponse,
)
from journey_api.controlled_task_authorization import task_version_contract_sha256
from journey_api.controlled_task_runtime import authorization_scope_sha256


router = APIRouter(prefix="/api/v1")

RUBRIC_TITLES = {
    "problem_clarity": "问题清晰度",
    "evidence_quality": "依据质量",
    "action_feasibility": "行动可执行性",
    "validation_design": "验证设计",
}


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def review_request_out(
    session: Session,
    item: NextTrainingStageReviewRequest,
    *,
    already_received: bool = False,
    idempotency_replay: bool = False,
) -> NextTrainingStageReviewRequestOut:
    assignment = session.scalar(
        select(NextTrainingStageReviewAssignment).where(
            NextTrainingStageReviewAssignment.organization_id == item.organization_id,
            NextTrainingStageReviewAssignment.review_request_id == item.id,
        )
    )
    resolution = session.scalar(
        select(NextTrainingStageReviewResolution).where(
            NextTrainingStageReviewResolution.organization_id == item.organization_id,
            NextTrainingStageReviewResolution.review_request_id == item.id,
        )
    )
    replacement_decision_id = session.scalar(
        select(NextTrainingStageDecision.id).where(
            NextTrainingStageDecision.organization_id == item.organization_id,
            NextTrainingStageDecision.source_review_request_id == item.id,
        )
    )
    return NextTrainingStageReviewRequestOut(
        id=item.id,
        next_training_stage_decision_id=item.next_training_stage_decision_id,
        source_decision=item.source_decision.value,
        reason=item.reason,
        evidence_refs=list(item.evidence_refs),
        status=(
            resolution.status.value
            if resolution is not None
            else "IN_REVIEW"
            if assignment is not None
            else "RECEIVED"
        ),
        requested_at=item.requested_at,
        assigned_reviewer_user_id=(
            assignment.reviewer_user_id if assignment is not None else None
        ),
        assigned_at=assignment.assigned_at if assignment is not None else None,
        resolution_reason=(
            resolution.resolution_reason if resolution is not None else None
        ),
        resolved_at=resolution.resolved_at if resolution is not None else None,
        replacement_decision_id=replacement_decision_id,
        already_received=already_received,
        idempotency_replay=idempotency_replay,
    )


def handoff_acceptance_out(
    item: HandoffAcceptance, *, idempotency_replay: bool = False
) -> HandoffAcceptanceOut:
    return HandoffAcceptanceOut(
        id=item.id,
        handoff_id=item.handoff_id,
        next_training_stage_decision_id=item.next_training_stage_decision_id,
        controlled_task_authorization_id=item.controlled_task_authorization_id,
        target_journey_version_id=item.target_journey_version_id,
        target_journey_stage_version_id=item.target_journey_stage_version_id,
        target_task_version_id=item.target_task_version_id,
        target_reviewer_user_id=item.target_reviewer_user_id,
        target_enrollment_id=item.target_enrollment_id,
        target_assignment_id=item.target_assignment_id,
        accepted_at=item.accepted_at,
        idempotency_replay=idempotency_replay,
    )


def notification_out(
    delivery: NotificationDelivery | None,
    *,
    external_confirmed: bool,
) -> NotificationDeliveryOut:
    if delivery is None:
        return NotificationDeliveryOut(
            status="NOT_REQUESTED",
            channel=None,
            display_status="没有通知投递事实；核心结果仍以本页为准。",
            attempt_count=0,
            next_attempt_at=None,
            last_error_code=None,
            delivered_at=None,
            delivery_scope="LOCAL_TEST_ONLY",
            external_delivery_confirmed=False,
        )
    if delivery.channel == NotificationChannel.LOCAL_TEST:
        labels = {
            NotificationStatus.PENDING: "通知任务已排队，尚未由本地测试适配器处理。",
            NotificationStatus.SENDING: "本地测试适配器正在处理；这不代表外部送达。",
            NotificationStatus.DELIVERED: "本地测试适配器已处理；不代表飞书真实送达。",
            NotificationStatus.RETRY_WAIT: "本地测试适配器处理失败，正在等待安全重试。",
            NotificationStatus.DEAD: "本地测试适配器已停止自动重试；核心结果不受影响。",
        }
    else:
        labels = {
            NotificationStatus.PENDING: "飞书通知任务已排队，核心结果以本页为准。",
            NotificationStatus.SENDING: "飞书通知正在处理，尚未确认外部回执。",
            NotificationStatus.DELIVERED: "飞书服务已接受通知请求。",
            NotificationStatus.RETRY_WAIT: "飞书通知暂未成功，正在等待安全重试。",
            NotificationStatus.DEAD: "飞书通知已停止自动重试；核心结果不受影响。",
        }
    return NotificationDeliveryOut(
        status=delivery.status.value,
        channel=delivery.channel.value,
        display_status=labels[delivery.status],
        attempt_count=delivery.attempt_count,
        next_attempt_at=delivery.next_attempt_at,
        last_error_code=delivery.last_error_code,
        delivered_at=delivery.delivered_at,
        delivery_scope=(
            "LOCAL_TEST_ONLY"
            if delivery.channel == NotificationChannel.LOCAL_TEST
            else "FEISHU"
        ),
        external_delivery_confirmed=external_confirmed,
    )


def rubric_feedback(
    evaluation: Evaluation, task: TaskVersion | None = None
) -> list[ResultRubricFeedbackOut]:
    configured_titles = {
        str(item.get("dimension_key")): str(item.get("title"))
        for item in (task.rubric.get("dimensions", []) if task is not None else [])
        if isinstance(item, dict) and item.get("dimension_key") and item.get("title")
    }
    structured = evaluation.structured_feedback
    if evaluation.feedback_structure_version == 1 and isinstance(structured, list):
        return [
            ResultRubricFeedbackOut(
                dimension_key=str(item["dimension_key"]),
                title=configured_titles.get(
                    str(item["dimension_key"]),
                    RUBRIC_TITLES.get(
                        str(item["dimension_key"]), str(item["dimension_key"])
                    ),
                ),
                rating=str(item["rating"]),
                feedback=str(item["feedback"]),
            )
            for item in structured
            if isinstance(item, dict)
            and "dimension_key" in item
            and "rating" in item
            and "feedback" in item
        ]
    return [
        ResultRubricFeedbackOut(
            dimension_key=key,
            title=configured_titles.get(key, RUBRIC_TITLES.get(key, key)),
            rating=rating,
            feedback=None,
        )
        for key, rating in evaluation.rubric_scores.items()
    ]


@router.get("/me/incentives", response_model=IncentiveLedgerResponse)
def learner_incentives(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    entries = list(
        session.scalars(
            select(IncentiveLedgerEntry)
            .where(
                IncentiveLedgerEntry.organization_id == actor.organization_id,
                IncentiveLedgerEntry.person_id == actor.id,
            )
            .order_by(IncentiveLedgerEntry.created_at, IncentiveLedgerEntry.id)
        ).all()
    )
    points_total = sum(
        entry.amount or 0
        for entry in entries
        if entry.incentive_type == IncentiveType.POINTS
    )
    xp_total = sum(
        entry.amount or 0
        for entry in entries
        if entry.incentive_type == IncentiveType.XP
    )
    return envelope(
        request,
        IncentiveLedgerOut(
            points_total=points_total,
            xp_total=xp_total,
            entries=[
                IncentiveLedgerEntryOut(
                    id=entry.id,
                    module_key=entry.module_key,
                    incentive_type=entry.incentive_type.value,
                    amount=entry.amount,
                    label=entry.label,
                    source_outcome_id=entry.source_outcome_id,
                    rule_ref=entry.rule_ref,
                    rule_sha256=entry.rule_sha256,
                    correction_of_entry_id=entry.correction_of_entry_id,
                    correction_reason=entry.correction_reason,
                    created_at=entry.created_at,
                )
                for entry in entries
            ],
        ),
    )


@router.get(
    "/me/next-training-stage-review-requests",
    response_model=NextTrainingStageReviewRequestListResponse,
)
def learner_next_training_stage_review_requests(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    items = list(
        session.scalars(
            select(NextTrainingStageReviewRequest)
            .where(
                NextTrainingStageReviewRequest.organization_id
                == actor.organization_id,
                NextTrainingStageReviewRequest.requester_user_id == actor.id,
            )
            .order_by(
                NextTrainingStageReviewRequest.requested_at.desc(),
                NextTrainingStageReviewRequest.id.desc(),
            )
        ).all()
    )
    return envelope(
        request,
        NextTrainingStageReviewRequestListOut(
            items=[review_request_out(session, item) for item in items]
        ),
    )


@router.post(
    "/me/next-training-stage-decisions/{decision_id}/review-requests",
    response_model=NextTrainingStageReviewRequestResponse,
)
def request_next_training_stage_review(
    decision_id: uuid.UUID,
    command: NextTrainingStageReviewRequestCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    payload = {
        **command.model_dump(mode="json"),
        "decision_id": str(decision_id),
    }
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="next-training-stage-review-request.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, NextTrainingStageReviewRequestOut(**replay))

    row = session.execute(
        select(NextTrainingStageDecision, Outcome)
        .join(
            Outcome,
            (Outcome.id == NextTrainingStageDecision.outcome_id)
            & (Outcome.organization_id == NextTrainingStageDecision.organization_id),
        )
        .where(
            NextTrainingStageDecision.id == decision_id,
            NextTrainingStageDecision.organization_id == actor.organization_id,
            NextTrainingStageDecision.person_id == actor.id,
            Outcome.learner_id == actor.id,
        )
    ).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有可由本人申请复核的下一训练阶段决定。")
    decision, _outcome = row
    if decision.decision == NextTrainingStageDecisionValue.READY:
        raise ApiError(409, "REVIEW_NOT_APPLICABLE", "该决定不需要人工复核申请。")

    existing = session.scalar(
        select(NextTrainingStageReviewRequest).where(
            NextTrainingStageReviewRequest.organization_id == actor.organization_id,
            NextTrainingStageReviewRequest.next_training_stage_decision_id
            == decision.id,
            NextTrainingStageReviewRequest.requester_user_id == actor.id,
        )
    )
    if existing is not None:
        response = review_request_out(session, existing, already_received=True)
        store_result(
            session,
            actor_id=actor.id,
            command="next-training-stage-review-request.create",
            key=idempotency_key,
            payload=payload,
            response=response.model_dump(mode="json"),
        )
        session.commit()
        return envelope(request, response)

    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "数据库时间不可用。")
    item = NextTrainingStageReviewRequest(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        handoff_id=decision.handoff_id,
        next_training_stage_decision_id=decision.id,
        decision_scope="NEXT_TRAINING_STAGE",
        source_decision=decision.decision,
        requester_user_id=actor.id,
        reason=command.reason.strip(),
        evidence_refs=command.evidence_refs,
        status=NextTrainingStageReviewRequestStatus.RECEIVED,
        requested_at=db_now,
        created_at=db_now,
    )
    session.add(item)
    session.flush()
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action="next_training_stage.review_requested",
            resource_type="next_training_stage_review_request",
            resource_id=item.id,
            result="RECEIVED",
            request_id=request.state.request_id,
            details={
                "decision_id": str(decision.id),
                "source_decision": decision.decision.value,
                "evidence_ref_count": len(command.evidence_refs),
            },
            occurred_at=db_now,
        )
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="next_training_stage.review_requested.v1",
        aggregate_type="next_training_stage_review_request",
        aggregate_id=item.id,
        organization_id=actor.organization_id,
        owner_id=actor.id,
        actor_id=actor.id,
        request_id=request.state.request_id,
        dedupe_key=f"next-training-stage-review-request:{item.id}",
        payload={
            "review_request_id": str(item.id),
            "decision_id": str(decision.id),
        },
        occurred_at=db_now,
    )
    response = review_request_out(session, item)
    store_result(
        session,
        actor_id=actor.id,
        command="next-training-stage-review-request.create",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


def _handoff_out(handoff: Handoff, owner: User) -> HandoffOut:
    return HandoffOut(
        id=handoff.id,
        status=handoff.status.value,
        owner_user_id=handoff.owner_user_id,
        owner_display_name=owner.display_name,
        title=handoff.title,
        next_step_code="CONFIRM_HANDOFF",
        next_step_title=handoff.next_step_title,
        instructions=handoff.instructions,
        created_at=handoff.created_at,
    )


@router.get("/me/handoffs/{handoff_id}", response_model=HandoffDetailResponse)
def learner_handoff_detail(
    handoff_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    row = session.execute(
        select(Handoff, Outcome, User, NextTrainingStageDecision, HandoffAcceptance)
        .join(
            Outcome,
            (Outcome.id == Handoff.outcome_id)
            & (Outcome.organization_id == Handoff.organization_id),
        )
        .join(
            User,
            (User.id == Handoff.owner_user_id)
            & (User.organization_id == Handoff.organization_id),
        )
        .outerjoin(
            NextTrainingStageDecision,
            (NextTrainingStageDecision.handoff_id == Handoff.id)
            & (NextTrainingStageDecision.organization_id == Handoff.organization_id)
            & (
                NextTrainingStageDecision.revision
                == select(func.max(NextTrainingStageDecision.revision))
                .where(
                    NextTrainingStageDecision.handoff_id == Handoff.id,
                    NextTrainingStageDecision.organization_id
                    == Handoff.organization_id,
                )
                .correlate(Handoff)
                .scalar_subquery()
            ),
        )
        .outerjoin(
            HandoffAcceptance,
            (HandoffAcceptance.handoff_id == Handoff.id)
            & (HandoffAcceptance.organization_id == Handoff.organization_id),
        )
        .where(
            Handoff.id == handoff_id,
            Handoff.organization_id == actor.organization_id,
            Outcome.learner_id == actor.id,
        )
    ).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有可由本人查看的交接内容。")
    handoff, _outcome, owner, decision, acceptance = row
    db_now = session.scalar(select(func.clock_timestamp()))
    authorization = None
    if (
        acceptance is None
        and decision is not None
        and decision.decision == NextTrainingStageDecisionValue.READY
        and db_now is not None
    ):
        authorization = session.scalar(
            select(ControlledTaskAuthorization)
            .where(
                ControlledTaskAuthorization.organization_id == actor.organization_id,
                ControlledTaskAuthorization.status
                == ControlledTaskAuthorizationStatus.ACTIVE,
                ControlledTaskAuthorization.valid_from <= db_now,
                ControlledTaskAuthorization.expires_at > db_now,
            )
            .order_by(
                ControlledTaskAuthorization.authorization_version.desc(),
                ControlledTaskAuthorization.id.desc(),
            )
        )
    authorization_out = (
        HandoffControlledTaskAuthorizationOut(
            id=authorization.id,
            status="ACTIVE",
            revision=authorization.revision,
            target_journey_version_id=authorization.target_journey_version_id,
            target_journey_stage_version_id=authorization.target_journey_stage_version_id,
            target_task_version_id=authorization.task_version_id,
            task_version_sha256=authorization.task_version_sha256,
            scope_sha256=authorization.scope_sha256,
            policy_snapshot_sha256=authorization.policy_snapshot_sha256,
            primary_reviewer_user_id=authorization.primary_reviewer_user_id,
            valid_from=authorization.valid_from,
            expires_at=authorization.expires_at,
        )
        if authorization is not None
        else None
    )
    status = (
        "ALREADY_ACCEPTED"
        if acceptance is not None
        else "DECISION_REQUIRED"
        if decision is None or decision.decision != NextTrainingStageDecisionValue.READY
        else "AUTHORIZATION_REQUIRED"
        if authorization is None
        else "READY_TO_ACCEPT"
    )
    return envelope(
        request,
        HandoffDetailOut(
            handoff=_handoff_out(handoff, owner),
            next_training_stage_decision_id=decision.id if decision is not None else None,
            next_training_stage_decision=(
                "READY"
                if decision is not None
                and decision.decision == NextTrainingStageDecisionValue.READY
                else None
            ),
            controlled_task_authorization=authorization_out,
            acceptance=(
                handoff_acceptance_out(acceptance) if acceptance is not None else None
            ),
            acceptance_status=status,
        ),
    )


@router.post(
    "/me/handoffs/{handoff_id}/accept",
    response_model=HandoffAcceptanceResponse,
)
def accept_handoff(
    handoff_id: uuid.UUID,
    command: HandoffAcceptanceCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = {**command.model_dump(mode="json"), "handoff_id": str(handoff_id)}
    if not 8 <= len(idempotency_key) <= 120:
        raise ApiError(400, "INVALID_REQUEST", "Idempotency-Key 长度必须为 8–120。")
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {
            "lock_key": (
                f"handoff.accept:{actor.organization_id}:{actor.id}:{idempotency_key}"
            )
        },
    )
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="handoff.accept",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(request, HandoffAcceptanceOut(**replay))

    handoff_row = session.execute(
        select(Handoff, Outcome)
        .join(
            Outcome,
            (Outcome.id == Handoff.outcome_id)
            & (Outcome.organization_id == Handoff.organization_id),
        )
        .where(
            Handoff.id == handoff_id,
            Handoff.organization_id == actor.organization_id,
            Outcome.learner_id == actor.id,
        )
        .with_for_update(of=Handoff)
    ).one_or_none()
    if handoff_row is None:
        raise ApiError(404, "NOT_FOUND", "没有可由本人确认的交接内容。")
    handoff, outcome = handoff_row
    existing = session.scalar(
        select(HandoffAcceptance)
        .where(
            HandoffAcceptance.organization_id == actor.organization_id,
            HandoffAcceptance.handoff_id == handoff.id,
        )
        .with_for_update()
    )
    if existing is not None:
        raise ApiError(409, "HANDOFF_ALREADY_ACCEPTED", "该交接已由本人确认。")

    decision = session.scalar(
        select(NextTrainingStageDecision)
        .where(
            NextTrainingStageDecision.id
            == command.next_training_stage_decision_id,
            NextTrainingStageDecision.organization_id == actor.organization_id,
            NextTrainingStageDecision.handoff_id == handoff.id,
            NextTrainingStageDecision.outcome_id == outcome.id,
            NextTrainingStageDecision.person_id == actor.id,
            NextTrainingStageDecision.revision
            == select(func.max(NextTrainingStageDecision.revision))
            .where(
                NextTrainingStageDecision.handoff_id == handoff.id,
                NextTrainingStageDecision.organization_id == actor.organization_id,
            )
            .scalar_subquery(),
        )
        .with_for_update(read=True)
    )
    if decision is None or decision.decision != NextTrainingStageDecisionValue.READY:
        raise ApiError(409, "NEXT_TRAINING_STAGE_READY_REQUIRED", "缺少有效的下一训练阶段 READY 真人决定。")

    authorization = session.scalar(
        select(ControlledTaskAuthorization)
        .where(
            ControlledTaskAuthorization.id
            == command.controlled_task_authorization_id,
            ControlledTaskAuthorization.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if authorization is None:
        raise ApiError(404, "AUTHORIZATION_NOT_FOUND", "受控任务授权不存在。")
    if authorization.revision != command.expected_authorization_revision:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "受控任务授权已变化，请刷新后重试。",
            details={"current_revision": authorization.revision},
        )
    expected_scope = {
        "target_journey_version_id": command.expected_target_journey_version_id,
        "target_journey_stage_version_id": command.expected_target_journey_stage_version_id,
        "task_version_id": command.expected_target_task_version_id,
        "scope_sha256": command.expected_scope_sha256,
        "task_version_sha256": command.expected_task_version_sha256,
        "policy_snapshot_sha256": command.expected_policy_snapshot_sha256,
    }
    actual_scope = {
        "target_journey_version_id": authorization.target_journey_version_id,
        "target_journey_stage_version_id": authorization.target_journey_stage_version_id,
        "task_version_id": authorization.task_version_id,
        "scope_sha256": authorization.scope_sha256,
        "task_version_sha256": authorization.task_version_sha256,
        "policy_snapshot_sha256": authorization.policy_snapshot_sha256,
    }
    if expected_scope != actual_scope:
        raise ApiError(409, "AUTHORIZATION_SCOPE_CHANGED", "受控任务授权范围已变化，请刷新后重试。")

    journey_version = session.scalar(
        select(JourneyVersion)
        .where(
            JourneyVersion.id == authorization.target_journey_version_id,
            JourneyVersion.organization_id == actor.organization_id,
        )
        .with_for_update(read=True)
    )
    stage = session.scalar(
        select(JourneyStageVersion)
        .where(
            JourneyStageVersion.id
            == authorization.target_journey_stage_version_id,
            JourneyStageVersion.organization_id == actor.organization_id,
            JourneyStageVersion.journey_version_id
            == authorization.target_journey_version_id,
            JourneyStageVersion.task_version_id == authorization.task_version_id,
        )
        .with_for_update(read=True)
    )
    task = session.scalar(
        select(TaskVersion)
        .where(
            TaskVersion.id == authorization.task_version_id,
            TaskVersion.organization_id == actor.organization_id,
        )
        .with_for_update(read=True)
    )
    if journey_version is None or stage is None or task is None:
        raise ApiError(409, "AUTHORIZATION_LINEAGE_INVALID", "受控任务授权谱系不完整。")
    locked_users = list(
        session.scalars(
            select(User)
            .where(
                User.organization_id == actor.organization_id,
                User.id.in_(
                    sorted(
                        {
                            actor.id,
                            authorization.primary_reviewer_user_id,
                            authorization.backup_reviewer_user_id,
                        },
                        key=str,
                    )
                ),
            )
            .order_by(User.id)
            .with_for_update(read=True)
        ).all()
    )
    if len({user.id for user in locked_users}) != 3:
        raise ApiError(409, "AUTHORIZATION_RESPONSIBILITY_INVALID", "受控任务责任人未完整就位。")
    if task_version_contract_sha256(task) != authorization.task_version_sha256:
        raise ApiError(409, "TASK_VERSION_HASH_MISMATCH", "固定 TaskVersion 内容校验失败。")
    computed_scope_sha256 = authorization_scope_sha256(
        organization_id=authorization.organization_id,
        authorized_project_ref=authorization.authorized_project_ref,
        target_journey_version_id=authorization.target_journey_version_id,
        target_journey_stage_version_id=authorization.target_journey_stage_version_id,
        task_version_id=authorization.task_version_id,
        task_version_sha256=authorization.task_version_sha256,
        authorization_version=authorization.authorization_version,
        project_owner_user_id=authorization.project_owner_user_id,
        newcomer_operations_owner_user_id=authorization.newcomer_operations_owner_user_id,
        data_security_owner_user_id=authorization.data_security_owner_user_id,
        reviewer_owner_user_id=authorization.reviewer_owner_user_id,
        primary_reviewer_user_id=authorization.primary_reviewer_user_id,
        backup_reviewer_user_id=authorization.backup_reviewer_user_id,
        policy_snapshot_ref=authorization.policy_snapshot_ref,
        policy_snapshot_version=authorization.policy_snapshot_version,
        policy_snapshot_sha256=authorization.policy_snapshot_sha256,
        policy_evidence_ref=authorization.policy_evidence_ref,
        policy_evidence_sha256=authorization.policy_evidence_sha256,
        valid_from=authorization.valid_from,
        expires_at=authorization.expires_at,
    )
    if computed_scope_sha256 != authorization.scope_sha256:
        raise ApiError(409, "AUTHORIZATION_SCOPE_HASH_MISMATCH", "授权 scope 校验失败。")

    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "数据库时间不可用。")
    if (
        authorization.status != ControlledTaskAuthorizationStatus.ACTIVE
        or db_now < authorization.valid_from
        or db_now >= authorization.expires_at
    ):
        raise ApiError(409, "AUTHORIZATION_NOT_EFFECTIVE", "受控任务授权当前未生效或已过期。")

    target_enrollment = Enrollment(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        learner_id=actor.id,
        reviewer_id=authorization.primary_reviewer_user_id,
        journey_version_id=authorization.target_journey_version_id,
        status=EnrollmentStatus.ACTIVE,
        revision=1,
    )
    target_assignment = Assignment(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        enrollment_id=target_enrollment.id,
        task_definition_id=task.task_definition_id,
        task_version_id=task.id,
        journey_stage_version_id=stage.id,
        position=1,
        status=AssignmentStatus.AVAILABLE,
        revision=1,
        assigned_at=db_now,
    )
    acceptance = HandoffAcceptance(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        handoff_id=handoff.id,
        accepted_by_user_id=actor.id,
        next_training_stage_decision_id=decision.id,
        decision_scope="NEXT_TRAINING_STAGE",
        decision_value=NextTrainingStageDecisionValue.READY,
        controlled_task_authorization_id=authorization.id,
        target_journey_version_id=authorization.target_journey_version_id,
        target_journey_stage_version_id=authorization.target_journey_stage_version_id,
        target_task_version_id=authorization.task_version_id,
        target_reviewer_user_id=authorization.primary_reviewer_user_id,
        target_enrollment_id=target_enrollment.id,
        target_assignment_id=target_assignment.id,
        accepted_at=db_now,
        created_at=db_now,
    )
    # These models intentionally have no ORM ownership relationships; flush in
    # the same explicit lineage order as the database contract while retaining
    # one transaction for all-or-nothing rollback.
    session.add(target_enrollment)
    session.flush()
    session.add(target_assignment)
    session.flush()
    session.add(acceptance)
    session.flush()
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action="handoff.accepted",
            resource_type="handoff_acceptance",
            resource_id=acceptance.id,
            result="ACCEPTED",
            request_id=request.state.request_id,
            details={
                "handoff_id": str(handoff.id),
                "authorization_id": str(authorization.id),
                "target_enrollment_id": str(target_enrollment.id),
                "target_assignment_id": str(target_assignment.id),
            },
            occurred_at=db_now,
        )
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="handoff.accepted.v1",
        aggregate_type="handoff_acceptance",
        aggregate_id=acceptance.id,
        organization_id=actor.organization_id,
        owner_id=actor.id,
        actor_id=actor.id,
        request_id=request.state.request_id,
        dedupe_key=f"handoff-acceptance:{acceptance.id}",
        payload={
            "handoff_acceptance_id": str(acceptance.id),
            "target_assignment_id": str(target_assignment.id),
        },
        occurred_at=db_now,
    )
    response = handoff_acceptance_out(acceptance)
    store_result(
        session,
        actor_id=actor.id,
        command="handoff.accept",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.get("/me/result", response_model=ResultResponse)
def result(
    request: Request,
    enrollment_id: uuid.UUID | None = None,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    enrollment_scope = (
        (Enrollment.id == enrollment_id,) if enrollment_id is not None else ()
    )
    row = session.execute(
        select(
            Outcome,
            Handoff,
            Evaluation,
            User,
            NextTrainingStageDecision,
            NotificationDelivery,
            ExternalNotificationReceipt,
        )
        .join(Enrollment, Enrollment.id == Outcome.enrollment_id)
        .join(
            Handoff,
            (Handoff.outcome_id == Outcome.id)
            & (Handoff.organization_id == Outcome.organization_id)
            & (Handoff.enrollment_id == Outcome.enrollment_id)
            & (Handoff.source_evaluation_id == Outcome.source_evaluation_id),
        )
        .join(
            Evaluation,
            (Evaluation.id == Outcome.source_evaluation_id)
            & (Evaluation.organization_id == Outcome.organization_id)
            & (Evaluation.assignment_id == Outcome.assignment_id),
        )
        .join(
            User,
            (User.id == Handoff.owner_user_id)
            & (User.organization_id == Handoff.organization_id),
        )
        .outerjoin(
            NextTrainingStageDecision,
            (NextTrainingStageDecision.handoff_id == Handoff.id)
            & (NextTrainingStageDecision.organization_id == Handoff.organization_id)
            & (NextTrainingStageDecision.outcome_id == Outcome.id)
            & (
                NextTrainingStageDecision.revision
                == select(func.max(NextTrainingStageDecision.revision))
                .where(
                    NextTrainingStageDecision.handoff_id == Handoff.id,
                    NextTrainingStageDecision.organization_id
                    == Handoff.organization_id,
                )
                .correlate(Handoff)
                .scalar_subquery()
            ),
        )
        .outerjoin(
            NotificationDelivery,
            (NotificationDelivery.outcome_id == Outcome.id)
            & (NotificationDelivery.organization_id == Outcome.organization_id)
            & (NotificationDelivery.recipient_user_id == Outcome.learner_id),
        )
        .outerjoin(
            ExternalNotificationReceipt,
            ExternalNotificationReceipt.delivery_id == NotificationDelivery.id,
        )
        .where(
            Outcome.organization_id == actor.organization_id,
            Outcome.learner_id == actor.id,
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            *enrollment_scope,
        )
        .order_by(Outcome.created_at.desc(), Outcome.id.desc())
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "当前还没有最终结果。")
    outcome, handoff, evaluation, owner, next_stage_decision, delivery, receipt = row
    if evaluation.decision != Decision.PASS:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "最终结果缺少有效的通过结论。")
    reviewer = session.scalar(
        select(User).where(
            User.id == evaluation.reviewer_id,
            User.organization_id == actor.organization_id,
        )
    )
    if reviewer is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "最终结果缺少具名 Reviewer。")
    formal_rows = session.execute(
        select(JourneyStageVersion, Evaluation, TaskVersion)
        .join(
            JourneyOutcomeEvidence,
            JourneyOutcomeEvidence.journey_stage_version_id
            == JourneyStageVersion.id,
        )
        .join(Evaluation, Evaluation.id == JourneyOutcomeEvidence.evaluation_id)
        .join(Assignment, Assignment.id == Evaluation.assignment_id)
        .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
        .where(
            JourneyOutcomeEvidence.outcome_id == outcome.id,
            JourneyOutcomeEvidence.organization_id == actor.organization_id,
            JourneyStageVersion.organization_id == actor.organization_id,
            Evaluation.organization_id == actor.organization_id,
            Evaluation.decision == Decision.PASS,
        )
        .order_by(JourneyStageVersion.position)
    ).all()
    completed_stages, total_stages = session.execute(
        select(
            func.sum(
                case((Assignment.status == AssignmentStatus.COMPLETED, 1), else_=0)
            ),
            func.count(Assignment.id),
        ).where(
            Assignment.organization_id == actor.organization_id,
            Assignment.enrollment_id == outcome.enrollment_id,
            Assignment.journey_stage_version_id.is_not(None),
        )
    ).one()
    completed_count = int(completed_stages or 0)
    total_count = int(total_stages or 0)
    if total_count == 0:
        # Historical single-task Alpha outcomes predate JourneyStageVersion.
        # Preserve their result contract without pretending they completed V3.
        completed_count = 1
        total_count = 1
    elif completed_count != total_count:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "最终结果缺少完整旅程证据。")
    review_request = (
        session.scalar(
            select(NextTrainingStageReviewRequest).where(
                NextTrainingStageReviewRequest.organization_id
                == actor.organization_id,
                NextTrainingStageReviewRequest.next_training_stage_decision_id
                == next_stage_decision.id,
                NextTrainingStageReviewRequest.requester_user_id == actor.id,
            )
        )
        if next_stage_decision is not None
        else None
    )
    next_stage_out = (
        ResultNextTrainingStageOut(
            status="PENDING_HUMAN_DECISION",
            decision_id=None,
            decision=None,
            decision_reason=None,
            signed_by=None,
            signed_at=None,
            decision_evidence_ref=None,
            review_request_status="NOT_AVAILABLE_UNTIL_DECISION",
            can_request_review=False,
        )
        if next_stage_decision is None
        else ResultNextTrainingStageOut(
            status="RECORDED",
            decision_id=next_stage_decision.id,
            decision=next_stage_decision.decision.value,
            decision_reason=next_stage_decision.decision_reason,
            signed_by=next_stage_decision.decided_by_user_id,
            signed_at=next_stage_decision.decided_at,
            decision_evidence_ref=next_stage_decision.decision_evidence_ref,
            review_request_status=(
                "NOT_APPLICABLE"
                if next_stage_decision.decision == NextTrainingStageDecisionValue.READY
                else "RECEIVED"
                if review_request is not None
                else "AVAILABLE"
            ),
            can_request_review=(
                next_stage_decision.decision
                in {
                    NextTrainingStageDecisionValue.DEFER,
                    NextTrainingStageDecisionValue.NOT_READY,
                }
                and review_request is None
            ),
        )
    )
    return envelope(
        request,
        ResultOut(
            outcome_id=outcome.id,
            decision="PASS",
            status=outcome.status,
            summary=outcome.summary,
            learning_completion=ResultLearningCompletionOut(
                completed_stages=completed_count,
                total_stages=total_count,
            ),
            reviewer_conclusion=ResultReviewerConclusionOut(
                reviewer_id=evaluation.reviewer_id,
                reviewer_display_name=reviewer.display_name,
                submission_version_id=evaluation.submission_version_id,
                overall_feedback=evaluation.feedback,
                ai_use=evaluation.ai_use,
                concluded_at=evaluation.created_at,
            ),
            next_training_stage=next_stage_out,
            evaluation=ResultEvaluationOut(
                id=evaluation.id,
                reviewer_id=evaluation.reviewer_id,
                decision="PASS",
                overall_feedback=evaluation.feedback,
                rubric_feedback=rubric_feedback(evaluation),
                ai_use=evaluation.ai_use,
                created_at=evaluation.created_at,
            ),
            journey_evaluations=[
                JourneyResultEvaluationOut(
                    id=journey_evaluation.id,
                    reviewer_id=journey_evaluation.reviewer_id,
                    decision="PASS",
                    overall_feedback=journey_evaluation.feedback,
                    rubric_feedback=rubric_feedback(journey_evaluation, task),
                    ai_use=journey_evaluation.ai_use,
                    created_at=journey_evaluation.created_at,
                    stage_key=stage.stable_key,
                    stage_title=stage.title,
                )
                for stage, journey_evaluation, task in formal_rows
            ],
            handoff=HandoffOut(
                id=handoff.id,
                status=handoff.status.value,
                owner_user_id=handoff.owner_user_id,
                owner_display_name=owner.display_name,
                title=handoff.title,
                next_step_code="CONFIRM_HANDOFF",
                next_step_title=handoff.next_step_title,
                instructions=handoff.instructions,
                created_at=handoff.created_at,
            ),
            notification=notification_out(
                delivery, external_confirmed=receipt is not None
            ),
            ai_summary=AiSummaryOut(
                message="P0 未启用 AI 摘要；本页直接展示主管的最终人工评价。"
            ),
            created_at=outcome.created_at,
        ),
    )


def encode_cursor(item: TimelineItemOut) -> str:
    payload = json.dumps(
        [item.occurred_at.isoformat(), item.item_id], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode())
        value = json.loads(raw)
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError
        occurred_at = datetime.fromisoformat(str(value[0]))
        item_id = str(value[1])
        if occurred_at.tzinfo is None or not item_id or len(item_id) > 160:
            raise ValueError
        return occurred_at, item_id
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ApiError(400, "INVALID_REQUEST", "时间线游标无效。") from exc


def timeline_item(
    *,
    item_id: str,
    event_type: str,
    title: str,
    occurred_at: datetime,
    object_type: str,
    object_id: uuid.UUID,
    details: dict[str, str | int | bool | None],
) -> TimelineItemOut:
    return TimelineItemOut(
        item_id=item_id,
        event_type=event_type,
        title=title,
        occurred_at=occurred_at,
        object_type=object_type,
        object_id=object_id,
        details=details,
    )


def learner_timeline(
    session: Session,
    actor: Actor,
    enrollment_id: uuid.UUID | None = None,
) -> list[TimelineItemOut]:
    items: list[TimelineItemOut] = []
    enrollment_scope = (
        (Enrollment.id == enrollment_id,) if enrollment_id is not None else ()
    )
    submission_rows = session.execute(
        select(SubmissionVersion, Submission, Assignment, Enrollment, TaskVersion)
        .join(Submission, Submission.id == SubmissionVersion.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
        .where(
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            Assignment.organization_id == actor.organization_id,
            Submission.organization_id == actor.organization_id,
            TaskVersion.organization_id == actor.organization_id,
            *enrollment_scope,
        )
    ).all()
    for version, _submission, assignment, _enrollment, task in submission_rows:
        items.append(
            timeline_item(
                item_id=f"submission:{version.id}",
                event_type="SUBMISSION_VERSION_CREATED",
                title=f"提交版本 {version.version_no} 已创建",
                occurred_at=version.created_at,
                object_type="submission_version",
                object_id=version.id,
                details={
                    "assignment_id": str(assignment.id),
                    "version_no": version.version_no,
                    "task_title": task.title,
                },
            )
        )

    review_rows = session.execute(
        select(Review, Evaluation, SubmissionVersion, Assignment, Enrollment)
        .join(Assignment, Assignment.id == Review.assignment_id)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(SubmissionVersion, SubmissionVersion.id == Review.submission_version_id)
        .outerjoin(Evaluation, Evaluation.review_id == Review.id)
        .where(
            Review.organization_id == actor.organization_id,
            Assignment.organization_id == actor.organization_id,
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            *enrollment_scope,
        )
    ).all()
    for review, evaluation, version, _assignment, _enrollment in review_rows:
        items.append(
            timeline_item(
                item_id=f"review:{review.id}:assigned",
                event_type="REVIEW_ASSIGNED",
                title="评审已分配",
                occurred_at=review.assigned_at,
                object_type="review",
                object_id=review.id,
                details={"submission_version_no": version.version_no},
            )
        )
        if review.started_at is not None:
            items.append(
                timeline_item(
                    item_id=f"review:{review.id}:started",
                    event_type="REVIEW_STARTED",
                    title="主管已开始评审",
                    occurred_at=review.started_at,
                    object_type="review",
                    object_id=review.id,
                    details={"submission_version_no": version.version_no},
                )
            )
        if evaluation is not None:
            items.append(
                timeline_item(
                    item_id=f"evaluation:{evaluation.id}",
                    event_type="EVALUATION_FINALIZED",
                    title="主管最终评价已定稿",
                    occurred_at=evaluation.created_at,
                    object_type="evaluation",
                    object_id=evaluation.id,
                    details={"decision": evaluation.decision.value},
                )
            )

    outcome_rows = session.execute(
        select(Outcome, Handoff, Enrollment)
        .join(Enrollment, Enrollment.id == Outcome.enrollment_id)
        .join(Handoff, Handoff.outcome_id == Outcome.id)
        .where(
            Outcome.organization_id == actor.organization_id,
            Outcome.learner_id == actor.id,
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            Handoff.organization_id == actor.organization_id,
            *enrollment_scope,
        )
    ).all()
    for outcome, handoff, _enrollment in outcome_rows:
        items.extend(
            [
                timeline_item(
                    item_id=f"outcome:{outcome.id}",
                    event_type="OUTCOME_CREATED",
                    title="最终结果已生成",
                    occurred_at=outcome.created_at,
                    object_type="outcome",
                    object_id=outcome.id,
                    details={"status": outcome.status},
                ),
                timeline_item(
                    item_id=f"handoff:{handoff.id}",
                    event_type="HANDOFF_READY",
                    title="唯一交接步骤已准备",
                    occurred_at=handoff.created_at,
                    object_type="handoff",
                    object_id=handoff.id,
                    details={"status": handoff.status.value},
                ),
            ]
        )

    notification_rows = session.execute(
        select(OutboxEvent, NotificationDelivery, Outcome)
        .join(NotificationDelivery, NotificationDelivery.event_id == OutboxEvent.id)
        .join(Outcome, Outcome.id == NotificationDelivery.outcome_id)
        .where(
            OutboxEvent.event_type == "notification.requested.v1",
            OutboxEvent.organization_id == actor.organization_id,
            OutboxEvent.owner_id == actor.id,
            NotificationDelivery.organization_id == actor.organization_id,
            NotificationDelivery.recipient_user_id == actor.id,
            Outcome.organization_id == actor.organization_id,
            Outcome.learner_id == actor.id,
            *((Outcome.enrollment_id == enrollment_id,) if enrollment_id is not None else ()),
        )
    ).all()
    delivery_ids: list[uuid.UUID] = []
    delivery_channels = {
        delivery.id: delivery.channel for _event, delivery, _outcome in notification_rows
    }
    receipt_delivery_ids = set(
        session.scalars(
            select(ExternalNotificationReceipt.delivery_id).where(
                ExternalNotificationReceipt.delivery_id.in_(
                    [delivery.id for _event, delivery, _outcome in notification_rows]
                )
            )
        ).all()
    ) if notification_rows else set()
    for event, delivery, _outcome in notification_rows:
        delivery_ids.append(delivery.id)
        items.append(
            timeline_item(
                item_id=f"notification:{event.id}:requested",
                event_type="NOTIFICATION_REQUESTED",
                title="通知任务已创建",
                occurred_at=event.occurred_at,
                object_type="notification_delivery",
                object_id=delivery.id,
                details={
                    "channel": delivery.channel.value,
                    "template_version": delivery.template_version,
                    "external_delivery_confirmed": delivery.id in receipt_delivery_ids,
                },
            )
        )
    if delivery_ids:
        attempts = session.scalars(
            select(NotificationAttempt)
            .where(NotificationAttempt.delivery_id.in_(delivery_ids))
            .order_by(NotificationAttempt.attempted_at, NotificationAttempt.id)
        ).all()
        for attempt in attempts:
            channel = delivery_channels[attempt.delivery_id]
            items.append(
                timeline_item(
                    item_id=f"notification-attempt:{attempt.id}",
                    event_type=f"NOTIFICATION_{attempt.status.value}",
                    title=(
                        (
                            "本地测试通知已处理"
                            if channel == NotificationChannel.LOCAL_TEST
                            else "飞书通知已被服务接受"
                        )
                        if attempt.status.value == "DELIVERED"
                        else "通知尝试未成功"
                    ),
                    occurred_at=attempt.attempted_at,
                    object_type="notification_delivery",
                    object_id=attempt.delivery_id,
                    details={
                        "attempt_number": attempt.attempt_number,
                        "channel": channel.value,
                        "result": attempt.status.value,
                        "error_code": attempt.error_code,
                        "external_delivery_confirmed": (
                            attempt.delivery_id in receipt_delivery_ids
                        ),
                    },
                )
            )
    return sorted(items, key=lambda item: (item.occurred_at, item.item_id))


@router.get("/me/timeline", response_model=TimelineResponse)
def timeline(
    request: Request,
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    enrollment_id: uuid.UUID | None = None,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    if enrollment_id is not None and session.scalar(
        select(Enrollment.id).where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
        )
    ) is None:
        raise ApiError(404, "NOT_FOUND", "找不到当前账号可访问的模块加入记录。")
    items = learner_timeline(session, actor, enrollment_id)
    if cursor is not None:
        cursor_key = decode_cursor(cursor)
        items = [
            item
            for item in items
            if (item.occurred_at, item.item_id) > cursor_key
        ]
    page = items[:limit]
    next_cursor = encode_cursor(page[-1]) if len(items) > limit and page else None
    return envelope(request, TimelineOut(items=page, next_cursor=next_cursor))
