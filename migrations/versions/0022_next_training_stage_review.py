"""Add non-admission next-training-stage decisions and review-request intake.

Revision ID: 0022_next_training_stage_review
Revises: 0021_incentive_ledger
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0022_next_training_stage_review"
down_revision = "0021_incentive_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_handoffs_next_stage_scope",
        "handoffs",
        ["id", "organization_id", "outcome_id"],
    )
    op.create_table(
        "next_training_stage_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_id", sa.Uuid(), nullable=False),
        sa.Column("outcome_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("decision_scope", sa.String(length=40), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision_evidence_ref", sa.String(length=500), nullable=False),
        sa.Column("decision_evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision_scope = 'NEXT_TRAINING_STAGE'", name="ck_ntsd_scope"
        ),
        sa.CheckConstraint(
            "decision IN ('READY', 'DEFER', 'NOT_READY')",
            name="ck_ntsd_decision",
        ),
        sa.CheckConstraint(
            "length(trim(decision_reason)) BETWEEN 10 AND 2000",
            name="ck_ntsd_reason",
        ),
        sa.CheckConstraint(
            "decision_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ntsd_evidence_sha256",
        ),
        sa.CheckConstraint(
            "length(trim(decision_evidence_ref)) BETWEEN 3 AND 500",
            name="ck_ntsd_evidence_ref",
        ),
        sa.CheckConstraint(
            "decided_by_user_id <> person_id", name="ck_ntsd_human_independence"
        ),
        sa.ForeignKeyConstraint(
            ["handoff_id", "organization_id", "outcome_id"],
            ["handoffs.id", "handoffs.organization_id", "handoffs.outcome_id"],
            name="fk_ntsd_handoff_scope",
        ),
        sa.ForeignKeyConstraint(
            ["outcome_id", "organization_id", "person_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_ntsd_outcome_person_scope",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsd_decider_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "handoff_id",
            "decision_scope",
            name="uq_ntsd_handoff_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "handoff_id",
            "decision_scope",
            "decision",
            name="uq_ntsd_review_request_scope",
        ),
    )
    for column in ("organization_id", "handoff_id", "outcome_id", "person_id"):
        op.create_index(
            f"ix_next_training_stage_decisions_{column}",
            "next_training_stage_decisions",
            [column],
        )
    op.create_table(
        "next_training_stage_review_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_id", sa.Uuid(), nullable=False),
        sa.Column("next_training_stage_decision_id", sa.Uuid(), nullable=False),
        sa.Column("decision_scope", sa.String(length=40), nullable=False),
        sa.Column("source_decision", sa.String(length=20), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision_scope = 'NEXT_TRAINING_STAGE'", name="ck_ntsrr_scope"
        ),
        sa.CheckConstraint(
            "source_decision IN ('DEFER', 'NOT_READY')",
            name="ck_ntsrr_adverse_decision",
        ),
        sa.CheckConstraint("status = 'RECEIVED'", name="ck_ntsrr_received_only"),
        sa.CheckConstraint(
            "length(trim(reason)) BETWEEN 10 AND 2000", name="ck_ntsrr_reason"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_refs) = 'array' AND jsonb_array_length(evidence_refs) <= 20",
            name="ck_ntsrr_evidence_refs",
        ),
        sa.ForeignKeyConstraint(
            [
                "next_training_stage_decision_id",
                "organization_id",
                "handoff_id",
                "decision_scope",
                "source_decision",
            ],
            [
                "next_training_stage_decisions.id",
                "next_training_stage_decisions.organization_id",
                "next_training_stage_decisions.handoff_id",
                "next_training_stage_decisions.decision_scope",
                "next_training_stage_decisions.decision",
            ],
            name="fk_ntsrr_adverse_decision",
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsrr_requester_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "next_training_stage_decision_id",
            "requester_user_id",
            name="uq_ntsrr_decision_person",
        ),
    )
    request_indexes = {
        "organization_id": "ix_ntsrr_organization",
        "handoff_id": "ix_ntsrr_handoff",
        "next_training_stage_decision_id": "ix_ntsrr_decision",
        "requester_user_id": "ix_ntsrr_requester",
    }
    for column, index_name in request_indexes.items():
        op.create_index(
            index_name,
            "next_training_stage_review_requests",
            [column],
        )
    op.execute(
        """
        CREATE FUNCTION validate_next_training_stage_decision() RETURNS trigger AS $$
        DECLARE
            formal_evaluation_count integer;
        BEGIN
            SELECT count(DISTINCT joe.journey_stage_version_id)
              INTO formal_evaluation_count
              FROM journey_outcome_evidence joe
              JOIN evaluations e
                ON e.id = joe.evaluation_id
               AND e.organization_id = joe.organization_id
             WHERE joe.outcome_id = NEW.outcome_id
               AND joe.organization_id = NEW.organization_id
               AND e.decision = 'PASS';
            IF formal_evaluation_count <> 3 THEN
                RAISE EXCEPTION 'next training stage decision requires exactly three fixed PASS human evaluations';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ntsd_validate_formal_basis
        BEFORE INSERT ON next_training_stage_decisions
        FOR EACH ROW EXECUTE FUNCTION validate_next_training_stage_decision();

        CREATE FUNCTION validate_next_training_stage_review_request() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM jsonb_array_elements(NEW.evidence_refs) item
                 WHERE jsonb_typeof(item) <> 'string'
                    OR length(trim(item #>> '{}')) NOT BETWEEN 3 AND 300
            ) THEN
                RAISE EXCEPTION 'review request evidence references must be bounded strings';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                  FROM next_training_stage_decisions d
                  JOIN outcomes o
                    ON o.id = d.outcome_id
                   AND o.organization_id = d.organization_id
                 WHERE d.id = NEW.next_training_stage_decision_id
                   AND d.organization_id = NEW.organization_id
                   AND d.handoff_id = NEW.handoff_id
                   AND o.learner_id = NEW.requester_user_id
            ) THEN
                RAISE EXCEPTION 'review request must belong to the target person';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ntsrr_validate_person
        BEFORE INSERT ON next_training_stage_review_requests
        FOR EACH ROW EXECUTE FUNCTION validate_next_training_stage_review_request();

        CREATE FUNCTION reject_next_training_stage_fact_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'next training stage decision and review request facts are immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ntsd_immutable
        BEFORE UPDATE OR DELETE ON next_training_stage_decisions
        FOR EACH ROW EXECUTE FUNCTION reject_next_training_stage_fact_mutation();

        CREATE TRIGGER trg_ntsrr_immutable
        BEFORE UPDATE OR DELETE ON next_training_stage_review_requests
        FOR EACH ROW EXECUTE FUNCTION reject_next_training_stage_fact_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER trg_ntsrr_immutable ON next_training_stage_review_requests;
        DROP TRIGGER trg_ntsd_immutable ON next_training_stage_decisions;
        DROP FUNCTION reject_next_training_stage_fact_mutation();
        DROP TRIGGER trg_ntsrr_validate_person ON next_training_stage_review_requests;
        DROP FUNCTION validate_next_training_stage_review_request();
        DROP TRIGGER trg_ntsd_validate_formal_basis ON next_training_stage_decisions;
        DROP FUNCTION validate_next_training_stage_decision();
        """
    )
    op.drop_table("next_training_stage_review_requests")
    op.drop_table("next_training_stage_decisions")
    op.drop_constraint(
        "uq_handoffs_next_stage_scope", "handoffs", type_="unique"
    )
