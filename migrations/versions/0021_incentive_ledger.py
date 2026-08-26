"""Add the append-only incentive ledger isolated from formal results.

Revision ID: 0021_incentive_ledger
Revises: 0020_shared_ai_provenance
"""

import sqlalchemy as sa
from alembic import op


revision = "0021_incentive_ledger"
down_revision = "0020_shared_ai_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incentive_ledger_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("module_key", sa.String(length=40), nullable=False),
        sa.Column("incentive_type", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("source_outcome_id", sa.Uuid(), nullable=False),
        sa.Column("rule_ref", sa.String(length=300), nullable=False),
        sa.Column("rule_sha256", sa.String(length=64), nullable=False),
        sa.Column("correction_of_entry_id", sa.Uuid(), nullable=True),
        sa.Column("correction_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "module_key IN ('exploration-camp', 'newcomer-village', "
            "'ai-academy', 'delivery-guild', 'certification-arena', 'career-map')",
            name="ck_incentive_entries_module_key",
        ),
        sa.CheckConstraint(
            "(incentive_type IN ('POINTS', 'XP') AND amount IS NOT NULL "
            "AND amount <> 0 AND label IS NULL) OR "
            "(incentive_type IN ('BADGE', 'RANK') AND amount IS NULL "
            "AND length(trim(label)) BETWEEN 1 AND 120)",
            name="ck_incentive_entries_value_shape",
        ),
        sa.CheckConstraint(
            "(correction_of_entry_id IS NULL AND correction_reason IS NULL) OR "
            "(correction_of_entry_id IS NOT NULL "
            "AND length(trim(correction_reason)) BETWEEN 10 AND 500)",
            name="ck_incentive_entries_correction_shape",
        ),
        sa.CheckConstraint(
            "rule_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_incentive_entries_rule_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_incentive_entries_person_organization",
        ),
        sa.ForeignKeyConstraint(
            ["created_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_incentive_entries_creator_organization",
        ),
        sa.ForeignKeyConstraint(
            ["source_outcome_id", "organization_id", "person_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_incentive_entries_outcome_person_scope",
        ),
        sa.ForeignKeyConstraint(
            ["correction_of_entry_id"],
            ["incentive_ledger_entries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_incentive_entries_id_organization"
        ),
    )
    for column in ("organization_id", "person_id", "source_outcome_id"):
        op.create_index(
            f"ix_incentive_ledger_entries_{column}",
            "incentive_ledger_entries",
            [column],
        )
    op.execute(
        """
        CREATE FUNCTION validate_incentive_ledger_entry() RETURNS trigger AS $$
        DECLARE
            original incentive_ledger_entries%ROWTYPE;
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM outcomes o
                JOIN evaluations e
                  ON e.id = o.source_evaluation_id
                 AND e.organization_id = o.organization_id
                WHERE o.id = NEW.source_outcome_id
                  AND o.organization_id = NEW.organization_id
                  AND o.learner_id = NEW.person_id
                  AND o.status = 'HANDOFF_READY'
                  AND e.decision = 'PASS'
            ) THEN
                RAISE EXCEPTION 'incentive source must be an immutable outcome backed by a PASS human evaluation for the same person and organization';
            END IF;
            IF NEW.correction_of_entry_id IS NOT NULL THEN
                SELECT * INTO original
                FROM incentive_ledger_entries
                WHERE id = NEW.correction_of_entry_id;
                IF NOT FOUND
                   OR original.organization_id <> NEW.organization_id
                   OR original.person_id <> NEW.person_id
                   OR original.module_key <> NEW.module_key
                   OR original.incentive_type <> NEW.incentive_type
                   OR original.source_outcome_id <> NEW.source_outcome_id THEN
                    RAISE EXCEPTION 'incentive correction must preserve original scope and source';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_incentive_ledger_validate
        BEFORE INSERT ON incentive_ledger_entries
        FOR EACH ROW EXECUTE FUNCTION validate_incentive_ledger_entry();

        CREATE FUNCTION reject_incentive_ledger_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'incentive ledger entries are immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_incentive_ledger_immutable
        BEFORE UPDATE OR DELETE ON incentive_ledger_entries
        FOR EACH ROW EXECUTE FUNCTION reject_incentive_ledger_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER trg_incentive_ledger_immutable ON incentive_ledger_entries;
        DROP FUNCTION reject_incentive_ledger_mutation();
        DROP TRIGGER trg_incentive_ledger_validate ON incentive_ledger_entries;
        DROP FUNCTION validate_incentive_ledger_entry();
        """
    )
    op.drop_table("incentive_ledger_entries")
