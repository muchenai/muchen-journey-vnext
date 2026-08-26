"""Bind identity, invite, session, and join facts to one organization.

Revision ID: 0026_identity_organization_scope
Revises: 0025_formal_result_gate
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_identity_organization_scope"
down_revision = "0025_formal_result_gate"
branch_labels = None
depends_on = None


def _require_zero(bind: sa.Connection, label: str, sql: str) -> None:
    count = int(bind.execute(sa.text(sql)).scalar_one())
    if count:
        raise RuntimeError(
            f"CORE-001 identity organization preflight failed: {label} has {count} invalid rows"
        )


def upgrade() -> None:
    bind = op.get_bind()
    checks = {
        "role_assignments": """
            SELECT count(*) FROM role_assignments AS fact
            JOIN users AS person ON person.id = fact.user_id
            WHERE fact.organization_id IS DISTINCT FROM person.organization_id
        """,
        "external_identities": """
            SELECT count(*) FROM external_identities AS fact
            JOIN users AS person ON person.id = fact.user_id
            WHERE fact.organization_id IS DISTINCT FROM person.organization_id
        """,
        "invites": """
            SELECT count(*) FROM invites AS fact
            JOIN users AS reviewer ON reviewer.id = fact.reviewer_id
            JOIN task_versions AS task ON task.id = fact.task_version_id
            JOIN users AS creator ON creator.id = fact.created_by
            LEFT JOIN users AS target ON target.id = fact.target_user_id
            LEFT JOIN users AS consumer ON consumer.id = fact.consumed_by
            WHERE fact.organization_id IS DISTINCT FROM reviewer.organization_id
               OR fact.organization_id IS DISTINCT FROM task.organization_id
               OR fact.organization_id IS DISTINCT FROM creator.organization_id
               OR (fact.target_user_id IS NOT NULL AND fact.organization_id IS DISTINCT FROM target.organization_id)
               OR (fact.consumed_by IS NOT NULL AND fact.organization_id IS DISTINCT FROM consumer.organization_id)
        """,
        "join_contexts": """
            SELECT count(*) FROM join_contexts AS fact
            JOIN invites AS invite ON invite.id = fact.invite_id
            JOIN users AS person ON person.id = fact.user_id
            JOIN enrollments AS enrollment ON enrollment.id = fact.enrollment_id
            WHERE invite.organization_id IS DISTINCT FROM person.organization_id
               OR invite.organization_id IS DISTINCT FROM enrollment.organization_id
               OR enrollment.learner_id IS DISTINCT FROM fact.user_id
        """,
        "identity_sessions": """
            SELECT count(*) FROM identity_sessions AS fact
            JOIN users AS person ON person.id = fact.user_id
            LEFT JOIN external_identities AS identity ON identity.id = fact.external_identity_id
            WHERE fact.organization_id IS DISTINCT FROM person.organization_id
               OR (fact.external_identity_id IS NOT NULL AND fact.organization_id IS DISTINCT FROM identity.organization_id)
        """,
        "external_identity_links": """
            SELECT count(*) FROM external_identity_links AS fact
            JOIN users AS person ON person.id = fact.user_id
            LEFT JOIN users AS creator ON creator.id = fact.created_by
            WHERE fact.organization_id IS DISTINCT FROM person.organization_id
               OR (fact.created_by IS NOT NULL AND fact.organization_id IS DISTINCT FROM creator.organization_id)
        """,
        "invitation_controls": """
            SELECT count(*) FROM invitation_controls AS fact
            LEFT JOIN users AS updater ON updater.id = fact.updated_by
            WHERE fact.updated_by IS NOT NULL
              AND fact.organization_id IS DISTINCT FROM updater.organization_id
        """,
    }
    for label, sql in checks.items():
        _require_zero(bind, label, sql)

    op.create_unique_constraint(
        "uq_external_identities_id_organization",
        "external_identities",
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_invites_id_organization", "invites", ["id", "organization_id"]
    )

    op.create_foreign_key(
        "fk_role_assignments_user_organization",
        "role_assignments",
        "users",
        ["user_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_external_identities_user_organization",
        "external_identities",
        "users",
        ["user_id", "organization_id"],
        ["id", "organization_id"],
    )
    for column, name in (
        ("reviewer_id", "fk_invites_reviewer_organization"),
        ("target_user_id", "fk_invites_target_organization"),
        ("created_by", "fk_invites_creator_organization"),
        ("consumed_by", "fk_invites_consumer_organization"),
    ):
        op.create_foreign_key(
            name,
            "invites",
            "users",
            [column, "organization_id"],
            ["id", "organization_id"],
        )
    op.create_foreign_key(
        "fk_invites_task_version_organization",
        "invites",
        "task_versions",
        ["task_version_id", "organization_id"],
        ["id", "organization_id"],
    )

    op.add_column("join_contexts", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE join_contexts AS context
               SET organization_id = invite.organization_id
              FROM invites AS invite
             WHERE invite.id = context.invite_id
            """
        )
    )
    op.alter_column("join_contexts", "organization_id", nullable=False)
    op.create_index(
        "ix_join_contexts_organization_id", "join_contexts", ["organization_id"]
    )
    op.create_foreign_key(
        "fk_join_contexts_organization",
        "join_contexts",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_join_contexts_invite_organization",
        "join_contexts",
        "invites",
        ["invite_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_join_contexts_user_organization",
        "join_contexts",
        "users",
        ["user_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_join_contexts_enrollment_person_organization",
        "join_contexts",
        "enrollments",
        ["enrollment_id", "organization_id", "user_id"],
        ["id", "organization_id", "learner_id"],
    )

    op.create_foreign_key(
        "fk_identity_sessions_user_organization",
        "identity_sessions",
        "users",
        ["user_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_identity_sessions_external_identity_organization",
        "identity_sessions",
        "external_identities",
        ["external_identity_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_external_identity_links_user_organization",
        "external_identity_links",
        "users",
        ["user_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_external_identity_links_creator_organization",
        "external_identity_links",
        "users",
        ["created_by", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_invitation_controls_updater_organization",
        "invitation_controls",
        "users",
        ["updated_by", "organization_id"],
        ["id", "organization_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_invitation_controls_updater_organization",
        "invitation_controls",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_external_identity_links_creator_organization",
        "external_identity_links",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_external_identity_links_user_organization",
        "external_identity_links",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_identity_sessions_external_identity_organization",
        "identity_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_identity_sessions_user_organization",
        "identity_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_join_contexts_enrollment_person_organization",
        "join_contexts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_join_contexts_user_organization", "join_contexts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_join_contexts_invite_organization", "join_contexts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_join_contexts_organization", "join_contexts", type_="foreignkey"
    )
    op.drop_index("ix_join_contexts_organization_id", table_name="join_contexts")
    op.drop_column("join_contexts", "organization_id")
    op.drop_constraint(
        "fk_invites_task_version_organization", "invites", type_="foreignkey"
    )
    for name in (
        "fk_invites_consumer_organization",
        "fk_invites_creator_organization",
        "fk_invites_target_organization",
        "fk_invites_reviewer_organization",
    ):
        op.drop_constraint(name, "invites", type_="foreignkey")
    op.drop_constraint(
        "fk_external_identities_user_organization",
        "external_identities",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_role_assignments_user_organization",
        "role_assignments",
        type_="foreignkey",
    )
    op.drop_constraint("uq_invites_id_organization", "invites", type_="unique")
    op.drop_constraint(
        "uq_external_identities_id_organization",
        "external_identities",
        type_="unique",
    )
