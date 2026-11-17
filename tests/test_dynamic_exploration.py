"""Regression coverage for the authenticated dynamic exploration lifecycle."""
import uuid
import sys
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.exploration_models import ExplorationCatalogTask, ExplorationWork
from journey_api.exploration_service import settle_treasures
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.models import Assignment, Review
from test_reviewer_workbench import client_for
from test_wp09_feishu_identity import assert_ok


def post(pair, path, body, key=None):
    return pair[0].post('/api/v1/' + path, json=body,
        headers={'X-CSRF-Token': pair[1], 'Idempotency-Key': key or str(uuid.uuid4())})


@pytest.fixture
def exploration(monkeypatch):
    """Each scenario owns its organization and leaves the default queue alone."""
    from journey_api.config import get_settings
    from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
    from journey_api.models import ExternalIdentity, IdentitySession, Organization, Role, RoleAssignment, User
    from journey_api.review_admin_models import ReviewAdminAccess
    organization_id, author, learner_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(sys.modules[__name__], 'ORGANIZATION_ID', organization_id)
    with SessionLocal.begin() as session:
        session.add(Organization(id=organization_id, name='独立探索营回归测试组织'))
        session.flush()
        session.add_all([User(id=author, organization_id=organization_id, display_name='课程发布人'),
            User(id=learner_id, organization_id=organization_id, display_name='课程学员')])
        session.flush()
        session.add_all([RoleAssignment(id=uuid.uuid4(), organization_id=organization_id, user_id=author, role=Role.REVIEWER),
            RoleAssignment(id=uuid.uuid4(), organization_id=organization_id, user_id=learner_id, role=Role.LEARNER)])
        session.add(ReviewAdminAccess(user_id=author, organization_id=organization_id, access_role='super_admin',
            level='初级', domain='产品开发', granted_by=author))

    def login(user_id, role):
        token, csrf = uuid.uuid4().hex + uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
        with SessionLocal.begin() as session:
            identity = ExternalIdentity(id=uuid.uuid4(), user_id=user_id, organization_id=organization_id,
                provider='FEISHU' if role == Role.REVIEWER else 'NICKNAME_PHONE', subject=uuid.uuid4().hex,
                revision=1, verified_at=datetime.now(UTC))
            session.add(identity)
            session.flush()
            session.add(IdentitySession(id=uuid.uuid4(), organization_id=organization_id, user_id=user_id,
                external_identity_id=identity.id, external_identity_revision=1, role=role,
                token_hash=credential_hash(get_settings().session_secret, 'session', token),
                csrf_token_hash=credential_hash(get_settings().session_secret, 'csrf', csrf),
                expires_at=datetime.now(UTC) + timedelta(hours=1)))
        client = client_for('exploration-' + str(user_id))
        client.cookies.set(SESSION_COOKIE, token)
        client.cookies.set(CSRF_COOKIE, csrf)
        return client, csrf

    return login(author, Role.REVIEWER), login(learner_id, Role.LEARNER), author


def publish(exploration, mode='learning', *, legacy_empty_requirements=False, **changes):
    staff, learner, author = exploration
    task_id = str(uuid.uuid4())
    content = dict(title='动态探索营课程', summary='阅读课程材料，了解公司的任务要求和具体学习内容。',
        camp='exploration', order=9999, completionMode=mode, domain='', difficulty='', badges=[],
        materials=[dict(id='link', name='课程材料', type='link', url='https://example.com/learning')],
        reviewMode='manual', passScore=60, rubric=[], rubricAttachments=[])
    content.update(changes)
    if mode == 'assessment' and not content.get('taskFiles') and 'assessmentUrl' not in changes:
        content['assessmentUrl'] = 'https://example.com/test'
    draft = assert_ok(staff[0].put(f'/api/v1/review-admin/tasks/{task_id}',
        headers={'X-CSRF-Token': staff[1]}, json={'id': task_id, 'expected_revision': 0, 'content': content}))
    if legacy_empty_requirements:
        # Reconstruct a pre-upgrade draft before its immutable first publish.
        from journey_api.models import TaskDefinition
        from journey_api.review_admin_models import ReviewAdminTask
        with SessionLocal.begin() as session:
            session.get(TaskDefinition, uuid.UUID(task_id)).stable_key = 'EXPLORATION-DYNAMIC-20261117-' + task_id
            profile = session.get(ReviewAdminTask, uuid.UUID(task_id))
            profile.content = {**profile.content, 'requirements': []}
    resources = [*content['materials'], *(content.get('taskFiles', []) if mode == 'assessment' else [])]
    links = [item['url'] for item in resources if item['type'] == 'link']
    if mode == 'assessment' and content.get('assessmentUrl'):
        links.append(content['assessmentUrl'])
    live = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', dict(expected_revision=draft['revision'],
        reviewed_by=str(author), verified_material_urls=list(dict.fromkeys(links)))))
    return task_id, live, content


def read(learner, task_id):
    return assert_ok(learner[0].get('/api/v1/me/exploration', params={'command': 'learnerTask', 'taskId': task_id}))


def command(learner, task, name, **values):
    return post(learner, 'me/exploration', dict(command=name, taskId=task['id'],
        versionId=task['versionId'], revision=task['revision'], **values))


def finish_for_unlock(learner, task_id):
    task = read(learner, task_id)
    if task['completionMode'] == 'assessment':
        if not task['claimed']:
            task = assert_ok(command(learner, task, 'claim'))
        return assert_ok(command(learner, task, 'submit', answer='已经完成本课程测试，提交结果供审核。'))
    if task['completionMode'] == 'learning':
        for index in range(len(task['materials'])):
            task = assert_ok(command(learner, task, 'readMaterial', index=index))
    return assert_ok(command(learner, task, 'completeLearning', checkinConfirmed=task['completionMode'] == 'checkin'))


def test_reading_complete_idempotency_and_novice_isolation(exploration):
    _, learner, _ = exploration
    task_id, _, _ = publish(exploration)
    task = read(learner, task_id)
    assert task['status'] == 'active' and task['completionMode'] == 'learning'
    assert task['experience'] == task['points'] == 0
    assert command(learner, task, 'completeLearning').status_code == 409
    task = assert_ok(command(learner, task, 'readMaterial', index=0))
    assert task['openedMaterials'] == [0] and task['claimed']
    key = str(uuid.uuid4())
    body = dict(command='completeLearning', taskId=task_id, versionId=task['versionId'], revision=task['revision'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: assert_ok(post(learner, 'me/exploration', body, key)), range(2)))
    assert results[0]['status'] == results[1]['status'] == 'completed'
    assert results[0]['revision'] == results[1]['revision']
    listing = assert_ok(learner[0].get('/api/v1/me/novice/tasks'))
    assert task_id not in {item['id'] for item in listing['items']}
    assert learner[0].get('/api/v1/me/novice/tasks/' + task_id).status_code == 404
    assert command(learner, task, 'readMaterial', index=0).status_code == 409


def test_checkin_requires_explicit_confirmation_and_keeps_no_fake_review(exploration):
    _, learner, _ = exploration
    task_id, _, _ = publish(exploration, 'checkin', reviewMode='ai')
    task = read(learner, task_id)
    assert command(learner, task, 'completeLearning').status_code == 422
    task = assert_ok(command(learner, task, 'completeLearning', checkinConfirmed=True))
    assert task['status'] == 'completed' and task['checkinConfirmed']
    with SessionLocal() as session:
        assert session.scalar(select(Review.id).where(Review.assignment_id == uuid.UUID(task['assignmentId']))) is None


def test_assessment_real_review_return_and_resubmit(exploration):
    staff, learner, _ = exploration
    task_id, _, _ = publish(exploration, 'assessment', assessmentUrl='https://example.com/test')
    task = assert_ok(command(learner, read(learner, task_id), 'claim'))
    assert command(learner, task, 'submit', answer='   ').status_code == 422
    for decision in ('REQUEST_REVISION', 'APPROVE'):
        task = assert_ok(command(learner, task, 'submit', answer='测试已完成，结果链接 https://example.com/result'))
        assert task['status'] == 'pending'
        with SessionLocal() as session:
            review_id = session.scalar(select(Review.id).where(Review.assignment_id == uuid.UUID(task['assignmentId']))
                .order_by(Review.assigned_at.desc()).limit(1))
        detail = assert_ok(staff[0].get('/api/v1/review-admin/reviews/' + str(review_id)))
        lease = assert_ok(post(staff, f'review-admin/reviews/{review_id}/claim', dict(action='acquire', expected_revision=detail['revision'])))
        assert_ok(post(staff, f'review-admin/reviews/{review_id}/decision', dict(expected_revision=lease['revision'],
            claim_token=lease['token'], decision=decision, feedback='请补充结果说明和实际完成情况，便于核对。',
            reasons=['依据或论证不足'] if decision == 'REQUEST_REVISION' else [])))
        task = read(learner, task_id)
        assert task['status'] == ('returned' if decision == 'REQUEST_REVISION' else 'completed')
    assert task['submissionCount'] == 2
    assert [item['status'] for item in task['activityRecords']] == ['NEEDS_REVISION', 'COMPLETED']
    assert [item['decision'] for item in task['feedbackRecords']] == ['REVISION_REQUIRED', 'PASS']
    treasures = assert_ok(learner[0].get('/api/v1/me/exploration', params={'command': 'treasures'}))['treasures']
    assert treasures['count'] <= 4


def test_version_is_pinned_and_restore_uses_published_order(exploration):
    staff, learner, _ = exploration
    task_id, live, content = publish(exploration)
    claimed = assert_ok(command(learner, read(learner, task_id), 'claim'))
    content.update(title='尚未发布的课程标题', order=1)
    draft = assert_ok(staff[0].put('/api/v1/review-admin/tasks/' + task_id, headers={'X-CSRF-Token': staff[1]},
        json={'id': task_id, 'expected_revision': live['revision'], 'content': content}))
    assert read(learner, task_id)['title'] == '动态探索营课程'
    old_order = claimed['order']
    archived = assert_ok(post(staff, f'review-admin/tasks/{task_id}/archive', dict(expected_revision=draft['revision'], archived=True)))
    assert read(learner, task_id)['assignmentId'] == claimed['assignmentId']
    restored = assert_ok(post(staff, f'review-admin/tasks/{task_id}/archive', dict(expected_revision=archived['revision'], archived=False)))
    assert restored['publishedOrder'] == old_order
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/delete', dict(expected_revision=restored['revision'])))
    assert learner[0].get('/api/v1/me/exploration', params={'command':'learnerTask','taskId':task_id}).status_code == 404
    with SessionLocal() as session:
        assert session.get(Assignment, uuid.UUID(claimed['assignmentId'])) is not None


def test_large_material_real_upload_range_and_unpublished_acl(exploration):
    staff, learner, _ = exploration
    raw = b'x' * (2 * 1024 * 1024 + 1)
    uploaded = assert_ok(staff[0].post('/api/v1/review-admin/exploration/materials?name=training.mp4', content=raw,
        headers={'X-CSRF-Token':staff[1], 'Content-Type':'video/mp4'}))
    path = '/api/v1/me/exploration/materials/' + uploaded['id']
    assert learner[0].get(path).status_code == 404
    task_id, _, _ = publish(exploration, materials=[uploaded])
    metadata = assert_ok(learner[0].get('/api/v1/me/exploration', params={'command':'material','taskId':task_id,'index':0}))
    assert metadata['id'] == uploaded['id']
    response = learner[0].get(path + '?inline=1', headers={'Range':'bytes=1-5'})
    assert response.status_code == 206 and response.content == b'xxxxx'
    assert response.headers['content-range'] == f'bytes 1-5/{len(raw)}'
    assert learner[0].head(path).headers['content-length'] == str(len(raw))
    assert learner[0].get(path, headers={'Range':'bytes=999999999-'}).status_code == 416


@pytest.mark.parametrize('count', [1, 2, 3, 8])
def test_treasures_unique_once_and_short_catalog_can_graduate(count):
    entries = [SimpleNamespace(task_id=str(index)) for index in range(count)]
    completed = [(str(index), f'2026-11-17T10:00:{index:02}', '课程') for index in reversed(range(count))]
    game = dict(attempts=[], drops=[], ruleVersion=2)
    settle_treasures(game, entries, completed)
    original = list(game['drops'])
    assert {drop['treasureId'] for drop in original} == {'compass','crystal','starmap','key'}
    assert {'0', str(count - 1)}.issubset({drop['taskId'] for drop in original})
    settle_treasures(game, entries, completed)
    assert game['drops'] == original and len(game['attempts']) == count


def test_real_ai_failure_is_saved_without_completing_task(exploration, monkeypatch):
    from journey_api.errors import ApiError
    class FailedReviewer:
        def review(self, *_):
            raise ApiError(503, 'AI_UNAVAILABLE', '模型服务暂时不可用。')
    monkeypatch.setattr('journey_api.ai_self_check_clients.get_reviewer', lambda: FailedReviewer())
    _, learner, _ = exploration
    task_id, _, _ = publish(exploration, 'assessment')
    task = assert_ok(command(learner, read(learner, task_id), 'claim'))
    checked = assert_ok(command(learner, task, 'selfCheck', answer='测试结果已经完成，等待审核确认。'))
    assert checked['record']['status'] == 'FAILED' and checked['record']['mode'] == 'AI'
    assert checked['task']['status'] == 'active'
    history = assert_ok(learner[0].get('/api/v1/me/exploration', params={'command':'selfCheckHistory','taskId':task_id}))
    assert history['items'][0]['id'] == checked['record']['id']


@pytest.mark.parametrize('phone', [True, False])
def test_graduation_real_code_identity_and_preserved_legacy_state(exploration, monkeypatch, phone):
    from journey_api.auth import Actor
    from journey_api.exploration_service import treasure_view, unlock_graduation
    from journey_api.exploration_models import ExplorationProgress
    from journey_api.models import CompletionCode, Enrollment, ExternalIdentity, Role
    _, learner, author = exploration
    task_id, _, _ = publish(exploration)
    task = assert_ok(command(learner, read(learner, task_id), 'readMaterial', index=0))
    task = assert_ok(command(learner, task, 'completeLearning'))
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        user_id = session.get(Enrollment, assignment.enrollment_id).learner_id
        actor = Actor(id=user_id, organization_id=ORGANIZATION_ID, roles=frozenset({Role.LEARNER}), display_name='学员')
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == user_id))
        identity.provider = 'PHONE_PASSWORD' if phone else 'FEISHU'
        monkeypatch.setattr('journey_api.exploration_service.catalog', lambda *_: [session.get(ExplorationCatalogTask, uuid.UUID(task_id))])
        result = unlock_graduation(session, actor)['graduation']
        assert result['status'] == ('READY' if phone else 'NOT_REQUIRED')
        code = session.scalar(select(CompletionCode).where(CompletionCode.user_id == user_id))
        if not phone:
            assert code is None
            return
        assert result['code'].startswith('MJ-') and len(result['code']) == 11
        original_hash = code.code_hash
        assert unlock_graduation(session, actor)['graduation']['code'] == result['code']
        progress = session.get(ExplorationProgress, (ORGANIZATION_ID, user_id))
        progress.unlocked_at = None
        assert treasure_view(session, actor)['graduation']['status'] == 'READY'
        assert code.code_hash == original_hash
        code.used_at, code.migrated_to_user_id = datetime.now(UTC), author
        assert treasure_view(session, actor)['graduation']['status'] == 'MIGRATED'


def test_explicit_seed_is_rerunnable_and_preserves_admin_edits(exploration):
    from scripts.import_exploration_catalog import import_catalog
    from journey_api.models import TaskDefinition
    from journey_api.review_admin_models import ReviewAdminTask
    _, _, author = exploration
    with SessionLocal.begin() as session:
        first = import_catalog(session, ORGANIZATION_ID, author, author)
        seeded = session.scalar(select(TaskDefinition).where(TaskDefinition.organization_id == ORGANIZATION_ID,
            TaskDefinition.stable_key == 'EXPLORATION-DYNAMIC-20261117-01'))
        profile = session.get(ReviewAdminTask, seeded.id)
        profile.content = {**profile.content, 'title': '管理员已经更改的课程标题'}
        profile.revision += 1
    with SessionLocal.begin() as session:
        second = import_catalog(session, ORGANIZATION_ID, author, author)
        assert not second['inserted'] and len(second['preserved']) == 8
        profile = session.get(ReviewAdminTask, seeded.id)
        assert profile.content['title'] == '管理员已经更改的课程标题'


def test_reference_requirements_and_criteria_are_exact_without_rewriting_snapshots(exploration):
    from journey_api.models import TaskDefinition
    from journey_api.review_admin_models import PublishedTaskContent
    _, learner, _ = exploration
    expected_default = {
        'learning': ['打开并学习全部有效学习材料。', '学完后点击进入下一板块，无需文字作业或人工审核。'],
        'checkin': ['完成培训签退，并成功进入项目培训群。', '确认已经进入项目培训群后完成本任务，无需文字作业。'],
        'assessment': ['打开测试文档，按文档要求完成测试。', '提交测试结果、结果链接或简短说明，等待审核。'],
    }
    expected_seed = {
        'learning': ['逐项打开并学习本任务的学习材料。', '学完后进入下一板块，无需提交文字作业或等待人工审核。'],
        'checkin': ['扫码签退，填写的手机号须与招聘时预留号码一致。',
            '签退后查看入项邀请、项目信息和负责人，并加入项目培训群；看不到项目请在培训群反馈。',
            '确认已经成功进入项目培训群后，完成培训签退。'],
        'assessment': ['阅读福利与实用信息学习材料。', '打开培训测试文档，按文档要求完成测试。',
            '提交测试结果、结果截图链接或简短说明，等待审核。'],
    }
    for mode in expected_default:
        task_id, live, _ = publish(exploration, mode)
        task = read(learner, task_id)
        assert task['requirements'] == expected_default[mode]
        assert task['criteria'] == (['完成测试并提交结果，由审核人确认。'] if mode == 'assessment' else expected_default[mode])
        finish_for_unlock(learner, task_id)
        task_id, live, _ = publish(exploration, mode, legacy_empty_requirements=True)
        assert read(learner, task_id)['requirements'] == expected_seed[mode]
        with SessionLocal() as session:
            assert session.get(PublishedTaskContent, uuid.UUID(live['versionId'])).content['requirements'] == []
        finish_for_unlock(learner, task_id)
    task_id, _, _ = publish(exploration, 'assessment', reviewMode='ai', rubric=[dict(
        id='result', name='结果说明', points=100, description='核对测试结果与任务要求。')])
    assert read(learner, task_id)['criteria'] == ['结果说明：核对测试结果与任务要求。']


def test_editing_legacy_seed_preserves_same_mode_and_resets_changed_mode_requirements(exploration):
    from journey_api.review_admin_models import PublishedTaskContent
    staff, learner, author = exploration
    task_id, live, content = publish(exploration, 'assessment', legacy_empty_requirements=True)

    def save(revision, fields):
        return assert_ok(staff[0].put('/api/v1/review-admin/tasks/' + task_id,
            headers={'X-CSRF-Token': staff[1]},
            json={'id': task_id, 'expected_revision': revision, 'content': fields}))

    first = save(live['revision'], content)
    assert first['requirements'] == ['阅读福利与实用信息学习材料。', '打开培训测试文档，按文档要求完成测试。',
        '提交测试结果、结果截图链接或简短说明，等待审核。']
    custom = ['管理员明确配置的本阶段任务要求。']
    second = save(first['revision'], {**content, 'requirements': custom})
    third = save(second['revision'], content)
    assert third['requirements'] == custom
    changed = {**content, 'completionMode': 'learning', 'requirements': custom}
    fourth = save(third['revision'], changed)
    assert fourth['requirements'] == ['打开并学习全部有效学习材料。', '学完后点击进入下一板块，无需文字作业或人工审核。']
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', dict(expected_revision=fourth['revision'],
        reviewed_by=str(author), verified_material_urls=['https://example.com/learning'])))
    assert read(learner, task_id)['requirements'] == fourth['requirements']
    with SessionLocal() as session:
        original = session.get(PublishedTaskContent, uuid.UUID(live['versionId']))
        assert original.content['requirements'] == [] and original.content['completionMode'] == 'assessment'
