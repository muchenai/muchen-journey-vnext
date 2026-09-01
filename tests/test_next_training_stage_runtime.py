import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID
from journey_api.models import (
    Handoff,
    NextTrainingStageDecision,
    NextTrainingStageDecisionValue,
    Outcome,
)
from test_incentive_ledger_runtime import passed_flow


def test_single_task_outcome_cannot_receive_a_next_training_stage_decision():
    _flow, evaluation_id, person_id = passed_flow("next-stage-single-task")
    with SessionLocal() as session:
        outcome = session.scalar(
            select(Outcome).where(Outcome.source_evaluation_id == evaluation_id)
        )
        assert outcome is not None
        handoff = session.scalar(select(Handoff).where(Handoff.outcome_id == outcome.id))
        assert handoff is not None
        organization_id = outcome.organization_id
        outcome_id = outcome.id
        handoff_id = handoff.id
        outcome_created_at = outcome.created_at

    with pytest.raises(DBAPIError, match="exactly three fixed PASS human evaluations"):
        with SessionLocal.begin() as session:
            session.add(
                NextTrainingStageDecision(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    handoff_id=handoff_id,
                    outcome_id=outcome_id,
                    person_id=person_id,
                    decision_scope="NEXT_TRAINING_STAGE",
                    decision=NextTrainingStageDecisionValue.READY,
                    decision_reason="A single task result cannot decide the next stage.",
                    decided_by_user_id=REVIEWER_ID,
                    decision_evidence_ref="tests/invalid-single-task-decision",
                    decision_evidence_sha256="8" * 64,
                    decided_at=outcome_created_at,
                )
            )
            session.flush()


def test_openapi_exposes_review_intake_but_no_decision_mutation_route():
    from journey_api.main import app

    paths = app.openapi()["paths"]
    review_path = (
        "/api/v1/me/next-training-stage-decisions/{decision_id}/review-requests"
    )
    assert set(paths[review_path]) == {"post"}
    assert set(paths["/api/v1/me/next-training-stage-review-requests"]) == {"get"}
    assert set(paths["/api/v1/ops/next-training-stage-review-requests"]) == {"get"}
    assert set(
        paths[
            "/api/v1/ops/next-training-stage-review-requests/{review_request_id}/assignment"
        ]
    ) == {"post"}
    assert set(paths["/api/v1/reviews/next-training-stage-review-requests"]) == {
        "get"
    }
    assert set(
        paths[
            "/api/v1/reviews/next-training-stage-review-requests/{review_request_id}/resolution"
        ]
    ) == {"post"}
    assert set(
        paths["/api/v1/me/next-training-stage-review-requests/{review_request_id}"]
    ) == {"get"}
    assert all(
        "next-training-stage-decisions" not in path or path == review_path
        for path in paths
    )
