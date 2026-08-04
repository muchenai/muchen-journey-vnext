from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Decision,
    Enrollment,
    Evaluation,
    ExternalNotificationReceipt,
    Handoff,
    JourneyOutcomeEvidence,
    JourneyAdmissionDecision,
    JourneyStageVersion,
    NotificationAttempt,
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    Outcome,
    OutboxEvent,
    Review,
    Role,
    Submission,
    SubmissionVersion,
    TaskVersion,
    User,
)
from journey_api.schemas import (
    AiSummaryOut,
    HandoffOut,
    JourneyResultEvaluationOut,
    NotificationDeliveryOut,
    ResultEvaluationOut,
    ResultLearningCompletionOut,
    ResultOperatorAdmissionOut,
    ResultOut,
    ResultReviewerConclusionOut,
    ResultResponse,
    ResultRubricFeedbackOut,
    ResultSystemRecommendationOut,
    TimelineItemOut,
    TimelineOut,
    TimelineResponse,
)


router = APIRouter(prefix="/api/v1")

RUBRIC_TITLES = {
    "problem_clarity": "问题清晰度",
    "evidence_quality": "依据质量",
    "action_feasibility": "行动可执行性",
    "validation_design": "验证设计",
}


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


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


@router.get("/me/result", response_model=ResultResponse)
def result(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    row = session.execute(
        select(
            Outcome,
            Handoff,
            Evaluation,
            User,
            NotificationDelivery,
            ExternalNotificationReceipt,
            JourneyAdmissionDecision,
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
            NotificationDelivery,
            (NotificationDelivery.outcome_id == Outcome.id)
            & (NotificationDelivery.organization_id == Outcome.organization_id)
            & (NotificationDelivery.recipient_user_id == Outcome.learner_id),
        )
        .outerjoin(
            ExternalNotificationReceipt,
            ExternalNotificationReceipt.delivery_id == NotificationDelivery.id,
        )
        .outerjoin(
            JourneyAdmissionDecision,
            (JourneyAdmissionDecision.outcome_id == Outcome.id)
            & (JourneyAdmissionDecision.organization_id == Outcome.organization_id)
            & (JourneyAdmissionDecision.enrollment_id == Outcome.enrollment_id),
        )
        .where(
            Outcome.organization_id == actor.organization_id,
            Outcome.learner_id == actor.id,
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
        )
        .order_by(Outcome.created_at.desc(), Outcome.id.desc())
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "当前还没有最终结果。")
    outcome, handoff, evaluation, owner, delivery, receipt, admission = row
    if evaluation.decision != Decision.PASS:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "最终结果缺少有效的通过结论。")
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
    recommended_decision = None
    if admission is not None:
        recommended_decision = (
            "ADMIT"
            if admission.recommendation_tier in {"A", "B"}
            else "DEFER"
            if admission.recommendation_tier == "C"
            else "NOT_ADMIT"
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
                overall_feedback=evaluation.feedback,
                concluded_at=evaluation.created_at,
            ),
            system_recommendation=ResultSystemRecommendationOut(
                status="RECORDED" if admission is not None else "PENDING_OPERATOR_INPUT",
                recommendation_tier=(
                    admission.recommendation_tier if admission is not None else None
                ),
                recommended_decision=recommended_decision,
            ),
            operator_admission=ResultOperatorAdmissionOut(
                status="DECIDED" if admission is not None else "PENDING",
                decision=admission.decision.value if admission is not None else None,
                decision_reason=(
                    admission.decision_reason if admission is not None else None
                ),
                total_score=admission.total_score if admission is not None else None,
                decided_at=admission.created_at if admission is not None else None,
            ),
            evaluation=ResultEvaluationOut(
                id=evaluation.id,
                reviewer_id=evaluation.reviewer_id,
                decision="PASS",
                overall_feedback=evaluation.feedback,
                rubric_feedback=rubric_feedback(evaluation),
                created_at=evaluation.created_at,
            ),
            journey_evaluations=[
                JourneyResultEvaluationOut(
                    id=journey_evaluation.id,
                    reviewer_id=journey_evaluation.reviewer_id,
                    decision="PASS",
                    overall_feedback=journey_evaluation.feedback,
                    rubric_feedback=rubric_feedback(journey_evaluation, task),
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


def learner_timeline(session: Session, actor: Actor) -> list[TimelineItemOut]:
    items: list[TimelineItemOut] = []
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
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    items = learner_timeline(session, actor)
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
