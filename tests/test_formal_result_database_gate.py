import uuid

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import DBAPIError

import test_reviewer_workbench as reviewer_workbench
from journey_api.db import SessionLocal, engine
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    Outcome,
    Review,
    ReviewStatus,
    SubmissionVersion,
)


def _finalize_review(*, label: str, decision: str) -> dict[str, object]:
    flow = reviewer_workbench.create_submission(label)
    reviewer = reviewer_workbench.client_for(f"gov-001-reviewer-{label}")
    started = reviewer_workbench.assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **reviewer_workbench.REVIEWER_HEADERS,
                "Idempotency-Key": f"gov-001-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    finalized = reviewer_workbench.assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={
                **reviewer_workbench.REVIEWER_HEADERS,
                "Idempotency-Key": f"gov-001-finalize-{uuid.uuid4()}",
            },
            json=reviewer_workbench.finalize_payload(
                started["review_revision"],
                decision=decision,
                needs_work_key=(
                    "evidence_quality" if decision == "REQUEST_REVISION" else None
                ),
                overall_feedback=(
                    "固定实操证据不足，请按 Rubric 补充后提交新的不可变版本。"
                    if decision == "REQUEST_REVISION"
                    else "固定实操提交已由指定 Reviewer 按 Rubric 核验并签署通过。"
                ),
            ),
        )
    )
    return {**flow, "finalized": finalized}


def test_positive_formal_result_reuses_fixed_practice_and_human_gate_facts():
    flow = _finalize_review(
        label=f"gov-001-pass-{uuid.uuid4()}", decision="APPROVE"
    )

    with SessionLocal() as session:
        outcome = session.scalar(
            select(Outcome).where(
                Outcome.source_evaluation_id
                == uuid.UUID(str(flow["finalized"]["evaluation_id"]))
            )
        )
        assert outcome is not None
        evaluation = session.get(Evaluation, outcome.source_evaluation_id)
        assignment = session.get(Assignment, outcome.assignment_id)
        enrollment = session.get(Enrollment, outcome.enrollment_id)
        assert evaluation is not None
        assert assignment is not None
        assert enrollment is not None
        review = session.get(Review, evaluation.review_id)
        submission_version = session.get(
            SubmissionVersion, evaluation.submission_version_id
        )
        assert review is not None
        assert submission_version is not None

        assert evaluation.decision is Decision.PASS
        assert evaluation.created_by == evaluation.reviewer_id
        assert review.status is ReviewStatus.FINALIZED
        assert review.finalized_at is not None
        assert review.reviewer_id == enrollment.reviewer_id
        assert review.reviewer_id != enrollment.learner_id
        assert submission_version.created_by == enrollment.learner_id
        assert assignment.status is AssignmentStatus.COMPLETED
        assert enrollment.status is EnrollmentStatus.COMPLETED


def test_database_rejects_formal_outcome_from_revision_required_evaluation():
    flow = _finalize_review(
        label=f"gov-001-revision-{uuid.uuid4()}",
        decision="REQUEST_REVISION",
    )
    evaluation_id = uuid.UUID(str(flow["finalized"]["evaluation_id"]))

    with SessionLocal() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        assignment = session.get(Assignment, evaluation.assignment_id)
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        assert evaluation.decision is Decision.REVISION_REQUIRED
        assert assignment.status is AssignmentStatus.NEEDS_REVISION
        assert enrollment.status is EnrollmentStatus.ACTIVE

        session.add(
            Outcome(
                id=uuid.uuid4(),
                organization_id=enrollment.organization_id,
                learner_id=enrollment.learner_id,
                assignment_id=assignment.id,
                enrollment_id=enrollment.id,
                source_evaluation_id=evaluation.id,
                status="HANDOFF_READY",
                summary="This synthetic invalid result must be rejected by the database.",
            )
        )
        with pytest.raises(
            DBAPIError,
            match="formal result requires fixed practice evidence and a finalized human PASS gate",
        ):
            session.flush()


@pytest.mark.parametrize(
    "non_formal_source_table",
    [
        "learning_material_completions",
        "incentive_ledger_entries",
    ],
)
def test_non_formal_fact_tables_have_no_direct_outcome_source_path(
    non_formal_source_table: str,
):
    inspector = inspect(engine)
    outcome_targets = {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("outcomes")
    }
    assert outcome_targets == {"enrollments", "evaluations"}
    assert non_formal_source_table not in outcome_targets


def test_database_has_no_second_person_evidence_or_human_gate_fact_table():
    table_names = set(inspect(engine).get_table_names())
    assert "people" not in table_names
    assert "evidence" not in table_names
    assert "human_gates" not in table_names
    assert {
        "users",
        "submission_versions",
        "reviews",
        "evaluations",
        "outcomes",
    }.issubset(table_names)
