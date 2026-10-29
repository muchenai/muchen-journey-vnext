"""Independent novice claims and immutable published presentation metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0048_novice_task_claims"
down_revision = "0047_learner_notification_reads"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("enrollments", sa.Column("novice_task_id", sa.Uuid(),
        sa.ForeignKey("task_definitions.id"), nullable=True))
    op.create_unique_constraint("uq_novice_claim_owner_task", "enrollments",
        ["organization_id", "learner_id", "novice_task_id"])
    op.drop_index("uq_enrollments_active_learner", table_name="enrollments")
    op.create_index("uq_enrollments_active_learner", "enrollments",
        ["organization_id", "learner_id"], unique=True,
        postgresql_where=sa.text("status IN ('PENDING_IDENTITY', 'ACTIVE') AND novice_task_id IS NULL"))
    op.create_table("published_task_content",
        sa.Column("task_version_id", sa.Uuid(), sa.ForeignKey("task_versions.id"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False))
    # Only published drafts reliably describe the current published version.
    op.execute("""INSERT INTO published_task_content (task_version_id, organization_id, content)
        SELECT v.id, v.organization_id, p.content FROM review_admin_tasks p
        JOIN task_versions v ON v.task_definition_id=p.task_definition_id AND v.organization_id=p.organization_id
        WHERE p.status='published' AND v.version=(SELECT max(v2.version) FROM task_versions v2
            WHERE v2.task_definition_id=v.task_definition_id)""")
    op.execute("""CREATE FUNCTION reject_published_task_content_change() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Published task content is immutable'; END;
        $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER published_task_content_immutable BEFORE UPDATE OR DELETE
        ON published_task_content FOR EACH ROW EXECUTE FUNCTION reject_published_task_content_change()""")


def downgrade():
    # Do not silently discard learner activity during a downgrade.
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM enrollments WHERE novice_task_id IS NOT NULL)
        THEN RAISE EXCEPTION 'Novice claims exist; preserve learner activity before downgrade'; END IF; END $$""")
    op.drop_table("published_task_content")
    op.execute("DROP FUNCTION reject_published_task_content_change()")
    op.drop_index("uq_enrollments_active_learner", table_name="enrollments")
    op.create_index("uq_enrollments_active_learner", "enrollments", ["organization_id", "learner_id"],
        unique=True, postgresql_where=sa.text("status IN ('PENDING_IDENTITY', 'ACTIVE')"))
    op.drop_constraint("uq_novice_claim_owner_task", "enrollments", type_="unique")
    op.drop_column("enrollments", "novice_task_id")
