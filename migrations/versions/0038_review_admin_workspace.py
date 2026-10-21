"""Persist Review UI drafts and metadata alongside existing canonical workflows."""
from alembic import op
import sqlalchemy as sa

revision = "0038_review_admin_workspace"
down_revision = "0037_ai_self_check_revisions"
branch_labels = None
depends_on = None


def upgrade():
    for name, key, target in (("review_admin_tasks", "task_definition_id", "task_definitions.id"),
                              ("review_admin_decisions", "review_id", "reviews.id"),
                              ("review_admin_certifications", "user_id", "users.id")):
        columns = [sa.Column(key, sa.Uuid(), sa.ForeignKey(target), primary_key=True),
                   sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
                   sa.Column("content", sa.JSON(), nullable=False)]
        if name != "review_admin_decisions":
            columns.append(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        if name == "review_admin_tasks":
            columns.extend([sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
                            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())])
        op.create_table(name, *columns)
        op.create_index(f"ix_{name}_organization_id", name, ["organization_id"])


def downgrade():
    for name in ("review_admin_certifications", "review_admin_decisions", "review_admin_tasks"):
        op.drop_table(name)
