"""Add WP-24 learning content and immutable human admission decisions.

Revision ID: 0016_wp24_formal_camp_v2
Revises: 0015_wp19_formal_journey
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_wp24_formal_camp_v2"
down_revision = "0015_wp19_formal_journey"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "task_versions",
        sa.Column(
            "learning_experience",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "journey_admission_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("journey_version_id", UUID, nullable=False),
        sa.Column("outcome_id", UUID, nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("recommendation_tier", sa.String(32), nullable=False),
        sa.Column("scorecard", sa.JSON(), nullable=False),
        sa.Column("source_evaluation_ids", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("decided_by", UUID, nullable=False),
        sa.Column(
            "created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "organization_id"],
            ["enrollments.id", "enrollments.organization_id"],
            name="fk_journey_admission_enrollment_scope",
        ),
        sa.ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_journey_admission_version_scope",
        ),
        sa.ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.enrollment_id"],
            name="fk_journey_admission_outcome_scope",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_journey_admission_decider_scope",
        ),
        sa.UniqueConstraint(
            "enrollment_id",
            "journey_version_id",
            name="uq_journey_admission_enrollment_version",
        ),
        sa.CheckConstraint(
            "total_score BETWEEN 0 AND 100",
            name="ck_journey_admission_total_score",
        ),
        sa.CheckConstraint(
            "decision IN ('ADMIT', 'DEFER', 'NOT_ADMIT')",
            name="ck_journey_admission_decision",
        ),
    )
    op.create_index(
        "ix_journey_admission_decisions_organization_id",
        "journey_admission_decisions",
        ["organization_id"],
    )
    op.create_index(
        "ix_journey_admission_decisions_enrollment_id",
        "journey_admission_decisions",
        ["enrollment_id"],
    )
    op.create_index(
        "ix_journey_admission_decisions_journey_version_id",
        "journey_admission_decisions",
        ["journey_version_id"],
    )
    op.create_index(
        "ix_journey_admission_decisions_outcome_id",
        "journey_admission_decisions",
        ["outcome_id"],
    )
    op.create_index(
        "ix_journey_admission_decisions_decided_by",
        "journey_admission_decisions",
        ["decided_by"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_journey_admission_decision_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'journey admission decisions are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER journey_admission_decisions_immutable
        BEFORE UPDATE OR DELETE ON journey_admission_decisions
        FOR EACH ROW EXECUTE FUNCTION reject_journey_admission_decision_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS journey_admission_decisions_immutable "
        "ON journey_admission_decisions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_journey_admission_decision_mutation()")
    op.drop_table("journey_admission_decisions")
    op.drop_column("task_versions", "learning_experience")
