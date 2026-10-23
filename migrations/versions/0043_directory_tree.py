"""Keep department ancestry in the same committed directory snapshot as members."""
from alembic import op
import sqlalchemy as sa

revision = '0043_directory_tree'
down_revision = '0042_directory_cache'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('directory_sync', sa.Column('department_tree', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('directory_sync', 'department_tree')
