"""Add the WP-12 data-rights request ledger.

Revision ID: 0014_wp12_data_lifecycle
Revises: 0013_wp11_notify_observability
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_wp12_data_lifecycle"
down_revision = "0013_wp11_notify_observability"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "data_rights_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "organization_id",
            UUID,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "subject_user_id",
            UUID,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("request_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "requested_by",
            UUID,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            TIMESTAMP,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("due_at", TIMESTAMP, nullable=False),
        sa.Column(
            "legal_hold",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("legal_hold_reason", sa.String(120), nullable=True),
        sa.Column("resolution_code", sa.String(120), nullable=True),
        sa.Column("completed_at", TIMESTAMP, nullable=True),
        sa.Column(
            "completed_by",
            UUID,
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "request_type IN ('DELETE', 'CORRECT')",
            name="ck_data_rights_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'COMPLETED', 'REJECTED')",
            name="ck_data_rights_request_status",
        ),
        sa.CheckConstraint(
            "due_at > requested_at",
            name="ck_data_rights_request_due_after_request",
        ),
        sa.CheckConstraint(
            "(legal_hold = false AND legal_hold_reason IS NULL) "
            "OR (legal_hold = true AND legal_hold_reason IS NOT NULL)",
            name="ck_data_rights_request_legal_hold",
        ),
        sa.CheckConstraint(
            "(status = 'OPEN' AND completed_at IS NULL AND completed_by IS NULL "
            "AND resolution_code IS NULL) "
            "OR (status IN ('COMPLETED', 'REJECTED') AND completed_at IS NOT NULL "
            "AND completed_by IS NOT NULL AND resolution_code IS NOT NULL)",
            name="ck_data_rights_request_resolution",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_data_rights_request_revision",
        ),
    )
    op.create_index(
        "ix_data_rights_requests_organization_id",
        "data_rights_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_data_rights_requests_subject_user_id",
        "data_rights_requests",
        ["subject_user_id"],
    )
    op.create_index(
        "ix_data_rights_requests_status",
        "data_rights_requests",
        ["status"],
    )
    op.create_index(
        "ix_data_rights_requests_due_at",
        "data_rights_requests",
        ["due_at"],
    )


def downgrade() -> None:
    op.drop_table("data_rights_requests")
