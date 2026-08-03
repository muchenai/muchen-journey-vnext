from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from journey_api.config import get_settings
from journey_api.models import (
    Assignment,
    Enrollment,
    Evaluation,
    Handoff,
    HandoffStatus,
    NotificationChannel,
    NotificationDelivery,
    NotificationStatus,
    Outcome,
    JourneyOutcomeEvidence,
    OutboxEvent,
    OutboxStatus,
)

if TYPE_CHECKING:
    from journey_api.journey_service import FormalEvaluationEvidence


def add_scoped_outbox_event(
    session: Session,
    *,
    event_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    actor_id: uuid.UUID,
    request_id: str,
    dedupe_key: str,
    payload: dict[str, object],
    occurred_at: datetime,
) -> OutboxEvent:
    event = OutboxEvent(
        id=event_id,
        organization_id=organization_id,
        owner_id=owner_id,
        actor_id=actor_id,
        request_id=request_id,
        payload_version=1,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        status=OutboxStatus.PENDING,
        attempt_count=0,
        next_attempt_at=occurred_at,
        dedupe_key=dedupe_key,
        occurred_at=occurred_at,
    )
    session.add(event)
    return event


def create_pass_outcome_bundle(
    session: Session,
    *,
    enrollment: Enrollment,
    assignment: Assignment,
    evaluation: Evaluation,
    reviewer_id: uuid.UUID,
    request_id: str,
    formal_evidence: list[FormalEvaluationEvidence] | None = None,
) -> tuple[Outcome, Handoff, NotificationDelivery]:
    """Create the result, one next step, and its notification request atomically."""

    now = datetime.now(UTC)
    is_formal_journey = bool(formal_evidence)
    outcome = Outcome(
        id=uuid.uuid4(),
        organization_id=enrollment.organization_id,
        learner_id=enrollment.learner_id,
        assignment_id=assignment.id,
        enrollment_id=enrollment.id,
        source_evaluation_id=evaluation.id,
        status="HANDOFF_READY",
        summary=(
            "四个宝藏与三项能力评测已完成，三份独立人工评价构成最终结果。"
            if is_formal_journey
            else "任务已通过并形成最终人工评价，探索营交接已准备。"
        ),
        created_at=now,
    )
    handoff = Handoff(
        id=uuid.uuid4(),
        organization_id=enrollment.organization_id,
        enrollment_id=enrollment.id,
        outcome_id=outcome.id,
        source_evaluation_id=evaluation.id,
        owner_user_id=reviewer_id,
        status=HandoffStatus.READY,
        title="探索营完成，交接已准备" if is_formal_journey else "探索营交接已准备",
        next_step_code="CONFIRM_HANDOFF",
        next_step_title="与交接责任人确认下一步",
        instructions=(
            "查看三项能力评测反馈，并与交接责任人确认后续安排。"
            if is_formal_journey
            else "查看主管的结构化反馈，并与交接责任人确认后续安排。"
        ),
        created_at=now,
    )
    # The fixed-scope composite FKs intentionally have no ORM relationships, so
    # keep explicit dependency boundaries while combining independent children:
    # Evaluation/Outcome first, then Handoff and Outbox in one flush. This retains
    # immediate constraint checks and removes one database round trip.
    session.add(outcome)
    session.flush()
    if formal_evidence:
        session.add_all(
            [
                JourneyOutcomeEvidence(
                    outcome_id=outcome.id,
                    evaluation_id=item.evaluation.id,
                    journey_stage_version_id=item.stage.id,
                    organization_id=enrollment.organization_id,
                    enrollment_id=enrollment.id,
                )
                for item in formal_evidence
            ]
        )
    session.add(handoff)

    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="outcome.created.v1",
        aggregate_type="outcome",
        aggregate_id=outcome.id,
        organization_id=enrollment.organization_id,
        owner_id=enrollment.learner_id,
        actor_id=reviewer_id,
        request_id=request_id,
        dedupe_key=f"outcome.created:{outcome.id}",
        payload={"outcome_id": str(outcome.id)},
        occurred_at=now,
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="handoff.ready.v1",
        aggregate_type="handoff",
        aggregate_id=handoff.id,
        organization_id=enrollment.organization_id,
        owner_id=enrollment.learner_id,
        actor_id=reviewer_id,
        request_id=request_id,
        dedupe_key=f"handoff.ready:{handoff.id}",
        payload={"handoff_id": str(handoff.id), "outcome_id": str(outcome.id)},
        occurred_at=now,
    )

    event_id = uuid.uuid4()
    template_version = "outcome-ready.v1"
    notification_channel = NotificationChannel(get_settings().notification_channel)
    dedupe_key = (
        f"notification:{outcome.id}:{enrollment.learner_id}:"
        f"{notification_channel.value}:{template_version}"
    )
    notification_event = add_scoped_outbox_event(
        session,
        event_id=event_id,
        event_type="notification.requested.v1",
        aggregate_type="outcome",
        aggregate_id=outcome.id,
        organization_id=enrollment.organization_id,
        owner_id=enrollment.learner_id,
        actor_id=reviewer_id,
        request_id=request_id,
        dedupe_key=dedupe_key,
        payload={
            "outcome_id": str(outcome.id),
            "template_version": template_version,
        },
        occurred_at=now,
    )
    session.flush()
    delivery = NotificationDelivery(
        id=uuid.uuid4(),
        organization_id=enrollment.organization_id,
        event_id=notification_event.id,
        outcome_id=outcome.id,
        recipient_user_id=enrollment.learner_id,
        channel=notification_channel,
        template_version=template_version,
        status=NotificationStatus.PENDING,
        attempt_count=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(delivery)
    return outcome, handoff, delivery
