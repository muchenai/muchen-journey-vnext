"""Align the final outcome gate with task-author and super-admin review authority.

Existing immutable evaluations/outcomes are preserved. Only new result inserts
use the new authorization rule; all fixed evidence and finalized PASS checks remain.
"""
from alembic import op

revision = '0044_task_author_review'
down_revision = '0043_directory_tree'
branch_labels = None
depends_on = None

_LEGACY_BASIS = """
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

_BASIS = """
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
          review.reviewer_id = enrollment.reviewer_id
          OR EXISTS (SELECT 1 FROM review_delegations d
              WHERE d.review_id = review.id AND d.organization_id = review.organization_id
                AND d.reviewer_id = enrollment.reviewer_id)
      )
      AND EXISTS (
          SELECT 1 FROM task_definitions task
          JOIN users executor ON executor.id = evaluation.executor_id
             AND executor.organization_id = task.organization_id AND executor.status = 'ACTIVE'
          WHERE task.id = assignment.task_definition_id
            AND task.organization_id = evaluation.organization_id
            AND EXISTS (SELECT 1 FROM role_assignments role
                WHERE role.user_id = executor.id AND role.organization_id = executor.organization_id
                  AND role.role = 'REVIEWER')
            AND NOT EXISTS (SELECT 1 FROM review_admin_access access
                WHERE access.user_id = executor.id AND access.organization_id = executor.organization_id
                  AND access.revoked_at IS NOT NULL)
            AND (
                task.created_by = executor.id
                OR EXISTS (SELECT 1 FROM review_admin_access access
                    WHERE access.user_id = executor.id AND access.organization_id = task.organization_id
                      AND access.revoked_at IS NULL AND access.access_role = 'super_admin')
                OR COALESCE((SELECT profile.content->>'camp' FROM review_admin_tasks profile
                    WHERE profile.task_definition_id = task.id AND profile.organization_id = task.organization_id),
                    CASE WHEN task.stable_key IN ('DAY-0', 'TRE-001-COMPANY-VALUES', 'TRE-002-AI-DATA-BASICS',
                        'TRE-003-PROJECT-AWARENESS', 'TRE-004-DELIVERY-FIT', 'ASM-001-RULE-BREAKDOWN',
                        'ASM-002-MODEL-JUDGEMENT', 'ASM-003-DATA-CONSTRUCTION') THEN 'exploration' ELSE 'novice' END
                ) = 'exploration'
            )
      )
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

def install(basis):
    query = basis.replace('TARGET.', 'NEW.') + '\n      FOR SHARE OF assignment, enrollment'
    op.execute(f"""
        CREATE OR REPLACE FUNCTION validate_formal_outcome_basis() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM * FROM ({query}) AS fixed_formal_basis;
            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'formal result requires fixed practice evidence and a finalized human PASS gate'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)


def upgrade():
    install(_BASIS)


def downgrade():
    install(_LEGACY_BASIS)
