"""Persist authored course editions and account-bound course progress."""

from alembic import op
import sqlalchemy as sa

revision = "0062_course_workspace"
down_revision = "0061_management_access"
branch_labels = None
depends_on = None


def ref(name, table, *, primary=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(table + ".id"), primary_key=primary, nullable=False)


def upgrade():
    op.create_table(
        "workspace_courses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        ref("organization_id", "organizations"),
        ref("author_id", "users"),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("live", sa.JSON(none_as_null=True), nullable=True),
    )
    op.create_index("ix_workspace_courses_catalog", "workspace_courses", ["organization_id", "scope"])
    op.create_table(
        "course_study_records",
        ref("course_id", "workspace_courses", primary=True),
        ref("user_id", "users", primary=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    op.create_table(
        "course_study_preferences",
        ref("course_id", "workspace_courses", primary=True),
        ref("user_id", "users", primary=True),
        sa.Column("saved", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "course_roster_codes",
        ref("user_id", "users", primary=True),
        ref("organization_id", "organizations"),
        sa.Column("code", sa.String(40), unique=True, nullable=False),
    )
    op.create_table(
        "course_study_awards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        ref("organization_id", "organizations"),
        ref("user_id", "users"),
        ref("course_id", "workspace_courses"),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("title", sa.String(340), nullable=False),
        sa.Column("award_key", sa.String(120), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "course_id", "award_key", name="uq_course_study_credit"),
    )
    op.create_index("ix_course_study_awards_org_learner", "course_study_awards", ["organization_id", "user_id"])


def downgrade():
    if op.get_bind().scalar(sa.text("""
        SELECT EXISTS (SELECT FROM workspace_courses)
            OR EXISTS (SELECT FROM course_roster_codes)
    """)):
        # All study records, preferences and awards reference workspace_courses.
        raise RuntimeError("Preserve course learning records and roster data before downgrade.")
    for table in (
        "course_study_awards",
        "course_roster_codes",
        "course_study_preferences",
        "course_study_records",
        "workspace_courses",
    ):
        op.drop_table(table)
