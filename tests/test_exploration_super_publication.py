"""Exploration editing is super-admin only and publication has no reviewer hop."""
import uuid
from sqlalchemy import delete, func, select

from journey_api.db import SessionLocal
from journey_api.models import TaskDefinition, TaskVersion
from journey_api.review_admin_models import ReviewAdminAccess, ReviewAdminTask, TaskPublicationRequest
from journey_api.review_admin_routes import task_content_for_publish
from test_dynamic_exploration import exploration, post, read
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


def test_ordinary_cannot_create_upload_or_switch_novice_to_exploration(exploration):
    staff, _, author = exploration
    demote(author)
    task_id = str(uuid.uuid4())
    assert save(staff, task_id, 0, content()).status_code == 403
    with SessionLocal() as session:
        assert session.get(TaskDefinition, uuid.UUID(task_id)) is None
    upload = staff[0].post('/api/v1/review-admin/exploration/materials', params={'name': 'questions.txt'},
        headers={'X-CSRF-Token': staff[1], 'Content-Type': 'text/plain'}, content=b'Questions')
    assert upload.status_code == 403
    assert post(staff, 'review-admin/sandbox', {'task': content(), 'answer': '已经阅读材料并完成这次学习。'}).status_code == 403
    novice = assert_ok(save(staff, task_id, 0, novice_content()))
    assert save(staff, task_id, novice['revision'], content()).status_code == 403
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/submit-publication', {
        'expected_revision': novice['revision'], 'verified_material_urls': ['https://example.com/material']}))


def test_demoted_owner_cannot_modify_rename_camp_archive_delete_or_publish_existing_exploration(exploration):
    staff, _, author = exploration
    task_id = str(uuid.uuid4())
    data = content()
    draft = assert_ok(save(staff, task_id, 0, data))
    demote(author)
    assert save(staff, task_id, draft['revision'], {**data, 'title': '不允许更新'}).status_code == 403
    assert save(staff, task_id, draft['revision'], novice_content()).status_code == 403
    assert post(staff, f'review-admin/tasks/{task_id}/publish', {'expected_revision': draft['revision'],
        'verified_material_urls': ['https://example.com/learning']}).status_code == 403
    assert post(staff, f'review-admin/tasks/{task_id}/submit-publication', {'expected_revision': draft['revision'],
        'verified_material_urls': ['https://example.com/learning']}).status_code == 403
    assert post(staff, f'review-admin/tasks/{task_id}/archive', {
        'expected_revision': draft['revision'], 'archived': True}).status_code == 403
    assert post(staff, f'review-admin/tasks/{task_id}/delete', {
        'expected_revision': draft['revision']}).status_code == 403
    generic = task_content_for_publish(data)
    assert post(staff, f'ops/task-definitions/{task_id}/publish', {**generic,
        'expected_revision': draft['definitionRevision'], 'reviewed_by': str(author),
        'verified_material_urls': ['https://example.com/learning']}).status_code == 403
    with SessionLocal() as session:
        row = session.get(ReviewAdminTask, uuid.UUID(task_id))
        assert row.revision == draft['revision'] and row.content['camp'] == 'exploration'
        assert row.content['title'] == data['title'] and row.status == 'draft'
        assert session.scalar(select(func.count(TaskVersion.id)).where(TaskVersion.task_definition_id == uuid.UUID(task_id))) == 0


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


def test_exploration_has_no_new_approval_requests_and_legacy_pending_cannot_publish(exploration):
    staff, _, author = exploration
    task_id = str(uuid.uuid4())
    draft = assert_ok(save(staff, task_id, 0, content()))
    response = post(staff, f'review-admin/tasks/{task_id}/submit-publication', {'expected_revision': draft['revision'],
        'verified_material_urls': ['https://example.com/learning']})
    assert response.status_code == 409 and response.json()['error']['code'] == 'EXPLORATION_DIRECT_PUBLISH_ONLY'
    request_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        row = session.get(ReviewAdminTask, uuid.UUID(task_id))
        session.add(TaskPublicationRequest(id=request_id, organization_id=row.organization_id, task_id=uuid.UUID(task_id),
            submitted_by=author, task_revision=row.revision, revision=1, status='pending', content=dict(row.content),
            verified_material_urls=['https://example.com/learning'], comment=''))
    response = post(staff, f'review-admin/publications/{request_id}/decision', {
        'expected_revision': 1, 'decision': 'approved', 'comment': ''})
    assert response.status_code == 409 and response.json()['error']['code'] == 'EXPLORATION_DIRECT_PUBLISH_ONLY'
    assert_ok(post(staff, f'review-admin/publications/{request_id}/decision', {
        'expected_revision': 1, 'decision': 'rejected', 'comment': '请使用超级管理员直接发布。'}))
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', {'expected_revision': draft['revision'],
        'verified_material_urls': ['https://example.com/learning']}))


def test_novice_super_still_requires_explicit_content_reviewer(exploration):
    staff, _, author = exploration
    task_id = str(uuid.uuid4())
    draft = assert_ok(save(staff, task_id, 0, novice_content()))
    response = post(staff, f'review-admin/tasks/{task_id}/publish', {'expected_revision': draft['revision'],
        'verified_material_urls': ['https://example.com/material']})
    assert response.status_code == 422
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', {'expected_revision': draft['revision'],
        'reviewed_by': str(author), 'verified_material_urls': ['https://example.com/material']}))


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
