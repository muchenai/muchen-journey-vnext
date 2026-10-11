"""Allow Feishu OAuth to return to the learner workspace."""
from alembic import op

revision = "0031_learner_feishu_login"
down_revision = "0030_all_stages_review"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_oauth_login_states_return_to", "oauth_login_states", type_="check")
    op.create_check_constraint("ck_oauth_login_states_return_to", "oauth_login_states",
                               "return_to IN ('/review', '/ops', '/content', '/app')")


def downgrade():
    op.execute("DELETE FROM oauth_login_states WHERE return_to = '/app'")
    op.drop_constraint("ck_oauth_login_states_return_to", "oauth_login_states", type_="check")
    op.create_check_constraint("ck_oauth_login_states_return_to", "oauth_login_states",
                               "return_to IN ('/review', '/ops', '/content')")
