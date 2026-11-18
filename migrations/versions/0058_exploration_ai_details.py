"""Retain dynamic AI input, comment delivery and idempotent attempt metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0058_exploration_ai_details"
down_revision = "0057_dynamic_exploration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("exploration_self_checks", sa.Column("details", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM exploration_self_checks WHERE details::text <> '{}')")).scalar():
        raise RuntimeError("AI delivery metadata exists; refusing to discard durable comment state.")
    op.drop_column("exploration_self_checks", "details")
