"""Grant only the five additive exploration tables to the established runtime role."""
import os
from sqlalchemy import create_engine, text

TABLES = ("exploration_catalog_tasks", "exploration_work", "exploration_progress",
          "exploration_materials", "exploration_self_checks")
GRANT_SQL = "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE " + ", ".join("public." + name for name in TABLES) + " TO journey_next_runtime"


if __name__ == "__main__":
    with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0060_migrated_ai_ownership"
        connection.execute(text(GRANT_SQL))
