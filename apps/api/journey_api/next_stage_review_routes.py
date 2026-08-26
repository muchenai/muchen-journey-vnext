from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.models import (
    AuditEntry,
    NextTrainingStageDecision,
    NextTrainingStageDecisionValue,
    NextTrainingStageReviewAssignment,
    NextTrainingStageReviewRequest,
    NextTrainingStageReviewResolution,
    NextTrainingStageReviewResolutionStatus,
    Role,
    RoleAssignment,
    User,
)
from journey_api.outcome_service import add_scoped_outbox_event
from journey_api.schemas import (
    NextTrainingStageReviewAssignmentCommand,
    NextTrainingStageReviewAssignmentOut,
    NextTrainingStageReviewAssignmentResponse,
    NextTrainingStageReviewRequestListOut,
    NextTrainingStageReviewRequestListResponse,
    NextTrainingStageReviewRequestOut,
    NextTrainingStageReviewRequestResponse,
    NextTrainingStageReviewResolutionCommand,
    NextTrainingStageReviewResolutionOut,
    NextTrainingStageReviewResolutionResponse,
)


router = APIRouter(prefix="/api/v1")


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def _lineage(
    session: Session, item: NextTrainingStageReviewRequest
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
    replacement_id = session.scalar(
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
        replacement_decision_id=replacement_id,
    )


def _assignment_out(
    item: NextTrainingStageReviewAssignment, *, replay: bool = False
) -> NextTrainingStageReviewAssignmentOut:
    return NextTrainingStageReviewAssignmentOut(
        id=item.id,
        review_request_id=item.review_request_id,
        source_decision_id=item.source_decision_id,
        person_id=item.person_id,
        reviewer_user_id=item.reviewer_user_id,
        assigned_by_user_id=item.assigned_by_user_id,
        assignment_reason=item.assignment_reason,
        assignment_evidence_ref=item.assignment_evidence_ref,
        assigned_at=item.assigned_at,
        idempotency_replay=replay,
    )


@router.get(
    "/ops/next-training-stage-review-requests",
    response_model=NextTrainingStageReviewRequestListResponse,
)
def operator_review_requests(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    items = list(
        session.scalars(
            select(NextTrainingStageReviewRequest)
            .where(
                NextTrainingStageReviewRequest.organization_id
                == actor.organization_id
            )
            .order_by(NextTrainingStageReviewRequest.requested_at)
        ).all()
    )
    return envelope(
        request,
        NextTrainingStageReviewRequestListOut(
            items=[_lineage(session, item) for item in items]
        ),
    )


@router.post(
    "/ops/next-training-stage-review-requests/{review_request_id}/assignment",
    response_model=NextTrainingStageReviewAssignmentResponse,
)
def assign_independent_reviewer(
    review_request_id: uuid.UUID,
    command: NextTrainingStageReviewAssignmentCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {
        **command.model_dump(mode="json"),
        "review_request_id": str(review_request_id),
    }
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="next-training-stage-review.assign",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        replay["idempotency_replay"] = True
        return envelope(
            request,
            NextTrainingStageReviewAssignmentOut(**replay),
        )

    row = session.execute(
        select(NextTrainingStageReviewRequest, NextTrainingStageDecision)
        .join(
            NextTrainingStageDecision,
            NextTrainingStageDecision.id
            == NextTrainingStageReviewRequest.next_training_stage_decision_id,
        )
        .where(
            NextTrainingStageReviewRequest.id == review_request_id,
            NextTrainingStageReviewRequest.organization_id == actor.organization_id,
        )
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "复核请求不存在或不在当前组织。")
    review_request, source_decision = row
    if session.scalar(
        select(NextTrainingStageReviewAssignment.id).where(
            NextTrainingStageReviewAssignment.review_request_id == review_request.id
        )
    ):
        raise ApiError(409, "INVALID_STATE_TRANSITION", "复核请求已经分配。")
    reviewer = session.scalar(
        select(User).where(
            User.id == command.reviewer_user_id,
            User.organization_id == actor.organization_id,
        )
    )
    if reviewer is None:
        raise ApiError(404, "NOT_FOUND", "指定复核人不存在或不在当前组织。")
    if session.scalar(
        select(RoleAssignment.id).where(
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.user_id == command.reviewer_user_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    ) is None:
        raise ApiError(409, "REVIEWER_NOT_ELIGIBLE", "指定人员没有有效 Reviewer 角色。")
    if command.reviewer_user_id in {
        review_request.requester_user_id,
        source_decision.decided_by_user_id,
        actor.id,
    }:
        raise ApiError(409, "REVIEWER_NOT_INDEPENDENT", "复核人必须独立于本人、原签署人和分配人。")
    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "数据库时间不可用。")
    item = NextTrainingStageReviewAssignment(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        review_request_id=review_request.id,
        source_decision_id=source_decision.id,
        person_id=review_request.requester_user_id,
        reviewer_user_id=command.reviewer_user_id,
        assigned_by_user_id=actor.id,
        assignment_reason=command.assignment_reason.strip(),
        assignment_evidence_ref=command.assignment_evidence_ref.strip(),
        assigned_at=db_now,
        created_at=db_now,
    )
    session.add(item)
    session.flush()
    response = _assignment_out(item)
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action="next_training_stage.review_assigned",
            resource_type="next_training_stage_review_request",
            resource_id=review_request.id,
            result="IN_REVIEW",
            request_id=request.state.request_id,
            details={
                "assignment_id": str(item.id),
                "reviewer_user_id": str(item.reviewer_user_id),
            },
            occurred_at=db_now,
        )
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="next_training_stage.review_assigned.v1",
        aggregate_type="next_training_stage_review_request",
        aggregate_id=review_request.id,
        organization_id=actor.organization_id,
        owner_id=item.reviewer_user_id,
        actor_id=actor.id,
        request_id=request.state.request_id,
        dedupe_key=f"next-training-stage-review-assignment:{item.id}",
        payload={
            "review_request_id": str(review_request.id),
            "assignment_id": str(item.id),
        },
        occurred_at=db_now,
    )
    store_result(
        session,
        actor_id=actor.id,
        command="next-training-stage-review.assign",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.get(
    "/reviews/next-training-stage-review-requests",
    response_model=NextTrainingStageReviewRequestListResponse,
)
def reviewer_review_requests(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.REVIEWER)
    items = list(
        session.scalars(
            select(NextTrainingStageReviewRequest)
            .join(
                NextTrainingStageReviewAssignment,
                NextTrainingStageReviewAssignment.review_request_id
                == NextTrainingStageReviewRequest.id,
            )
            .where(
                NextTrainingStageReviewRequest.organization_id
                == actor.organization_id,
                NextTrainingStageReviewAssignment.reviewer_user_id == actor.id,
            )
            .order_by(NextTrainingStageReviewAssignment.assigned_at)
        ).all()
    )
    return envelope(
        request,
        NextTrainingStageReviewRequestListOut(
            items=[_lineage(session, item) for item in items]
        ),
    )


@router.post(
    "/reviews/next-training-stage-review-requests/{review_request_id}/resolution",
    response_model=NextTrainingStageReviewResolutionResponse,
)
def resolve_independent_review(
    review_request_id: uuid.UUID,
    command: NextTrainingStageReviewResolutionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.REVIEWER)
    payload = {
        **command.model_dump(mode="json"),
        "review_request_id": str(review_request_id),
    }
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="next-training-stage-review.resolve",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        replay["idempotency_replay"] = True
        return envelope(
            request,
            NextTrainingStageReviewResolutionOut(**replay),
        )

    review_request = session.scalar(
        select(NextTrainingStageReviewRequest)
        .where(
            NextTrainingStageReviewRequest.id == review_request_id,
            NextTrainingStageReviewRequest.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if review_request is None:
        raise ApiError(404, "NOT_FOUND", "复核请求不存在或不在当前组织。")
    assignment = session.scalar(
        select(NextTrainingStageReviewAssignment)
        .where(
            NextTrainingStageReviewAssignment.review_request_id == review_request.id,
            NextTrainingStageReviewAssignment.organization_id == actor.organization_id,
            NextTrainingStageReviewAssignment.reviewer_user_id == actor.id,
        )
        .with_for_update()
    )
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "没有可由当前复核人处理的请求。")
    source_decision = session.scalar(
        select(NextTrainingStageDecision)
        .where(
            NextTrainingStageDecision.id == assignment.source_decision_id,
            NextTrainingStageDecision.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if source_decision is None:
        raise ApiError(409, "LINEAGE_INVALID", "原决定谱系不可用。")
    if session.scalar(
        select(NextTrainingStageReviewResolution.id).where(
            NextTrainingStageReviewResolution.review_request_id == review_request.id
        )
    ):
        raise ApiError(409, "INVALID_STATE_TRANSITION", "复核请求已经形成结论。")
    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now is None:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", "数据库时间不可用。")
    resolution = NextTrainingStageReviewResolution(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        review_request_id=review_request.id,
        assignment_id=assignment.id,
        reviewer_user_id=actor.id,
        status=NextTrainingStageReviewResolutionStatus(command.status),
        resolution_reason=command.resolution_reason.strip(),
        evidence_refs=command.evidence_refs,
        resolved_at=db_now,
        created_at=db_now,
    )
    session.add(resolution)
    session.flush()
    replacement = None
    if command.replacement_decision is not None:
        replacement_command = command.replacement_decision
        replacement = NextTrainingStageDecision(
            id=uuid.uuid4(),
            organization_id=source_decision.organization_id,
            handoff_id=source_decision.handoff_id,
            outcome_id=source_decision.outcome_id,
            person_id=source_decision.person_id,
            decision_scope="NEXT_TRAINING_STAGE",
            decision=NextTrainingStageDecisionValue(replacement_command.decision),
            decision_reason=replacement_command.decision_reason.strip(),
            decided_by_user_id=actor.id,
            decision_evidence_ref=replacement_command.decision_evidence_ref.strip(),
            decision_evidence_sha256=replacement_command.decision_evidence_sha256,
            decided_at=db_now,
            revision=source_decision.revision + 1,
            supersedes_decision_id=source_decision.id,
            source_review_request_id=review_request.id,
            created_at=db_now,
        )
        session.add(replacement)
        session.flush()
    response = NextTrainingStageReviewResolutionOut(
        id=resolution.id,
        review_request_id=review_request.id,
        assignment_id=assignment.id,
        reviewer_user_id=actor.id,
        status=resolution.status.value,
        resolution_reason=resolution.resolution_reason,
        evidence_refs=list(resolution.evidence_refs),
        resolved_at=resolution.resolved_at,
        replacement_decision_id=replacement.id if replacement is not None else None,
    )
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action="next_training_stage.review_resolved",
            resource_type="next_training_stage_review_request",
            resource_id=review_request.id,
            result=resolution.status.value,
            request_id=request.state.request_id,
            details={
                "resolution_id": str(resolution.id),
                "replacement_decision_id": (
                    str(replacement.id) if replacement is not None else None
                ),
            },
            occurred_at=db_now,
        )
    )
    add_scoped_outbox_event(
        session,
        event_id=uuid.uuid4(),
        event_type="next_training_stage.review_resolved.v1",
        aggregate_type="next_training_stage_review_request",
        aggregate_id=review_request.id,
        organization_id=actor.organization_id,
        owner_id=review_request.requester_user_id,
        actor_id=actor.id,
        request_id=request.state.request_id,
        dedupe_key=f"next-training-stage-review-resolution:{resolution.id}",
        payload={
            "review_request_id": str(review_request.id),
            "status": resolution.status.value,
            "replacement_decision_id": (
                str(replacement.id) if replacement is not None else None
            ),
        },
        occurred_at=db_now,
    )
    store_result(
        session,
        actor_id=actor.id,
        command="next-training-stage-review.resolve",
        key=idempotency_key,
        payload=payload,
        response=response.model_dump(mode="json"),
    )
    session.commit()
    return envelope(request, response)


@router.get(
    "/me/next-training-stage-review-requests/{review_request_id}",
    response_model=NextTrainingStageReviewRequestResponse,
)
def person_review_lineage(
    review_request_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    item = session.scalar(
        select(NextTrainingStageReviewRequest).where(
            NextTrainingStageReviewRequest.id == review_request_id,
            NextTrainingStageReviewRequest.organization_id == actor.organization_id,
            NextTrainingStageReviewRequest.requester_user_id == actor.id,
        )
    )
    if item is None:
        raise ApiError(404, "NOT_FOUND", "复核请求不存在或不属于本人。")
    return envelope(request, _lineage(session, item))
