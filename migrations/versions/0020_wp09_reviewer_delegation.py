"""Add immutable Reviewer delegation and actual evaluation executor.

Revision ID: 0020_wp09_reviewer_delegation
Revises: 0019_wp30_invitation_control
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_wp09_reviewer_delegation"
down_revision = "0019_wp30_invitation_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_delegations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("delegated_by", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("revision >= 1", name="ck_review_delegations_positive_revision"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["delegated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", name="uq_review_delegations_review"),
    )
    op.create_index(
        "ix_review_delegations_organization_id",
        "review_delegations",
        ["organization_id"],
    )
    op.create_index(
        "ix_review_delegations_reviewer_id",
        "review_delegations",
        ["reviewer_id"],
    )
    op.create_index(
        "ix_review_delegations_review_id",
        "review_delegations",
        ["review_id"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_review_delegation_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Review delegation rows are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_review_delegations_immutable
        BEFORE UPDATE OR DELETE ON review_delegations
        FOR EACH ROW EXECUTE FUNCTION reject_review_delegation_mutation()
        """
    )
    op.add_column("evaluations", sa.Column("executor_id", sa.Uuid(), nullable=True))
    op.execute("DROP TRIGGER trg_reject_evaluation_mutation ON evaluations")
    op.execute("UPDATE evaluations SET executor_id = created_by")
    op.execute(
        """
        CREATE TRIGGER trg_reject_evaluation_mutation
        BEFORE UPDATE OR DELETE ON evaluations
        FOR EACH ROW EXECUTE FUNCTION reject_evaluation_mutation()
        """
    )
    op.alter_column("evaluations", "executor_id", nullable=False)
    op.create_foreign_key(
        "fk_evaluations_executor",
        "evaluations",
        "users",
        ["executor_id"],
        ["id"],
    )
    op.create_index("ix_evaluations_executor_id", "evaluations", ["executor_id"])
    op.drop_constraint(
        "ck_evaluations_reviewer_is_actor",
        "evaluations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evaluations_executor_is_actor",
        "evaluations",
        "created_by = executor_id",
    )


def downgrade() -> None:
    delegation_exists = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM review_delegations LIMIT 1)")
    ).scalar_one()
    if delegation_exists:
        raise RuntimeError(
            "WP-09 Reviewer delegation records exist and cannot be downgraded"
        )

    op.drop_constraint(
        "ck_evaluations_executor_is_actor",
        "evaluations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evaluations_reviewer_is_actor",
        "evaluations",
        "created_by = reviewer_id",
    )
    op.drop_index("ix_evaluations_executor_id", table_name="evaluations")
    op.drop_constraint(
        "fk_evaluations_executor",
        "evaluations",
        type_="foreignkey",
    )
    op.drop_column("evaluations", "executor_id")
    op.execute("DROP TRIGGER trg_review_delegations_immutable ON review_delegations")
    op.execute("DROP FUNCTION reject_review_delegation_mutation()")
    op.drop_table("review_delegations")
