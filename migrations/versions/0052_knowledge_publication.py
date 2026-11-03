"""Persist learner knowledge favorites; module publication lives in existing item JSON."""
from alembic import op
import sqlalchemy as sa

revision = '0052_knowledge_publication'
down_revision = '0051_community_modules'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('knowledge_favorites',
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('item_id', sa.Uuid(), primary_key=True))


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM knowledge_favorites) THEN RAISE EXCEPTION 'Preserve knowledge favorites before downgrade'; END IF; END $$")
    op.drop_table('knowledge_favorites')
