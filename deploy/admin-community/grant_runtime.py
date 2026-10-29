"""Grant only new module table DML to the existing application role."""
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ['DATABASE_URL']).begin() as connection:
    assert connection.execute(text('SELECT current_database()')).scalar_one() == 'journey_next_canary_20260901_c72fea5'
    assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0051_community_modules'
    for table in ('published_task_content', 'medal_definitions', 'medal_redemptions', 'novice_unlock_debits', 'task_publication_requests', 'community_states', 'knowledge_files', 'knowledge_chunks', 'guild_contributions'):
        connection.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO journey_next_runtime'))
