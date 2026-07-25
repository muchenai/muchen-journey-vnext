"""Add WP-09 Feishu identity links, OAuth state, and revocable sessions.

Revision ID: 0011_wp09_feishu_identity
Revises: 0010_wp06_governance
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_wp09_feishu_identity"
down_revision = "0010_wp06_governance"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "external_identities",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "external_identities",
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
    )
    op.add_column(
        "identity_sessions",
        sa.Column("external_identity_id", UUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_identity_sessions_external_identity",
        "identity_sessions",
        "external_identities",
        ["external_identity_id"],
        ["id"],
    )
    op.create_index(
        "ix_identity_sessions_external_identity_id",
        "identity_sessions",
        ["external_identity_id"],
    )

    op.create_table(
        "external_identity_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("consumed_at", TIMESTAMP, nullable=True),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint("role IN ('REVIEWER', 'OPERATOR')", name="ck_identity_links_role"),
        sa.CheckConstraint("provider = 'FEISHU'", name="ck_identity_links_provider"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONSUMED', 'REVOKED', 'EXPIRED')",
            name="ck_identity_links_status",
        ),
    )
    op.create_index(
        "ix_external_identity_links_organization_id",
        "external_identity_links",
        ["organization_id"],
    )
    op.create_index(
        "ix_external_identity_links_user_id", "external_identity_links", ["user_id"]
    )
    op.create_index(
        "ix_external_identity_links_status", "external_identity_links", ["status"]
    )
    op.create_index(
        "ix_external_identity_links_expires_at",
        "external_identity_links",
        ["expires_at"],
    )

    op.create_table(
        "oauth_login_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("browser_token_hash", sa.String(64), nullable=False),
        sa.Column(
            "identity_link_id",
            UUID,
            sa.ForeignKey("external_identity_links.id"),
            nullable=True,
        ),
        sa.Column("return_to", sa.String(40), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("consumed_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint("provider = 'FEISHU'", name="ck_oauth_login_states_provider"),
        sa.CheckConstraint(
            "return_to IN ('/review', '/ops')", name="ck_oauth_login_states_return_to"
        ),
    )
    op.create_index(
        "ix_oauth_login_states_identity_link_id",
        "oauth_login_states",
        ["identity_link_id"],
    )
    op.create_index(
        "ix_oauth_login_states_expires_at", "oauth_login_states", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("oauth_login_states")
    op.drop_table("external_identity_links")
    op.drop_index(
        "ix_identity_sessions_external_identity_id", table_name="identity_sessions"
    )
    op.drop_constraint(
        "fk_identity_sessions_external_identity", "identity_sessions", type_="foreignkey"
    )
    op.drop_column("identity_sessions", "external_identity_id")
    op.drop_column("external_identities", "revoked_at")
    op.drop_column("external_identities", "revision")
