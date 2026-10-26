"""Read-only fingerprints of every existing business table, including AI history."""
import json
import re
from sqlalchemy import create_engine, text
from journey_api.config import get_settings

def fingerprint_query(table):
    assert re.fullmatch(r"[a-z][a-z0-9_]*", table)
    value = "to_jsonb(t)"
    return text(f'SELECT count(*), md5(COALESCE(string_agg(md5(({value})::text), \'\' ORDER BY md5(({value})::text)), \'\')) FROM "{table}" t')


def snapshot(connection):
    connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    tables = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")).scalars().all()
    result = {}
    for table in tables:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", table)
        if table in {"alembic_version", "worker_heartbeats", "directory_sync", "directory_members"}:
            continue
        row = connection.execute(fingerprint_query(table)).one()
        result[table] = list(row)
    return result


if __name__ == "__main__":
    with create_engine(get_settings().database_url).connect() as connection:
        print(json.dumps(snapshot(connection), sort_keys=True))
