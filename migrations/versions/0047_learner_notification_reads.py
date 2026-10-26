"""Persist read state for learner review-result reminders."""
from alembic import op
import sqlalchemy as sa

revision = "0047_learner_notification_reads"
down_revision = "0046_learner_phone_display"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("learner_notification_reads",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("learner_id", sa.Uuid(), primary_key=True),
        sa.Column("review_id", sa.Uuid(), sa.ForeignKey("reviews.id"), primary_key=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["learner_id", "organization_id"],
                                ["users.id", "users.organization_id"],
                                name="fk_learner_notification_read_owner"))


def downgrade():
    op.drop_table("learner_notification_reads")
