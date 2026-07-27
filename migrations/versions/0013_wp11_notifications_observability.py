"""Add encrypted notification endpoints, external receipts, and redrive facts.

Revision ID: 0013_wp11_notify_observability
Revises: 0012_wp10_file_security
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_wp11_notify_observability"
down_revision = "0012_wp10_file_security"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.drop_constraint(
        "ck_notification_deliveries_state_fields",
        "notification_deliveries",
        type_="check",
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("redrive_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("attempt_offset", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_notification_deliveries_revision",
        "notification_deliveries",
        "revision >= 1",
    )
    op.create_check_constraint(
        "ck_notification_deliveries_redrive",
        "notification_deliveries",
        "redrive_count >= 0 AND attempt_offset >= 0 AND attempt_offset <= attempt_count",
    )
    op.create_check_constraint(
        "ck_notification_deliveries_state_fields",
        "notification_deliveries",
        "(status = 'PENDING' AND attempt_count = attempt_offset AND delivered_at IS NULL) "
        "OR (status = 'SENDING' AND attempt_count > attempt_offset AND delivered_at IS NULL) "
        "OR (status = 'DELIVERED' AND attempt_count >= 1 AND delivered_at IS NOT NULL) "
        "OR (status = 'RETRY_WAIT' AND attempt_count > attempt_offset "
        "    AND next_attempt_at IS NOT NULL AND last_error_code IS NOT NULL "
        "    AND delivered_at IS NULL) "
        "OR (status = 'DEAD' AND attempt_count > attempt_offset "
        "    AND next_attempt_at IS NULL AND last_error_code IS NOT NULL "
        "    AND delivered_at IS NULL)",
    )

    op.create_table(
        "notification_endpoints",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("receive_id_type", sa.String(24), nullable=False),
        sa.Column("encrypted_receive_id", sa.Text(), nullable=False),
        sa.Column("recipient_fingerprint", sa.String(64), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "source", sa.String(40), server_default="OPERATOR_CONFIG", nullable=False
        ),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_notification_endpoints_user_scope",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "channel",
            name="uq_notification_endpoint_user_channel",
        ),
        sa.CheckConstraint(
            "channel = 'FEISHU'", name="ck_notification_endpoint_channel"
        ),
        sa.CheckConstraint(
            "receive_id_type = 'open_id'",
            name="ck_notification_endpoint_receive_id_type",
        ),
        sa.CheckConstraint(
            "key_version = 1", name="ck_notification_endpoint_key_version"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')",
            name="ck_notification_endpoint_status",
        ),
        sa.CheckConstraint(
            "source = 'OPERATOR_CONFIG'", name="ck_notification_endpoint_source"
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_notification_endpoint_revision"
        ),
    )
    op.create_index(
        "ix_notification_endpoints_organization_id",
        "notification_endpoints",
        ["organization_id"],
    )
    op.create_index(
        "ix_notification_endpoints_user_id", "notification_endpoints", ["user_id"]
    )
    op.create_index(
        "ix_notification_endpoints_status", "notification_endpoints", ["status"]
    )

    op.create_table(
        "external_notification_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "delivery_id",
            UUID,
            sa.ForeignKey("notification_deliveries.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_message_id", sa.String(200), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "delivery_id", name="uq_external_notification_receipt_delivery"
        ),
        sa.UniqueConstraint(
            "dedupe_key", name="uq_external_notification_receipt_dedupe"
        ),
        sa.CheckConstraint(
            "provider = 'FEISHU'", name="ck_external_receipt_provider"
        ),
    )
    op.create_index(
        "ix_external_notification_receipts_delivery_id",
        "external_notification_receipts",
        ["delivery_id"],
    )


def downgrade() -> None:
    op.drop_table("external_notification_receipts")
    op.drop_table("notification_endpoints")
    op.drop_constraint(
        "ck_notification_deliveries_redrive", "notification_deliveries", type_="check"
    )
    op.drop_constraint(
        "ck_notification_deliveries_revision",
        "notification_deliveries",
        type_="check",
    )
    op.drop_constraint(
        "ck_notification_deliveries_state_fields",
        "notification_deliveries",
        type_="check",
    )
    op.drop_column("notification_deliveries", "attempt_offset")
    op.drop_column("notification_deliveries", "redrive_count")
    op.drop_column("notification_deliveries", "revision")
    op.create_check_constraint(
        "ck_notification_deliveries_state_fields",
        "notification_deliveries",
        "(status = 'PENDING' AND attempt_count = 0 AND delivered_at IS NULL) "
        "OR (status = 'SENDING' AND attempt_count >= 1 AND delivered_at IS NULL) "
        "OR (status = 'DELIVERED' AND attempt_count >= 1 AND delivered_at IS NOT NULL) "
        "OR (status = 'RETRY_WAIT' AND attempt_count >= 1 "
        "    AND next_attempt_at IS NOT NULL AND last_error_code IS NOT NULL "
        "    AND delivered_at IS NULL) "
        "OR (status = 'DEAD' AND attempt_count >= 1 "
        "    AND next_attempt_at IS NULL AND last_error_code IS NOT NULL "
        "    AND delivered_at IS NULL)",
    )
