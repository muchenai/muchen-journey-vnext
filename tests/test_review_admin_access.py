import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID
from journey_api.identity import credential_hash, utc_now, SESSION_COOKIE
from journey_api.models import User, UserStatus, Role, RoleAssignment, ExternalIdentity, IdentitySession, TaskVersion, Organization
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.review_admin_routes import directory_subject
from test_wp09_feishu_identity import oauth_provider, begin_oauth, callback, client_for, assert_ok
from test_review_admin import content


class Directory:
    def __init__(self):
        self.people = [{"open_id":"ou_"+uuid.uuid4().hex,"name":"同名成员","departments":["产品部"],"avatar":""},
                       {"open_id":"ou_"+uuid.uuid4().hex,"name":"同名成员","departments":["交付部"],"avatar":""}]
        self.available = True
    def search(self,q):
        return {"items":[p for p in self.people if q in p["name"]],"has_more":False}
    def get_user(self,open_id):
        if not self.available:
            raise ApiError(503,"DIRECTORY_UNAVAILABLE","通讯录暂不可用")
        match=next((p for p in self.people if p["open_id"]==open_id),None)
        if not match:
            raise ApiError(422,"DIRECTORY_MEMBER_INVALID","非公司成员")
        return match


def login_admin(provider,subject):
    c=client_for('admin-'+uuid.uuid4().hex)
    code=uuid.uuid4().hex
    provider.subjects[code]=subject
    response=callback(c,code,begin_oauth(c,'/review'))
    return c,response


@pytest.fixture
def admin_setup(oauth_provider,monkeypatch):
    from journey_api import feishu_directory
    monkeypatch.setenv('FEISHU_LEARNER_ORGANIZATION_ID',str(ORGANIZATION_ID))
    get_settings.cache_clear()
    directory=Directory()
    monkeypatch.setattr(feishu_directory,'get_directory',lambda:directory)
    super_id=uuid.uuid4(); subject='ou_'+uuid.uuid4().hex
    with SessionLocal.begin() as s:
        s.add(User(id=super_id,organization_id=ORGANIZATION_ID,display_name='授权超级管理员',status=UserStatus.ACTIVE));s.flush()
        for role in [Role.OPERATOR,Role.REVIEWER]:
            s.add(RoleAssignment(id=uuid.uuid4(),organization_id=ORGANIZATION_ID,user_id=super_id,role=role))
        s.add(ReviewAdminAccess(user_id=super_id,organization_id=ORGANIZATION_ID,access_role='super_admin',level='高级',domain='产品开发',granted_by=super_id))
        s.add(ExternalIdentity(id=uuid.uuid4(),organization_id=ORGANIZATION_ID,user_id=super_id,provider='FEISHU',subject=directory_subject(subject),revision=1))
    c,response=login_admin(oauth_provider,subject)
    csrf=assert_ok(response)['csrf_token']
    return c,{'X-CSRF-Token':csrf},directory,oauth_provider,super_id


def grant(setup,index=0,revision=0,level='初级'):
    c,h,d,_,_=setup
    result=assert_ok(c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[index]['open_id'],'domain':'产品开发','level':level,'expected_revision':revision}))
    with SessionLocal() as s:
        identity=s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(d.people[index]['open_id'])))
        return next(m for m in result['items'] if m['id']==str(identity.user_id))


def test_directory_selects_stable_account_and_requires_super(admin_setup):
    c,h,d,provider,super_id=admin_setup
    results=assert_ok(c.get('/api/v1/review-admin/directory?q=同名'))['items']
    assert len(results)==2 and results[0]['open_id']!=results[1]['open_id']
    member=grant(admin_setup,1)
    admin,response=login_admin(provider,d.people[1]['open_id']);token=assert_ok(response)['csrf_token']
    assert assert_ok(admin.get('/api/v1/session'))['user_id']==member['id']
    rights=assert_ok(admin.get('/api/v1/review-admin/capabilities'))
    assert rights=={'isSuperAdmin':False,'canGrantSuperAdmins':False,'canPublish':True,'level':'初级','allowedDifficulties':['入门']}
    for path in ['/members','/directory?q=同名','/directory/status']:
        assert admin.get('/api/v1/review-admin'+path).status_code==403
    assert admin.post('/api/v1/review-admin/directory/refresh',headers={'X-CSRF-Token':token}).status_code==403
    assert admin.get('/api/v1/ops/identity-access').status_code==403
    assert admin.post('/api/v1/review-admin/members/grant',headers={'X-CSRF-Token':token},json={'open_id':d.people[0]['open_id']}).status_code==403
    assert admin.post(f'/api/v1/review-admin/members/{super_id}/revoke',headers={'X-CSRF-Token':token},json={'expected_revision':1,'confirmed':True}).status_code==403
    _,response=login_admin(provider,d.people[0]['open_id']);assert response.status_code==403
    with SessionLocal() as s:
        assert not s.scalar(select(ExternalIdentity.id).where(ExternalIdentity.subject==directory_subject(d.people[0]['open_id'])))
    assert c.post(f'/api/v1/review-admin/members/{super_id}/revoke',headers=h,json={'expected_revision':1,'confirmed':True}).status_code==403


def test_members_enrich_cached_profiles_by_identity_not_name_and_preserve_revoked(admin_setup,monkeypatch):
    from journey_api.directory_cache_models import DirectoryMember
    c,h,d,_,_=admin_setup
    first=grant(admin_setup,0)
    second=grant(admin_setup,1)
    settings=get_settings()
    with SessionLocal.begin() as s:
        oid=uuid.uuid4()
        s.add(Organization(id=oid,name='其他组织'));s.flush()
        for org,app,number in [(ORGANIZATION_ID,settings.feishu_app_id,'MCE00001'),
                               (ORGANIZATION_ID,settings.feishu_app_id+'-other','WRONG-APP'),
                               (oid,settings.feishu_app_id,'WRONG-ORG')]:
            s.add(DirectoryMember(organization_id=org,app_id=app,open_id=d.people[0]['open_id'],search_name='同名成员',
                profile={'name':'同名成员','employee_no':number,'departments':['开发部'],'department_paths':['平台中心 / 开发部']}))
    def no_provider(*args,**kwargs):pytest.fail('administrator list must only use cached directory data')
    monkeypatch.setattr(d,'get_user',no_provider)
    monkeypatch.setattr(d,'search',no_provider)
    rows={m['id']:m for m in assert_ok(c.get('/api/v1/review-admin/members'))['items']}
    assert rows[first['id']]['employee_no']=='MCE00001'
    assert rows[first['id']]['department_paths']==['平台中心 / 开发部']
    assert rows[second['id']]['employee_no']=='' and rows[second['id']]['department_paths']==[]
    assert_ok(c.post('/api/v1/review-admin/members/'+first['id']+'/revoke',headers=h,
        json={'expected_revision':1,'confirmed':True}))
    row=next(m for m in assert_ok(c.get('/api/v1/review-admin/members'))['items'] if m['id']==first['id'])
    assert row['status']=='revoked' and row['employee_no']=='MCE00001'
    assert row['accessRole']=='admin'


def test_publish_level_is_checked_again_after_downgrade(admin_setup):
    c,h,d,provider,_=admin_setup
    member=grant(admin_setup)
    admin,response=login_admin(provider,d.people[0]['open_id']);ah={'X-CSRF-Token':assert_ok(response)['csrf_token']}
    task_id=str(uuid.uuid4()); body=content();body['difficulty']='挑战'
    url='/api/v1/review-admin/tasks/'+task_id
    assert admin.put(url,headers=ah,json={'id':task_id,'expected_revision':0,'content':body}).status_code==403
    cert='/api/v1/review-admin/members/'+member['id']+'/certification'
    assert_ok(c.put(cert,headers=h,json={'expected_revision':1,'domain':'产品开发','level':'高级'}))
    draft=assert_ok(admin.put(url,headers=ah,json={'id':task_id,'expected_revision':0,'content':body}))
    assert draft['revision']==1
    assert_ok(c.put(cert,headers=h,json={'expected_revision':2,'domain':'产品开发','level':'初级'}))
    publish={'expected_revision':1,'reviewed_by':str(REVIEWER_ID),'verified_material_urls':['https://example.com/material']}
    assert admin.post(url+'/publish',headers={**ah,'Idempotency-Key':str(uuid.uuid4())},json=publish).status_code==403
    from journey_api.review_admin_routes import task_content_for_publish
    raw={**task_content_for_publish(body),'expected_revision':draft['definitionRevision'],'reviewed_by':str(REVIEWER_ID),'verified_material_urls':['https://example.com/material']}
    assert admin.post('/api/v1/ops/task-definitions/'+task_id+'/publish',headers={**ah,'Idempotency-Key':str(uuid.uuid4())},json=raw).status_code==403
    assert admin.post(url+'/archive',headers=ah,json={'expected_revision':1,'archived':False}).status_code==403
    with SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(TaskVersion).where(TaskVersion.task_definition_id==uuid.UUID(task_id)))==0
    assert_ok(c.put(cert,headers=h,json={'expected_revision':3,'domain':'产品开发','level':'高级'}))
    assert assert_ok(admin.post(url+'/publish',headers={**ah,'Idempotency-Key':str(uuid.uuid4())},json=publish))['version']==1


def test_revocation_blocks_old_sessions_and_new_oauth_preserves_learner_and_tasks(admin_setup):
    c,h,d,provider,_=admin_setup
    member=grant(admin_setup);uid=uuid.UUID(member['id'])
    admin,response=login_admin(provider,d.people[0]['open_id']);ah={'X-CSRF-Token':assert_ok(response)['csrf_token']}
    task_id=str(uuid.uuid4())
    assert_ok(admin.put('/api/v1/review-admin/tasks/'+task_id,headers=ah,json={'id':task_id,'expected_revision':0,'content':content()}))
    # A separate existing learner session must remain valid after revocation.
    learner=client_for('preserved-learner-'+uuid.uuid4().hex);token=uuid.uuid4().hex
    with SessionLocal.begin() as s:
        s.add(RoleAssignment(id=uuid.uuid4(),user_id=uid,organization_id=ORGANIZATION_ID,role=Role.LEARNER))
        s.add(IdentitySession(id=uuid.uuid4(),user_id=uid,organization_id=ORGANIZATION_ID,role=Role.LEARNER,
            token_hash=credential_hash(get_settings().session_secret,'session',token),csrf_token_hash='x'*64,expires_at=utc_now()+timedelta(hours=1)))
    learner.cookies.set(SESSION_COOKIE,token)
    assert_ok(c.post('/api/v1/review-admin/members/'+member['id']+'/revoke',headers=h,json={'expected_revision':1,'confirmed':True}))
    assert admin.get('/api/v1/review-admin/reviews').status_code==401
    assert learner.get('/api/v1/session').status_code==200
    assert learner.get('/api/v1/review-admin/reviews').status_code==403
    _,response=login_admin(provider,d.people[0]['open_id']);assert response.status_code==403
    from journey_api.review_admin_models import ReviewAdminTask
    with SessionLocal() as s:
        assert s.get(ReviewAdminTask,uuid.UUID(task_id)) is not None
        assert s.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id==uid)).revoked_at is None
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={'open_id':d.people[0]['open_id'],'expected_revision':1}).status_code==409
    restored=grant(admin_setup,revision=2)
    assert restored['id']==member['id'] and restored['status']=='active'
    _,response=login_admin(provider,d.people[0]['open_id']);assert_ok(response)


def test_no_grant_on_directory_failure_or_forged_account(admin_setup):
    c,h,d,_,_=admin_setup
    before=c.get('/api/v1/review-admin/members').json()['data']['items']
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={'open_id':'ou_outsider'}).status_code==422
    d.available=False
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={'open_id':d.people[0]['open_id']}).status_code==503
    assert c.get('/api/v1/review-admin/members').json()['data']['items']==before


def test_directory_account_in_other_organization_is_not_reassigned(admin_setup):
    c,h,d,_,_=admin_setup
    oid=uuid.uuid4();uid=uuid.uuid4()
    with SessionLocal.begin() as s:
        s.add(Organization(id=oid,name='隔离企业'));s.flush()
        s.add(User(id=uid,organization_id=oid,display_name='同名成员',status=UserStatus.ACTIVE));s.flush()
        s.add(ExternalIdentity(id=uuid.uuid4(),organization_id=oid,user_id=uid,provider='FEISHU',subject=directory_subject(d.people[0]['open_id']),revision=1))
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={'open_id':d.people[0]['open_id']}).status_code==409
    with SessionLocal() as s:
        assert s.get(User,uid).organization_id==oid
        assert s.get(ReviewAdminAccess,uid) is None


def make_grant_owner(setup):
    with SessionLocal.begin() as s:
        s.get(ReviewAdminAccess, setup[4]).can_grant_super_admin=True


@pytest.mark.parametrize('display_name',['刘默文','李鑫波','其他超级管理员'])
def test_names_do_not_confer_super_grant_authority(admin_setup,display_name):
    c,h,d,_,uid=admin_setup
    with SessionLocal.begin() as s:s.get(User,uid).display_name=display_name
    assert assert_ok(c.get('/api/v1/review-admin/capabilities'))['canGrantSuperAdmins'] is False
    response=c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'super_admin'})
    assert response.status_code==403
    with SessionLocal() as s:
        assert s.scalar(select(ExternalIdentity.id).where(
            ExternalIdentity.subject==directory_subject(d.people[0]['open_id']))) is None
    assert grant(admin_setup)['accessRole']=='admin'


def test_owner_can_grant_super_without_delegating_owner_authority(admin_setup):
    c,h,d,provider,owner=admin_setup
    make_grant_owner(admin_setup)
    assert assert_ok(c.get('/api/v1/review-admin/capabilities'))['canGrantSuperAdmins'] is True
    assert_ok(c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'super_admin','level':'初级'}))
    delegated,response=login_admin(provider,d.people[0]['open_id'])
    dh={'X-CSRF-Token':assert_ok(response)['csrf_token']}
    rights=assert_ok(delegated.get('/api/v1/review-admin/capabilities'))
    assert rights['isSuperAdmin'] and not rights['canGrantSuperAdmins']
    assert rights['allowedDifficulties']==['入门','进阶','挑战'] and rights['level']=='高级'
    assert_ok(delegated.get('/api/v1/review-admin/directory?q=同名'))
    assert delegated.post('/api/v1/review-admin/members/grant',headers=dh,json={
        'open_id':d.people[1]['open_id'],'access_role':'super_admin'}).status_code==403
    # New super admins can still grant, certify, and revoke ordinary members.
    result=assert_ok(delegated.post('/api/v1/review-admin/members/grant',headers=dh,json={
        'open_id':d.people[1]['open_id'],'access_role':'admin'}))
    with SessionLocal() as s:
        identity=s.scalar(select(ExternalIdentity).where(ExternalIdentity.subject==directory_subject(d.people[1]['open_id'])))
        member=next(m for m in result['items'] if m['id']==str(identity.user_id))
    assert member['certification']['level']=='初级'
    url='/api/v1/review-admin/members/'+member['id']
    assert_ok(delegated.put(url+'/certification',headers=dh,json={'expected_revision':1,'domain':'产品开发','level':'中级'}))
    assert_ok(delegated.post(url+'/revoke',headers=dh,json={'expected_revision':2,'confirmed':True}))
    assert delegated.post(f'/api/v1/review-admin/members/{owner}/revoke',headers=dh,
        json={'expected_revision':1,'confirmed':True}).status_code==403


def test_owner_promotes_existing_admin_without_new_identity_or_self_modification(admin_setup):
    c,h,d,provider,owner=admin_setup
    make_grant_owner(admin_setup)
    member=grant(admin_setup)
    response=c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'super_admin','expected_revision':0})
    assert response.status_code==409
    result=assert_ok(c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'super_admin','expected_revision':1}))
    promoted=next(m for m in result['items'] if m['id']==member['id'])
    assert promoted['accessRole']=='super_admin' and promoted['revision']==2
    with SessionLocal() as s:
        row=s.get(ReviewAdminAccess,uuid.UUID(member['id']))
        assert not row.can_grant_super_admin
        assert s.scalar(select(func.count()).select_from(ExternalIdentity).where(
            ExternalIdentity.subject==directory_subject(d.people[0]['open_id'])))==1
    # The grant form cannot demote existing super admins or change their authority.
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'admin','expected_revision':2}).status_code==403


def test_privileged_flag_cannot_be_injected_and_revoked_owner_has_no_authority(admin_setup):
    c,h,d,_,uid=admin_setup
    make_grant_owner(admin_setup)
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'super_admin','can_grant_super_admin':True}).status_code==422
    with SessionLocal.begin() as s:s.get(ReviewAdminAccess,uid).revoked_at=utc_now()
    assert c.post('/api/v1/review-admin/members/grant',headers=h,json={
        'open_id':d.people[0]['open_id'],'access_role':'super_admin'}).status_code==401


def test_directory_refresh_requires_csrf_and_super_admin(admin_setup,monkeypatch):
    from journey_api import directory_cache
    c,h,_,_,_=admin_setup
    calls=[]
    info={'ready':True,'syncing':False,'last_updated_at':'2026-10-23T02:00:00+00:00'}
    monkeypatch.setattr(directory_cache,'status',lambda settings:info)
    monkeypatch.setattr(directory_cache,'request_refresh',lambda settings:calls.append('refresh') or {**info,'syncing':True})
    assert assert_ok(c.get('/api/v1/review-admin/directory/status'))==info
    assert c.post('/api/v1/review-admin/directory/refresh').status_code==403
    assert not calls
    assert assert_ok(c.post('/api/v1/review-admin/directory/refresh',headers=h))['syncing']
    assert calls==['refresh']
