import uuid
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from types import SimpleNamespace
import pytest
from sqlalchemy import delete
from journey_api import directory_cache as cache
from journey_api.db import SessionLocal
from journey_api.directory_cache_models import DirectoryMember, DirectorySync
from journey_api.errors import ApiError
from journey_api.fixtures import ORGANIZATION_ID


@pytest.fixture
def directory():
    class Directory:
        settings = SimpleNamespace(feishu_learner_organization_id=ORGANIZATION_ID, feishu_app_id='cache-test-'+uuid.uuid4().hex)
        people = [{'open_id':'ou_a', 'name':'李测试', 'avatar':'', 'departments':['研发部'], 'job_title':'经理'},
                  {'open_id':'ou_b', 'name':'同名', 'avatar':'', 'departments':['产品部']},
                  {'open_id':'ou_c', 'name':'同名', 'avatar':'', 'departments':['研发部']}]
        tree = [{'id':'od-test','name':'研发部','parent_id':'0','path_ids':['od-test'],'default_mode':'all'}]
        def read_snapshot(self):
            return [{**p,'department_ids':['od-test'],'job_title':p.get('job_title','')} for p in self.read_profiles()], self.tree
        calls = 0
        def read_profiles(self):
            self.calls += 1
            return self.people
    d = Directory()
    yield d
    with SessionLocal.begin() as s:
        for model in (DirectoryMember, DirectorySync):
            s.execute(delete(model).where(*cache.filters(model,d.settings)))


def test_search_is_persistent_and_app_scoped_without_provider_calls(directory):
    d=directory
    assert not cache.search(d.settings,'李')['directory']['ready']
    assert cache.sync_once(d)
    assert cache.search(d.settings,'李')['items'][0]['name']=='李测试'
    # New process/object sees the same database snapshot; search never calls the provider.
    clone=SimpleNamespace(**vars(d.settings))
    assert len(cache.search(clone,'同名')['items'])==2
    assert cache.search(clone,'%')['items']==[]
    clone.feishu_app_id+='other'
    assert cache.search(clone,'李')['items']==[]
    from journey_api.feishu_directory import PersistentFeishuDirectory
    restarted=PersistentFeishuDirectory(d.settings)
    restarted._call=lambda *a,**kw:pytest.fail('search must not call Feishu')
    assert restarted.search('李')['items']
    clone.feishu_app_id=d.settings.feishu_app_id
    clone.feishu_learner_organization_id=uuid.uuid4()
    assert cache.search(clone,'李')['items']==[]
    assert d.calls==1
    assert not cache.sync_once(d) and d.calls==1


def test_failed_sync_keeps_complete_snapshot_then_success_removes_departed_members(directory,monkeypatch):
    d=directory;assert cache.sync_once(d)
    original=d.read_profiles
    def fail():raise ApiError(503,'DIRECTORY_UNAVAILABLE','provider private data')
    monkeypatch.setattr(d,'read_profiles',fail)
    assert not cache.sync_once(d,force=True)
    assert cache.search(d.settings,'李')['items']
    info=cache.status(d.settings)
    assert info['error_code']=='DIRECTORY_UNAVAILABLE' and info['last_updated_at']
    monkeypatch.setattr(d,'read_profiles',original);d.people=d.people[1:]
    assert cache.sync_once(d,force=True)
    assert cache.search(d.settings,'李')['items']==[]
    assert cache.status(d.settings)['error_code'] is None


def test_employee_number_search_is_cached_scoped_case_insensitive_and_literal(directory):
    from journey_api.feishu_directory import PersistentFeishuDirectory
    d=directory
    d.people=[{**d.people[0],'employee_no':'MCE00000004'},
              {**d.people[1],'employee_no':None}, d.people[2]]
    assert cache.sync_once(d)
    cached=PersistentFeishuDirectory(d.settings)
    cached._call=lambda *a,**kw:pytest.fail('employee number search must not call Feishu')
    assert [p['open_id'] for p in cached.search(' mce00000004 ')['items']]==['ou_a']
    assert [p['open_id'] for p in cached.search('00000004')['items']]==['ou_a']
    assert [p['open_id'] for p in cached.search('李测试')['items']]==['ou_a']
    assert len(cached.search('同名')['items'])==2
    for query in ['%', '_', 'MCE00000005', 'ou_a']:
        assert cached.search(query)['items']==[]
    clone=SimpleNamespace(**vars(d.settings))
    clone.feishu_app_id+='other'
    assert cache.search(clone,'MCE00000004')['items']==[]
    clone.feishu_app_id=d.settings.feishu_app_id
    clone.feishu_learner_organization_id=uuid.uuid4()
    assert cache.search(clone,'MCE00000004')['items']==[]
    assert d.calls==1


def test_search_does_not_wait_for_sync_and_duplicate_sync_is_skipped(directory,monkeypatch):
    d=directory;assert cache.sync_once(d)
    entered=Event();release=Event();done=[]
    def slow():
        entered.set()
        assert release.wait(5)
        return d.people
    monkeypatch.setattr(d,'read_profiles',slow)
    worker=Thread(target=lambda:done.append(cache.sync_once(d,force=True)))
    worker.start()
    try:
        assert entered.wait(3)
        assert cache.status(d.settings)['syncing']
        assert cache.search(d.settings,'李')['items']
        assert not cache.sync_once(d,force=True)
    finally:
        release.set();worker.join(5)
    assert done==[True]


def test_manual_refresh_is_coalesced_and_can_run_before_daily_schedule(directory):
    d=directory
    first=cache.request_refresh(d.settings)
    assert first['syncing']
    assert cache.request_refresh(d.settings)['syncing']
    assert cache.sync_once(d)
    assert cache.request_refresh(d.settings)['retry_after_seconds']>0
    with SessionLocal.begin() as s:
        state=s.get(DirectorySync,cache.key(d.settings))
        stamp=cache.now()
        state.last_attempt=stamp-timedelta(seconds=31)
    assert cache.request_refresh(d.settings)['syncing']
    assert cache.sync_once(d) and d.calls==2


def test_incomplete_and_permission_failed_sync_never_serves_partial_results(directory,monkeypatch):
    d=directory;assert cache.sync_once(d)
    def denied():raise ApiError(503,'DIRECTORY_PERMISSION_REQUIRED','denied')
    monkeypatch.setattr(d,'read_profiles',denied)
    assert not cache.sync_once(d,force=True)
    with pytest.raises(ApiError) as exc:cache.search(d.settings,'李')
    assert exc.value.code=='DIRECTORY_PERMISSION_REQUIRED'


def test_invalid_snapshot_is_rolled_back_atomically(directory,monkeypatch):
    d=directory;assert cache.sync_once(d)
    monkeypatch.setattr(d,'read_profiles',lambda:[d.people[0],d.people[0]])
    assert not cache.sync_once(d,force=True)
    assert len(cache.search(d.settings,'同名')['items'])==2
    assert cache.status(d.settings)['error_code']=='DIRECTORY_SYNC_FAILED'


def test_unconfigured_and_test_environment_do_not_start_worker():
    settings=SimpleNamespace(app_env='test')
    assert callable(cache.start_worker(settings))


def test_search_limits_matches_without_losing_same_name_accounts(directory):
    d=directory
    d.people=[{'open_id':f'ou_{i:03d}','name':'同名','departments':[],'avatar':''} for i in range(40)]
    assert cache.sync_once(d)
    result=cache.search(d.settings,'同名')
    assert len(result['items'])==30 and result['has_more']
    assert len({p['open_id'] for p in result['items']})==30


def test_bulk_snapshot_uses_database_and_requires_complete_tree(directory):
    from journey_api.feishu_directory import PersistentFeishuDirectory
    d=directory
    with pytest.raises(ApiError) as exc:cache.bulk_snapshot(d.settings)
    assert exc.value.code=='DIRECTORY_PREPARING'
    assert cache.sync_once(d)
    cached=PersistentFeishuDirectory(d.settings)
    cached._call=lambda *a,**k:pytest.fail('preview must not contact Feishu')
    snapshot=cached.bulk_snapshot()
    assert len(snapshot['people'])==3 and snapshot['tree']==d.tree
    assert snapshot['people'][0]['department_ids']==['od-test']
    assert cached.bulk_snapshot(include_people=False)['people']==[]
    with SessionLocal.begin() as s:
        state=s.get(DirectorySync,cache.key(d.settings));state.department_tree=None
    assert cache.status(d.settings)['ready']  # Name search remains available during upgrade.
    with pytest.raises(ApiError):cached.bulk_snapshot()


def test_tree_and_people_are_read_from_same_database_snapshot(directory,monkeypatch):
    d=directory;assert cache.sync_once(d)
    old_tree=d.tree;original_view=cache.view;triggered=False
    def concurrent_publish(state):
        nonlocal triggered
        info=original_view(state)
        if not triggered:
            triggered=True
            d.tree=[{**d.tree[0],'name':'新部门'}]
            d.people=[{**d.people[0],'name':'新员工'}]
            assert cache.sync_once(d,force=True)
        return info
    monkeypatch.setattr(cache,'view',concurrent_publish)
    snapshot=cache.bulk_snapshot(d.settings)
    assert snapshot['tree']==old_tree and len(snapshot['people'])==3
    latest=cache.bulk_snapshot(d.settings)
    assert latest['tree'][0]['name']=='新部门' and latest['people'][0]['name']=='新员工'


def test_failed_tree_sync_preserves_both_old_tree_and_old_members(directory,monkeypatch):
    d=directory;assert cache.sync_once(d)
    def fail():raise ApiError(503,'DIRECTORY_INCOMPLETE','tree read failed')
    monkeypatch.setattr(d,'read_snapshot',fail)
    assert not cache.sync_once(d,force=True)
    snapshot=cache.bulk_snapshot(d.settings)
    assert len(snapshot['people'])==3 and snapshot['tree']==d.tree


@pytest.mark.parametrize('last_success,current,expected', [
    # Local 03:00 is UTC 19:00 on the preceding date.
    ('2026-10-22T19:00:00+00:00','2026-10-23T18:59:59+00:00',False),
    ('2026-10-22T19:00:00+00:00','2026-10-23T19:00:00+00:00',True),
    ('2026-10-23T19:00:00+00:00','2026-10-23T19:00:00+00:00',False),
    # A manual refresh does not postpone the following daily 03:00 run.
    ('2026-10-23T10:00:00+00:00','2026-10-23T18:59:59+00:00',False),
    ('2026-10-23T10:00:00+00:00','2026-10-23T19:00:00+00:00',True),
    # Catch up after a missed scheduled run, including multi-day downtime.
    ('2026-10-22T10:00:00+00:00','2026-10-23T01:00:00+00:00',True),
    ('2026-10-20T10:00:00+00:00','2026-10-23T01:00:00+00:00',True),
    ('2026-10-23T01:00:00+00:00','2026-10-23T01:05:00+00:00',False),
    ('2026-10-31T03:00:00+08:00','2026-11-01T03:00:00+08:00',True),
])
def test_daily_sync_boundary_and_restart_catchup(last_success,current,expected):
    previous=datetime.fromisoformat(last_success)
    state=SimpleNamespace(department_tree=[],error_code=None,requested_at=None,
        last_attempt=previous,last_success=previous,finished_at=previous)
    assert cache.due(state,datetime.fromisoformat(current)) is expected


def test_daily_schedule_preserves_first_sync_and_failure_retry():
    stamp=datetime(2026,10,23,4,tzinfo=UTC)
    assert cache.due(None,stamp)
    state=SimpleNamespace(department_tree=None,error_code='DIRECTORY_UNAVAILABLE',requested_at=None,member_count=0,
        last_attempt=stamp,last_success=None,finished_at=stamp)
    assert not cache.due(state,stamp+timedelta(seconds=59))
    assert cache.due(state,stamp+timedelta(seconds=60))
    state.error_code=None;state.department_tree=[];state.last_success=stamp-timedelta(days=1)
    state.finished_at=stamp-timedelta(seconds=1)
    assert not cache.due(state,stamp+timedelta(seconds=59))
    assert cache.due(state,stamp+timedelta(seconds=60))
    assert cache.view(state)['interval_seconds']==86400
