import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.identity import credential_hash, utc_now, SESSION_COOKIE
from journey_api.models import User, UserStatus, Organization, Role, RoleAssignment, IdentitySession, ExternalIdentity
from journey_api.review_admin_models import ReviewAdminAccess, ReviewAdminTask
from test_review_admin import content
from test_review_admin_access import admin_setup, oauth_provider, login_admin, make_grant_owner, directory_subject
from test_wp09_feishu_identity import assert_ok, client_for


def member(client, uid):
    return next(m for m in assert_ok(client.get('/api/v1/review-admin/members'))['items'] if m['id']==str(uid))


def grant_super(setup,index=0):
    client,headers,directory,provider,_=setup
    make_grant_owner(setup)
    assert_ok(client.post('/api/v1/review-admin/members/grant',headers=headers,json={
        'open_id':directory.people[index]['open_id'],'access_role':'super_admin','department':'开发部'}))
    with SessionLocal() as session:
        uid=session.scalar(select(ExternalIdentity.user_id).where(
            ExternalIdentity.subject==directory_subject(directory.people[index]['open_id'])))
    c,response=login_admin(provider,directory.people[index]['open_id'])
    return member(client,uid),c,{'X-CSRF-Token':assert_ok(response)['csrf_token']}


def learner_session(uid):
    c=client_for('preserved-learner-'+uuid.uuid4().hex)
    token=uuid.uuid4().hex
    with SessionLocal.begin() as session:
        session.add(RoleAssignment(id=uuid.uuid4(),user_id=uuid.UUID(uid),organization_id=ORGANIZATION_ID,role=Role.LEARNER))
        session.add(IdentitySession(id=uuid.uuid4(),user_id=uuid.UUID(uid),organization_id=ORGANIZATION_ID,role=Role.LEARNER,
            token_hash=credential_hash(get_settings().session_secret,'session',token),csrf_token_hash='x'*64,
            expires_at=utc_now()+timedelta(hours=1)))
    c.cookies.set(SESSION_COOKIE,token)
    return c


@pytest.mark.parametrize('level,difficulties',[('初级',['入门']),('中级',['入门','进阶']),('高级',['入门','进阶','挑战'])])
def test_owner_demotes_preserving_department_history_and_learner_session(admin_setup,level,difficulties):
    client,headers,directory,provider,_=admin_setup
    row,target,th=grant_super(admin_setup)
    uid=row['id'];url=f'/api/v1/review-admin/members/{uid}/demote'
    learner=learner_session(uid)
    task_id=str(uuid.uuid4())
    assert_ok(target.put('/api/v1/review-admin/tasks/'+task_id,headers=th,json={'id':task_id,'expected_revision':0,'content':content()}))
    result=assert_ok(client.post(url,headers=headers,json={'expected_revision':row['revision'],'confirmed':True,'level':level}))
    changed=next(m for m in result['items'] if m['id']==uid)
    assert changed['accessRole']=='admin' and not changed['protectedAdmin']
    assert changed['certification']['department']=='开发部' and changed['certification']['level']==level
    assert changed['revision']==row['revision']+1
    assert target.get('/api/v1/review-admin/reviews').status_code==401
    assert learner.get('/api/v1/session').status_code==200
    fresh,response=login_admin(provider,directory.people[0]['open_id'])
    fh={'X-CSRF-Token':assert_ok(response)['csrf_token']}
    rights=assert_ok(fresh.get('/api/v1/review-admin/capabilities'))
    assert not rights['isSuperAdmin'] and not rights['canGrantSuperAdmins']
    assert rights['allowedDifficulties']==difficulties
    assert fresh.get('/api/v1/review-admin/members').status_code==403
    assert fresh.post(url,headers=fh,json={'expected_revision':changed['revision'],'confirmed':True,'level':'高级'}).status_code==403
    assert client.post(url,headers=headers,json={'expected_revision':row['revision'],'confirmed':True,'level':level}).status_code==409
    with SessionLocal() as session:
        assert session.get(ReviewAdminTask,uuid.UUID(task_id)) is not None
        assert session.get(User,uuid.UUID(uid)).status==UserStatus.ACTIVE
        assert session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id==uuid.UUID(uid))).revoked_at is None
        roles=set(session.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id==uuid.UUID(uid))))
        assert Role.REVIEWER in roles and Role.LEARNER in roles
        assert Role.OPERATOR not in roles and Role.CONTENT_EDITOR not in roles


def test_owner_revokes_super_and_only_owner_can_reauthorize(admin_setup):
    client,headers,directory,provider,_=admin_setup
    row,target,th=grant_super(admin_setup)
    peer,other,oh=grant_super(admin_setup,1)
    learner=learner_session(row['id'])
    path=f"/api/v1/review-admin/members/{row['id']}/revoke"
    result=assert_ok(client.post(path,headers=headers,json={'expected_revision':row['revision'],'confirmed':True}))
    changed=next(m for m in result['items'] if m['id']==row['id'])
    assert changed['status']=='revoked'
    assert changed['certification']['department']=='开发部'
    assert target.get('/api/v1/review-admin/reviews').status_code==401
    assert learner.get('/api/v1/session').status_code==200
    _,response=login_admin(provider,directory.people[0]['open_id'])
    assert response.status_code==403
    data={'open_id':directory.people[0]['open_id'],'access_role':'admin','expected_revision':changed['revision'],'level':'中级'}
    assert other.post('/api/v1/review-admin/members/grant',headers=oh,json=data).status_code==403
    restored=assert_ok(client.post('/api/v1/review-admin/members/grant',headers=headers,json=data))
    restored=next(m for m in restored['items'] if m['id']==row['id'])
    assert restored['status']=='active' and restored['accessRole']=='admin'
    assert restored['certification']['department']=='开发部' and restored['certification']['level']=='中级'
    _,response=login_admin(provider,directory.people[0]['open_id']);assert_ok(response)


def test_super_cannot_manage_peers_and_owners_are_protected(admin_setup):
    client,headers,directory,provider,owner=admin_setup
    first,actor,ah=grant_super(admin_setup)
    second,_,_=grant_super(admin_setup,1)
    for action in ['demote','revoke']:
        data={'expected_revision':second['revision'],'confirmed':True,**({'level':'初级'} if action=='demote' else {})}
        assert actor.post(f"/api/v1/review-admin/members/{second['id']}/{action}",headers=ah,json=data).status_code==403
        assert actor.post(f"/api/v1/review-admin/members/{first['id']}/{action}",headers=ah,json=data).status_code==403
        assert client.post(f'/api/v1/review-admin/members/{owner}/{action}',headers=headers,json=data).status_code==403
    # A second highest-authority account is also protected, regardless of its display name.
    with SessionLocal.begin() as session:
        session.get(ReviewAdminAccess,uuid.UUID(second['id'])).can_grant_super_admin=True
        session.get(User,uuid.UUID(second['id'])).display_name='已改名的最高权限账号'
    assert member(client,second['id'])['protectedAdmin']
    for action in ['demote','revoke']:
        data={'expected_revision':second['revision'],'confirmed':True,**({'level':'初级'} if action=='demote' else {})}
        assert client.post(f"/api/v1/review-admin/members/{second['id']}/{action}",headers=headers,json=data).status_code==403
    assert member(client,second['id'])['accessRole']=='super_admin'


def test_super_management_rejects_stale_forged_and_other_org_requests(admin_setup):
    client,headers,directory,_,_=admin_setup
    row,_,_=grant_super(admin_setup)
    url=f"/api/v1/review-admin/members/{row['id']}/demote"
    data={'expected_revision':row['revision'],'confirmed':True,'level':'初级'}
    assert client.post(url,json=data).status_code==403
    assert client.post(url,headers=headers,json={**data,'expected_revision':row['revision']-1}).status_code==409
    for change in [{'confirmed':False},{'level':'未知'},{'can_grant_super_admin':True},{'access_role':'super_admin'}]:
        assert client.post(url,headers=headers,json={**data,**change}).status_code==422
    assert member(client,row['id'])['accessRole']=='super_admin'
    with SessionLocal.begin() as session:
        oid=uuid.uuid4();uid=uuid.uuid4()
        session.add(Organization(id=oid,name='隔离组织'));session.flush()
        session.add(User(id=uid,organization_id=oid,display_name='隔离管理员',status=UserStatus.ACTIVE));session.flush()
        session.add(ReviewAdminAccess(user_id=uid,organization_id=oid,access_role='super_admin',level='高级',domain='产品开发',granted_by=uid))
    for action in ['demote','revoke']:
        command=data if action=='demote' else {k:v for k,v in data.items() if k!='level'}
        assert client.post(f'/api/v1/review-admin/members/{uid}/{action}',headers=headers,json=command).status_code==404
