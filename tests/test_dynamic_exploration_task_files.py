"""Task question files stay separate from learning evidence and obey version gates."""
import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from journey_api.db import SessionLocal
from journey_api.models import Review
from journey_api.review_admin_models import PublishedTaskContent
from test_dynamic_exploration import command, exploration, finish_for_unlock, post, publish, read
from test_wp09_feishu_identity import assert_ok


def upload(staff, name='questions.docx', raw=b'Task questions and written answers'):
    return assert_ok(staff[0].post('/api/v1/review-admin/exploration/materials', params={'name': name},
        content=raw, headers={'X-CSRF-Token': staff[1],
            'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}))


def save(staff, task_id, revision, content):
    return staff[0].put('/api/v1/review-admin/tasks/' + task_id, headers={'X-CSRF-Token': staff[1]},
        json={'id': task_id, 'expected_revision': revision, 'content': content})


def test_uploaded_task_file_is_independent_and_review_uses_pinned_evidence(exploration):
    staff, learner, author = exploration
    raw = b'Question 1: explain your answer.\n' * 100000
    old_file = upload(staff, raw=raw)
    path = '/api/v1/me/exploration/materials/' + old_file['id']
    from journey_api.identity import SESSION_COOKIE, STAFF_SESSION_COOKIE
    staff_headers = {'X-Journey-Session-Scope': 'staff',
        'Cookie': STAFF_SESSION_COOKIE + '=' + staff[0].cookies.get(SESSION_COOKIE)}
    admin_path = '/api/v1/review-admin/exploration/materials/' + old_file['id']
    assert staff[0].get(admin_path, headers=staff_headers).content == raw
    assert staff[0].head(admin_path, headers=staff_headers).headers['content-length'] == str(len(raw))
    assert staff[0].get(path, headers=staff_headers).status_code == 403
    assert learner[0].get(admin_path).status_code == learner[0].head(admin_path).status_code == 403
    assert learner[0].get(path).status_code == 404
    task_id, live, content = publish(exploration, 'assessment', taskFiles=[old_file])
    task = read(learner, task_id)
    assert task['materials'][0]['name'] == '课程材料'
    assert task['taskFiles'][0]['name'] == 'questions.docx'
    metadata = assert_ok(learner[0].get('/api/v1/me/exploration', params={
        'command': 'material', 'taskId': task_id, 'index': 0, 'group': 'task'}))
    assert metadata['id'] == old_file['id'] and metadata['size'] == len(raw)
    response = learner[0].get(path, headers={'Range': 'bytes=0-9'})
    assert response.status_code == 206 and response.content == raw[:10]
    assert learner[0].head(path).headers['content-length'] == str(len(raw))
    task = assert_ok(command(learner, task, 'claim'))
    assert task['openedMaterials'] == []
    new_file = upload(staff, 'revised-questions.docx', b'New questions')
    updated = {**content, 'taskFiles': [new_file]}
    draft = assert_ok(save(staff, task_id, live['revision'], updated))
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', {
        'expected_revision': draft['revision'], 'reviewed_by': str(author),
        'verified_material_urls': ['https://example.com/learning']}))
    pinned = read(learner, task_id)
    assert pinned['versionId'] == task['versionId'] and pinned['taskFiles'] == task['taskFiles']
    assert learner[0].get(path).content == raw
    assert learner[0].get('/api/v1/me/exploration/materials/' + new_file['id']).status_code == 404
    draft = assert_ok(save(staff, task_id, draft['revision'], {**updated, 'completionMode': 'learning'}))
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', {
        'expected_revision': draft['revision'], 'reviewed_by': str(author),
        'verified_material_urls': ['https://example.com/learning']}))
    task = assert_ok(command(learner, pinned, 'submit', answer='已按照题目文件完成测试，提交答案供审核。'))
    with SessionLocal() as session:
        review_id = session.scalar(select(Review.id).where(Review.assignment_id == uuid.UUID(task['assignmentId'])))
    detail = assert_ok(staff[0].get('/api/v1/review-admin/reviews/' + str(review_id)))
    assert detail['task_task_files'][0]['id'] == old_file['id']
    assert detail['task_assessment_url'] == ''
    assert detail['task_completion_mode'] == 'assessment'
    assert any(item['source_label'] == '任务题目文件' for item in detail['task_learning_materials'])
    archived = assert_ok(post(staff, f'review-admin/tasks/{task_id}/archive',
        {'expected_revision': draft['revision'], 'archived': True}))
    assert read(learner, task_id)['taskFiles'] == pinned['taskFiles']
    assert learner[0].get(path).content == raw
    assert archived['status'] == 'archived'


def test_locked_task_file_is_hidden_and_cannot_be_downloaded_by_id(exploration):
    from journey_api.models import Role, RoleAssignment, User
    staff, learner, author = exploration
    first, _, _ = publish(exploration)
    question_file = upload(staff)
    task_id, _, _ = publish(exploration, 'assessment', taskFiles=[question_file])
    snapshot = assert_ok(learner[0].get('/api/v1/me/exploration'))
    locked = next(item for item in snapshot['items'] if item['id'] == task_id)
    assert locked['status'] == 'locked' and locked['taskFiles'] == []
    assert locked['taskFileCount'] == 1 and question_file['url'] not in str(locked)
    metadata = {'command': 'material', 'taskId': task_id, 'index': 0, 'group': 'task'}
    assert learner[0].get('/api/v1/me/exploration', params=metadata).status_code == 409
    path = '/api/v1/me/exploration/materials/' + question_file['id']
    assert learner[0].get(path).status_code == 404
    assert learner[0].head(path).status_code == 404
    # A staff member's learner entry must still obey its learning-stage gate.
    with SessionLocal.begin() as session:
        organization_id = session.get(User, author).organization_id
        user_id = session.scalar(select(User.id).where(User.organization_id == organization_id, User.id != author))
        session.add(RoleAssignment(id=uuid.uuid4(), organization_id=organization_id, user_id=user_id, role=Role.REVIEWER))
    assert learner[0].get(path).status_code == learner[0].head(path).status_code == 404
    assert learner[0].get('/api/v1/review-admin/exploration/materials/' + question_file['id']).status_code == 403
    finish_for_unlock(learner, first)
    assert assert_ok(learner[0].get('/api/v1/me/exploration', params=metadata))['id'] == question_file['id']
    assert learner[0].get(path).status_code == 200


@pytest.mark.parametrize('mode', ['learning', 'checkin'])
def test_no_task_mode_clears_question_files_and_test_link(exploration, mode):
    staff, learner, _ = exploration
    question_file = upload(staff)
    task_id, _, _ = publish(exploration, mode, taskFiles=[question_file,
        {'id': 'unused-question-link', 'name': '已取消的题目链接', 'type': 'link', 'url': 'https://example.com/questions'}],
        assessmentUrl='not-a-valid-url')
    task = read(learner, task_id)
    assert task['taskFiles'] == [] and task['assessmentUrl'] is None
    assert learner[0].get('/api/v1/me/exploration', params={
        'command': 'material', 'taskId': task_id, 'index': 0, 'group': 'task'}).status_code == 404
    assert learner[0].get('/api/v1/me/exploration/materials/' + question_file['id']).status_code == 404
    metadata = assert_ok(learner[0].get('/api/v1/me/exploration', params={
        'command': 'material', 'taskId': task_id, 'index': 0}))
    assert metadata['name'] == '课程材料'
    with SessionLocal() as session:
        published = session.get(PublishedTaskContent, uuid.UUID(task['versionId']))
        assert published.content['taskFiles'] == [] and published.content['assessmentUrl'] == ''
    assert finish_for_unlock(learner, task_id)['status'] == 'completed'


def test_new_assessment_requires_questions_and_verifies_all_resource_links(exploration):
    staff, _, author = exploration
    task_id = str(uuid.uuid4())
    content = {'title': '需要做题的探索课程', 'summary': '阅读材料之后完成选择题或者解答题。',
        'camp': 'exploration', 'completionMode': 'assessment',
        'materials': [{'id': 'learning', 'name': '学习说明', 'type': 'link', 'url': 'https://example.com/read'}]}
    draft = assert_ok(save(staff, task_id, 0, content))
    body = {'expected_revision': draft['revision'], 'reviewed_by': str(author),
        'verified_material_urls': ['https://example.com/read']}
    response = post(staff, f'review-admin/tasks/{task_id}/publish', body)
    assert response.status_code == 422 and '请上传任务文件' in response.text
    submitted = post(staff, f'review-admin/tasks/{task_id}/submit-publication', {
        'expected_revision': draft['revision'], 'verified_material_urls': ['https://example.com/read']})
    assert submitted.status_code == 409 and 'EXPLORATION_DIRECT_PUBLISH_ONLY' in submitted.text
    content.update(taskFiles=[{'id': 'questions', 'name': '任务题目', 'type': 'link',
        'url': 'https://example.com/questions'}], assessmentUrl='https://example.com/test')
    draft = assert_ok(save(staff, task_id, draft['revision'], content))
    response = post(staff, f'review-admin/tasks/{task_id}/publish', {**body, 'expected_revision': draft['revision']})
    assert response.status_code == 422 and 'MATERIAL_LINK_VERIFICATION_REQUIRED' in response.text
    links = ['https://example.com/read', 'https://example.com/questions', 'https://example.com/test']
    published = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish',
        {'expected_revision': draft['revision'], 'verified_material_urls': links}))
    assert published['status'] == 'published'
    assert published['taskFiles'][0]['url'] == content['taskFiles'][0]['url']


def test_legacy_assessment_without_new_fields_remains_submittable(exploration):
    _, learner, _ = exploration
    def legacy_snapshot(session, *_):
        # Recreate the old JSON format before insert; immutable rows stay intact.
        for row in session.new:
            if isinstance(row, PublishedTaskContent):
                row.content = {key: value for key, value in row.content.items()
                    if key not in {'taskFiles', 'assessmentUrl'}}
    event.listen(Session, 'before_flush', legacy_snapshot)
    try:
        task_id, _, _ = publish(exploration, 'assessment')
    finally:
        event.remove(Session, 'before_flush', legacy_snapshot)
    task = read(learner, task_id)
    assert task['taskFiles'] == [] and task['assessmentUrl'] is None
    task = assert_ok(command(learner, task, 'claim'))
    task = assert_ok(command(learner, task, 'submit', answer='按原任务说明完成作业，提交审核。'))
    assert task['status'] == 'pending'


def test_question_file_reference_and_novice_scope_are_validated(exploration):
    from journey_api.exploration_models import ExplorationMaterial
    from journey_api.models import Organization, User
    staff, learner, _ = exploration
    missing = {'id': 'missing', 'name': '题目文件', 'type': 'file',
        'url': 'exploration-material:' + str(uuid.uuid4())}
    task_id = str(uuid.uuid4())
    content = {'title': '探索课程', 'summary': '阅读材料之后完成作业。',
        'camp': 'exploration', 'completionMode': 'assessment', 'taskFiles': [missing]}
    response = save(staff, task_id, 0, content)
    assert response.status_code == 422 and 'INVALID_MATERIAL' in response.text
    response = save(staff, task_id, 0, {**content, 'camp': 'novice'})
    assert response.status_code == 422
    response = save(staff, task_id, 0, {**content, 'taskFiles': [missing] * 21})
    assert response.status_code == 422
    foreign_org, foreign_author, foreign_file = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=foreign_org, name='其他组织'))
        session.flush()
        session.add(User(id=foreign_author, organization_id=foreign_org, display_name='其他发布人'))
        session.flush()
        session.add(ExplorationMaterial(id=foreign_file, organization_id=foreign_org, uploaded_by=foreign_author,
            name='other-questions.txt', kind='file', mime='text/plain', size=1, sha256='0' * 64, content=b'x'))
    foreign = {**missing, 'url': 'exploration-material:' + str(foreign_file)}
    response = save(staff, task_id, 0, {**content, 'taskFiles': [foreign]})
    assert response.status_code == 422 and 'INVALID_MATERIAL' in response.text
    path = '/api/v1/me/exploration/materials/' + str(foreign_file)
    assert learner[0].get(path).status_code == 404
    assert staff[0].get('/api/v1/review-admin/exploration/materials/' + str(foreign_file)).status_code == 404


def test_learning_and_question_file_limits_remain_independent(exploration):
    from journey_api.models import TaskVersion
    _, learner, _ = exploration
    resources = [{'id': str(index), 'name': f'材料 {index}', 'type': 'link',
        'url': f'https://example.com/material/{index}'} for index in range(40)]
    task_id, live, _ = publish(exploration, 'assessment', materials=resources[:20], taskFiles=resources[20:],
        assessmentUrl='https://example.com/test')
    task = read(learner, task_id)
    assert len(task['materials']) == len(task['taskFiles']) == 20
    metadata = assert_ok(learner[0].get('/api/v1/me/exploration', params={
        'command': 'material', 'taskId': task_id, 'index': 19, 'group': 'task'}))
    assert metadata['url'] == resources[-1]['url']
    with SessionLocal() as session:
        version = session.get(TaskVersion, uuid.UUID(live['versionId']))
        assert len(version.learning_materials) == 41
