"""Separate eight guilds without attributing legacy global certifications."""
from alembic import op
import sqlalchemy as sa

revision = "0056_guild_halls"
down_revision = "0055_guild_certification"
branch_labels = None
depends_on = None


def account_columns():
    return [sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True)]


def upgrade():
    op.add_column("guild_certification_requests", sa.Column("guild_id", sa.String(40)))
    op.add_column("guild_certification_requests", sa.Column("task_snapshot", sa.JSON()))
    op.create_check_constraint("ck_guild_request_task_scope", "guild_certification_requests",
        "(guild_id IS NULL AND task_snapshot IS NULL) OR (guild_id IS NOT NULL AND task_snapshot IS NOT NULL)")
    for name in ("uq_guild_pending_request", "uq_guild_approved_level"):
        op.drop_index(name, table_name="guild_certification_requests")
    for name, columns, predicate in [
        ("uq_guild_pending_request", ["organization_id", "user_id"], "status = 'pending' AND guild_id IS NULL"),
        ("uq_guild_approved_level", ["organization_id", "user_id", "level"], "status = 'approved' AND guild_id IS NULL"),
        ("uq_guild_scoped_pending", ["organization_id", "user_id", "guild_id"], "status = 'pending' AND guild_id IS NOT NULL"),
        ("uq_guild_scoped_approved", ["organization_id", "user_id", "guild_id", "level"], "status = 'approved' AND guild_id IS NOT NULL"),
    ]:
        op.create_index(name, "guild_certification_requests", columns, unique=True, postgresql_where=sa.text(predicate))
    op.create_table("guild_memberships", *account_columns(),
        sa.Column("guild_id", sa.String(40), primary_key=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("guild_selections", *account_columns(), sa.Column("guild_id", sa.String(40), nullable=False))
    op.create_table("guild_task_submissions", *account_columns(),
        sa.Column("guild_id", sa.String(40), primary_key=True), sa.Column("level", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(80), nullable=False), sa.Column("task_version", sa.Integer(), nullable=False),
        sa.Column("artifact", sa.Text(), nullable=False), sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name="ck_guild_submission_level"),
        sa.CheckConstraint("revision > 0", name="ck_guild_submission_revision"),
        sa.CheckConstraint("status IN ('draft','submitted')", name="ck_guild_submission_status"),
        sa.CheckConstraint("(status = 'draft' AND submitted_at IS NULL) OR (status = 'submitted' AND submitted_at IS NOT NULL)", name="ck_guild_submission_time"))


def downgrade():
    connection = op.get_bind()
    for table in ("guild_memberships", "guild_selections", "guild_task_submissions"):
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("Guild progress exists; refusing a destructive downgrade.")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM guild_certification_requests WHERE guild_id IS NOT NULL)")).scalar():
        raise RuntimeError("Scoped certification history exists; refusing a destructive downgrade.")
    for table in ("guild_task_submissions", "guild_selections", "guild_memberships"):
        op.drop_table(table)
    for name in ("uq_guild_pending_request", "uq_guild_approved_level", "uq_guild_scoped_pending", "uq_guild_scoped_approved"):
        op.drop_index(name, table_name="guild_certification_requests")
    op.drop_constraint("ck_guild_request_task_scope", "guild_certification_requests")
    op.drop_column("guild_certification_requests", "task_snapshot")
    op.drop_column("guild_certification_requests", "guild_id")
    op.create_index("uq_guild_pending_request", "guild_certification_requests", ["organization_id", "user_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index("uq_guild_approved_level", "guild_certification_requests", ["organization_id", "user_id", "level"], unique=True, postgresql_where=sa.text("status = 'approved'"))
