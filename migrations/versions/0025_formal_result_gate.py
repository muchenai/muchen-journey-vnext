"""Enforce the deduplicated formal-result basis at the database boundary.

Revision ID: 0025_formal_result_gate
Revises: 0024_module_content_binding
"""

from alembic import op


revision = "0025_formal_result_gate"
down_revision = "0024_module_content_binding"
branch_labels = None
depends_on = None


_FORMAL_BASIS = """
    SELECT 1
    FROM evaluations AS evaluation
    JOIN reviews AS review
      ON review.id = evaluation.review_id
     AND review.organization_id = evaluation.organization_id
     AND review.assignment_id = evaluation.assignment_id
     AND review.submission_id = evaluation.submission_id
     AND review.submission_version_id = evaluation.submission_version_id
     AND review.reviewer_id = evaluation.reviewer_id
    JOIN assignments AS assignment
      ON assignment.id = evaluation.assignment_id
     AND assignment.organization_id = evaluation.organization_id
    JOIN enrollments AS enrollment
      ON enrollment.id = assignment.enrollment_id
     AND enrollment.organization_id = assignment.organization_id
    JOIN submissions AS submission
      ON submission.id = evaluation.submission_id
     AND submission.organization_id = evaluation.organization_id
     AND submission.assignment_id = evaluation.assignment_id
    JOIN submission_versions AS submission_version
      ON submission_version.id = evaluation.submission_version_id
     AND submission_version.submission_id = evaluation.submission_id
    WHERE evaluation.id = TARGET.source_evaluation_id
      AND evaluation.organization_id = TARGET.organization_id
      AND evaluation.assignment_id = TARGET.assignment_id
      AND evaluation.decision = 'PASS'
      AND evaluation.created_by = evaluation.reviewer_id
      AND length(trim(evaluation.feedback)) >= 10
      AND review.status = 'FINALIZED'
      AND review.finalized_at IS NOT NULL
      AND review.reviewer_id = enrollment.reviewer_id
      AND review.reviewer_id <> enrollment.learner_id
      AND assignment.enrollment_id = TARGET.enrollment_id
      AND assignment.status = 'COMPLETED'
      AND enrollment.id = TARGET.enrollment_id
      AND enrollment.learner_id = TARGET.learner_id
      AND enrollment.status = 'COMPLETED'
      AND submission.current_version_no = submission_version.version_no
      AND submission_version.created_by = enrollment.learner_id
      AND length(trim(submission_version.body)) >= 1
"""


def upgrade() -> None:
    # Fail closed before installing the trigger. The release line does not import
    # Legacy records, but a future non-production or production upgrade must not
    # silently bless an already-invalid formal Outcome.
    historical_basis = _FORMAL_BASIS.replace("TARGET.", "outcome.")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM outcomes AS outcome
                WHERE NOT EXISTS ({historical_basis})
            ) THEN
                RAISE EXCEPTION
                    'existing formal result lacks fixed practice evidence or a finalized human PASS gate';
            END IF;
        END;
        $$;
        """
    )
    insert_basis = (
        _FORMAL_BASIS.replace("TARGET.", "NEW.")
        + "\n      FOR SHARE OF assignment, enrollment"
    )
    op.execute(
        f"""
        CREATE FUNCTION validate_formal_outcome_basis() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM * FROM ({insert_basis}) AS fixed_formal_basis;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'formal result requires fixed practice evidence and a finalized human PASS gate'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_outcomes_validate_formal_basis
        BEFORE INSERT ON outcomes
        FOR EACH ROW EXECUTE FUNCTION validate_formal_outcome_basis();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_outcomes_validate_formal_basis ON outcomes")
    op.execute("DROP FUNCTION validate_formal_outcome_basis()")
