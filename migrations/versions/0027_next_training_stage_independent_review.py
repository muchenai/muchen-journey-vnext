"""Persist independent review and append-only replacement decision lineage.

Revision ID: 0027_next_stage_review
Revises: 0026_identity_org_scope
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0027_next_stage_review"
down_revision = "0026_identity_organization_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "next_training_stage_decisions",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "next_training_stage_decisions",
        sa.Column("supersedes_decision_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "next_training_stage_decisions",
        sa.Column("source_review_request_id", sa.Uuid(), nullable=True),
    )
    op.drop_constraint(
        "uq_ntsd_handoff_scope", "next_training_stage_decisions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_ntsd_handoff_scope_revision",
        "next_training_stage_decisions",
        ["organization_id", "handoff_id", "decision_scope", "revision"],
    )
    op.create_unique_constraint(
        "uq_ntsd_source_review_request",
        "next_training_stage_decisions",
        ["source_review_request_id"],
    )
    op.create_check_constraint(
        "ck_ntsd_positive_revision",
        "next_training_stage_decisions",
        "revision >= 1",
    )
    op.create_check_constraint(
        "ck_ntsd_replacement_lineage_shape",
        "next_training_stage_decisions",
        "(revision = 1 AND supersedes_decision_id IS NULL "
        "AND source_review_request_id IS NULL) OR "
        "(revision > 1 AND supersedes_decision_id IS NOT NULL "
        "AND source_review_request_id IS NOT NULL)",
    )
    op.create_index(
        "ix_ntsd_supersedes_decision",
        "next_training_stage_decisions",
        ["supersedes_decision_id"],
    )
    op.create_index(
        "ix_ntsd_source_review_request",
        "next_training_stage_decisions",
        ["source_review_request_id"],
    )
    op.create_unique_constraint(
        "uq_ntsrr_assignment_scope",
        "next_training_stage_review_requests",
        [
            "id",
            "organization_id",
            "next_training_stage_decision_id",
            "requester_user_id",
        ],
    )

    op.create_table(
        "next_training_stage_review_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_request_id", sa.Uuid(), nullable=False),
        sa.Column("source_decision_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_reason", sa.Text(), nullable=False),
        sa.Column("assignment_evidence_ref", sa.String(length=300), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reviewer_user_id <> person_id", name="ck_ntsra_reviewer_not_person"
        ),
        sa.CheckConstraint(
            "assigned_by_user_id <> reviewer_user_id",
            name="ck_ntsra_assigner_not_reviewer",
        ),
        sa.CheckConstraint(
            "length(trim(assignment_reason)) BETWEEN 10 AND 1000",
            name="ck_ntsra_reason",
        ),
        sa.CheckConstraint(
            "length(trim(assignment_evidence_ref)) BETWEEN 3 AND 300",
            name="ck_ntsra_evidence_ref",
        ),
        sa.ForeignKeyConstraint(
            [
                "review_request_id",
                "organization_id",
                "source_decision_id",
                "person_id",
            ],
            [
                "next_training_stage_review_requests.id",
                "next_training_stage_review_requests.organization_id",
                "next_training_stage_review_requests.next_training_stage_decision_id",
                "next_training_stage_review_requests.requester_user_id",
            ],
            name="fk_ntsra_request_scope",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsra_reviewer_scope",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsra_assigner_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_request_id", name="uq_ntsra_request"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "review_request_id",
            "reviewer_user_id",
            name="uq_ntsra_resolution_scope",
        ),
    )
    for column in (
        "organization_id",
        "review_request_id",
        "source_decision_id",
        "person_id",
        "reviewer_user_id",
        "assigned_by_user_id",
    ):
        op.create_index(
            f"ix_ntsra_{column}",
            "next_training_stage_review_assignments",
            [column],
        )

    op.create_table(
        "next_training_stage_review_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_request_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("resolution_reason", sa.Text(), nullable=False),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('UPHELD', 'OVERTURNED', 'RETURNED_FOR_REVIEW')",
            name="ck_ntsrrs_terminal_status",
        ),
        sa.CheckConstraint(
            "length(trim(resolution_reason)) BETWEEN 10 AND 2000",
            name="ck_ntsrrs_reason",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_refs) = 'array' "
            "AND jsonb_array_length(evidence_refs) <= 20",
            name="ck_ntsrrs_evidence_refs",
        ),
        sa.ForeignKeyConstraint(
            [
                "assignment_id",
                "organization_id",
                "review_request_id",
                "reviewer_user_id",
            ],
            [
                "next_training_stage_review_assignments.id",
                "next_training_stage_review_assignments.organization_id",
                "next_training_stage_review_assignments.review_request_id",
                "next_training_stage_review_assignments.reviewer_user_id",
            ],
            name="fk_ntsrrs_assignment_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_request_id", name="uq_ntsrrs_request"),
        sa.UniqueConstraint("assignment_id", name="uq_ntsrrs_assignment"),
    )
    for column in (
        "organization_id",
        "review_request_id",
        "assignment_id",
        "reviewer_user_id",
    ):
        op.create_index(
            f"ix_ntsrrs_{column}",
            "next_training_stage_review_resolutions",
            [column],
        )

    op.execute(
        """
        CREATE FUNCTION reject_next_stage_review_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'next training stage review facts are immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ntsra_immutable
        BEFORE UPDATE OR DELETE ON next_training_stage_review_assignments
        FOR EACH ROW EXECUTE FUNCTION reject_next_stage_review_mutation();

        CREATE TRIGGER trg_ntsrrs_immutable
        BEFORE UPDATE OR DELETE ON next_training_stage_review_resolutions
        FOR EACH ROW EXECUTE FUNCTION reject_next_stage_review_mutation();

        CREATE FUNCTION validate_next_stage_review_assignment() RETURNS trigger AS $$
        DECLARE original_decider uuid;
        BEGIN
            SELECT d.decided_by_user_id INTO original_decider
              FROM next_training_stage_review_requests r
              JOIN next_training_stage_decisions d
                ON d.id = r.next_training_stage_decision_id
               AND d.organization_id = r.organization_id
             WHERE r.id = NEW.review_request_id
               AND r.organization_id = NEW.organization_id
             FOR SHARE OF r, d;
            IF original_decider IS NULL OR original_decider = NEW.reviewer_user_id THEN
                RAISE EXCEPTION 'independent reviewer cannot be the original decision signer';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM role_assignments ra
                 WHERE ra.organization_id = NEW.organization_id
                   AND ra.user_id = NEW.reviewer_user_id
                   AND ra.role = 'REVIEWER'
            ) THEN
                RAISE EXCEPTION 'assigned independent reviewer lacks REVIEWER role';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM role_assignments ra
                 WHERE ra.organization_id = NEW.organization_id
                   AND ra.user_id = NEW.assigned_by_user_id
                   AND ra.role = 'OPERATOR'
            ) THEN
                RAISE EXCEPTION 'review assignment requires OPERATOR authority';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ntsra_validate_independence
        BEFORE INSERT ON next_training_stage_review_assignments
        FOR EACH ROW EXECUTE FUNCTION validate_next_stage_review_assignment();

        CREATE FUNCTION validate_next_stage_review_resolution() RETURNS trigger AS $$
        DECLARE assigned_at_value timestamptz;
        BEGIN
            SELECT a.assigned_at INTO assigned_at_value
              FROM next_training_stage_review_assignments a
             WHERE a.id = NEW.assignment_id
               AND a.organization_id = NEW.organization_id
               AND a.review_request_id = NEW.review_request_id
               AND a.reviewer_user_id = NEW.reviewer_user_id
             FOR SHARE OF a;
            IF assigned_at_value IS NULL OR NEW.resolved_at < assigned_at_value THEN
                RAISE EXCEPTION 'appeal resolution must follow its independent assignment';
            END IF;
            IF EXISTS (
                SELECT 1 FROM jsonb_array_elements(NEW.evidence_refs) item
                 WHERE jsonb_typeof(item) <> 'string'
                    OR length(trim(item #>> '{}')) NOT BETWEEN 3 AND 300
            ) THEN
                RAISE EXCEPTION 'resolution evidence references must be bounded strings';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ntsrrs_validate_assignment
        BEFORE INSERT ON next_training_stage_review_resolutions
        FOR EACH ROW EXECUTE FUNCTION validate_next_stage_review_resolution();

        CREATE FUNCTION require_overturned_replacement_decision() RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'OVERTURNED' AND NOT EXISTS (
                SELECT 1 FROM next_training_stage_decisions d
                 WHERE d.source_review_request_id = NEW.review_request_id
                   AND d.organization_id = NEW.organization_id
                   AND d.decided_by_user_id = NEW.reviewer_user_id
            ) THEN
                RAISE EXCEPTION 'overturned review requires an append-only replacement decision';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER trg_ntsrrs_require_replacement
        AFTER INSERT ON next_training_stage_review_resolutions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION require_overturned_replacement_decision();

        CREATE OR REPLACE FUNCTION validate_next_training_stage_decision() RETURNS trigger AS $$
        DECLARE
            formal_evaluation_count integer;
            prior_decision next_training_stage_decisions%ROWTYPE;
            source_request next_training_stage_review_requests%ROWTYPE;
            source_resolution next_training_stage_review_resolutions%ROWTYPE;
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
            IF NEW.revision > 1 THEN
                SELECT * INTO prior_decision
                  FROM next_training_stage_decisions d
                 WHERE d.id = NEW.supersedes_decision_id
                 FOR SHARE OF d;
                SELECT * INTO source_request
                  FROM next_training_stage_review_requests r
                 WHERE r.id = NEW.source_review_request_id
                 FOR SHARE OF r;
                SELECT * INTO source_resolution
                  FROM next_training_stage_review_resolutions rr
                 WHERE rr.review_request_id = NEW.source_review_request_id
                 FOR SHARE OF rr;
                IF prior_decision.id IS NULL
                   OR source_request.id IS NULL
                   OR source_resolution.id IS NULL
                   OR source_resolution.status <> 'OVERTURNED'
                   OR source_request.next_training_stage_decision_id <> prior_decision.id
                   OR prior_decision.organization_id <> NEW.organization_id
                   OR prior_decision.handoff_id <> NEW.handoff_id
                   OR prior_decision.outcome_id <> NEW.outcome_id
                   OR prior_decision.person_id <> NEW.person_id
                   OR prior_decision.decision_scope <> NEW.decision_scope
                   OR prior_decision.revision + 1 <> NEW.revision
                   OR source_resolution.reviewer_user_id <> NEW.decided_by_user_id
                   OR NEW.decided_at < source_resolution.resolved_at THEN
                    RAISE EXCEPTION 'replacement decision lacks valid independent appeal lineage';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    fact_count = int(
        bind.execute(
            sa.text(
                "SELECT "
                "(SELECT count(*) FROM next_training_stage_review_assignments) + "
                "(SELECT count(*) FROM next_training_stage_review_resolutions) + "
                "(SELECT count(*) FROM next_training_stage_decisions "
                "WHERE source_review_request_id IS NOT NULL)"
            )
        ).scalar_one()
    )
    if fact_count:
        raise RuntimeError(
            "0027 contains append-only review facts; use a forward fix instead of destructive downgrade"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_next_training_stage_decision() RETURNS trigger AS $$
        DECLARE formal_evaluation_count integer;
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
        DROP TRIGGER trg_ntsrrs_require_replacement ON next_training_stage_review_resolutions;
        DROP FUNCTION require_overturned_replacement_decision();
        DROP TRIGGER trg_ntsrrs_validate_assignment ON next_training_stage_review_resolutions;
        DROP FUNCTION validate_next_stage_review_resolution();
        DROP TRIGGER trg_ntsra_validate_independence ON next_training_stage_review_assignments;
        DROP FUNCTION validate_next_stage_review_assignment();
        DROP TRIGGER trg_ntsrrs_immutable ON next_training_stage_review_resolutions;
        DROP TRIGGER trg_ntsra_immutable ON next_training_stage_review_assignments;
        DROP FUNCTION reject_next_stage_review_mutation();
        """
    )
    op.drop_table("next_training_stage_review_resolutions")
    op.drop_table("next_training_stage_review_assignments")
    op.drop_constraint(
        "uq_ntsrr_assignment_scope",
        "next_training_stage_review_requests",
        type_="unique",
    )
    op.drop_index("ix_ntsd_source_review_request", table_name="next_training_stage_decisions")
    op.drop_index("ix_ntsd_supersedes_decision", table_name="next_training_stage_decisions")
    op.drop_constraint(
        "ck_ntsd_replacement_lineage_shape",
        "next_training_stage_decisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_ntsd_positive_revision", "next_training_stage_decisions", type_="check"
    )
    op.drop_constraint(
        "uq_ntsd_source_review_request",
        "next_training_stage_decisions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ntsd_handoff_scope_revision",
        "next_training_stage_decisions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ntsd_handoff_scope",
        "next_training_stage_decisions",
        ["organization_id", "handoff_id", "decision_scope"],
    )
    op.drop_column("next_training_stage_decisions", "source_review_request_id")
    op.drop_column("next_training_stage_decisions", "supersedes_decision_id")
    op.drop_column("next_training_stage_decisions", "revision")
