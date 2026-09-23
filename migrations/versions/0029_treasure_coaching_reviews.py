"""Add non-blocking treasure coaching reviews and immutable AI advice contract.

Revision ID: 0029_treasure_coaching_reviews
Revises: 0028_canary_main_merge
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0029_treasure_coaching_reviews"
down_revision = "0028_canary_main_merge"
branch_labels = None
depends_on = None

AI_PROVENANCE_CHECK = """
jsonb_typeof(ai_use) = 'object'
AND ai_use ?& ARRAY['used','purpose','model_version','prompt_version','output_is_advisory_only']
AND (ai_use - ARRAY['used','purpose','model_version','prompt_version','output_is_advisory_only']) = '{}'::jsonb
AND jsonb_typeof(ai_use -> 'used') = 'boolean'
AND (ai_use ->> 'output_is_advisory_only')::boolean = TRUE
AND (
  ((ai_use ->> 'used')::boolean = FALSE
   AND ai_use -> 'purpose' = 'null'::jsonb
   AND ai_use -> 'model_version' = 'null'::jsonb
   AND ai_use -> 'prompt_version' = 'null'::jsonb)
  OR
  ((ai_use ->> 'used')::boolean = TRUE
   AND length(ai_use ->> 'purpose') BETWEEN 3 AND 200
   AND length(ai_use ->> 'model_version') BETWEEN 1 AND 200
   AND length(ai_use ->> 'prompt_version') BETWEEN 1 AND 200)
)
"""


def upgrade() -> None:
    op.add_column(
        "invites", sa.Column("target_assignment_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        "ix_invites_target_assignment_id", "invites", ["target_assignment_id"]
    )
    op.create_foreign_key(
        "fk_invites_target_assignment_organization",
        "invites",
        "assignments",
        ["target_assignment_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.add_column(
        "reviews",
        sa.Column(
            "review_kind",
            sa.String(length=32),
            nullable=False,
            server_default="FORMAL_EVALUATION",
        ),
    )
    op.add_column(
        "reviews", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint("ck_reviews_status", "reviews", type_="check")
    op.create_check_constraint(
        "ck_reviews_status",
        "reviews",
        "status IN ('ASSIGNED', 'IN_REVIEW', 'FINALIZED', 'SUPERSEDED')",
    )
    op.drop_constraint("ck_reviews_status_timestamps", "reviews", type_="check")
    op.create_check_constraint(
        "ck_reviews_kind",
        "reviews",
        "review_kind IN ('FORMAL_EVALUATION', 'LEARNING_COACHING')",
    )
    op.create_check_constraint(
        "ck_reviews_status_timestamps",
        "reviews",
        "(status = 'ASSIGNED' AND started_at IS NULL AND finalized_at IS NULL) "
        "OR (status = 'IN_REVIEW' AND started_at IS NOT NULL AND finalized_at IS NULL) "
        "OR (status = 'FINALIZED' AND started_at IS NOT NULL AND finalized_at IS NOT NULL) "
        "OR (status = 'SUPERSEDED' AND finalized_at IS NULL AND superseded_at IS NOT NULL)",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_review_history() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Review rows are immutable history';
            END IF;
            IF OLD.status IN ('FINALIZED', 'SUPERSEDED') THEN
                RAISE EXCEPTION 'Closed Review rows are immutable';
            END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.assignment_id IS DISTINCT FROM OLD.assignment_id
               OR NEW.submission_id IS DISTINCT FROM OLD.submission_id
               OR NEW.submission_version_id IS DISTINCT FROM OLD.submission_version_id
               OR NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id
               OR NEW.assigned_at IS DISTINCT FROM OLD.assigned_at
               OR NEW.review_kind IS DISTINCT FROM OLD.review_kind THEN
                RAISE EXCEPTION 'Review fixed references are immutable';
            END IF;
            IF NEW.revision <> OLD.revision + 1 THEN
                RAISE EXCEPTION 'Review revision must increase by one';
            END IF;
            IF OLD.status = 'ASSIGNED'
               AND NEW.status NOT IN ('IN_REVIEW', 'SUPERSEDED') THEN
                RAISE EXCEPTION 'Invalid Review state transition';
            END IF;
            IF OLD.status = 'IN_REVIEW'
               AND NEW.status NOT IN ('FINALIZED', 'SUPERSEDED') THEN
                RAISE EXCEPTION 'Invalid Review state transition';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.create_table(
        "coaching_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("submission_version_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("executor_id", sa.Uuid(), nullable=False),
        sa.Column("review_revision", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=17), nullable=False),
        sa.Column("structured_feedback", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column(
            "ai_use", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "created_by = executor_id", name="ck_coaching_feedback_executor_is_actor"
        ),
        sa.CheckConstraint(
            "review_revision >= 1", name="ck_coaching_feedback_positive_review_revision"
        ),
        sa.CheckConstraint(
            "decision IN ('PASS', 'REVISION_REQUIRED')",
            name="ck_coaching_feedback_decision",
        ),
        sa.CheckConstraint(
            AI_PROVENANCE_CHECK, name="ck_coaching_feedback_ai_provenance"
        ),
        sa.ForeignKeyConstraint(["executor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            [
                "review_id",
                "organization_id",
                "assignment_id",
                "submission_id",
                "submission_version_id",
                "reviewer_id",
            ],
            [
                "reviews.id",
                "reviews.organization_id",
                "reviews.assignment_id",
                "reviews.submission_id",
                "reviews.submission_version_id",
                "reviews.reviewer_id",
            ],
            name="fk_coaching_feedback_review_fixed_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", name="uq_coaching_feedback_review"),
    )
    op.create_index(
        "ix_coaching_feedback_organization_id",
        "coaching_feedback",
        ["organization_id"],
    )
    op.create_index(
        "ix_coaching_feedback_executor_id", "coaching_feedback", ["executor_id"]
    )
    op.create_table(
        "ai_advisory_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("submission_version_id", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(length=180), nullable=False),
        sa.Column("prompt_version", sa.String(length=180), nullable=False),
        sa.Column("policy_version", sa.String(length=180), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("advisory_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("advisory_only = true", name="ck_ai_advisory_only"),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ai_advisory_input_sha256"
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_ai_advisory_assignment_organization",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "organization_id", "assignment_id"],
            ["submissions.id", "submissions.organization_id", "submissions.assignment_id"],
            name="fk_ai_advisory_submission_scope",
        ),
        sa.ForeignKeyConstraint(
            ["submission_version_id", "submission_id"],
            ["submission_versions.id", "submission_versions.submission_id"],
            name="fk_ai_advisory_submission_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_version_id", name="uq_ai_advisory_submission_version"
        ),
    )
    op.create_index(
        "ix_ai_advisory_records_organization_id",
        "ai_advisory_records",
        ["organization_id"],
    )
    op.execute(
        """
        CREATE FUNCTION validate_review_result_kind() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE expected_kind text;
        BEGIN
            expected_kind := CASE TG_TABLE_NAME
                WHEN 'evaluations' THEN 'FORMAL_EVALUATION'
                ELSE 'LEARNING_COACHING'
            END;
            IF NOT EXISTS (
                SELECT 1 FROM reviews
                WHERE id = NEW.review_id AND review_kind = expected_kind
            ) THEN
                RAISE EXCEPTION 'Review result type does not match Review kind';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_evaluations_review_kind
        BEFORE INSERT ON evaluations
        FOR EACH ROW EXECUTE FUNCTION validate_review_result_kind();
        CREATE TRIGGER trg_coaching_feedback_review_kind
        BEFORE INSERT ON coaching_feedback
        FOR EACH ROW EXECUTE FUNCTION validate_review_result_kind();

        CREATE FUNCTION reject_coaching_fact_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Coaching and AI advisory facts are immutable';
        END;
        $$;
        CREATE TRIGGER trg_coaching_feedback_immutable
        BEFORE UPDATE OR DELETE ON coaching_feedback
        FOR EACH ROW EXECUTE FUNCTION reject_coaching_fact_mutation();
        CREATE TRIGGER trg_ai_advisory_records_immutable
        BEFORE UPDATE OR DELETE ON ai_advisory_records
        FOR EACH ROW EXECUTE FUNCTION reject_coaching_fact_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM reviews WHERE review_kind = 'LEARNING_COACHING')
               OR EXISTS (SELECT 1 FROM ai_advisory_records)
               OR EXISTS (
                    SELECT 1 FROM invites WHERE target_assignment_id IS NOT NULL
               ) THEN
                RAISE EXCEPTION
                    'coaching, AI advisory, or assignment-bound reentry facts exist; downgrade would destroy protected history';
            END IF;
        END;
        $$;
        """
    )
    op.execute(
        """
        DROP TRIGGER trg_ai_advisory_records_immutable ON ai_advisory_records;
        DROP TRIGGER trg_coaching_feedback_immutable ON coaching_feedback;
        DROP FUNCTION reject_coaching_fact_mutation();
        DROP TRIGGER trg_coaching_feedback_review_kind ON coaching_feedback;
        DROP TRIGGER trg_evaluations_review_kind ON evaluations;
        DROP FUNCTION validate_review_result_kind();
        CREATE OR REPLACE FUNCTION protect_review_history() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Review rows are immutable history';
            END IF;
            IF OLD.status = 'FINALIZED' THEN
                RAISE EXCEPTION 'Finalized Review rows are immutable';
            END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.assignment_id IS DISTINCT FROM OLD.assignment_id
               OR NEW.submission_id IS DISTINCT FROM OLD.submission_id
               OR NEW.submission_version_id IS DISTINCT FROM OLD.submission_version_id
               OR NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id
               OR NEW.assigned_at IS DISTINCT FROM OLD.assigned_at THEN
                RAISE EXCEPTION 'Review fixed references are immutable';
            END IF;
            IF NEW.revision <> OLD.revision + 1 THEN
                RAISE EXCEPTION 'Review revision must increase by one';
            END IF;
            IF OLD.status = 'ASSIGNED' AND NEW.status <> 'IN_REVIEW' THEN
                RAISE EXCEPTION 'Invalid Review state transition';
            END IF;
            IF OLD.status = 'IN_REVIEW' AND NEW.status <> 'FINALIZED' THEN
                RAISE EXCEPTION 'Invalid Review state transition';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.drop_index(
        "ix_ai_advisory_records_organization_id", table_name="ai_advisory_records"
    )
    op.drop_table("ai_advisory_records")
    op.drop_index(
        "ix_coaching_feedback_executor_id", table_name="coaching_feedback"
    )
    op.drop_index(
        "ix_coaching_feedback_organization_id", table_name="coaching_feedback"
    )
    op.drop_table("coaching_feedback")
    op.drop_constraint("ck_reviews_status_timestamps", "reviews", type_="check")
    op.drop_constraint("ck_reviews_kind", "reviews", type_="check")
    op.drop_constraint("ck_reviews_status", "reviews", type_="check")
    op.create_check_constraint(
        "ck_reviews_status",
        "reviews",
        "status IN ('ASSIGNED', 'IN_REVIEW', 'FINALIZED')",
    )
    op.create_check_constraint(
        "ck_reviews_status_timestamps",
        "reviews",
        "(status = 'ASSIGNED' AND started_at IS NULL AND finalized_at IS NULL) "
        "OR (status = 'IN_REVIEW' AND started_at IS NOT NULL AND finalized_at IS NULL) "
        "OR (status = 'FINALIZED' AND started_at IS NOT NULL AND finalized_at IS NOT NULL)",
    )
    op.drop_column("reviews", "superseded_at")
    op.drop_column("reviews", "review_kind")
    op.drop_constraint(
        "fk_invites_target_assignment_organization", "invites", type_="foreignkey"
    )
    op.drop_index("ix_invites_target_assignment_id", table_name="invites")
    op.drop_column("invites", "target_assignment_id")
