"""Record company learners' XP exchanges for local mall points."""
import sqlalchemy as sa
from alembic import op

revision = "0064_profile_mall_points"
down_revision = "0063_admin_video_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mall_point_exchanges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("points", sa.BigInteger(), nullable=False),
        sa.Column("spent_xp", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"]),
        sa.UniqueConstraint("organization_id", "user_id", "request_key", name="uq_mall_point_exchange_request"),
        sa.CheckConstraint("points > 0 AND spent_xp > 0 AND spent_xp % points = 0", name="ck_mall_exchange_amounts"),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM mall_point_exchanges)")):
        raise RuntimeError("Cannot downgrade while recorded mall point exchanges exist.")
    op.drop_table("mall_point_exchanges")
