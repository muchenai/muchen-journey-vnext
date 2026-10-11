"""Persist assigned/shared review mode without changing existing enrollment owners."""
from alembic import op
import sqlalchemy as sa

revision = "0032_shared_learner_review"
down_revision = "0031_learner_feishu_login"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("enrollments", sa.Column("review_assignment_mode", sa.String(16), nullable=False, server_default="ASSIGNED"))
    op.create_check_constraint("ck_enrollments_review_assignment_mode", "enrollments", "review_assignment_mode IN ('ASSIGNED', 'SHARED')")


def downgrade():
    # Once shared enrollments exist, an older schema would lose their access policy.
    # Require an explicit forward reconciliation instead of silently reassigning them.
    if op.get_bind().execute(sa.text("select exists(select 1 from enrollments where review_assignment_mode='SHARED')")).scalar_one():
        raise RuntimeError("Shared enrollments exist; review policy reconciliation is required before downgrade")
    op.drop_constraint("ck_enrollments_review_assignment_mode", "enrollments", type_="check")
    op.drop_column("enrollments", "review_assignment_mode")
