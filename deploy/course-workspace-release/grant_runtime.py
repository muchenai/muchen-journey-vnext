"""Grant only the new course and experience tables to the established runtime role."""
import os

TABLES = (
    "course_management_settings", "experience_roster_snapshots", "offline_experience_grants",
    "workspace_courses", "course_study_records", "course_study_preferences", "course_roster_codes",
    "course_study_awards", "exploration_material_chunks",
)
GRANT_SQL = "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE " + ", ".join("public." + name for name in TABLES) + " TO journey_next_runtime"


if __name__ == "__main__":
    from sqlalchemy import create_engine, text

    with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == "journey_next_canary_20260901_c72fea5"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0063_admin_video_storage"
        connection.execute(text(GRANT_SQL))
