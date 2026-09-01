from __future__ import annotations

import uuid

import pytest

from journey_api.formal_assignment_workflow import (
    FormalAssignmentEvent,
    FormalAssignmentTransitionError,
    WorkflowActorKind,
    public_assignment_status,
    transition_formal_assignment,
)
from journey_api.models import AssignmentStatus


LEARNER_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
REVIEWER_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")


def transition(
    status: AssignmentStatus,
    event: FormalAssignmentEvent,
    actor: WorkflowActorKind,
    **overrides: object,
) -> AssignmentStatus:
    values: dict[str, object] = {
        "current": status,
        "event": event,
        "actor_kind": actor,
        "actor_id": LEARNER_ID if actor is WorkflowActorKind.LEARNER else REVIEWER_ID,
        "learner_id": LEARNER_ID,
        "assigned_reviewer_id": REVIEWER_ID,
        "fixed_submission_version": True,
        "new_submission_version": True,
        "rubric_complete": True,
        "reason": "固定 Rubric 已逐项填写，证据与结论可核对。",
    }
    values.update(overrides)
    return transition_formal_assignment(**values)  # type: ignore[arg-type]


def test_revision_cycle_reaches_database_completed_and_public_passed() -> None:
    status = transition(
        AssignmentStatus.AVAILABLE,
        FormalAssignmentEvent.START,
        WorkflowActorKind.LEARNER,
    )
    status = transition(
        status, FormalAssignmentEvent.SUBMIT, WorkflowActorKind.LEARNER
    )
    status = transition(
        status,
        FormalAssignmentEvent.START_REVIEW,
        WorkflowActorKind.ASSIGNED_REVIEWER,
    )
    status = transition(
        status,
        FormalAssignmentEvent.REQUEST_REVISION,
        WorkflowActorKind.ASSIGNED_REVIEWER,
    )
    status = transition(
        status, FormalAssignmentEvent.RESUBMIT, WorkflowActorKind.LEARNER
    )
    status = transition(
        status,
        FormalAssignmentEvent.START_REVIEW,
        WorkflowActorKind.ASSIGNED_REVIEWER,
    )
    status = transition(
        status, FormalAssignmentEvent.PASS, WorkflowActorKind.ASSIGNED_REVIEWER
    )

    assert status is AssignmentStatus.COMPLETED
    assert public_assignment_status(status) == "PASSED"


@pytest.mark.parametrize(
    ("status", "event", "actor"),
    [
        (
            AssignmentStatus.AVAILABLE,
            FormalAssignmentEvent.PASS,
            WorkflowActorKind.ASSIGNED_REVIEWER,
        ),
        (
            AssignmentStatus.IN_PROGRESS,
            FormalAssignmentEvent.PASS,
            WorkflowActorKind.ASSIGNED_REVIEWER,
        ),
        (
            AssignmentStatus.SUBMITTED,
            FormalAssignmentEvent.PASS,
            WorkflowActorKind.ASSIGNED_REVIEWER,
        ),
    ],
)
def test_cannot_skip_review(
    status: AssignmentStatus,
    event: FormalAssignmentEvent,
    actor: WorkflowActorKind,
) -> None:
    with pytest.raises(FormalAssignmentTransitionError, match="not allowed"):
        transition(status, event, actor)


def test_ai_cannot_mutate_formal_assignment() -> None:
    with pytest.raises(FormalAssignmentTransitionError, match="AI actor"):
        transition(
            AssignmentStatus.IN_REVIEW,
            FormalAssignmentEvent.PASS,
            WorkflowActorKind.AI,
            actor_id=uuid.uuid4(),
        )


def test_unassigned_reviewer_cannot_review() -> None:
    with pytest.raises(FormalAssignmentTransitionError, match="assigned Reviewer"):
        transition(
            AssignmentStatus.SUBMITTED,
            FormalAssignmentEvent.START_REVIEW,
            WorkflowActorKind.ASSIGNED_REVIEWER,
            actor_id=uuid.uuid4(),
        )


def test_pass_requires_fixed_version_complete_rubric_and_reason() -> None:
    for override in (
        {"fixed_submission_version": False},
        {"rubric_complete": False},
        {"reason": ""},
    ):
        with pytest.raises(FormalAssignmentTransitionError):
            transition(
                AssignmentStatus.IN_REVIEW,
                FormalAssignmentEvent.PASS,
                WorkflowActorKind.ASSIGNED_REVIEWER,
                **override,
            )


def test_resubmission_requires_a_new_immutable_version() -> None:
    with pytest.raises(FormalAssignmentTransitionError, match="new SubmissionVersion"):
        transition(
            AssignmentStatus.NEEDS_REVISION,
            FormalAssignmentEvent.RESUBMIT,
            WorkflowActorKind.LEARNER,
            new_submission_version=False,
        )


def test_learner_cannot_start_another_person_assignment() -> None:
    with pytest.raises(FormalAssignmentTransitionError, match="own Assignment"):
        transition(
            AssignmentStatus.AVAILABLE,
            FormalAssignmentEvent.START,
            WorkflowActorKind.LEARNER,
            actor_id=uuid.uuid4(),
        )


def test_operator_cancel_requires_reason_and_cannot_erase_revision_lineage() -> None:
    with pytest.raises(FormalAssignmentTransitionError, match="human reason"):
        transition(
            AssignmentStatus.IN_PROGRESS,
            FormalAssignmentEvent.CANCEL,
            WorkflowActorKind.MODULE_OPERATOR,
            reason="",
        )
    with pytest.raises(FormalAssignmentTransitionError, match="not allowed"):
        transition(
            AssignmentStatus.NEEDS_REVISION,
            FormalAssignmentEvent.CANCEL,
            WorkflowActorKind.MODULE_OPERATOR,
        )
