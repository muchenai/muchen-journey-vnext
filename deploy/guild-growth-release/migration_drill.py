"""Rehearse 0054 -> 0056 with existing courses, media, progress and favorites."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent))
from facts_guard import snapshot
from grant_runtime import GRANT_SQL

url = make_url(os.environ['DATABASE_URL'])
assert os.environ.get('APP_ENV') == 'test'
assert url.database == 'journey_guild_growth_drill_test', 'DISPOSABLE_DATABASE_REQUIRED'
NEW_TABLES = ('guild_certification_requests', 'guild_memberships', 'guild_selections', 'guild_task_submissions')


def run(*args):
    subprocess.run(args, check=True)


run('alembic', 'upgrade', '0054_academy_covers')
run('python', '-m', 'journey_api.seed')
from journey_api.fixtures import ORGANIZATION_ID, LEARNER_ID, OPERATOR_ID
engine = create_engine(url)
course_id, video_id = uuid.uuid4(), uuid.uuid4()
video, cover = b'isolated-preexisting-video-content', b'isolated-preexisting-cover-content'
with engine.begin() as connection:
    connection.execute(text('INSERT INTO knowledge_favorites (organization_id,user_id,item_id) VALUES (:org,:user,:item)'),
                       {'org': ORGANIZATION_ID, 'user': LEARNER_ID, 'item': uuid.uuid4()})
    connection.execute(text("INSERT INTO community_states (organization_id,module,revision,content) VALUES (:org,'knowledge',3,CAST(:content AS json))"),
                       {'org': ORGANIZATION_ID, 'content': '{"items":[{"title":"Existing published knowledge","modules":["academy"]}]}'} )
    connection.execute(text("INSERT INTO academy_videos (id,organization_id,created_by,file_name,mime_type,size,complete,sha256) VALUES (:id,:org,:author,'existing.mp4','video/mp4',:size,true,:sha)"),
                       {'id': video_id, 'org': ORGANIZATION_ID, 'author': OPERATOR_ID, 'size': len(video), 'sha': hashlib.sha256(video).hexdigest()})
    connection.execute(text('INSERT INTO academy_video_chunks (video_id,position,data) VALUES (:id,0,:data)'), {'id': video_id, 'data': video})
    connection.execute(text("INSERT INTO academy_courses (id,organization_id,author_id,kind,visibility,review_reason,video_id,revision,content) VALUES (:id,:org,:author,'internal','published','',:video,4,CAST(:content AS json))"),
                       {'id': course_id, 'org': ORGANIZATION_ID, 'author': OPERATOR_ID, 'video': video_id,
                        'content': '{"title":"Existing course","description":"Preserve this course during release"}'})
    connection.execute(text('INSERT INTO academy_learning_records (organization_id,user_id,course_id,favorite,seconds,duration,progress,completed) VALUES (:org,:user,:course,true,70,100,70,false)'),
                       {'org': ORGANIZATION_ID, 'user': LEARNER_ID, 'course': course_id})
    connection.execute(text("INSERT INTO academy_course_covers (course_id,source_hash,status,data,sha256) VALUES (:course,:source,'ready',:data,:sha)"),
                       {'course': course_id, 'source': 'a' * 64, 'data': cover, 'sha': hashlib.sha256(cover).hexdigest()})
with engine.connect() as connection:
    before = snapshot(connection)
    for table in ('knowledge_favorites', 'academy_courses', 'academy_videos', 'academy_video_chunks', 'academy_course_covers', 'academy_learning_records'):
        assert before[table][0] == 1, 'PREEXISTING_FIXTURE_MISSING'

run('alembic', 'upgrade', '0056_guild_halls')
with engine.connect() as connection:
    assert snapshot(connection) == before, 'EXISTING_FACTS_CHANGED'
    assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0056_guild_halls'
    for table in NEW_TABLES:
        assert connection.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
    indexes = set(connection.execute(text("SELECT indexname FROM pg_indexes WHERE tablename='guild_certification_requests'")).scalars())
    assert {'uq_guild_pending_request', 'uq_guild_approved_level', 'uq_guild_scoped_pending', 'uq_guild_scoped_approved'} <= indexes

# Exercise the exact new-table grant against an unprivileged role. Roll back
# the role/grants transaction so the disposable drill leaves no cluster roles.
with engine.connect() as connection:
    transaction = connection.begin()
    try:
        if not connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='journey_next_runtime')")).scalar_one():
            connection.execute(text('CREATE ROLE journey_next_runtime NOLOGIN'))
        connection.execute(text(GRANT_SQL))
        for table in NEW_TABLES:
            for permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE'):
                assert connection.execute(text('SELECT has_table_privilege(:role,:table,:permission)'),
                    {'role': 'journey_next_runtime', 'table': 'public.' + table, 'permission': permission}).scalar_one()
    finally:
        transaction.rollback()

print('Exact 0054 to 0056 migration: existing Academy media, learning progress, favorites and all business facts preserved; four new runtime table grants verified', flush=True)
