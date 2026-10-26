"""Store verified learner phone numbers encrypted for scoped review display."""
from alembic import op
import sqlalchemy as sa

revision = "0046_learner_phone_display"
down_revision = "0045_admin_feedback_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("external_identities", sa.Column("phone_ciphertext", sa.Text(), nullable=False, server_default=""))


def downgrade():
    op.drop_column("external_identities", "phone_ciphertext")
