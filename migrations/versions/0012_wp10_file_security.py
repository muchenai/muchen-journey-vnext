"""Add object-store upload expiry, object identity, and real scan states.

Revision ID: 0012_wp10_file_security
Revises: 0011_wp09_feishu_identity
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_wp10_file_security"
down_revision = "0011_wp09_feishu_identity"
branch_labels = None
depends_on = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("attachments", sa.Column("upload_expires_at", TIMESTAMP, nullable=True))
    op.add_column("attachments", sa.Column("storage_etag", sa.String(160), nullable=True))
    op.add_column(
        "attachments", sa.Column("storage_version_id", sa.String(200), nullable=True)
    )
    op.add_column("attachments", sa.Column("scan_completed_at", TIMESTAMP, nullable=True))
    # Bound attachments are deliberately immutable at runtime. The status rename is
    # a bounded data migration, so suspend only that trigger inside this
    # transactional revision and restore it before returning.
    op.execute("ALTER TABLE attachments DISABLE TRIGGER bound_attachments_immutable")
    op.drop_constraint("ck_attachments_scan_status", "attachments", type_="check")
    op.execute(
        "UPDATE attachments SET scan_status = 'CLEAN' WHERE scan_status = 'LOCAL_CLEAN'"
    )
    op.execute(
        "UPDATE attachments SET scan_status = 'INFECTED' "
        "WHERE scan_status = 'LOCAL_REJECTED'"
    )
    op.create_check_constraint(
        "ck_attachments_scan_status",
        "attachments",
        "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'ERROR')",
    )
    op.execute("ALTER TABLE attachments ENABLE TRIGGER bound_attachments_immutable")


def downgrade() -> None:
    op.execute("ALTER TABLE attachments DISABLE TRIGGER bound_attachments_immutable")
    op.drop_constraint("ck_attachments_scan_status", "attachments", type_="check")
    op.execute(
        "UPDATE attachments SET scan_status = 'LOCAL_CLEAN' WHERE scan_status = 'CLEAN'"
    )
    op.execute(
        "UPDATE attachments SET scan_status = 'LOCAL_REJECTED' "
        "WHERE scan_status IN ('INFECTED', 'ERROR')"
    )
    op.create_check_constraint(
        "ck_attachments_scan_status",
        "attachments",
        "scan_status IN ('PENDING', 'LOCAL_CLEAN', 'LOCAL_REJECTED')",
    )
    op.execute("ALTER TABLE attachments ENABLE TRIGGER bound_attachments_immutable")
    op.drop_column("attachments", "scan_completed_at")
    op.drop_column("attachments", "storage_version_id")
    op.drop_column("attachments", "storage_etag")
    op.drop_column("attachments", "upload_expires_at")
