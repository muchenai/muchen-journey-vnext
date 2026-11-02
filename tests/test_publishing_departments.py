import uuid
from typing import get_args
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from journey_api.publishing_departments import PublishingDepartment
from journey_api.review_admin_routes import TaskContent, task_content_for_publish
from journey_api.review_admin_models import ReviewAdminCertification, PublishedTaskContent
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from test_review_admin import content
from test_review_admin_access import admin_setup, oauth_provider, grant, login_admin
from test_publication_approvals import setup_flow, save, submit, request_for, decision
from test_wp09_feishu_identity import assert_ok


def test_department_catalog_and_legacy_draft_are_separate_from_domain():
    assert len(get_args(PublishingDepartment)) == 19
    for department in get_args(PublishingDepartment):
        task = TaskContent(**{**content(), 'publishingDepartment':department})
        assert task.domain == '产品开发'
        assert task.publishingDepartment == department
    with pytest.raises(ValidationError):
        TaskContent(**{**content(), 'publishingDepartment':'产品开发'})
    legacy = {k:v for k,v in content().items() if k != 'publishingDepartment'}
    assert TaskContent(**legacy).publishingDepartment == ''
    with pytest.raises(ApiError, match='请选择发布部门'):
        task_content_for_publish(legacy)


def test_department_survives_save_approval_and_immutable_published_snapshot():
    owner,boss,task_id,data,saved = setup_flow()
    data['publishingDepartment'] = '多语种数据交付线'
    saved = save(owner,task_id,saved['revision'],data)
    assert saved['publishingDepartment'] == data['publishingDepartment']
    assert_ok(submit(owner,task_id,saved['revision']))
    pending = request_for(boss,task_id)
    assert pending['task']['publishingDepartment'] == data['publishingDepartment']
    assert decision(owner,pending).status_code == 403
    assert_ok(decision(boss,pending))
    with SessionLocal() as session:
        from journey_api.models import TaskVersion
        row = session.scalar(select(PublishedTaskContent).join(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id)))
        assert row.content['publishingDepartment'] == data['publishingDepartment']
    save(owner,task_id,saved['revision'],{**data,'publishingDepartment':'IT部'})
    with SessionLocal() as session:
        row = session.scalar(select(PublishedTaskContent).join(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id)))
        assert row.content['publishingDepartment'] == '多语种数据交付线'


def test_member_department_round_trip_no_duplicate_or_privilege_change(admin_setup):
    client,headers,directory,provider,super_id = admin_setup
    member=grant(admin_setup,level='高级')
    assert member['certification']['department'] == ''
    url=f"/api/v1/review-admin/members/{member['id']}/certification"
    changed=assert_ok(client.put(url,headers=headers,json={'expected_revision':member['revision'],
        'department':'IT部','level':'初级'}))
    row=next(m for m in changed['items'] if m['id']==member['id'])
    assert row['certification'] == {'department':'IT部','domain':'产品开发','level':'初级'}
    assert row['accessRole']=='admin'
    assert client.put(url,headers=headers,json={'expected_revision':member['revision'],'department':'开发部','level':'高级'}).status_code == 409
    updated=assert_ok(client.post('/api/v1/review-admin/members/grant',headers=headers,json={
        'open_id':directory.people[0]['open_id'],'expected_revision':row['revision'],'department':'开发部','level':'中级'}))
    rows=[m for m in updated['items'] if m['id']==member['id']]
    assert len(rows)==1 and rows[0]['certification']['department']=='开发部'
    assert client.put(url,headers=headers,json={'expected_revision':rows[0]['revision'],'department':'无效部门','level':'高级'}).status_code==422
    ordinary,response=login_admin(provider,directory.people[0]['open_id'])
    csrf=assert_ok(response)['csrf_token']
    assert ordinary.put(url,headers={'X-CSRF-Token':csrf},json={'expected_revision':rows[0]['revision'],
        'department':'IT部','level':'高级'}).status_code==403
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(ReviewAdminCertification).where(
            ReviewAdminCertification.user_id==uuid.UUID(member['id'])))==1


def test_department_only_edit_preserves_super_identity_and_grant_rights(admin_setup):
    from journey_api.review_admin_models import ReviewAdminAccess
    from journey_api.models import RoleAssignment
    client,headers,directory,provider,super_id=admin_setup
    ordinary=grant(admin_setup,level='高级')
    with SessionLocal.begin() as session:
        session.get(ReviewAdminAccess,super_id).can_grant_super_admin=True
        other=session.get(ReviewAdminAccess,uuid.UUID(ordinary['id']))
        other.access_role='super_admin'
    for target in [str(super_id),ordinary['id']]:
        with SessionLocal() as session:
            access=session.get(ReviewAdminAccess,uuid.UUID(target))
            before=(access.access_role,access.can_grant_super_admin,access.level,access.domain,access.revoked_at,access.granted_by)
            roles=set(session.scalars(select(RoleAssignment.id).where(RoleAssignment.user_id==uuid.UUID(target))))
        url=f'/api/v1/review-admin/members/{target}/department'
        rows=assert_ok(client.put(url,headers=headers,json={'expected_revision':0,'department':'开发部'}))['items']
        row=next(m for m in rows if m['id']==target)
        assert row['certification']['department']=='开发部' and row['departmentRevision']==1
        assert row['accessRole']=='super_admin'
        assert client.put(url,headers=headers,json={'expected_revision':0,'department':'IT部'}).status_code==409
        for extra in [{'access_role':'admin'},{'can_grant_super_admin':False},{'level':'初级'}]:
            assert client.put(url,headers=headers,json={'expected_revision':1,'department':'IT部',**extra}).status_code==422
        assert client.put(url,headers=headers,json={'expected_revision':1,'department':'无效部门'}).status_code==422
        with SessionLocal() as session:
            access=session.get(ReviewAdminAccess,uuid.UUID(target))
            assert before==(access.access_role,access.can_grant_super_admin,access.level,access.domain,access.revoked_at,access.granted_by)
            assert roles==set(session.scalars(select(RoleAssignment.id).where(RoleAssignment.user_id==uuid.UUID(target))))
    # Search resolves the exact existing account for the department editor, not its display name.
    results=assert_ok(client.get('/api/v1/review-admin/directory?q=同名'))['items']
    assert results[0]['member_id']==ordinary['id']
    # The old grant restriction still protects existing super administrators from demotion.
    assert client.post('/api/v1/review-admin/members/grant',headers=headers,json={
        'open_id':directory.people[0]['open_id'],'expected_revision':row['revision'],'department':'IT部'}).status_code==403


def test_department_only_edit_does_not_restore_access_or_allow_ordinary_edit(admin_setup):
    from journey_api.models import User,UserStatus,Organization
    client,headers,directory,provider,_=admin_setup
    member=grant(admin_setup,level='高级')
    url=f"/api/v1/review-admin/members/{member['id']}/department"
    ordinary,response=login_admin(provider,directory.people[0]['open_id'])
    csrf=assert_ok(response)['csrf_token']
    assert ordinary.put(url,headers={'X-CSRF-Token':csrf},json={'expected_revision':0,'department':'IT部'}).status_code==403
    assert_ok(client.put(url,headers=headers,json={'expected_revision':0,'department':'IT部'}))
    # A form opened before the department change cannot silently overwrite it.
    assert client.put(url.replace('/department','/certification'),headers=headers,json={
        'expected_revision':member['revision'],'department':'开发部','level':'初级'}).status_code==409
    row=next(m for m in assert_ok(client.get('/api/v1/review-admin/members'))['items'] if m['id']==member['id'])
    assert_ok(client.post(url.replace('/department','/revoke'),headers=headers,json={'expected_revision':row['revision'],'confirmed':True}))
    rows=assert_ok(client.put(url,headers=headers,json={'expected_revision':1,'department':'开发部'}))['items']
    row=next(m for m in rows if m['id']==member['id'])
    assert row['status']=='revoked' and row['roles']==[] and row['certification']['level']=='高级'
    assert row['certification']['department']=='开发部'
    with SessionLocal.begin() as session:
        org=Organization(id=uuid.uuid4(),name='其他组织')
        session.add(org);session.flush()
        outsider=User(id=uuid.uuid4(),organization_id=org.id,display_name='其他组织成员',status=UserStatus.ACTIVE)
        session.add(outsider);session.flush()
        outside_id=str(outsider.id)
    assert client.put(f'/api/v1/review-admin/members/{outside_id}/department',headers=headers,json={'expected_revision':0,'department':'IT部'}).status_code==404
