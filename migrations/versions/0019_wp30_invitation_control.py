"""Add fail-closed per-organization invitation control for WP-30.

Revision ID: 0019_wp30_invitation_control
Revises: 0018_wp26_content_drafts
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_wp30_invitation_control"
down_revision = "0018_wp26_content_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitation_controls",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("new_invites_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="ck_invitation_controls_revision"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.execute(
        """
        INSERT INTO invitation_controls (
            organization_id, new_invites_enabled, revision, reason, updated_by
        )
        SELECT id, TRUE, 1, NULL, NULL FROM organizations
        """
    )


def downgrade() -> None:
    op.drop_table("invitation_controls")
