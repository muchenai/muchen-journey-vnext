"""Bind signed module content packages to immutable Journey and Task versions.

Revision ID: 0024_module_content_binding
Revises: 0023_controlled_task_acceptance
"""

import sqlalchemy as sa
from alembic import op


revision = "0024_module_content_binding"
down_revision = "0023_controlled_task_acceptance"
branch_labels = None
depends_on = None


def _user_scope_fk(column: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column, "organization_id"],
        ["users.id", "users.organization_id"],
        name=name,
    )


def upgrade() -> None:
    op.create_table(
        "module_content_package_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("journey_version_id", sa.Uuid(), nullable=False),
        sa.Column("task_version_id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.String(length=120), nullable=False),
        sa.Column("package_version", sa.String(length=40), nullable=False),
        sa.Column("module_key", sa.String(length=40), nullable=False),
        sa.Column("package_sha256", sa.String(length=64), nullable=False),
        sa.Column("task_package_sha256", sa.String(length=64), nullable=False),
        sa.Column("rubric_package_sha256", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("owner_role", sa.String(length=50), nullable=False),
        sa.Column("owner_signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("reviewer_pool_ref", sa.String(length=120), nullable=False),
        sa.Column("primary_reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("backup_reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("first_response_sla_minutes", sa.Integer(), nullable=False),
        sa.Column("completion_sla_minutes", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.JSON(), nullable=False),
        sa.Column("data_classification", sa.String(length=40), nullable=False),
        sa.Column("retention_policy", sa.String(length=120), nullable=False),
        sa.Column("package_document", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_module_content_package_bindings"),
        sa.UniqueConstraint(
            "organization_id",
            "package_id",
            "package_version",
            name="uq_mcpb_package_version",
        ),
        sa.UniqueConstraint(
            "journey_version_id", name="uq_mcpb_journey_version"
        ),
        sa.CheckConstraint(
            "module_key IN ('ai-academy','delivery-guild')",
            name="ck_mcpb_initial_modules",
        ),
        sa.CheckConstraint(
            "package_sha256 ~ '^[0-9a-f]{64}$' AND "
            "task_package_sha256 ~ '^[0-9a-f]{64}$' AND "
            "rubric_package_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_mcpb_hashes",
        ),
        sa.CheckConstraint(
            "owner_user_id <> primary_reviewer_user_id AND "
            "owner_user_id <> backup_reviewer_user_id AND "
            "primary_reviewer_user_id <> backup_reviewer_user_id",
            name="ck_mcpb_separation_of_duties",
        ),
        sa.CheckConstraint(
            "first_response_sla_minutes >= 1 AND "
            "completion_sla_minutes >= first_response_sla_minutes",
            name="ck_mcpb_sla",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_mcpb_validity",
        ),
        sa.CheckConstraint(
            "package_document->>'sha256' = package_sha256 AND "
            "package_document->>'package_id' = package_id AND "
            "package_document->>'version' = package_version AND "
            "package_document->>'module_key' = module_key AND "
            "package_document->'task_versions'->0->>'sha256' = task_package_sha256 AND "
            "package_document->'rubrics'->0->>'sha256' = rubric_package_sha256",
            name="ck_mcpb_document_lineage",
        ),
        sa.CheckConstraint(
            "package_document->'data_policy'->>'production_write_allowed' = 'false' AND "
            "package_document->'data_policy'->>'raw_customer_data_allowed' = 'false' AND "
            "package_document->'data_policy'->>'ai_high_impact_decision_allowed' = 'false' AND "
            "package_document->'task_versions'->0->>'execution_environment' = 'SIMULATION'",
            name="ck_mcpb_safety_boundary",
        ),
        sa.ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_mcpb_journey_version_scope",
        ),
        sa.ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_mcpb_task_version_scope",
        ),
        _user_scope_fk("owner_user_id", "fk_mcpb_owner_scope"),
        _user_scope_fk("primary_reviewer_user_id", "fk_mcpb_primary_reviewer_scope"),
        _user_scope_fk("backup_reviewer_user_id", "fk_mcpb_backup_reviewer_scope"),
        _user_scope_fk("created_by_user_id", "fk_mcpb_created_by_scope"),
    )
    op.create_index(
        "ix_mcpb_organization_module",
        "module_content_package_bindings",
        ["organization_id", "module_key"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_module_content_package_binding_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'module content package bindings are immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_module_content_package_bindings_immutable
        BEFORE UPDATE OR DELETE ON module_content_package_bindings
        FOR EACH ROW EXECUTE FUNCTION reject_module_content_package_binding_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_module_content_package_bindings_immutable "
        "ON module_content_package_bindings"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS reject_module_content_package_binding_mutation()"
    )
    op.drop_index("ix_mcpb_organization_module", table_name="module_content_package_bindings")
    op.drop_table("module_content_package_bindings")
