"""Move encrypted display value to completion codes.

Revision ID: 0034_fix_code_ciphertext
Revises: 0033_phone_login_codes
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_fix_code_ciphertext"
down_revision = "0033_phone_login_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("phone_otp_challenges", "code_ciphertext")
    op.add_column("completion_codes", sa.Column("code_ciphertext", sa.Text(), nullable=False))


def downgrade() -> None:
    op.drop_column("completion_codes", "code_ciphertext")
    op.add_column("phone_otp_challenges", sa.Column("code_ciphertext", sa.Text(), nullable=False))
