"""Merge the controlled Canary and current main migration histories.

Revision ID: 0028_canary_main_merge
Revises: 0027_next_stage_review, 0021_p0_identity_principal
"""

from alembic import op


revision = "0028_canary_main_merge"
down_revision = ("0027_next_stage_review", "0021_p0_identity_principal")
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
      AND evaluation.created_by = evaluation.executor_id
      AND (
          (
              evaluation.executor_id = review.reviewer_id
              AND review.reviewer_id = enrollment.reviewer_id
          )
          OR EXISTS (
              SELECT 1
              FROM review_delegations AS delegation
              WHERE delegation.review_id = review.id
                AND delegation.organization_id = review.organization_id
                AND delegation.reviewer_id = evaluation.executor_id
                AND delegation.reviewer_id = enrollment.reviewer_id
          )
      )
      AND evaluation.executor_id <> enrollment.learner_id
      AND length(trim(evaluation.feedback)) >= 10
      AND review.status = 'FINALIZED'
      AND review.finalized_at IS NOT NULL
      AND assignment.enrollment_id = TARGET.enrollment_id
      AND assignment.status = 'COMPLETED'
      AND enrollment.id = TARGET.enrollment_id
      AND enrollment.learner_id = TARGET.learner_id
      AND enrollment.status = 'COMPLETED'
      AND submission.current_version_no = submission_version.version_no
      AND submission_version.created_by = enrollment.learner_id
      AND length(trim(submission_version.body)) >= 1
"""


_PRE_MERGE_FORMAL_BASIS = _FORMAL_BASIS.replace(
    "evaluation.created_by = evaluation.executor_id\n      AND (\n"
    "          (\n"
    "              evaluation.executor_id = review.reviewer_id\n"
    "              AND review.reviewer_id = enrollment.reviewer_id\n"
    "          )\n"
    "          OR EXISTS (\n"
    "              SELECT 1\n"
    "              FROM review_delegations AS delegation\n"
    "              WHERE delegation.review_id = review.id\n"
    "                AND delegation.organization_id = review.organization_id\n"
    "                AND delegation.reviewer_id = evaluation.executor_id\n"
    "                AND delegation.reviewer_id = enrollment.reviewer_id\n"
    "          )\n"
    "      )\n"
    "      AND evaluation.executor_id <> enrollment.learner_id",
    "evaluation.created_by = evaluation.reviewer_id\n"
    "      AND review.reviewer_id = enrollment.reviewer_id\n"
    "      AND review.reviewer_id <> enrollment.learner_id",
)


def _install_formal_result_gate(basis: str) -> None:
    insert_basis = basis.replace("TARGET.", "NEW.") + "\n      FOR SHARE OF assignment, enrollment"
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


def upgrade() -> None:
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
                    'existing formal result lacks a valid direct or delegated human PASS gate';
            END IF;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER trg_outcomes_validate_formal_basis ON outcomes")
    op.execute("DROP FUNCTION validate_formal_outcome_basis()")
    _install_formal_result_gate(_FORMAL_BASIS)


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM outcomes AS outcome
                JOIN evaluations AS evaluation
                  ON evaluation.id = outcome.source_evaluation_id
                 AND evaluation.organization_id = outcome.organization_id
                WHERE evaluation.executor_id <> evaluation.reviewer_id
            ) THEN
                RAISE EXCEPTION
                    'delegated formal outcomes exist and cannot be downgraded before the merge gate';
            END IF;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER trg_outcomes_validate_formal_basis ON outcomes")
    op.execute("DROP FUNCTION validate_formal_outcome_basis()")
    _install_formal_result_gate(_PRE_MERGE_FORMAL_BASIS)
