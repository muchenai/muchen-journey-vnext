"""Grant only the new knowledge favorites table to the existing runtime role."""
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0052_knowledge_publication"
    connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.knowledge_favorites TO journey_next_runtime"))
