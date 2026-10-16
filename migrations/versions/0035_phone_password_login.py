"""Add password credentials for temporary phone accounts.

Revision ID: 0035_phone_password_login
Revises: 0034_fix_code_ciphertext
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_phone_password_login"
down_revision = "0034_fix_code_ciphertext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_password_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_identity_id", sa.Uuid(), nullable=False),
        sa.Column("password_salt", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["external_identity_id"],
            ["external_identities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_identity_id"),
    )
    op.create_index(
        "ix_phone_password_credentials_external_identity_id",
        "phone_password_credentials",
        ["external_identity_id"],
    )


def downgrade() -> None:
    op.drop_table("phone_password_credentials")
