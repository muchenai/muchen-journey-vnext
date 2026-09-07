from __future__ import annotations

import os
import uuid

import pytest


def test_exported_snapshot_hides_post_export_commits() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        pytest.skip("DATABASE_URL is required for the disposable PostgreSQL integration test")

    import psycopg
    import sqlalchemy
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from scripts.wp31_database_snapshot import export_snapshot, import_snapshot

    assert sqlalchemy.__version__ == "2.0.51"
    assert psycopg.__version__ == "3.3.4"
    parsed = make_url(database_url)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.host == "db-test"
    assert parsed.database == "journey_next_test"

    table = f"wp31_snapshot_{uuid.uuid4().hex}"
    quoted_table = f'"{table}"'
    engine = create_engine(database_url)
    try:
        with engine.begin() as setup:
            setup.exec_driver_sql(f"CREATE TABLE {quoted_table} (value integer NOT NULL)")
            setup.exec_driver_sql(f"INSERT INTO {quoted_table} (value) VALUES (1)")

        with engine.connect() as exporter:
            snapshot_id = export_snapshot(exporter)
            with engine.begin() as writer:
                writer.exec_driver_sql(f"INSERT INTO {quoted_table} (value) VALUES (2)")
            with engine.connect() as importer:
                import_snapshot(importer, snapshot_id)
                imported_count = importer.exec_driver_sql(
                    f"SELECT count(*) FROM {quoted_table}"
                ).scalar_one()
            with engine.connect() as current:
                current_count = current.exec_driver_sql(
                    f"SELECT count(*) FROM {quoted_table}"
                ).scalar_one()

        assert imported_count == 1
        assert current_count == 2
    finally:
        with engine.begin() as cleanup:
            cleanup.exec_driver_sql(f"DROP TABLE IF EXISTS {quoted_table}")
        engine.dispose()
