"""Add phone OTP login and one-time exploration completion codes.

Revision ID: 0033_phone_login_codes
Revises: 0032_shared_learner_review
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_phone_login_codes"
down_revision = "0032_shared_learner_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_otp_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_subject", sa.String(length=64), nullable=False),
        sa.Column("phone_last_four", sa.String(length=4), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("code_ciphertext", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_phone_otp_attempts_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_phone_otp_challenges_phone_subject", "phone_otp_challenges", ["phone_subject"])
    op.create_index("ix_phone_otp_challenges_expires_at", "phone_otp_challenges", ["expires_at"])
    op.create_table(
        "completion_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hint", sa.String(length=4), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migrated_to_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["migrated_to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"], name="fk_completion_codes_user_organization"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
        sa.UniqueConstraint("user_id", name="uq_completion_codes_user"),
    )
    op.create_index("ix_completion_codes_organization_id", "completion_codes", ["organization_id"])
    op.create_index("ix_completion_codes_user_id", "completion_codes", ["user_id"])
    op.create_index("ix_completion_codes_expires_at", "completion_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_table("completion_codes")
    op.drop_table("phone_otp_challenges")
