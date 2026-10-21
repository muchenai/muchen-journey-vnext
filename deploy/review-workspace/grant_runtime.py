"""Grant DML only on the new Review tables in the existing database."""
import os
from sqlalchemy import create_engine, text


with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0038_review_admin_workspace"
    for table in ("review_admin_tasks", "review_admin_decisions", "review_admin_certifications"):
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO journey_next_runtime"))
