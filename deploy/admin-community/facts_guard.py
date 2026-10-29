"""Read-only fingerprints of every existing business table, including AI history."""
import json
import re
from sqlalchemy import create_engine, text
from journey_api.config import get_settings

def fingerprint_query(table):
    assert re.fullmatch(r"[a-z][a-z0-9_]*", table)
    value = "to_jsonb(t) - 'novice_task_id'" if table == "enrollments" else "to_jsonb(t)"
    return text(f'SELECT count(*), md5(COALESCE(string_agg(md5(({value})::text), \'\' ORDER BY md5(({value})::text)), \'\')) FROM "{table}" t')


def snapshot(connection):
    connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    tables = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")).scalars().all()
    result = {}
    new_tables = ('published_task_content', 'medal_definitions', 'medal_redemptions', 'novice_unlock_debits', 'task_publication_requests', 'community_states', 'knowledge_files', 'knowledge_chunks', 'guild_contributions')
    if 'published_task_content' in tables:
        assert connection.execute(text("SELECT count(*) FROM enrollments WHERE novice_task_id IS NOT NULL")).scalar_one() == 0, 'NEW_NOVICE_ACTIVITY'
        # The only permitted backfill is an exact snapshot of existing published task metadata.
        mismatch = connection.execute(text("""WITH expected AS (
            SELECT v.id AS task_version_id, v.organization_id, p.content::jsonb AS content
            FROM review_admin_tasks p JOIN task_versions v
            ON v.task_definition_id=p.task_definition_id AND v.organization_id=p.organization_id
            WHERE p.status='published' AND v.version=(SELECT max(v2.version) FROM task_versions v2 WHERE v2.task_definition_id=v.task_definition_id)
        ), actual AS (SELECT task_version_id, organization_id, content::jsonb AS content FROM published_task_content)
        SELECT count(*) FROM ((SELECT * FROM expected EXCEPT SELECT * FROM actual)
        UNION ALL (SELECT * FROM actual EXCEPT SELECT * FROM expected)) differences""")).scalar_one()
        assert mismatch == 0, 'PUBLISHED_CONTENT_BACKFILL_CHANGED'
    for table in new_tables[1:]:
        if table in tables:
            assert connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0, 'NEW_MODULE_ACTIVITY'

    for table in tables:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", table)
        if table in new_tables:
            continue
        if table in {"alembic_version", "worker_heartbeats", "directory_sync", "directory_members"}:
            continue
        row = connection.execute(fingerprint_query(table)).one()
        result[table] = list(row)
    return result


if __name__ == "__main__":
    with create_engine(get_settings().database_url).connect() as connection:
        print(json.dumps(snapshot(connection), sort_keys=True))
