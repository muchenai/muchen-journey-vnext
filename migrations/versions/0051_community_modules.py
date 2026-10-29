"""Persist knowledge files and delivery guild management."""
from alembic import op
import sqlalchemy as sa

revision = '0051_community_modules'
down_revision = '0050_task_publication_requests'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('community_states',
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('module', sa.String(20), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False))
    op.create_table('knowledge_files',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False, index=True),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('knowledge_chunks',
        sa.Column('file_id', sa.Uuid(), sa.ForeignKey('knowledge_files.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('position', sa.Integer(), primary_key=True),
        sa.Column('data', sa.LargeBinary(), nullable=False))
    op.create_table('guild_contributions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False, index=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('task_id', sa.Uuid(), sa.ForeignKey('task_definitions.id'), nullable=False),
        sa.Column('evaluation_id', sa.Uuid(), sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.UniqueConstraint('organization_id','user_id','task_id', name='uq_guild_first_completion'))


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM community_states) OR EXISTS (SELECT 1 FROM knowledge_files) OR EXISTS (SELECT 1 FROM guild_contributions) THEN RAISE EXCEPTION 'Preserve community data before downgrade'; END IF; END $$")
    for table in ['guild_contributions','knowledge_chunks','knowledge_files','community_states']:
        op.drop_table(table)
