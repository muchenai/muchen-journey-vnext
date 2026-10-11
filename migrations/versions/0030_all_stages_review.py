"""Allow review-required learning stages without rewriting published history."""
from alembic import op

revision = "0030_all_stages_review"
down_revision = "0029_treasure_coaching_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_journey_stages_kind_policy", "journey_stage_versions")
    op.create_check_constraint(
        "ck_journey_stages_kind_policy", "journey_stage_versions",
        "completion_policy = 'REVIEW_REQUIRED' OR "
        "(stage_kind IN ('DAY_0', 'TREASURE') AND completion_policy = 'LEARNER_EVIDENCE')",
    )


def downgrade() -> None:
    # Reject downgrade if new published stages exist; never rewrite frozen content.
    op.drop_constraint("ck_journey_stages_kind_policy", "journey_stage_versions")
    op.create_check_constraint(
        "ck_journey_stages_kind_policy", "journey_stage_versions",
        "(stage_kind IN ('DAY_0', 'TREASURE') AND completion_policy = 'LEARNER_EVIDENCE') "
        "OR (stage_kind = 'ASSESSMENT' AND completion_policy = 'REVIEW_REQUIRED')",
    )
