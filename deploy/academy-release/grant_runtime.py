"""Grant only the five new Academy tables to the existing runtime role."""
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
    assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0054_academy_covers"
    connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.academy_videos, public.academy_video_chunks, public.academy_courses, public.academy_learning_records, public.academy_course_covers TO journey_next_runtime"))
