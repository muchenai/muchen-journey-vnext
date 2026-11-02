"""Compatibility probe only: this release grants no new database permissions."""
import os
from sqlalchemy import create_engine, text


with create_engine(os.environ["DATABASE_URL"]).connect() as connection:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0051_community_modules"
