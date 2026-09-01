"""Bind staff sessions to the external identity revision.

Revision ID: 0021_p0_identity_principal
Revises: 0020_wp09_reviewer_delegation
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_p0_identity_principal"
down_revision = "0020_wp09_reviewer_delegation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "identity_sessions",
        sa.Column("external_identity_revision", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE identity_sessions AS identity_session
        SET external_identity_revision = external_identity.revision
        FROM external_identities AS external_identity
        WHERE identity_session.external_identity_id = external_identity.id
        """
    )
    op.create_check_constraint(
        "ck_identity_sessions_positive_external_identity_revision",
        "identity_sessions",
        "external_identity_revision IS NULL OR external_identity_revision >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_identity_sessions_positive_external_identity_revision",
        "identity_sessions",
        type_="check",
    )
    op.drop_column("identity_sessions", "external_identity_revision")
