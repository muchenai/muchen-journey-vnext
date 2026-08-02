#!/usr/bin/env python3
"""Emit only PII-free migration, schema, count, and aggregate-content facts."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import create_engine, text
from journey_api.config import get_settings


engine = create_engine(get_settings().database_url)
with engine.connect() as connection:
    migration = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    tables = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' "
            "ORDER BY table_name"
        )
    ).scalars().all()
    counts = {}
    content_fingerprints = {}
    for table in tables:
        if not table.replace("_", "").isalnum():
            raise RuntimeError("unsafe table name")
        counts[table] = connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        content_fingerprints[table] = connection.execute(
            text(
                f'SELECT md5(COALESCE(string_agg(md5(to_jsonb(t)::text), \'\' '
                f'ORDER BY md5(to_jsonb(t)::text)), \'\')) FROM "{table}" AS t'
            )
        ).scalar_one()
    active_notification_recipients = connection.execute(
        text("SELECT count(*) FROM notification_endpoints WHERE status='ACTIVE'")
    ).scalar_one()
    schema_rows = connection.execute(
        text(
            "SELECT table_name,column_name,data_type,is_nullable,COALESCE(column_default,'') "
            "FROM information_schema.columns WHERE table_schema='public' "
            "ORDER BY table_name,ordinal_position"
        )
    ).all()
schema_hash = hashlib.sha256(
    json.dumps([list(row) for row in schema_rows], separators=(",", ":")).encode()
).hexdigest()
print(
    json.dumps(
        {
            "migration": migration,
            "schema_sha256": schema_hash,
            "counts": counts,
            "content_fingerprints": content_fingerprints,
            "active_notification_recipients": active_notification_recipients,
        },
        sort_keys=True,
    )
)
