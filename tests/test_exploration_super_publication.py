"""Certified administrators submit exploration tasks and super administrators publish them."""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from journey_api.db import SessionLocal
from journey_api.models import Assignment, Organization, Role, RoleAssignment, TaskDefinition, TaskDefinitionStatus, TaskVersion
from journey_api.review_admin_models import ReviewAdminAccess, TaskPublicationRequest
from journey_api.review_admin_routes import task_content_for_publish
from test_dynamic_exploration import command as learner_command, exploration, post, read
from test_course_workspace import identity
from test_review_admin import content as novice_content
from test_wp09_feishu_identity import assert_ok


def content():
    return dict(title='超级管理员直接发布的探索营任务', summary='阅读课程材料后确认完成学习。', camp='exploration',
        order=9999, completionMode='learning', materials=[dict(id='learn', name='学习材料', type='link',
        url='https://example.com/learning')], reviewMode='manual')


def save(staff, task_id, revision, data):
    return staff[0].put('/api/v1/review-admin/tasks/' + task_id, headers={'X-CSRF-Token': staff[1]},
        json={'id': task_id, 'expected_revision': revision, 'content': data})


def demote(author):
    with SessionLocal.begin() as session:
        row = session.get(ReviewAdminAccess, author)
        row.access_role, row.level = 'admin', '高级'


def test_ordinary_exploration_publisher_submits_to_another_certified_super(exploration):
    staff, learner, author = exploration
    demote(author)
    task_id = str(uuid.uuid4())
    draft = assert_ok(save(staff, task_id, 0, content()))
    upload = staff[0].post('/api/v1/review-admin/exploration/materials', params={'name': 'questions.txt'},
        headers={'X-CSRF-Token': staff[1], 'Content-Type': 'text/plain'}, content=b'Questions')
    assert_ok(upload)
    draft = assert_ok(save(staff, task_id, draft['revision'], {**content(), 'title': '普通管理员发布的课程'}))
    links = {'expected_revision': draft['revision'], 'verified_material_urls': ['https://example.com/learning']}
    assert post(staff, f'review-admin/tasks/{task_id}/publish', links).status_code == 403
    generic = task_content_for_publish(content())
    assert post(staff, f'ops/task-definitions/{task_id}/publish', {**generic, **links,
        'expected_revision': draft['definitionRevision'], 'reviewed_by': str(author)}).status_code == 403
    assert post(staff, f'review-admin/tasks/{task_id}/archive', {
        'expected_revision': draft['revision'], 'archived': True}).status_code == 403
    assert post(staff, f'review-admin/tasks/{task_id}/delete', {
        'expected_revision': draft['revision']}).status_code == 403
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/submit-publication', links))
    pending = assert_ok(staff[0].get('/api/v1/review-admin/publications'))['items'][0]
    endpoint = f"/api/v1/review-admin/publications/{pending['id']}/decision"
    decision = {'expected_revision': 1, 'decision': 'approved'}
    assert staff[0].post(endpoint, json=decision, headers={'X-CSRF-Token': staff[1]}).status_code == 403
    with SessionLocal() as session:
        org = session.get(ReviewAdminAccess, author).organization_id
        assert session.scalar(select(func.count(TaskVersion.id)).where(TaskVersion.task_definition_id == uuid.UUID(task_id))) == 0
    other_super, reviewer_id = identity(org, Role.REVIEWER, '另一位超级管理员', 'super_admin')
    assert_ok(other_super.post(endpoint, json=decision))
    assert read(learner, task_id)['title'] == '普通管理员发布的课程'
    with SessionLocal() as session:
        version = session.scalar(select(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id)))
        assert version.reviewed_by == reviewer_id


@pytest.mark.parametrize('decision', ['approved', 'rejected'])
def test_super_can_decide_own_pending_request_after_promotion(exploration, decision):
    staff, _, author = exploration
    demote(author)
    task_id = str(uuid.uuid4())
    draft = assert_ok(save(staff, task_id, 0, content()))
    submitted = assert_ok(post(staff, f'review-admin/tasks/{task_id}/submit-publication',
        {'expected_revision': draft['revision'], 'verified_material_urls': ['https://example.com/learning']}))
    path = f"review-admin/publications/{submitted['publication']['id']}/decision"
    command = {'expected_revision': 1, 'decision': decision, 'comment': '请补充材料。' if decision == 'rejected' else ''}
    assert post(staff, path, command).status_code == 403
    with SessionLocal.begin() as session:
        session.get(ReviewAdminAccess, author).access_role = 'super_admin'
    result = assert_ok(post(staff, path, command))
    assert result['status'] == decision
    assert result['submittedBy']['id'] == result['reviewedBy']['id'] == str(author)
    assert post(staff, path, command).status_code == 409
    with SessionLocal() as session:
        versions = session.scalars(select(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id))).all()
        assert [v.published_by for v in versions] == ([author] if decision == 'approved' else [])


@pytest.mark.parametrize('data', [content(), novice_content()], ids=['exploration', 'novice'])
def test_super_manages_other_publishers_task_without_changing_authorship(exploration, data):
    staff, learner, author = exploration
    task_id = str(uuid.uuid4())
    draft = assert_ok(save(staff, task_id, 0, data))
    verified = [material['url'] for material in data['materials']]
    first = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish',
        {'expected_revision': draft['revision'], 'verified_material_urls': verified}))
    if data['camp'] == 'exploration':
        work = assert_ok(learner_command(learner, read(learner, task_id), 'claim'))
    other_org = uuid.uuid4()
    with SessionLocal.begin() as session:
        access = session.get(ReviewAdminAccess, author)
        org = access.organization_id
        access.revoked_at = datetime.now(UTC)
        session.add(Organization(id=other_org, name='独立的外部组织'))
    ordinary, _ = identity(org, Role.REVIEWER, '普通管理员', 'admin')
    foreign, _ = identity(other_org, Role.REVIEWER, '其他组织超级管理员', 'super_admin')
    manager, manager_id = identity(org, Role.REVIEWER, '超级管理员', 'super_admin')
    with SessionLocal.begin() as session:
        session.get(ReviewAdminAccess, manager_id).can_grant_super_admin = False
    path = f'review-admin/tasks/{task_id}'
    rev = first['revision']
    for client in [ordinary, foreign]:
        credential = (client, client.headers['X-CSRF-Token'])
        assert save(credential, task_id, rev, data).status_code == 403
        assert post(credential, path + '/archive', {'expected_revision': rev, 'archived': True}).status_code == 404
        assert post(credential, path + '/submit-publication', {'expected_revision': rev}).status_code == 404
        assert post(credential, path + '/publish', {'expected_revision': rev}).status_code == (403 if client is ordinary else 404)
        if data['camp'] == 'exploration':
            assert post(credential, path + '/delete', {'expected_revision': rev}).status_code == (403 if client is ordinary else 404)
    manager = (manager, manager.headers['X-CSRF-Token'])
    updated = assert_ok(save(manager, task_id, rev, {**data, 'title': '编辑他人发布的任务'}))
    assert save(manager, task_id, rev, data).status_code == 409
    live = assert_ok(post(manager, path + '/publish',
        {'expected_revision': updated['revision'], 'verified_material_urls': verified}))
    assert live['authorId'] == str(author) and live['version'] == 2 and live['status'] == 'published'
    archived = assert_ok(post(manager, path + '/archive', {'expected_revision': live['revision'], 'archived': True}))
    assert archived['status'] == 'archived'
    restored = assert_ok(post(manager, path + '/archive', {'expected_revision': archived['revision'], 'archived': False}))
    assert restored['status'] == 'published'
    if data['camp'] == 'exploration':
        deleted = assert_ok(post(manager, path + '/delete', {'expected_revision': restored['revision']}))
        assert deleted['deleted']
        assert post(manager, path + '/archive', {'expected_revision': deleted['revision'], 'archived': False}).status_code == 404
    with SessionLocal() as session:
        versions = session.scalars(select(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id))
            .order_by(TaskVersion.version)).all()
        assert [v.published_by for v in versions] == [author, manager_id]
        assert [v.reviewed_by for v in versions] == [author, manager_id]
        if data['camp'] == 'exploration':
            assignment = session.get(Assignment, uuid.UUID(work['assignmentId']))
            assert assignment.task_version_id == versions[0].id


def test_super_can_delete_another_authors_legacy_exploration_task(exploration):
    _, _, author = exploration
    task_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        org = session.get(ReviewAdminAccess, author).organization_id
        session.add(TaskDefinition(id=task_id, organization_id=org, created_by=author,
            stable_key='DAY-0', status=TaskDefinitionStatus.DRAFT, revision=1))
    client, _ = identity(org, Role.REVIEWER, '超级管理员', 'super_admin')
    deleted = assert_ok(post((client, client.headers['X-CSRF-Token']), f'review-admin/tasks/{task_id}/delete',
        {'expected_revision': 0}))
    assert deleted['deleted'] and deleted['revision'] == 1
    assert str(task_id) not in {t['id'] for t in assert_ok(client.get('/api/v1/review-admin/tasks'))['items']}


def test_company_learner_session_cannot_publish_with_same_users_staff_role(exploration):
    _, learner, author = exploration
    with SessionLocal.begin() as session:
        org = session.get(ReviewAdminAccess, author).organization_id
        uid = session.scalar(select(RoleAssignment.user_id).where(
            RoleAssignment.organization_id == org, RoleAssignment.role == Role.LEARNER))
        session.add(RoleAssignment(id=uuid.uuid4(), user_id=uid, organization_id=org, role=Role.REVIEWER))
        session.add(ReviewAdminAccess(user_id=uid, organization_id=org, access_role="super_admin", granted_by=author))
    # The same account has certified staff access, but this cookie represents its learner login.
    assert save(learner, str(uuid.uuid4()), 0, content()).status_code == 403


def test_super_direct_publish_requires_no_reviewer_and_audits_actual_publisher(exploration):
    staff, learner, author = exploration
    task_id = str(uuid.uuid4())
    data = content()
    draft = assert_ok(save(staff, task_id, 0, data))
    live = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', {'expected_revision': draft['revision'],
        'verified_material_urls': ['https://example.com/learning']}))
    assert live['status'] == 'published' and read(learner, task_id)['title'] == data['title']
    # Even a forged reviewer ID cannot credit someone who did not publish it.
    draft = assert_ok(save(staff, task_id, live['revision'], {**data, 'title': '超级管理员直接发布的更新'}))
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', {'expected_revision': draft['revision'],
        'reviewed_by': str(uuid.uuid4()), 'verified_material_urls': ['https://example.com/learning']}))
    with SessionLocal() as session:
        versions = session.scalars(select(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id))).all()
        assert len(versions) == 2 and all(v.reviewed_by == v.published_by == author for v in versions)
        assert session.scalar(select(func.count(TaskPublicationRequest.id)).where(TaskPublicationRequest.task_id == uuid.UUID(task_id))) == 0


def test_super_generic_exploration_publish_also_records_actual_publisher(exploration):
    staff, _, author = exploration
    task_id = str(uuid.uuid4())
    draft = assert_ok(save(staff, task_id, 0, content()))
    generic = task_content_for_publish(content())
    result = assert_ok(post(staff, f'ops/task-definitions/{task_id}/publish', {**generic,
        'expected_revision': draft['definitionRevision'], 'reviewed_by': str(uuid.uuid4()),
        'verified_material_urls': ['https://example.com/learning']}))
    assert result['reviewed_by'] == result['published_by'] == str(author)


def test_super_uses_direct_publish_in_both_camps(exploration):
    staff, _, author = exploration
    for task, url in ((content(), 'https://example.com/learning'), (novice_content(), 'https://example.com/material')):
        task_id = str(uuid.uuid4())
        draft = assert_ok(save(staff, task_id, 0, task))
        command = {'expected_revision': draft['revision'], 'verified_material_urls': [url]}
        submitted = post(staff, f'review-admin/tasks/{task_id}/submit-publication', command)
        assert submitted.status_code == 409 and submitted.json()['error']['code'] == 'DIRECT_PUBLISH_ONLY'
        assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', command))
        with SessionLocal() as session:
            version = session.scalar(select(TaskVersion).where(TaskVersion.task_definition_id == uuid.UUID(task_id)))
            assert version.reviewed_by == version.published_by == author


def test_legacy_content_apis_cannot_bypass_exploration_super_authority(exploration):
    from journey_api.models import Role, RoleAssignment
    from test_wp26_content_editor import payload
    staff, _, author = exploration
    task_id = str(uuid.uuid4())
    assert_ok(save(staff, task_id, 0, content()))
    try:
        with SessionLocal.begin() as session:
            organization_id = session.get(ReviewAdminAccess, author).organization_id
            session.add_all([RoleAssignment(id=uuid.uuid4(), organization_id=organization_id, user_id=author, role=role)
                for role in [Role.CONTENT_EDITOR, Role.OPERATOR]])
        draft = assert_ok(post(staff, f'content/task-definitions/{task_id}/drafts', {'content': payload()}))
        with SessionLocal.begin() as session:
            # Legacy staff with OPERATOR/CONTENT_EDITOR roles but no super-admin grant.
            session.delete(session.get(ReviewAdminAccess, author))
        assert post(staff, f'content/task-definitions/{task_id}/drafts', {'content': payload()}).status_code == 403
        assert staff[0].put('/api/v1/content/drafts/' + draft['id'],
            headers={'X-CSRF-Token': staff[1], 'Idempotency-Key': str(uuid.uuid4())},
            json={'expected_revision': draft['revision'], 'content': payload('不允许的探索营旧版编辑')}).status_code == 403
        assert post(staff, f"content/drafts/{draft['id']}/submit", {
            'expected_revision': draft['revision'], 'review_note': '请求发布探索营任务内容，请核对材料。'}).status_code == 403
        assert post(staff, f"ops/content-drafts/{draft['id']}/publish", {
            'expected_revision': draft['revision'], 'expected_definition_revision': 1,
            'reviewed_by': str(author), 'review_acknowledged': True, 'verified_material_urls': []}).status_code == 403
        assert post(staff, 'ops/task-definitions', {'stable_key': 'DAY-0'}).status_code == 403
    finally:
        # Fixture-role tests elsewhere select one editor/operator globally.
        with SessionLocal.begin() as session:
            session.execute(delete(RoleAssignment).where(RoleAssignment.user_id == author,
                RoleAssignment.role.in_([Role.CONTENT_EDITOR, Role.OPERATOR])))
