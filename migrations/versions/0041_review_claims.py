"""Add exclusive, expiring reviewer claims without changing historical decisions."""
from alembic import op
import sqlalchemy as sa

revision = "0041_review_claims"
down_revision = "0040_review_super_grant"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("review_claims",
        sa.Column("review_id", sa.Uuid(), sa.ForeignKey("reviews.id"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_review_claims_organization_id", "review_claims", ["organization_id"])


def downgrade():
    op.drop_table("review_claims")
