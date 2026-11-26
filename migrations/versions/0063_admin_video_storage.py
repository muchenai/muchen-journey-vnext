"""Store large task and course assets in bounded chunks."""
import sqlalchemy as sa
from alembic import op

revision = "0063_admin_video_storage"
down_revision = "0062_course_workspace"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("academy_videos", "knowledge_files", "exploration_materials"):
        op.alter_column(table, "size", type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False)
    op.add_column("exploration_materials", sa.Column("purpose", sa.String(16), nullable=False, server_default="exploration"))
    op.add_column("exploration_materials", sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("exploration_materials", sa.Column("chunked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("exploration_material_chunks",
        sa.Column("material_id", sa.Uuid(), sa.ForeignKey("exploration_materials.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False))


def downgrade():
    conn = op.get_bind()
    if conn.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM exploration_materials WHERE chunked)")):
        raise RuntimeError("Cannot downgrade while chunked course or task files are stored.")
    for table in ("academy_videos", "knowledge_files", "exploration_materials"):
        op.alter_column(table, "size", type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False)
    op.drop_table("exploration_material_chunks")
    for column in ("chunked", "complete", "purpose"):
        op.drop_column("exploration_materials", column)
