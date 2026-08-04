"""Add scoped content-editor drafts for the WP-26 real learning slice.

Revision ID: 0018_wp26_content_drafts
Revises: 0017_wp26_material_completion
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_wp26_content_drafts"
down_revision = "0017_wp26_material_completion"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def _replace_check(table: str, name: str, expression: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    _replace_check(
        "role_assignments",
        "ck_role_assignments_role",
        "role IN ('LEARNER', 'REVIEWER', 'OPERATOR', 'CONTENT_EDITOR')",
    )
    _replace_check(
        "identity_sessions",
        "ck_identity_sessions_role",
        "role IN ('LEARNER', 'REVIEWER', 'OPERATOR', 'CONTENT_EDITOR')",
    )
    _replace_check(
        "external_identity_links",
        "ck_identity_links_role",
        "role IN ('REVIEWER', 'OPERATOR', 'CONTENT_EDITOR')",
    )
    _replace_check(
        "oauth_login_states",
        "ck_oauth_login_states_return_to",
        "return_to IN ('/review', '/ops', '/content')",
    )

    op.create_table(
        "content_drafts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "task_definition_id",
            UUID,
            sa.ForeignKey("task_definitions.id"),
            nullable=False,
        ),
        sa.Column("owner_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("submitted_at", TIMESTAMP, nullable=True),
        sa.Column("published_at", TIMESTAMP, nullable=True),
        sa.Column(
            "published_task_version_id",
            UUID,
            sa.ForeignKey("task_versions.id"),
            nullable=True,
        ),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'PUBLISHED')",
            name="ck_content_drafts_status",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_content_drafts_positive_revision"
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND submitted_at IS NULL AND published_at IS NULL "
            "AND published_task_version_id IS NULL) OR "
            "(status = 'SUBMITTED' AND submitted_at IS NOT NULL AND published_at IS NULL "
            "AND published_task_version_id IS NULL) OR "
            "(status = 'PUBLISHED' AND submitted_at IS NOT NULL AND published_at IS NOT NULL "
            "AND published_task_version_id IS NOT NULL)",
            name="ck_content_drafts_lifecycle",
        ),
        sa.UniqueConstraint(
            "published_task_version_id",
            name="uq_content_drafts_published_task_version",
        ),
    )
    op.create_index(
        "ix_content_drafts_organization_id", "content_drafts", ["organization_id"]
    )
    op.create_index(
        "ix_content_drafts_task_definition_id",
        "content_drafts",
        ["task_definition_id"],
    )
    op.create_index("ix_content_drafts_owner_id", "content_drafts", ["owner_id"])
    op.create_index("ix_content_drafts_status", "content_drafts", ["status"])
    op.execute(
        """
        CREATE FUNCTION reject_content_draft_rewrite() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND OLD.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'submitted content draft is immutable';
          END IF;
          IF TG_OP = 'UPDATE' AND OLD.status <> 'DRAFT' THEN
            IF NOT (
              OLD.status = 'SUBMITTED'
              AND NEW.status = 'PUBLISHED'
              AND NEW.organization_id = OLD.organization_id
              AND NEW.task_definition_id = OLD.task_definition_id
              AND NEW.owner_id = OLD.owner_id
              AND NEW.content::text = OLD.content::text
              AND NEW.submitted_at = OLD.submitted_at
              AND NEW.published_at IS NOT NULL
              AND NEW.published_task_version_id IS NOT NULL
              AND NEW.revision = OLD.revision + 1
            ) THEN
              RAISE EXCEPTION 'submitted content draft is immutable';
            END IF;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_content_drafts_immutable
        BEFORE UPDATE OR DELETE ON content_drafts
        FOR EACH ROW EXECUTE FUNCTION reject_content_draft_rewrite();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_content_drafts_immutable ON content_drafts"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_content_draft_rewrite()")
    op.drop_table("content_drafts")
    _replace_check(
        "oauth_login_states",
        "ck_oauth_login_states_return_to",
        "return_to IN ('/review', '/ops')",
    )
    _replace_check(
        "external_identity_links",
        "ck_identity_links_role",
        "role IN ('REVIEWER', 'OPERATOR')",
    )
    _replace_check(
        "identity_sessions",
        "ck_identity_sessions_role",
        "role IN ('LEARNER', 'REVIEWER', 'OPERATOR')",
    )
    _replace_check(
        "role_assignments",
        "ck_role_assignments_role",
        "role IN ('LEARNER', 'REVIEWER', 'OPERATOR')",
    )
