"""Construction V1 formal-assignment transition contract.

The database keeps ``COMPLETED`` for backward compatibility. Product/API
surfaces must expose that formal terminal state as ``PASSED``.
"""

from __future__ import annotations

import enum
import uuid

from journey_api.models import AssignmentStatus


class FormalAssignmentTransitionError(ValueError):
    pass


class WorkflowActorKind(str, enum.Enum):
    LEARNER = "LEARNER"
    ASSIGNED_REVIEWER = "ASSIGNED_REVIEWER"
    MODULE_OPERATOR = "MODULE_OPERATOR"
    AI = "AI"


class FormalAssignmentEvent(str, enum.Enum):
    START = "START"
    SUBMIT = "SUBMIT"
    START_REVIEW = "START_REVIEW"
    REQUEST_REVISION = "REQUEST_REVISION"
    RESUBMIT = "RESUBMIT"
    PASS = "PASS"
    CANCEL = "CANCEL"


_TRANSITIONS = {
    (AssignmentStatus.AVAILABLE, FormalAssignmentEvent.START): (
        AssignmentStatus.IN_PROGRESS,
        WorkflowActorKind.LEARNER,
    ),
    (AssignmentStatus.IN_PROGRESS, FormalAssignmentEvent.SUBMIT): (
        AssignmentStatus.SUBMITTED,
        WorkflowActorKind.LEARNER,
    ),
    (AssignmentStatus.SUBMITTED, FormalAssignmentEvent.START_REVIEW): (
        AssignmentStatus.IN_REVIEW,
        WorkflowActorKind.ASSIGNED_REVIEWER,
    ),
    (AssignmentStatus.IN_REVIEW, FormalAssignmentEvent.REQUEST_REVISION): (
        AssignmentStatus.NEEDS_REVISION,
        WorkflowActorKind.ASSIGNED_REVIEWER,
    ),
    (AssignmentStatus.NEEDS_REVISION, FormalAssignmentEvent.RESUBMIT): (
        AssignmentStatus.SUBMITTED,
        WorkflowActorKind.LEARNER,
    ),
    (AssignmentStatus.IN_REVIEW, FormalAssignmentEvent.PASS): (
        AssignmentStatus.COMPLETED,
        WorkflowActorKind.ASSIGNED_REVIEWER,
    ),
    (AssignmentStatus.AVAILABLE, FormalAssignmentEvent.CANCEL): (
        AssignmentStatus.CANCELLED,
        WorkflowActorKind.MODULE_OPERATOR,
    ),
    (AssignmentStatus.IN_PROGRESS, FormalAssignmentEvent.CANCEL): (
        AssignmentStatus.CANCELLED,
        WorkflowActorKind.MODULE_OPERATOR,
    ),
}


def public_assignment_status(
    status: AssignmentStatus, *, formal: bool = True
) -> str:
    """Return the single Construction V1 public status language."""
    if formal and status is AssignmentStatus.COMPLETED:
        return "PASSED"
    return status.value


def transition_formal_assignment(
    *,
    current: AssignmentStatus,
    event: FormalAssignmentEvent,
    actor_kind: WorkflowActorKind,
    actor_id: uuid.UUID,
    learner_id: uuid.UUID,
    assigned_reviewer_id: uuid.UUID,
    fixed_submission_version: bool = False,
    new_submission_version: bool = False,
    rubric_complete: bool = False,
    reason: str | None = None,
) -> AssignmentStatus:
    """Validate one formal assignment transition without mutating a row."""
    if actor_kind is WorkflowActorKind.AI:
        raise FormalAssignmentTransitionError(
            "AI actor cannot mutate a formal Assignment"
        )
    transition = _TRANSITIONS.get((current, event))
    if transition is None:
        raise FormalAssignmentTransitionError(
            f"event {event.value} is not allowed from {current.value}"
        )
    target, required_actor = transition
    if actor_kind is not required_actor:
        raise FormalAssignmentTransitionError(
            f"event {event.value} requires {required_actor.value}"
        )
    if actor_kind is WorkflowActorKind.LEARNER and actor_id != learner_id:
        raise FormalAssignmentTransitionError(
            "Learner can mutate only their own Assignment"
        )
    if actor_kind is WorkflowActorKind.ASSIGNED_REVIEWER:
        if actor_id != assigned_reviewer_id:
            raise FormalAssignmentTransitionError(
                "formal review requires the assigned Reviewer"
            )
        if not fixed_submission_version:
            raise FormalAssignmentTransitionError(
                "formal review requires a fixed SubmissionVersion"
            )
    if event in {FormalAssignmentEvent.SUBMIT, FormalAssignmentEvent.RESUBMIT}:
        if not new_submission_version:
            raise FormalAssignmentTransitionError(
                "submission requires a new SubmissionVersion"
            )
    if event in {
        FormalAssignmentEvent.REQUEST_REVISION,
        FormalAssignmentEvent.PASS,
    }:
        if not rubric_complete:
            raise FormalAssignmentTransitionError(
                "final review requires a complete fixed Rubric"
            )
        if reason is None or not reason.strip():
            raise FormalAssignmentTransitionError(
                "final review requires a human reason"
            )
    if event is FormalAssignmentEvent.CANCEL and (
        reason is None or not reason.strip()
    ):
        raise FormalAssignmentTransitionError(
            "cancellation requires a human reason"
        )
    return target
