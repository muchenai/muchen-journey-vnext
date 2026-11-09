"""Grant only the four new Guild tables to the existing runtime role."""
import os
from sqlalchemy import create_engine, text

GRANT_SQL = "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.guild_certification_requests, public.guild_memberships, public.guild_selections, public.guild_task_submissions TO journey_next_runtime"


if __name__ == "__main__":
    with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0056_guild_halls"
        connection.execute(text(GRANT_SQL))
