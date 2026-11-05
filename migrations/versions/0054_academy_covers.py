"""Cache generated course covers without storing third-party media URLs."""
from alembic import op
import sqlalchemy as sa

revision = '0054_academy_covers'
down_revision = '0053_academy'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('academy_course_covers',
        sa.Column('course_id', sa.Uuid(), sa.ForeignKey('academy_courses.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('source_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('claim_id', sa.Uuid()),
        sa.Column('data', sa.LargeBinary()),
        sa.Column('sha256', sa.String(64)),
        sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    # These images are reproducible derivatives; original courses and videos remain.
    op.drop_table('academy_course_covers')
