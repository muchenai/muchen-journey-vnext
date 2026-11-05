"""Prove 0052 -> 0054 preserves populated existing content in a disposable DB."""
import os
from pathlib import Path
import subprocess
import sys
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent))
from facts_guard import snapshot

url = make_url(os.environ['DATABASE_URL'])
assert os.environ.get('APP_ENV') == 'test'
assert url.database == 'journey_academy_drill_test', 'DISPOSABLE_DATABASE_REQUIRED'


def run(*args):
    subprocess.run(args, check=True)


run('alembic', 'upgrade', '0052_knowledge_publication')
run('python', '-m', 'journey_api.seed')
from journey_api.fixtures import ORGANIZATION_ID, LEARNER_ID
engine = create_engine(url)
with engine.begin() as connection:
    connection.execute(text('INSERT INTO knowledge_favorites (organization_id,user_id,item_id) VALUES (:org,:user,:item)'),
                       {'org': ORGANIZATION_ID, 'user': LEARNER_ID, 'item': uuid.uuid4()})
    connection.execute(text("INSERT INTO community_states (organization_id,module,revision,content) VALUES (:org,'knowledge',3,CAST(:content AS json))"),
                       {'org': ORGANIZATION_ID, 'content': '{"items":[{"title":"Existing published knowledge","modules":["academy"]}]}'})
with engine.connect() as connection:
    before = snapshot(connection)
    assert before['knowledge_favorites'][0] == 1
run('alembic', 'upgrade', '0054_academy_covers')
with engine.connect() as connection:
    assert snapshot(connection) == before, 'EXISTING_FACTS_CHANGED'
    assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0054_academy_covers'
    for name in ('academy_videos','academy_video_chunks','academy_courses','academy_learning_records','academy_course_covers'):
        assert connection.execute(text(f'SELECT count(*) FROM {name}')).scalar_one() == 0
print('Exact 0052 to 0054 migration: existing knowledge favorites and all business facts preserved', flush=True)
