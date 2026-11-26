"""Persist authorized course roles, import snapshots and actual offline training credits."""
import sqlalchemy as sa
from alembic import op

revision = "0061_management_access"
down_revision = "0060_migrated_ai_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("course_management_settings",
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("assignments", sa.JSON(), nullable=False),
        sa.Column("issuers", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False))
    op.create_table("experience_roster_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id", "organization_id"], ["users.id", "users.organization_id"]))
    op.create_index("ix_experience_roster_expiry", "experience_roster_snapshots", ["expires_at"])
    op.create_table("offline_experience_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("batch", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("points", sa.BigInteger()),
        sa.Column("xp", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"]),
        sa.ForeignKeyConstraint(["issuer_id", "organization_id"], ["users.id", "users.organization_id"]),
        sa.UniqueConstraint("organization_id", "batch", "user_id", name="uq_offline_xp_batch_learner"),
        sa.CheckConstraint("xp > 0 AND (points IS NULL OR (points > 0 AND xp = points * 10))", name="ck_offline_xp_amount"))
    op.create_index("ix_offline_xp_learner", "offline_experience_grants", ["organization_id", "user_id"])


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM offline_experience_grants) OR EXISTS "
               "(SELECT 1 FROM course_management_settings) THEN RAISE EXCEPTION "
               "'Preserve management permissions and offline XP before downgrade'; END IF; END $$")
    op.drop_table("offline_experience_grants")
    op.drop_table("experience_roster_snapshots")
    op.drop_table("course_management_settings")
