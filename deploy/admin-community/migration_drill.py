"""Rehearse the exact production range in a disposable test database only."""
import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'tests'),str(Path(__file__).parent)]
from facts_guard import snapshot

url=make_url(os.environ['DATABASE_URL'])
assert url.database and url.database.endswith('_drill_test'), 'DISPOSABLE_DATABASE_REQUIRED'

def run(*args):
    subprocess.run(args,check=True)

run('alembic','upgrade','head')
run('python','-m','journey_api.seed')
from test_novice_tasks import setup
setup.__wrapped__()
run('alembic','downgrade','0047_learner_notification_reads')
engine=create_engine(url)
with engine.connect() as connection:
    before=snapshot(connection)
run('alembic','upgrade','0051_community_modules')
with engine.connect() as connection:
    assert snapshot(connection)==before, 'EXISTING_FACTS_CHANGED'
    assert connection.execute(text('SELECT count(*) FROM published_task_content')).scalar_one()>0
print('Exact 0047 to 0051 migration and published-content backfill: PASS',flush=True)
