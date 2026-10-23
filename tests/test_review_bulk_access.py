import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.errors import ApiError
from journey_api.models import ExternalIdentity, User, Role, RoleAssignment
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.review_admin_routes import directory_subject
from journey_api.department_directory import DepartmentDirectory
from journey_api.review_bulk_access import sign
from test_review_admin_access import admin_setup, grant, login_admin, make_grant_owner
from test_wp09_feishu_identity import oauth_provider, assert_ok


@pytest.fixture
def bulk(admin_setup,monkeypatch):
    from journey_api import review_bulk_access
    c,h,d,provider,owner=admin_setup
    people=[{**p,'job_title':'项目经理','department_ids':['od-child']} for p in d.people]
    tree=[{'id':'od-root','name':'AI数据交付中心','parent_id':'0','path_ids':['od-root'],'default_mode':'title'},
          {'id':'od-child','name':'项目交付','parent_id':'od-root','path_ids':['od-root','od-child'],'default_mode':'off'}]
    class Fake(DepartmentDirectory):
        def preview_snapshot(self, *, include_people=True):
            return {'tree':tree,'people':people if include_people else [],'directory':{'ready':True,'last_updated_at':'2026-10-23T00:00:00+00:00'}}
        def departments(self, *, root_only=False):return [d for d in tree if d['parent_id']=='0'] if root_only else tree
        def candidates(self,t,r):return people
        def fresh(self,oid,t):
            if not d.available:raise ApiError(422,'DIRECTORY_MEMBER_INVALID','已离职')
            return next(p for p in people if p['open_id']==oid)
    monkeypatch.setattr(review_bulk_access,'DepartmentDirectory',Fake)
    return admin_setup,people,tree


def preview(bulk,mode='title'):
    setup,_,_=bulk;c,h,*_=setup
    return assert_ok(c.post('/api/v1/review-admin/bulk/preview',headers=h,json={
        'rules':[{'department_id':'od-root','mode':mode,'domain':'数据交付'}]}))


def apply(bulk,p,ids):
    c,h,*_=bulk[0]
    return c.post('/api/v1/review-admin/bulk/apply',headers=h,json={
        'preview_token':p['preview_token'],'open_ids':ids,'confirmed':True})


def test_preview_read_only_apply_entry_level_and_idempotent(bulk):
    setup,people,_=bulk
    p=preview(bulk);assert p['new_count']==2
    with SessionLocal() as s:
        assert s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(people[0]['open_id']))) is None
    ids=[x['open_id'] for x in people]
    result=assert_ok(apply(bulk,p,[ids[0],ids[0],ids[1]]))
    assert len(result['items'])==2 and all(x['status']=='created' for x in result['items'])
    assert all(x['status']=='skipped' for x in assert_ok(apply(bulk,p,ids))['items'])
    with SessionLocal() as s:
        for oid in ids:
            identity=s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(oid)))
            row=s.get(ReviewAdminAccess,identity.user_id)
            assert (row.access_role,row.level,row.domain,row.can_grant_super_admin)==('admin','初级','数据交付',False)


def test_existing_advanced_super_and_revoked_never_changed(bulk):
    setup,people,_=bulk
    advanced=grant(setup,0,level='高级')
    make_grant_owner(setup)
    c,h,d,_,_=setup
    assert_ok(c.post('/api/v1/review-admin/members/grant',headers=h,json={'open_id':people[1]['open_id'],'access_role':'super_admin'}))
    p=preview(bulk)
    assert p['new_count']==0
    assert {x['status'] for x in p['items']}=={'existing','super'}
    assert apply(bulk,p,[people[0]['open_id']]).status_code==422
    assert_ok(c.post('/api/v1/review-admin/members/'+advanced['id']+'/revoke',headers=h,json={'expected_revision':advanced['revision'],'confirmed':True}))
    p=preview(bulk)
    assert any(x['status']=='revoked' for x in p['items'])
    assert apply(bulk,p,[people[0]['open_id']]).status_code==422


def test_match_title_not_name_and_all_department_accepts_empty_title(bulk):
    _,people,_=bulk
    people[0]['name']='经理助理';people[0]['job_title']='工程师'
    people[1]['job_title']=''
    p=preview(bulk)
    assert p['new_count']==0
    assert {x['status'] for x in p['items']}=={'not_matched','missing_title'}
    assert preview(bulk,'all')['new_count']==2


def test_fresh_employment_title_ancestry_rechecked(bulk):
    setup,people,tree=bulk
    p=preview(bulk);oid=people[0]['open_id']
    people[0]['job_title']='工程师'
    assert assert_ok(apply(bulk,p,[oid]))['items'][0]['status']=='failed'
    people[0]['job_title']='项目经理'
    tree[1]['path_ids']=['od-child']
    assert assert_ok(apply(bulk,p,[oid]))['items'][0]['status']=='failed'
    tree[1]['path_ids']=['od-root','od-child']
    setup[2].available=False
    assert assert_ok(apply(bulk,p,[oid]))['items'][0]['status']=='failed'


def test_preview_tamper_expiry_and_injected_selection_rejected(bulk):
    setup,people,_=bulk
    p=preview(bulk)
    assert apply(bulk,p,['ou_injected']).status_code==422
    forged={**p,'preview_token':p['preview_token']+'a'}
    assert apply(bulk,forged,[people[0]['open_id']]).status_code==409
    expired=sign({'actor':str(setup[4]),'org':'other','expires':time.time()-1})
    assert apply(bulk,{'preview_token':expired},[people[0]['open_id']]).status_code==409


def test_other_super_cannot_use_preview_and_ordinary_admin_cannot_bulk(bulk):
    setup,people,_=bulk
    p=preview(bulk)
    c,h,d,provider,owner=setup
    grant(setup,1)
    normal,response=login_admin(provider,people[1]['open_id'])
    nh={'X-CSRF-Token':assert_ok(response)['csrf_token']}
    assert normal.get('/api/v1/review-admin/bulk/departments').status_code==403
    body={'preview_token':p['preview_token'],'open_ids':[people[0]['open_id']],'confirmed':True}
    assert normal.post('/api/v1/review-admin/bulk/apply',headers=nh,json=body).status_code==403
    make_grant_owner(setup)
    grant_response=c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':people[1]['open_id'],'expected_revision':1,'access_role':'super_admin'})
    assert_ok(grant_response)
    assert normal.post('/api/v1/review-admin/bulk/apply',headers=nh,json=body).status_code==409


def test_intervening_grant_preserved_and_partial_failure_reported(bulk):
    setup,people,_=bulk
    p=preview(bulk)
    grant(setup,0,level='高级')
    people[1]['job_title']='工程师'
    result=assert_ok(apply(bulk,p,[x['open_id'] for x in people]))['items']
    assert [x['status'] for x in result]==['skipped','failed']
    with SessionLocal() as s:
        identity=s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(people[0]['open_id'])))
        assert s.get(ReviewAdminAccess,identity.user_id).level=='高级'


def test_concurrent_batches_only_create_once(bulk):
    p=preview(bulk);oid=bulk[1][0]['open_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:assert_ok(apply(bulk,p,[oid]))['items'][0]['status'],range(2)))
    assert sorted(results)==['created','skipped']


def test_department_traversal_pagination_dedup_and_partial_failure(monkeypatch):
    from journey_api.feishu_directory import FeishuDirectory
    d=FeishuDirectory(None)
    def pages(path,params):
        if path.endswith('/0/children'):
            yield {'items':[{'open_department_id':'od-root','name':'AI 数据交付中心'}]}
        elif path.endswith('/od-root/children'):
            yield {'items':[{'open_department_id':'od-child','name':'开发'}]}
        elif path.endswith('/children'):yield {'items':[]}
        else:
            u={'open_id':'ou_same','name':'测试','job_title':'高级助理','department_ids':['od-child'], 'status':{'is_activated':True}}
            yield {'items':[u]}
            yield {'items':[u,{**u,'open_id':'ou_left','status':{'is_activated':True,'is_resigned':True}}]}
    monkeypatch.setattr(d,'_pages',pages)
    directory=DepartmentDirectory(d);tree=directory.departments()
    assert tree[0]['default_mode']=='title'
    rules=[{'department_id':'od-root','mode':'title'},{'department_id':'od-child','mode':'all'}]
    assert directory.expanded(tree,rules)['od-child']=='all'
    assert len(directory.candidates(tree,rules))==1
    with pytest.raises(ApiError):directory.expanded(tree,[{'department_id':'bad','mode':'all'}])


def department_preview(bulk, rules):
    c,h,*_=bulk[0]
    return c.post('/api/v1/review-admin/bulk/preview',headers=h,json={'rules':rules})


def two_roots(bulk):
    tree=bulk[2]
    tree.append({'id':'od-other','name':'财务法务合规部','parent_id':'0','path_ids':['od-other'],'default_mode':'all'})
    return [{'department_id':'od-root','mode':'title','domain':'技术开发','level':'高级'},
            {'department_id':'od-other','mode':'all','domain':'PMO','level':'中级'}]


def test_only_roots_returned_and_child_duplicate_invalid_settings_rejected(bulk):
    c,h,*_=bulk[0]
    assert [d['id'] for d in assert_ok(c.get('/api/v1/review-admin/bulk/departments'))['items']]==['od-root']
    rule={'department_id':'od-root','mode':'all','domain':'产品开发','level':'初级'}
    assert department_preview(bulk,[{**rule,'department_id':'od-child'}]).status_code==409
    assert department_preview(bulk,[rule,rule]).status_code==409
    assert department_preview(bulk,[{**rule,'domain':'未知'}]).status_code==422
    assert department_preview(bulk,[{**rule,'level':'超级管理员'}]).status_code==422


def test_each_department_grants_its_domain_level_and_includes_descendants(bulk):
    rules=two_roots(bulk);people=bulk[1]
    people[1]['department_ids']=['od-other'];people[1]['job_title']=''
    p=assert_ok(department_preview(bulk,rules))
    assert p['new_count']==2 and p['conflict_count']==0
    assert {(x['target']['domain'],x['target']['level']) for x in p['items']}=={('技术开发','高级'),('PMO','中级')}
    assert all(x['status']=='created' for x in assert_ok(apply(bulk,p,[u['open_id'] for u in people]))['items'])
    with SessionLocal() as s:
        for person,rule in zip(people,rules):
            identity=s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(person['open_id'])))
            row=s.get(ReviewAdminAccess,identity.user_id)
            assert (row.domain,row.level,row.access_role,row.can_grant_super_admin)==(rule['domain'],rule['level'],'admin',False)


def test_conflict_requires_signed_option_choice_and_can_choose_lower_level(bulk):
    rules=two_roots(bulk);person=bulk[1][0];oid=person['open_id']
    person['department_ids']=['od-child','od-other']
    p=assert_ok(department_preview(bulk,rules))
    row=next(x for x in p['items'] if x['open_id']==oid)
    assert row['status']=='conflict' and row['target'] is None and len(row['options'])==2
    assert apply(bulk,p,[oid]).status_code==422
    c,h,*_=bulk[0]
    body={'preview_token':p['preview_token'],'open_ids':[oid],'confirmed':True}
    assert c.post('/api/v1/review-admin/bulk/apply',headers=h,json={**body,'choices':{oid:'od-child'}}).status_code==422
    assert c.post('/api/v1/review-admin/bulk/apply',headers=h,json={**body,'choices':{oid:'od-other'},'level':'高级'}).status_code==422
    result=assert_ok(c.post('/api/v1/review-admin/bulk/apply',headers=h,json={**body,'choices':{oid:'od-other'}}))
    assert result['items'][0]['status']=='created'
    with SessionLocal() as s:
        identity=s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(oid)))
        row=s.get(ReviewAdminAccess,identity.user_id)
        assert (row.domain,row.level)==('PMO','中级')


def test_same_settings_deduplicate_and_nonmatching_department_not_an_option(bulk):
    rules=two_roots(bulk);person=bulk[1][0]
    person['department_ids']=['od-child','od-other']
    rules[1].update(domain='技术开发',level='高级')
    p=assert_ok(department_preview(bulk,rules))
    row=next(x for x in p['items'] if x['open_id']==person['open_id'])
    assert row['status']=='new' and len(row['options'])==1
    rules[1].update(domain='PMO',level='初级');person['job_title']='工程师'
    p=assert_ok(department_preview(bulk,rules))
    row=next(x for x in p['items'] if x['open_id']==person['open_id'])
    assert row['status']=='new' and row['target']['department_id']=='od-other'


def test_department_ancestry_changed_to_different_configuration_rejected(bulk):
    rules=two_roots(bulk);oid=bulk[1][0]['open_id']
    p=assert_ok(department_preview(bulk,rules))
    bulk[2][1]['path_ids']=['od-other','od-child']
    assert assert_ok(apply(bulk,p,[oid]))['items'][0]['status']=='failed'


def test_legacy_preview_rejected_and_existing_roles_preserved_with_department_levels(bulk):
    rules=two_roots(bulk);setup,people,_=bulk
    grant(setup,0,level='高级');rules[0]['level']='初级'
    p=assert_ok(department_preview(bulk,rules))
    assert next(x for x in p['items'] if x['open_id']==people[0]['open_id'])['status']=='existing'
    from journey_api.review_bulk_access import verify
    from journey_api.auth import Actor
    # Missing version is rejected before an old global-domain payload can be used.
    with pytest.raises(ApiError):
        verify(sign({'expires':time.time()+100}),None)


def test_preview_never_uses_live_directory_or_per_person_permission_queries(bulk,monkeypatch):
    from journey_api import review_bulk_access as routes
    from journey_api.db import engine
    from sqlalchemy import event
    people=bulk[1]
    people[:]=[{**people[0],'open_id':'ou_cached_'+str(i),'job_title':'工程师'} for i in range(1500)]
    def forbidden(*args,**kwargs):pytest.fail('preview used a live or per-person lookup')
    monkeypatch.setattr(routes,'current_access',forbidden)
    monkeypatch.setattr(routes.DepartmentDirectory,'departments',forbidden)
    monkeypatch.setattr(routes.DepartmentDirectory,'candidates',forbidden)
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:
        p=preview(bulk)
    finally:
        event.remove(engine,'before_cursor_execute',capture)
    assert len(p['items'])==1500 and p['new_count']==0
    assert len(statements)<20
    assert p['directory']['ready']
    # Updating rules computes from the snapshot; no live Feishu reads.
    people[0]['job_title']='经理'
    rules=[{'department_id':'od-root','mode':'title','domain':'PMO','level':'高级'}]
    updated=assert_ok(department_preview(bulk,rules))
    assert updated['new_count']==1
    assert updated['items'][0]['target']['level']=='高级'


def test_batched_access_matches_grant_time_statuses(bulk):
    from types import SimpleNamespace
    from journey_api.review_bulk_access import current_access,preview_access
    setup,people,_=bulk
    grant(setup,0,level='高级')
    actor=SimpleNamespace(organization_id=ORGANIZATION_ID)
    with SessionLocal() as s:
        result=preview_access(s,actor,[p['open_id'] for p in people])
        for p in people:
            assert result[p['open_id']]==current_access(s,actor,p['open_id'])[1:]
