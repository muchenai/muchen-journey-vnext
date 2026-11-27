"""Allow the production runtime to read its wallet ledger while exchange is local-only."""
import os

TABLES = ("mall_point_exchanges",)


def grant_read_access(connection):
    from sqlalchemy import text

    # Default privileges on new tables can include writes. Retain only wallet reads.
    connection.execute(text("REVOKE ALL PRIVILEGES ON TABLE public.mall_point_exchanges FROM journey_next_runtime"))
    connection.execute(text("GRANT SELECT ON TABLE public.mall_point_exchanges TO journey_next_runtime"))
    privilege = text("SELECT has_table_privilege('journey_next_runtime', 'public.mall_point_exchanges', :action)")
    assert connection.scalar(privilege, {"action": "SELECT"})
    assert not connection.scalar(privilege, {"action": "INSERT,UPDATE,DELETE,TRUNCATE"})


if __name__ == "__main__":
    from sqlalchemy import create_engine, text

    with create_engine(os.environ["DATABASE_URL"]).begin() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "journey_next_canary_20260901_c72fea5"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0064_profile_mall_points"
        grant_read_access(connection)
