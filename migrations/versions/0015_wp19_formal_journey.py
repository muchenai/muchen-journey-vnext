"""Add versioned formal-journey composition and outcome evidence.

Revision ID: 0015_wp19_formal_journey
Revises: 0014_wp12_data_lifecycle
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_wp19_formal_journey"
down_revision = "0014_wp12_data_lifecycle"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def _create_immutability_guards() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_formal_journey_version_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'published formal journey rows are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("journey_versions", "journey_stage_versions", "journey_outcome_evidence"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_formal_journey_version_mutation()
            """
        )


def upgrade() -> None:
    op.create_table(
        "journey_definitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')",
            name="ck_journey_definitions_status",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_journey_definitions_positive_revision"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "stable_key",
            name="uq_journey_definitions_organization_key",
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_journey_definitions_id_organization"
        ),
    )
    op.create_index(
        "ix_journey_definitions_organization_id",
        "journey_definitions",
        ["organization_id"],
    )

    op.create_table(
        "journey_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("journey_definition_id", UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("content_review_note", sa.Text(), nullable=False),
        sa.Column("published_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "published_at", TIMESTAMP, server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="ck_journey_versions_positive_version"),
        sa.ForeignKeyConstraint(
            ["journey_definition_id", "organization_id"],
            ["journey_definitions.id", "journey_definitions.organization_id"],
            name="fk_journey_versions_definition_organization",
        ),
        sa.UniqueConstraint(
            "journey_definition_id",
            "version",
            name="uq_journey_versions_definition_version",
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_journey_versions_id_organization"
        ),
    )
    op.create_index(
        "ix_journey_versions_organization_id",
        "journey_versions",
        ["organization_id"],
    )

    op.create_unique_constraint(
        "uq_task_versions_id_organization",
        "task_versions",
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_enrollments_id_organization",
        "enrollments",
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_evaluations_id_organization",
        "evaluations",
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_outcomes_id_organization_enrollment",
        "outcomes",
        ["id", "organization_id", "enrollment_id"],
    )
    op.create_table(
        "journey_stage_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("journey_version_id", UUID, nullable=False),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage_kind", sa.String(20), nullable=False),
        sa.Column("completion_policy", sa.String(24), nullable=False),
        sa.Column("task_version_id", UUID, nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("short_description", sa.String(300), nullable=False),
        sa.ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_journey_stages_version_organization",
        ),
        sa.ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_journey_stages_task_organization",
        ),
        sa.CheckConstraint("position >= 0", name="ck_journey_stages_nonnegative_position"),
        sa.CheckConstraint(
            "stage_kind IN ('DAY_0', 'TREASURE', 'ASSESSMENT')",
            name="ck_journey_stages_kind",
        ),
        sa.CheckConstraint(
            "completion_policy IN ('LEARNER_EVIDENCE', 'REVIEW_REQUIRED')",
            name="ck_journey_stages_completion_policy",
        ),
        sa.CheckConstraint(
            "(stage_kind IN ('DAY_0', 'TREASURE') AND completion_policy = 'LEARNER_EVIDENCE') "
            "OR (stage_kind = 'ASSESSMENT' AND completion_policy = 'REVIEW_REQUIRED')",
            name="ck_journey_stages_kind_policy",
        ),
        sa.UniqueConstraint(
            "journey_version_id",
            "stable_key",
            name="uq_journey_stages_version_key",
        ),
        sa.UniqueConstraint(
            "journey_version_id",
            "position",
            name="uq_journey_stages_version_position",
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_journey_stages_id_organization"
        ),
    )
    op.create_index(
        "ix_journey_stage_versions_organization_id",
        "journey_stage_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_journey_stage_versions_journey_version_id",
        "journey_stage_versions",
        ["journey_version_id"],
    )
    op.create_index(
        "ix_journey_stage_versions_task_version_id",
        "journey_stage_versions",
        ["task_version_id"],
    )

    op.add_column("enrollments", sa.Column("journey_version_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_enrollments_journey_version_organization",
        "enrollments",
        "journey_versions",
        ["journey_version_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_index(
        "ix_enrollments_journey_version_id", "enrollments", ["journey_version_id"]
    )

    op.add_column("invites", sa.Column("journey_version_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_invites_journey_version_organization",
        "invites",
        "journey_versions",
        ["journey_version_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_index("ix_invites_journey_version_id", "invites", ["journey_version_id"])

    op.add_column(
        "assignments", sa.Column("journey_stage_version_id", UUID, nullable=True)
    )
    op.create_foreign_key(
        "fk_assignments_journey_stage_organization",
        "assignments",
        "journey_stage_versions",
        ["journey_stage_version_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_assignments_enrollment_journey_stage",
        "assignments",
        ["enrollment_id", "journey_stage_version_id"],
    )
    op.create_index(
        "ix_assignments_journey_stage_version_id",
        "assignments",
        ["journey_stage_version_id"],
    )

    op.create_table(
        "journey_outcome_evidence",
        sa.Column("outcome_id", UUID, primary_key=True),
        sa.Column("evaluation_id", UUID, primary_key=True),
        sa.Column("journey_stage_version_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column(
            "created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "outcome_id",
            "journey_stage_version_id",
            name="uq_journey_outcome_evidence_stage",
        ),
        sa.UniqueConstraint(
            "evaluation_id", name="uq_journey_outcome_evidence_evaluation"
        ),
        sa.ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.enrollment_id"],
            name="fk_journey_evidence_outcome_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "organization_id"],
            ["evaluations.id", "evaluations.organization_id"],
            name="fk_journey_evidence_evaluation_scope",
        ),
        sa.ForeignKeyConstraint(
            ["journey_stage_version_id", "organization_id"],
            ["journey_stage_versions.id", "journey_stage_versions.organization_id"],
            name="fk_journey_evidence_stage_scope",
        ),
    )
    op.create_index(
        "ix_journey_outcome_evidence_organization_id",
        "journey_outcome_evidence",
        ["organization_id"],
    )
    op.create_index(
        "ix_journey_outcome_evidence_enrollment_id",
        "journey_outcome_evidence",
        ["enrollment_id"],
    )
    _create_immutability_guards()


def downgrade() -> None:
    for table in ("journey_outcome_evidence", "journey_stage_versions", "journey_versions"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_formal_journey_version_mutation()")
    op.drop_table("journey_outcome_evidence")

    op.drop_index("ix_assignments_journey_stage_version_id", table_name="assignments")
    op.drop_constraint(
        "uq_assignments_enrollment_journey_stage", "assignments", type_="unique"
    )
    op.drop_constraint(
        "fk_assignments_journey_stage_organization", "assignments", type_="foreignkey"
    )
    op.drop_column("assignments", "journey_stage_version_id")

    op.drop_index("ix_invites_journey_version_id", table_name="invites")
    op.drop_constraint(
        "fk_invites_journey_version_organization", "invites", type_="foreignkey"
    )
    op.drop_column("invites", "journey_version_id")

    op.drop_index("ix_enrollments_journey_version_id", table_name="enrollments")
    op.drop_constraint(
        "fk_enrollments_journey_version_organization",
        "enrollments",
        type_="foreignkey",
    )
    op.drop_column("enrollments", "journey_version_id")

    op.drop_table("journey_stage_versions")
    op.drop_constraint(
        "uq_outcomes_id_organization_enrollment", "outcomes", type_="unique"
    )
    op.drop_constraint(
        "uq_evaluations_id_organization", "evaluations", type_="unique"
    )
    op.drop_constraint(
        "uq_enrollments_id_organization", "enrollments", type_="unique"
    )
    op.drop_constraint(
        "uq_task_versions_id_organization", "task_versions", type_="unique"
    )
    op.drop_table("journey_versions")
    op.drop_table("journey_definitions")
