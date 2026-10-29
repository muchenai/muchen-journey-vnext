"""Persistent publication approvals, separate from learner answer reviews."""
from alembic import op
import sqlalchemy as sa

revision = '0050_task_publication_requests'
down_revision = '0049_medal_economy'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('task_publication_requests',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False, index=True),
        sa.Column('task_id', sa.Uuid(), sa.ForeignKey('task_definitions.id'), nullable=False, index=True),
        sa.Column('submitted_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('task_revision', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('verified_material_urls', sa.JSON(), nullable=False),
        sa.Column('comment', sa.String(1000), nullable=False),
        sa.Column('reviewed_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('task_id', 'task_revision', name='uq_publication_task_revision'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='ck_publication_status'))
    op.create_index('uq_pending_publication', 'task_publication_requests', ['task_id'], unique=True,
        postgresql_where=sa.text("status = 'pending'"))

def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM task_publication_requests) THEN RAISE EXCEPTION 'Preserve publication history before downgrade'; END IF; END $$")
    op.drop_table('task_publication_requests')
