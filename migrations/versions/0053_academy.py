"""Persist AI Academy publishing, employee reviews, media and learning records."""
from alembic import op
import sqlalchemy as sa

revision = '0053_academy'
down_revision = '0052_knowledge_publication'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('academy_videos',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(80), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('complete', sa.Boolean(), nullable=False),
        sa.Column('sha256', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_academy_videos_organization_id', 'academy_videos', ['organization_id'])
    op.create_table('academy_video_chunks',
        sa.Column('video_id', sa.Uuid(), sa.ForeignKey('academy_videos.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('position', sa.Integer(), primary_key=True),
        sa.Column('data', sa.LargeBinary(), nullable=False))
    op.create_table('academy_courses',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('author_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('visibility', sa.String(16), nullable=False),
        sa.Column('review_status', sa.String(16)),
        sa.Column('review_reason', sa.String(), nullable=False),
        sa.Column('reviewed_by', sa.Uuid(), sa.ForeignKey('users.id')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('video_id', sa.Uuid(), sa.ForeignKey('academy_videos.id')),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_academy_courses_organization_id', 'academy_courses', ['organization_id'])
    op.create_index('ix_academy_courses_video_id', 'academy_courses', ['video_id'])
    op.create_table('academy_learning_records',
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('course_id', sa.Uuid(), sa.ForeignKey('academy_courses.id'), primary_key=True),
        sa.Column('favorite', sa.Boolean(), nullable=False),
        sa.Column('seconds', sa.Float(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM academy_courses) OR EXISTS (SELECT 1 FROM academy_learning_records) OR EXISTS (SELECT 1 FROM academy_videos) THEN RAISE EXCEPTION 'Preserve academy data before downgrade'; END IF; END $$")
    for table in ['academy_learning_records', 'academy_courses', 'academy_video_chunks', 'academy_videos']:
        op.drop_table(table)
