"""Persist global guild certification requests without changing ability grants."""
from alembic import op
import sqlalchemy as sa

revision = "0055_guild_certification"
down_revision = "0054_academy_covers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("guild_certification_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("student_name", sa.String(200), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("reviewer_name", sa.String(200), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name="ck_guild_request_level"),
        sa.CheckConstraint("status IN ('pending','approved','returned')", name="ck_guild_request_status"),
        sa.CheckConstraint("reviewer_id IS NULL OR reviewer_id <> user_id", name="ck_guild_request_no_self_review"),
        sa.CheckConstraint("(status = 'pending' AND reviewer_id IS NULL AND reviewed_at IS NULL) OR "
                           "(status <> 'pending' AND reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)",
                           name="ck_guild_request_review_state"))
    op.create_index("ix_guild_certification_requests_organization_id", "guild_certification_requests", ["organization_id"])
    op.create_index("ix_guild_certification_requests_user_id", "guild_certification_requests", ["user_id"])
    op.create_index("uq_guild_pending_request", "guild_certification_requests", ["organization_id", "user_id"],
                    unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index("uq_guild_approved_level", "guild_certification_requests", ["organization_id", "user_id", "level"],
                    unique=True, postgresql_where=sa.text("status = 'approved'"))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM guild_certification_requests)")).scalar():
        raise RuntimeError("Guild certification history exists; refusing a destructive downgrade.")
    op.drop_table("guild_certification_requests")
