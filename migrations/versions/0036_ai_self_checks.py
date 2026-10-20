"""Persist document self-check claims and title-comment delivery state."""
from alembic import op
import sqlalchemy as sa

revision = "0036_ai_self_checks"
down_revision = "0035_phone_password_login"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ai_self_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("learner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("document_token", sa.String(100), nullable=False),
        sa.Column("document_url", sa.Text(), nullable=False),
        sa.Column("document_revision", sa.String(40), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("result", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("comment_id", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "document_token", name="uq_ai_self_check_document"),
        sa.CheckConstraint("status IN ('RUNNING','SENDING','COMPLETED','FAILED','UNCERTAIN')", name="ck_ai_self_check_status"),
    )
    op.create_index("ix_ai_self_checks_assignment_id", "ai_self_checks", ["assignment_id"])


def downgrade():
    op.drop_table("ai_self_checks")
