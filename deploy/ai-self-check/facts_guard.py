"""Preserve every existing business table; new AI table must remain empty."""
import json
import re
from sqlalchemy import create_engine, text
from journey_api.config import get_settings

with create_engine(get_settings().database_url).connect() as connection:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    tables = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")).scalars().all()
    result = {}
    for table in tables:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", table)
        if table in {"alembic_version", "worker_heartbeats"}:
            continue
        if table in {"ai_self_checks"}:
            assert connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0, "NEW_AI_WRITES_DETECTED"
            continue
        value = "to_jsonb(t)"
        row = connection.execute(text(f'SELECT count(*), md5(COALESCE(string_agg(md5({value}::text), \'\' ORDER BY md5({value}::text)), \'\')) FROM "{table}" t')).one()
        result[table] = list(row)
    print(json.dumps(result, sort_keys=True))
