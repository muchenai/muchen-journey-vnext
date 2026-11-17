"""Dynamic exploration learning, catalog, treasures and durable materials."""
from alembic import op
import sqlalchemy as sa

revision = "0057_dynamic_exploration"
down_revision = "0056_guild_halls"
branch_labels = None
depends_on = None


def account_columns():
    return [sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True)]


def upgrade():
    op.create_table("exploration_catalog_tasks",
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task_definitions.id"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False))
    op.create_index("ix_exploration_catalog_tasks_organization_id", "exploration_catalog_tasks", ["organization_id"])
    op.create_table("exploration_work", *account_columns(),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("task_definitions.id"), primary_key=True),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("opened_materials", sa.JSON(), nullable=False),
        sa.Column("checkin_confirmed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("assignment_id", name="uq_exploration_work_assignment"))
    op.create_table("exploration_progress", *account_columns(),
        sa.Column("treasures", sa.JSON(), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True)))
    op.create_table("exploration_materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(240), nullable=False), sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False), sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_exploration_materials_organization_id", "exploration_materials", ["organization_id"])
    op.create_table("exploration_self_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("task_version_id", sa.Uuid(), sa.ForeignKey("task_versions.id"), nullable=False),
        sa.Column("answer", sa.String(8000), nullable=False), sa.Column("result", sa.String(20000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for field in ("organization_id", "user_id", "assignment_id"):
        op.create_index("ix_exploration_self_checks_" + field, "exploration_self_checks", [field])


def downgrade():
    for table in ("exploration_work", "exploration_progress", "exploration_self_checks", "exploration_materials", "exploration_catalog_tasks"):
        if op.get_bind().execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Exploration records exist; refusing destructive downgrade.")
    for table in ("exploration_self_checks", "exploration_work", "exploration_progress", "exploration_materials", "exploration_catalog_tasks"):
        op.drop_table(table)
