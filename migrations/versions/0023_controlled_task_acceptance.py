"""Add controlled task authorization and append-only handoff acceptance.

Revision ID: 0023_controlled_task_acceptance
Revises: 0022_next_training_stage_review
"""

import sqlalchemy as sa
from alembic import op


revision = "0023_controlled_task_acceptance"
down_revision = "0022_next_training_stage_review"
branch_labels = None
depends_on = None


def _user_scope_fk(column: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column, "organization_id"],
        ["users.id", "users.organization_id"],
        name=name,
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_jsv_acceptance_lineage",
        "journey_stage_versions",
        ["id", "organization_id", "journey_version_id", "task_version_id"],
    )
    op.create_unique_constraint(
        "uq_enrollments_acceptance_lineage",
        "enrollments",
        ["id", "organization_id", "learner_id", "journey_version_id", "reviewer_id"],
    )
    op.create_unique_constraint(
        "uq_assignments_acceptance_lineage",
        "assignments",
        [
            "id",
            "organization_id",
            "enrollment_id",
            "journey_stage_version_id",
            "task_version_id",
        ],
    )
    op.create_unique_constraint(
        "uq_ntsd_acceptance_person_scope",
        "next_training_stage_decisions",
        [
            "id",
            "organization_id",
            "handoff_id",
            "decision_scope",
            "decision",
            "person_id",
        ],
    )

    op.create_table(
        "controlled_task_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_scope", sa.String(length=50), nullable=False),
        sa.Column("authorized_project_ref", sa.String(length=500), nullable=False),
        sa.Column("target_journey_version_id", sa.Uuid(), nullable=False),
        sa.Column("target_journey_stage_version_id", sa.Uuid(), nullable=False),
        sa.Column("task_version_id", sa.Uuid(), nullable=False),
        sa.Column("task_version_sha256", sa.String(length=64), nullable=False),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.Column("scope_sha256", sa.String(length=64), nullable=False),
        sa.Column("project_owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("newcomer_operations_owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("data_security_owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("primary_reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("backup_reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("policy_snapshot_ref", sa.String(length=500), nullable=False),
        sa.Column("policy_snapshot_version", sa.String(length=80), nullable=False),
        sa.Column("policy_snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("policy_evidence_ref", sa.String(length=500), nullable=False),
        sa.Column("policy_evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("activated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("expired_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_controlled_task_authorizations"),
        sa.UniqueConstraint("id", "organization_id", name="uq_cta_id_org"),
        sa.UniqueConstraint(
            "id", "organization_id", "scope_sha256", name="uq_cta_scope_hash_ref"
        ),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "target_journey_version_id",
            "target_journey_stage_version_id",
            "task_version_id",
            "primary_reviewer_user_id",
            name="uq_cta_acceptance_lineage",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "target_journey_version_id",
            "target_journey_stage_version_id",
            "task_version_id",
            "authorization_version",
            name="uq_cta_stage_business_version",
        ),
        sa.CheckConstraint(
            "authorization_scope = 'NEWCOMER_CONTROLLED_TRAINING'",
            name="ck_cta_scope",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PENDING_APPROVALS','ACTIVE','REVOKED','EXPIRED')",
            name="ck_cta_status",
        ),
        sa.CheckConstraint(
            "authorization_version >= 1 AND revision >= 1",
            name="ck_cta_positive_versions",
        ),
        sa.CheckConstraint(
            "task_version_sha256 ~ '^[0-9a-f]{64}$' AND "
            "scope_sha256 ~ '^[0-9a-f]{64}$' AND "
            "policy_snapshot_sha256 ~ '^[0-9a-f]{64}$' AND "
            "policy_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_cta_hashes",
        ),
        sa.CheckConstraint("valid_from < expires_at", name="ck_cta_validity"),
        sa.CheckConstraint(
            "primary_reviewer_user_id <> backup_reviewer_user_id AND "
            "primary_reviewer_user_id NOT IN (project_owner_user_id, newcomer_operations_owner_user_id, data_security_owner_user_id, reviewer_owner_user_id) AND "
            "backup_reviewer_user_id NOT IN (project_owner_user_id, newcomer_operations_owner_user_id, data_security_owner_user_id, reviewer_owner_user_id)",
            name="ck_cta_distinct_reviewers",
        ),
        sa.CheckConstraint(
            "((status IN ('ACTIVE','REVOKED','EXPIRED')) = (activated_by_user_id IS NOT NULL AND activated_at IS NOT NULL))",
            name="ck_cta_activation_audit",
        ),
        sa.CheckConstraint(
            "(status = 'REVOKED' AND revoked_by_user_id IS NOT NULL AND revoked_at IS NOT NULL AND length(trim(revocation_reason)) BETWEEN 10 AND 500) OR "
            "(status <> 'REVOKED' AND revoked_by_user_id IS NULL AND revoked_at IS NULL AND revocation_reason IS NULL)",
            name="ck_cta_revocation_audit",
        ),
        sa.CheckConstraint(
            "(status = 'EXPIRED' AND expired_by_user_id IS NOT NULL AND expired_at IS NOT NULL) OR "
            "(status <> 'EXPIRED' AND expired_by_user_id IS NULL AND expired_at IS NULL)",
            name="ck_cta_expiration_audit",
        ),
        sa.CheckConstraint(
            "status <> 'EXPIRED' OR expired_at >= expires_at",
            name="ck_cta_expiration_time",
        ),
        sa.ForeignKeyConstraint(
            [
                "target_journey_stage_version_id",
                "organization_id",
                "target_journey_version_id",
                "task_version_id",
            ],
            [
                "journey_stage_versions.id",
                "journey_stage_versions.organization_id",
                "journey_stage_versions.journey_version_id",
                "journey_stage_versions.task_version_id",
            ],
            name="fk_cta_stage_lineage",
        ),
        _user_scope_fk("project_owner_user_id", "fk_cta_project_owner_scope"),
        _user_scope_fk(
            "newcomer_operations_owner_user_id", "fk_cta_operations_owner_scope"
        ),
        _user_scope_fk(
            "data_security_owner_user_id", "fk_cta_data_security_owner_scope"
        ),
        _user_scope_fk("reviewer_owner_user_id", "fk_cta_reviewer_owner_scope"),
        _user_scope_fk("primary_reviewer_user_id", "fk_cta_primary_reviewer_scope"),
        _user_scope_fk("backup_reviewer_user_id", "fk_cta_backup_reviewer_scope"),
        _user_scope_fk("created_by_user_id", "fk_cta_created_by_scope"),
        _user_scope_fk("activated_by_user_id", "fk_cta_activated_by_scope"),
        _user_scope_fk("revoked_by_user_id", "fk_cta_revoked_by_scope"),
        _user_scope_fk("expired_by_user_id", "fk_cta_expired_by_scope"),
    )
    op.create_index(
        "uq_cta_one_active_stage",
        "controlled_task_authorizations",
        [
            "organization_id",
            "target_journey_version_id",
            "target_journey_stage_version_id",
            "task_version_id",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "controlled_task_authorization_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("approval_role", sa.String(length=40), nullable=False),
        sa.Column("signer_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("signed_scope_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_evidence_ref", sa.String(length=500), nullable=False),
        sa.Column("signature_evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cta_approvals"),
        sa.UniqueConstraint(
            "authorization_id", "approval_role", name="uq_ctaa_authorization_role"
        ),
        sa.CheckConstraint(
            "approval_role IN ('NEWCOMER_OPERATIONS_OWNER','PROJECT_OWNER','DATA_SECURITY_OWNER','REVIEWER_OWNER')",
            name="ck_ctaa_role",
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVE','REJECT')", name="ck_ctaa_decision"
        ),
        sa.CheckConstraint(
            "signed_scope_sha256 ~ '^[0-9a-f]{64}$' AND signature_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ctaa_hashes",
        ),
        sa.CheckConstraint("created_at >= signed_at", name="ck_ctaa_time"),
        sa.ForeignKeyConstraint(
            ["authorization_id", "organization_id", "signed_scope_sha256"],
            [
                "controlled_task_authorizations.id",
                "controlled_task_authorizations.organization_id",
                "controlled_task_authorizations.scope_sha256",
            ],
            name="fk_ctaa_authorization_scope",
        ),
        _user_scope_fk("signer_user_id", "fk_ctaa_signer_scope"),
    )

    op.create_table(
        "handoff_acceptances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("next_training_stage_decision_id", sa.Uuid(), nullable=False),
        sa.Column("decision_scope", sa.String(length=40), nullable=False),
        sa.Column("decision_value", sa.String(length=20), nullable=False),
        sa.Column("controlled_task_authorization_id", sa.Uuid(), nullable=False),
        sa.Column("target_journey_version_id", sa.Uuid(), nullable=False),
        sa.Column("target_journey_stage_version_id", sa.Uuid(), nullable=False),
        sa.Column("target_task_version_id", sa.Uuid(), nullable=False),
        sa.Column("target_reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("target_assignment_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_handoff_acceptances"),
        sa.UniqueConstraint("handoff_id", name="uq_ha_handoff"),
        sa.UniqueConstraint("target_enrollment_id", name="uq_ha_target_enrollment"),
        sa.UniqueConstraint("target_assignment_id", name="uq_ha_target_assignment"),
        sa.CheckConstraint(
            "decision_scope = 'NEXT_TRAINING_STAGE'", name="ck_ha_decision_scope"
        ),
        sa.CheckConstraint("decision_value = 'READY'", name="ck_ha_ready_decision"),
        sa.CheckConstraint("created_at >= accepted_at", name="ck_ha_time"),
        sa.ForeignKeyConstraint(
            [
                "next_training_stage_decision_id",
                "organization_id",
                "handoff_id",
                "decision_scope",
                "decision_value",
                "accepted_by_user_id",
            ],
            [
                "next_training_stage_decisions.id",
                "next_training_stage_decisions.organization_id",
                "next_training_stage_decisions.handoff_id",
                "next_training_stage_decisions.decision_scope",
                "next_training_stage_decisions.decision",
                "next_training_stage_decisions.person_id",
            ],
            name="fk_ha_ready_decision_person",
        ),
        sa.ForeignKeyConstraint(
            [
                "controlled_task_authorization_id",
                "organization_id",
                "target_journey_version_id",
                "target_journey_stage_version_id",
                "target_task_version_id",
                "target_reviewer_user_id",
            ],
            [
                "controlled_task_authorizations.id",
                "controlled_task_authorizations.organization_id",
                "controlled_task_authorizations.target_journey_version_id",
                "controlled_task_authorizations.target_journey_stage_version_id",
                "controlled_task_authorizations.task_version_id",
                "controlled_task_authorizations.primary_reviewer_user_id",
            ],
            name="fk_ha_authorized_lineage",
        ),
        sa.ForeignKeyConstraint(
            [
                "target_enrollment_id",
                "organization_id",
                "accepted_by_user_id",
                "target_journey_version_id",
                "target_reviewer_user_id",
            ],
            [
                "enrollments.id",
                "enrollments.organization_id",
                "enrollments.learner_id",
                "enrollments.journey_version_id",
                "enrollments.reviewer_id",
            ],
            name="fk_ha_target_enrollment_lineage",
        ),
        sa.ForeignKeyConstraint(
            [
                "target_assignment_id",
                "organization_id",
                "target_enrollment_id",
                "target_journey_stage_version_id",
                "target_task_version_id",
            ],
            [
                "assignments.id",
                "assignments.organization_id",
                "assignments.enrollment_id",
                "assignments.journey_stage_version_id",
                "assignments.task_version_id",
            ],
            name="fk_ha_target_assignment_lineage",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION guard_assignment_journey_lineage() RETURNS trigger AS $$
        DECLARE enrollment_journey uuid;
        BEGIN
            IF TG_OP = 'UPDATE'
               AND NEW.organization_id IS NOT DISTINCT FROM OLD.organization_id
               AND NEW.enrollment_id IS NOT DISTINCT FROM OLD.enrollment_id
               AND NEW.journey_stage_version_id IS NOT DISTINCT FROM OLD.journey_stage_version_id
               AND NEW.task_version_id IS NOT DISTINCT FROM OLD.task_version_id THEN
                RETURN NEW;
            END IF;
            SELECT journey_version_id INTO enrollment_journey
              FROM enrollments
             WHERE id = NEW.enrollment_id
               AND organization_id = NEW.organization_id
             FOR KEY SHARE;
            IF enrollment_journey IS NOT NULL THEN
                IF NEW.journey_stage_version_id IS NULL OR NOT EXISTS (
                    SELECT 1 FROM journey_stage_versions
                     WHERE id = NEW.journey_stage_version_id
                       AND organization_id = NEW.organization_id
                       AND journey_version_id = enrollment_journey
                       AND task_version_id = NEW.task_version_id
                ) THEN
                    RAISE EXCEPTION 'assignment journey/stage/task lineage mismatch';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER ct_assignment_journey_lineage_guard
        AFTER INSERT OR UPDATE ON assignments
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION guard_assignment_journey_lineage();

        CREATE FUNCTION guard_review_enrollment_reviewer() RETURNS trigger AS $$
        DECLARE expected_reviewer uuid;
        BEGIN
            IF TG_OP = 'UPDATE'
               AND NEW.organization_id IS NOT DISTINCT FROM OLD.organization_id
               AND NEW.assignment_id IS NOT DISTINCT FROM OLD.assignment_id
               AND NEW.reviewer_id IS NOT DISTINCT FROM OLD.reviewer_id THEN
                RETURN NEW;
            END IF;
            SELECT e.reviewer_id INTO expected_reviewer
              FROM assignments a
              JOIN enrollments e
                ON e.id = a.enrollment_id
               AND e.organization_id = a.organization_id
             WHERE a.id = NEW.assignment_id
               AND a.organization_id = NEW.organization_id
             FOR KEY SHARE OF a, e;
            IF expected_reviewer IS NULL OR NEW.reviewer_id <> expected_reviewer THEN
                RAISE EXCEPTION 'review reviewer must equal enrollment reviewer';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER ct_review_enrollment_reviewer_guard
        AFTER INSERT OR UPDATE ON reviews
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION guard_review_enrollment_reviewer();

        CREATE FUNCTION guard_cta_insert() RETURNS trigger AS $$
        BEGIN
            IF NEW.status <> 'DRAFT' OR NEW.revision <> 1
               OR NEW.activated_by_user_id IS NOT NULL OR NEW.activated_at IS NOT NULL
               OR NEW.revoked_by_user_id IS NOT NULL OR NEW.revoked_at IS NOT NULL
               OR NEW.expired_by_user_id IS NOT NULL OR NEW.expired_at IS NOT NULL THEN
                RAISE EXCEPTION 'controlled task authorization must start as revision-one DRAFT';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_cta_guard_insert
        BEFORE INSERT ON controlled_task_authorizations
        FOR EACH ROW EXECUTE FUNCTION guard_cta_insert();

        CREATE FUNCTION guard_cta_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'controlled task authorization is not deletable';
            END IF;
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.authorization_scope IS DISTINCT FROM OLD.authorization_scope
               OR NEW.authorized_project_ref IS DISTINCT FROM OLD.authorized_project_ref
               OR NEW.target_journey_version_id IS DISTINCT FROM OLD.target_journey_version_id
               OR NEW.target_journey_stage_version_id IS DISTINCT FROM OLD.target_journey_stage_version_id
               OR NEW.task_version_id IS DISTINCT FROM OLD.task_version_id
               OR NEW.task_version_sha256 IS DISTINCT FROM OLD.task_version_sha256
               OR NEW.authorization_version IS DISTINCT FROM OLD.authorization_version
               OR NEW.scope_sha256 IS DISTINCT FROM OLD.scope_sha256
               OR NEW.project_owner_user_id IS DISTINCT FROM OLD.project_owner_user_id
               OR NEW.newcomer_operations_owner_user_id IS DISTINCT FROM OLD.newcomer_operations_owner_user_id
               OR NEW.data_security_owner_user_id IS DISTINCT FROM OLD.data_security_owner_user_id
               OR NEW.reviewer_owner_user_id IS DISTINCT FROM OLD.reviewer_owner_user_id
               OR NEW.primary_reviewer_user_id IS DISTINCT FROM OLD.primary_reviewer_user_id
               OR NEW.backup_reviewer_user_id IS DISTINCT FROM OLD.backup_reviewer_user_id
               OR NEW.policy_snapshot_ref IS DISTINCT FROM OLD.policy_snapshot_ref
               OR NEW.policy_snapshot_version IS DISTINCT FROM OLD.policy_snapshot_version
               OR NEW.policy_snapshot_sha256 IS DISTINCT FROM OLD.policy_snapshot_sha256
               OR NEW.policy_evidence_ref IS DISTINCT FROM OLD.policy_evidence_ref
               OR NEW.policy_evidence_sha256 IS DISTINCT FROM OLD.policy_evidence_sha256
               OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
               OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
               OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'controlled task authorization immutable scope changed';
            END IF;
            IF NEW.revision <> OLD.revision + 1 THEN
                RAISE EXCEPTION 'controlled task authorization revision must increment by one';
            END IF;
            IF NOT (
                (OLD.status = 'DRAFT' AND NEW.status = 'PENDING_APPROVALS') OR
                (OLD.status = 'PENDING_APPROVALS' AND NEW.status = 'ACTIVE') OR
                (OLD.status = 'ACTIVE' AND NEW.status IN ('REVOKED','EXPIRED'))
            ) THEN
                RAISE EXCEPTION 'controlled task authorization state transition rejected';
            END IF;
            IF NEW.status = 'EXPIRED' THEN
                IF clock_timestamp() < OLD.expires_at THEN
                    RAISE EXCEPTION 'controlled task authorization is not expired by database time';
                END IF;
                NEW.expired_at := clock_timestamp();
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_cta_guard_mutation
        BEFORE UPDATE OR DELETE ON controlled_task_authorizations
        FOR EACH ROW EXECUTE FUNCTION guard_cta_mutation();

        CREATE FUNCTION guard_cta_activation() RETURNS trigger AS $$
        DECLARE approval_count integer;
        DECLARE rejected_count integer;
        BEGIN
            IF NEW.status <> 'ACTIVE' OR OLD.status = 'ACTIVE' THEN
                RETURN NEW;
            END IF;
            IF NOT (NEW.valid_from <= clock_timestamp() AND clock_timestamp() < NEW.expires_at) THEN
                RAISE EXCEPTION 'controlled task authorization activation outside validity window';
            END IF;
            SELECT count(*), count(*) FILTER (WHERE decision = 'REJECT')
              INTO approval_count, rejected_count
              FROM controlled_task_authorization_approvals a
             WHERE a.authorization_id = NEW.id
               AND a.organization_id = NEW.organization_id
               AND a.signed_scope_sha256 = NEW.scope_sha256
               AND (
                    (a.approval_role = 'PROJECT_OWNER' AND a.signer_user_id = NEW.project_owner_user_id) OR
                    (a.approval_role = 'NEWCOMER_OPERATIONS_OWNER' AND a.signer_user_id = NEW.newcomer_operations_owner_user_id) OR
                    (a.approval_role = 'DATA_SECURITY_OWNER' AND a.signer_user_id = NEW.data_security_owner_user_id) OR
                    (a.approval_role = 'REVIEWER_OWNER' AND a.signer_user_id = NEW.reviewer_owner_user_id)
               );
            IF approval_count <> 4 OR rejected_count <> 0 OR EXISTS (
                SELECT 1 FROM controlled_task_authorization_approvals
                 WHERE authorization_id = NEW.id AND decision = 'REJECT'
            ) THEN
                RAISE EXCEPTION 'controlled task authorization requires four exact human approvals';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER ct_cta_activate_guard
        AFTER UPDATE ON controlled_task_authorizations
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION guard_cta_activation();

        CREATE FUNCTION reject_cta_approval_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'controlled task authorization approval is immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ctaa_reject_mutation
        BEFORE UPDATE OR DELETE ON controlled_task_authorization_approvals
        FOR EACH ROW EXECUTE FUNCTION reject_cta_approval_mutation();

        CREATE FUNCTION guard_handoff_acceptance() RETURNS trigger AS $$
        DECLARE authorization_status text;
        DECLARE authorization_valid_from timestamptz;
        DECLARE authorization_expires_at timestamptz;
        BEGIN
            SELECT status, valid_from, expires_at
              INTO authorization_status, authorization_valid_from, authorization_expires_at
              FROM controlled_task_authorizations
             WHERE id = NEW.controlled_task_authorization_id
               AND organization_id = NEW.organization_id
             FOR UPDATE;
            IF authorization_status IS NULL
               OR authorization_status <> 'ACTIVE'
               OR NOT (authorization_valid_from <= clock_timestamp() AND clock_timestamp() < authorization_expires_at) THEN
                RAISE EXCEPTION 'handoff acceptance requires an effective ACTIVE authorization';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER ct_ha_authorization_guard
        BEFORE INSERT ON handoff_acceptances
        FOR EACH ROW EXECUTE FUNCTION guard_handoff_acceptance();

        CREATE FUNCTION reject_handoff_acceptance_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'handoff acceptance is immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ha_reject_mutation
        BEFORE UPDATE OR DELETE ON handoff_acceptances
        FOR EACH ROW EXECUTE FUNCTION reject_handoff_acceptance_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM handoff_acceptances) THEN
                RAISE EXCEPTION 'cannot downgrade: immutable handoff acceptance facts exist';
            END IF;
        END $$;
        DROP TRIGGER trg_ha_reject_mutation ON handoff_acceptances;
        DROP FUNCTION reject_handoff_acceptance_mutation();
        DROP TRIGGER ct_ha_authorization_guard ON handoff_acceptances;
        DROP FUNCTION guard_handoff_acceptance();
        DROP TRIGGER trg_ctaa_reject_mutation ON controlled_task_authorization_approvals;
        DROP FUNCTION reject_cta_approval_mutation();
        DROP TRIGGER ct_cta_activate_guard ON controlled_task_authorizations;
        DROP FUNCTION guard_cta_activation();
        DROP TRIGGER trg_cta_guard_mutation ON controlled_task_authorizations;
        DROP FUNCTION guard_cta_mutation();
        DROP TRIGGER trg_cta_guard_insert ON controlled_task_authorizations;
        DROP FUNCTION guard_cta_insert();
        DROP TRIGGER ct_review_enrollment_reviewer_guard ON reviews;
        DROP FUNCTION guard_review_enrollment_reviewer();
        DROP TRIGGER ct_assignment_journey_lineage_guard ON assignments;
        DROP FUNCTION guard_assignment_journey_lineage();
        """
    )
    op.drop_table("handoff_acceptances")
    op.drop_table("controlled_task_authorization_approvals")
    op.drop_index("uq_cta_one_active_stage", table_name="controlled_task_authorizations")
    op.drop_table("controlled_task_authorizations")
    op.drop_constraint(
        "uq_ntsd_acceptance_person_scope",
        "next_training_stage_decisions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_assignments_acceptance_lineage", "assignments", type_="unique"
    )
    op.drop_constraint(
        "uq_enrollments_acceptance_lineage", "enrollments", type_="unique"
    )
    op.drop_constraint(
        "uq_jsv_acceptance_lineage", "journey_stage_versions", type_="unique"
    )
