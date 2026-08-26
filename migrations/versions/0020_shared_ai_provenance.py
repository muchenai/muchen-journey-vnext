"""Persist bounded advisory AI provenance on formal work.

Revision ID: 0020_shared_ai_provenance
Revises: 0019_wp30_invitation_control
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0020_shared_ai_provenance"
down_revision = "0019_wp30_invitation_control"
branch_labels = None
depends_on = None


NO_AI = """jsonb_build_object(
    'used', FALSE,
    'purpose', NULL,
    'model_version', NULL,
    'prompt_version', NULL,
    'output_is_advisory_only', TRUE
)"""

AI_PROVENANCE_CHECK = """
jsonb_typeof(ai_use) = 'object'
AND ai_use ?& ARRAY[
    'used', 'purpose', 'model_version', 'prompt_version',
    'output_is_advisory_only'
]
AND (ai_use - ARRAY[
    'used', 'purpose', 'model_version', 'prompt_version',
    'output_is_advisory_only'
]) = '{}'::jsonb
AND jsonb_typeof(ai_use -> 'used') = 'boolean'
AND jsonb_typeof(ai_use -> 'output_is_advisory_only') = 'boolean'
AND (ai_use ->> 'output_is_advisory_only')::boolean = TRUE
AND (
    (
        (ai_use ->> 'used')::boolean = FALSE
        AND ai_use -> 'purpose' = 'null'::jsonb
        AND ai_use -> 'model_version' = 'null'::jsonb
        AND ai_use -> 'prompt_version' = 'null'::jsonb
    )
    OR
    (
        (ai_use ->> 'used')::boolean = TRUE
        AND jsonb_typeof(ai_use -> 'purpose') = 'string'
        AND length(ai_use ->> 'purpose') BETWEEN 3 AND 200
        AND jsonb_typeof(ai_use -> 'model_version') = 'string'
        AND length(ai_use ->> 'model_version') BETWEEN 1 AND 200
        AND jsonb_typeof(ai_use -> 'prompt_version') = 'string'
        AND length(ai_use ->> 'prompt_version') BETWEEN 1 AND 200
    )
)
"""


def upgrade() -> None:
    for table in ("submission_versions", "evaluations"):
        op.add_column(
            table,
            sa.Column(
                "ai_use",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text(NO_AI),
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_ai_provenance",
            table,
            AI_PROVENANCE_CHECK,
        )


def downgrade() -> None:
    for table in ("evaluations", "submission_versions"):
        op.drop_constraint(
            f"ck_{table}_ai_provenance",
            table,
            type_="check",
        )
        op.drop_column(table, "ai_use")
