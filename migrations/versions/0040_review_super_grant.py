"""Separate privileged grant authority from the ordinary super-admin role."""
from alembic import op
import sqlalchemy as sa

revision = "0040_review_super_grant"
down_revision = "0039_review_admin_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("review_admin_access", sa.Column(
        "can_grant_super_admin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("review_admin_access", "can_grant_super_admin")
