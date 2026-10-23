"""Prepare the shared directory and exercise read-only administrator workflows; export counts only."""
import json
import time
import uuid
from sqlalchemy import select
from starlette.requests import Request
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api import directory_cache as cache
from journey_api.feishu_directory import get_directory
from journey_api.auth import Actor
from journey_api.models import RoleAssignment, User
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.review_admin_routes import members
from journey_api.review_bulk_access import Preview, preview

settings = get_settings()
assert settings.app_env == 'production' and not settings.allow_fixture_identity
directory = get_directory()
deadline = time.monotonic() + 300
while time.monotonic() < deadline:
    info = cache.status(settings)
    if info['ready'] and not info['error_code']:
        break
    cache.sync_once(directory)
    time.sleep(2)
else:
    raise RuntimeError('DIRECTORY_NOT_READY')
snapshot = directory.bulk_snapshot()
roots = [d for d in snapshot['tree'] if d['parent_id'] == '0']
assert len(roots) == 9 and snapshot['people'], 'DIRECTORY_ROOTS_CHANGED'
with SessionLocal() as session:
    user = session.get(User, uuid.UUID('934d4bab-2494-4ed3-ac15-9378913b9c01'))
    roles = frozenset(session.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == user.id)))
    actor = Actor(id=user.id, organization_id=user.organization_id, display_name=user.display_name, roles=roles)
    request = Request({'type':'http','state':{'request_id':'release-read-check'}})
    listed = members(request, actor=actor, session=session)['data']['items']
    owner = next(p for p in listed if p['id'] == str(user.id))
    assert owner['accessRole'] == 'super_admin' and owner['employee_no'] and owner['department_paths']
    started = time.monotonic()
    result = directory.search(owner['employee_no'].lower())
    assert any(p['name'] == owner['name'] for p in result['items'])
    elapsed = round((time.monotonic()-started)*1000)
    rules = [{'department_id':d['id'],'mode':d['default_mode'],'domain':'产品开发','level':'初级'} for d in roots if d['default_mode'] != 'off']
    assert len(rules) == 9
    result = preview(Preview(rules=rules),request,actor=actor,session=session)['data']
    assert len(result['items']) > 0
    assert sum(p['status']=='super' for p in result['items']) >= 2
    print(json.dumps({'verification':'PASS','directory_members':len(snapshot['people']),
        'root_departments':len(roots),'administrator_profiles':'PASS','employee_number_search_ms':elapsed,
        'bulk_preview':'PASS','daily_refresh':'03:00 Asia/Shanghai','bulk_grants_applied':0}))
