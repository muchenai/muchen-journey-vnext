"""Explicit Review administrators, without automatic privilege elevation."""
from alembic import op
import sqlalchemy as sa

revision = "0039_review_admin_access"
down_revision = "0038_review_admin_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("review_admin_access",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("access_role", sa.String(20), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"]),
        sa.CheckConstraint("access_role IN ('super_admin', 'admin')"),
        sa.CheckConstraint("level IN ('初级', '中级', '高级')"))
    op.create_index("ix_review_admin_access_organization_id", "review_admin_access", ["organization_id"])


def downgrade():
    op.drop_table("review_admin_access")
