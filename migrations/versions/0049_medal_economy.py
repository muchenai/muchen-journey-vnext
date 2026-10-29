"""Durable badge catalog, redemption snapshots and one-time task unlock debits."""
from alembic import op
import sqlalchemy as sa

revision = "0049_medal_economy"
down_revision = "0048_novice_task_claims"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("medal_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("medal_redemptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("medal_id", sa.Uuid(), sa.ForeignKey("medal_definitions.id"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", "medal_id", name="uq_medal_owner_once"))
    op.create_table("novice_unlock_debits",
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("enrollments.id"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_unlock_debit_positive"))
    op.execute("""CREATE FUNCTION reject_economy_history_change() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Economy history is immutable'; END; $$ LANGUAGE plpgsql""")
    for table in ["medal_redemptions", "novice_unlock_debits"]:
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_economy_history_change()")

def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM medal_redemptions) OR EXISTS (SELECT 1 FROM novice_unlock_debits)
        THEN RAISE EXCEPTION 'Economy activity exists; preserve before downgrade'; END IF; END $$""")
    op.drop_table("novice_unlock_debits")
    op.drop_table("medal_redemptions")
    op.drop_table("medal_definitions")
    op.execute("DROP FUNCTION reject_economy_history_change()")
