"""Persist app-scoped directory snapshots and synchronization status."""
from alembic import op
import sqlalchemy as sa

revision = '0042_directory_cache'
down_revision = '0041_review_claims'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('directory_sync',
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('app_id', sa.String(100), primary_key=True),
        sa.Column('last_success', sa.DateTime(timezone=True)),
        sa.Column('last_attempt', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('requested_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.String(100)),
        sa.Column('member_count', sa.Integer(), nullable=False))
    op.create_table('directory_members',
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('app_id', sa.String(100), primary_key=True),
        sa.Column('open_id', sa.String(180), primary_key=True),
        sa.Column('search_name', sa.String(255), nullable=False),
        sa.Column('profile', sa.JSON(), nullable=False))
    op.create_index('ix_directory_members_search', 'directory_members', ['organization_id', 'app_id', 'search_name'])


def downgrade():
    op.drop_table('directory_members')
    op.drop_table('directory_sync')
