"""Add WP-26 fixed learning materials and immutable completion facts.

Revision ID: 0017_wp26_material_completion
Revises: 0016_wp24_formal_camp_v2
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_wp26_material_completion"
down_revision = "0016_wp24_formal_camp_v2"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "task_versions",
        sa.Column(
            "learning_materials",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.create_table(
        "learning_material_completions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("assignment_id", UUID, nullable=False),
        sa.Column("task_version_id", UUID, nullable=False),
        sa.Column("learner_id", UUID, nullable=False),
        sa.Column("material_key", sa.String(80), nullable=False),
        sa.Column(
            "completed_at", TIMESTAMP, server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_material_completions_assignment_scope",
        ),
        sa.ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_material_completions_task_version_scope",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "organization_id", "learner_id"],
            ["enrollments.id", "enrollments.organization_id", "enrollments.learner_id"],
            name="fk_material_completions_enrollment_owner_scope",
        ),
        sa.UniqueConstraint(
            "assignment_id",
            "material_key",
            name="uq_material_completions_assignment_key",
        ),
        sa.CheckConstraint(
            "material_key ~ '^[a-z0-9][a-z0-9_-]{2,79}$'",
            name="ck_material_completions_key",
        ),
    )
    for column in (
        "organization_id",
        "enrollment_id",
        "assignment_id",
        "task_version_id",
        "learner_id",
    ):
        op.create_index(
            f"ix_learning_material_completions_{column}",
            "learning_material_completions",
            [column],
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_learning_material_completion_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'learning material completions are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER learning_material_completions_immutable
        BEFORE UPDATE OR DELETE ON learning_material_completions
        FOR EACH ROW EXECUTE FUNCTION reject_learning_material_completion_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS learning_material_completions_immutable "
        "ON learning_material_completions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_learning_material_completion_mutation()")
    op.drop_table("learning_material_completions")
    op.drop_column("task_versions", "learning_materials")
