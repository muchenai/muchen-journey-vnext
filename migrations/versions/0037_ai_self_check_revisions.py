"""Keep prior AI evaluations while updating a document's original comment."""
from alembic import op
import sqlalchemy as sa

revision = "0037_ai_self_check_revisions"
down_revision = "0036_ai_self_checks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_self_checks", sa.Column("comment_reply_id", sa.String(160), nullable=True))
    op.add_column("ai_self_checks", sa.Column("document_hash", sa.String(64), nullable=False, server_default=""))
    op.add_column("ai_self_checks", sa.Column("archived_results", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("ai_self_checks", "archived_results")
    op.drop_column("ai_self_checks", "document_hash")
    op.drop_column("ai_self_checks", "comment_reply_id")
