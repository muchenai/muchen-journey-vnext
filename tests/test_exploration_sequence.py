"""Sequential exploration gates use durable server-side learning milestones."""
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import func, select
from journey_api.db import SessionLocal
from journey_api.exploration_models import ExplorationProgress, ExplorationWork
from journey_api.models import Assignment, Enrollment, IdempotencyRecord, Review, SubmissionDraft
from test_dynamic_exploration import command, exploration, finish_for_unlock, post, publish, read
from test_wp09_feishu_identity import assert_ok


def listing(learner):
    return assert_ok(learner[0].get('/api/v1/me/exploration'))['items']


def statuses(learner):
    return {task['id']: task['status'] for task in listing(learner)}


def republish(exploration, task_id, live, content, **changes):
    staff, _, author = exploration
    content = {**content, **changes}
    if content['completionMode'] == 'assessment' and not content.get('taskFiles') and not content.get('assessmentUrl'):
        content['assessmentUrl'] = 'https://example.com/test'
    draft = assert_ok(staff[0].put('/api/v1/review-admin/tasks/' + task_id,
        headers={'X-CSRF-Token': staff[1]},
        json={'id': task_id, 'expected_revision': live['revision'], 'content': content}))
    links = [material['url'] for material in content['materials'] if material['type'] == 'link']
    if content['completionMode'] == 'assessment':
        links.extend(material['url'] for material in content.get('taskFiles', []) if material['type'] == 'link')
        if content.get('assessmentUrl'):
            links.append(content['assessmentUrl'])
    live = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish', dict(
        expected_revision=draft['revision'], reviewed_by=str(author),
        verified_material_urls=list(dict.fromkeys(links)))))
    return live, content


def test_locked_projection_and_all_direct_entry_points_are_protected(exploration):
    staff, learner, _ = exploration
    first, _, _ = publish(exploration)
    file = assert_ok(staff[0].post('/api/v1/review-admin/exploration/materials?name=private.txt',
        headers={'X-CSRF-Token': staff[1], 'Content-Type': 'text/plain'}, content=b'private course material'))
    second, _, _ = publish(exploration, 'assessment', materials=[file], assessmentUrl='https://example.com/private-test')
    tasks = listing(learner)
    assert [(task['id'], task['status']) for task in tasks] == [(first, 'active'), (second, 'locked')]
    assert tasks[0]['claimed'] is False and tasks[0]['assignmentId'] is None
    locked = tasks[1]
    for field in ('materials', 'requirements', 'criteria', 'rubric', 'activityRecords', 'feedbackRecords'):
        assert locked[field] == []
    assert locked['assessmentUrl'] is None and locked['materialCount'] == 1
    assert 'private course material' not in str(locked) and file['url'] not in str(locked)
    for action in ('learnerTask', 'selfCheckHistory', 'material'):
        denied = learner[0].get('/api/v1/me/exploration', params={'command': action, 'taskId': second, 'index': 0})
        assert denied.status_code == 409 and denied.json()['error']['code'] == 'JOURNEY_STAGE_LOCKED'
    for action in ('claim', 'readMaterial', 'completeLearning', 'draft', 'submit', 'selfCheck'):
        denied = command(learner, locked, action, answer='尝试直接提交锁定课程。', index=0, checkinConfirmed=True)
        assert denied.status_code == 409 and denied.json()['error']['code'] == 'JOURNEY_STAGE_LOCKED'
    cancelled = command(learner, locked, 'cancel')
    assert cancelled.status_code == 409
    assert cancelled.json()['error']['code'] == 'EXPLORATION_CANCEL_NOT_ALLOWED'
    path = '/api/v1/me/exploration/materials/' + file['id']
    assert learner[0].get(path).status_code == learner[0].head(path).status_code == 404
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(ExplorationWork).where(
            ExplorationWork.task_id == uuid.UUID(second))) == 0


def test_learning_completion_and_test_submission_unlock_next_without_waiting_for_review(exploration):
    staff, learner, _ = exploration
    first, _, _ = publish(exploration)
    second, _, _ = publish(exploration, 'assessment')
    third, _, _ = publish(exploration, 'checkin')
    task = assert_ok(command(learner, read(learner, first), 'readMaterial', index=0))
    assert statuses(learner)[second] == 'locked'
    cancelled = command(learner, task, 'cancel')
    assert cancelled.status_code == 409
    assert cancelled.json()['error']['message'] == '探索营任务接取后不能取消。'
    assert read(learner, first)['claimed'] is True
    assert statuses(learner)[second] == 'locked'
    assert_ok(command(learner, task, 'completeLearning'))
    assert statuses(learner) == {first: 'completed', second: 'active', third: 'locked'}
    task = assert_ok(command(learner, read(learner, second), 'claim'))
    task = assert_ok(command(learner, task, 'draft', answer='保存的测试草稿。'))
    assert statuses(learner)[third] == 'locked'
    task = assert_ok(command(learner, task, 'submit', answer='测试已完成，结果已经提交。'))
    assert statuses(learner) == {first: 'completed', second: 'pending', third: 'active'}
    with SessionLocal() as session:
        review_id = session.scalar(select(Review.id).where(Review.assignment_id == uuid.UUID(task['assignmentId'])))
    detail = assert_ok(staff[0].get('/api/v1/review-admin/reviews/' + str(review_id)))
    lease = assert_ok(post(staff, f'review-admin/reviews/{review_id}/claim', dict(
        action='acquire', expected_revision=detail['revision'])))
    assert_ok(post(staff, f'review-admin/reviews/{review_id}/decision', dict(
        expected_revision=lease['revision'], claim_token=lease['token'], decision='REQUEST_REVISION',
        feedback='请补充测试结果的详细说明。', reasons=['依据或论证不足'])))
    task = read(learner, second)
    assert task['status'] == 'returned' and statuses(learner)[third] == 'active'
    assert_ok(command(learner, task, 'draft', answer='修改中的新草稿，保留已经提交的版本。'))
    assert statuses(learner)[third] == 'active'
    assert finish_for_unlock(learner, third)['status'] == 'completed'


def cancellation_state(task):
    """Observe retained evidence and progress independently of the response."""
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        work = session.scalar(select(ExplorationWork).where(
            ExplorationWork.assignment_id == assignment.id))
        draft = session.scalar(select(SubmissionDraft).where(
            SubmissionDraft.assignment_id == assignment.id))
        progress = session.get(ExplorationProgress, (enrollment.organization_id, enrollment.learner_id))
        return copy.deepcopy(dict(assignment=(assignment.status, assignment.revision),
            enrollment=(enrollment.status, enrollment.revision),
            work=(work.assignment_id, work.opened_materials, work.checkin_confirmed, work.completed_at),
            draft=(draft.body, draft.revision, draft.updated_at) if draft else None,
            progress=(progress.treasures, progress.unlocked_at) if progress else None))


@pytest.mark.parametrize('mode', ['learning', 'assessment', 'checkin'])
def test_cancel_cannot_change_claim_materials_draft_or_sequence(exploration, mode):
    _, learner, _ = exploration
    first, _, _ = publish(exploration, mode)
    second, _, _ = publish(exploration)
    task = assert_ok(command(learner, read(learner, first), 'claim'))
    if mode == 'assessment':
        task = assert_ok(command(learner, task, 'draft', answer='取消请求不得丢失这份已保存的测试草稿。'))
    elif mode == 'learning':
        task = assert_ok(command(learner, task, 'readMaterial', index=0))
    before = cancellation_state(task)
    for revision in (task['revision'], task['revision'] - 1):
        rejected = command(learner, {**task, 'revision': revision}, 'cancel')
        assert rejected.status_code == 409
        assert rejected.json()['error']['code'] == 'EXPLORATION_CANCEL_NOT_ALLOWED'
        assert rejected.json()['error']['message'] == '探索营任务接取后不能取消。'
        assert cancellation_state(task) == before
    current = read(learner, first)
    assert current['claimed'] is True and current['assignmentId'] == task['assignmentId']
    assert current['revision'] == task['revision'] and statuses(learner)[second] == 'locked'
    if mode == 'assessment':
        assert current['answer'] == '取消请求不得丢失这份已保存的测试草稿。'


def test_cancel_rejects_historical_successful_idempotency_replay(exploration):
    from journey_api.exploration_routes import ExplorationCommand
    from journey_api.idempotency import store_result

    _, learner, _ = exploration
    task_id, _, _ = publish(exploration, 'assessment')
    task = assert_ok(command(learner, read(learner, task_id), 'claim'))
    task = assert_ok(command(learner, task, 'draft', answer='旧取消结果重放时也必须保留本次已领取的任务和草稿。'))
    key = str(uuid.uuid4())
    body = dict(command='cancel', taskId=task_id, versionId=task['versionId'], revision=task['revision'])
    payload = ExplorationCommand.model_validate(body).model_dump(mode='json', exclude={'key', 'idempotencyKey'})
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        store_result(session, actor_id=enrollment.learner_id, command='exploration.cancel',
            key=key, payload=payload, response={**task, 'claimed': False, 'status': 'active'})
    before = cancellation_state(task)
    for value in (body, {**body, 'revision': task['revision'] + 1}):
        rejected = post(learner, 'me/exploration', value, key=key)
        assert rejected.status_code == 409
        assert rejected.json()['error']['code'] == 'EXPLORATION_CANCEL_NOT_ALLOWED'
        assert cancellation_state(task) == before
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord).where(
            IdempotencyRecord.command == 'exploration.cancel', IdempotencyRecord.key == key)) == 1


@pytest.mark.parametrize('historical_replay', [False, True])
def test_novice_cancel_endpoint_cannot_cancel_exploration_claim(exploration, historical_replay):
    from journey_api.idempotency import store_result

    _, learner, _ = exploration
    task_id, _, _ = publish(exploration, 'assessment')
    task = assert_ok(command(learner, read(learner, task_id), 'claim'))
    task = assert_ok(command(learner, task, 'draft', answer='新手村取消接口不能取消探索营任务，也不能覆盖这份草稿。'))
    key = str(uuid.uuid4())
    body = dict(expected_revision=task['revision'])
    if historical_replay:
        with SessionLocal.begin() as session:
            assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
            enrollment = session.get(Enrollment, assignment.enrollment_id)
            store_result(session, actor_id=enrollment.learner_id, command='novice.cancel', key=key,
                payload={**body, 'task_id': task_id}, response={**task, 'claimed': False, 'status': 'available'})
    before = cancellation_state(task)
    rejected = post(learner, f'me/novice/tasks/{task_id}/cancel', body, key=key)
    assert rejected.status_code == 409
    assert rejected.json()['error']['code'] == 'EXPLORATION_CANCEL_NOT_ALLOWED'
    assert rejected.json()['error']['message'] == '探索营任务接取后不能取消。'
    assert cancellation_state(task) == before


@pytest.mark.parametrize('mode', ['learning', 'checkin'])
def test_generic_assignment_submission_cannot_bypass_non_test_completion(exploration, mode):
    _, learner, _ = exploration
    first, _, _ = publish(exploration, mode)
    second, _, _ = publish(exploration)
    task = assert_ok(command(learner, read(learner, first), 'claim'))
    headers = {'X-CSRF-Token': learner[1], 'Idempotency-Key': str(uuid.uuid4())}
    answer = '课程需要真实学习或完成签退，通用文字提交接口不能代替本课程规定的完成流程。' * 2
    draft = learner[0].put(f"/api/v1/me/assignments/{task['assignmentId']}/draft", headers=headers,
        json={'expected_revision': task['revision'], 'body': answer})
    submitted = post(learner, f"me/assignments/{task['assignmentId']}/submissions",
        {'expected_revision': task['revision'], 'body': answer})
    assert draft.status_code == submitted.status_code == 409
    assert statuses(learner)[second] == 'locked'


@pytest.mark.parametrize('mode', ['learning', 'assessment'])
def test_unlock_milestone_uses_the_learners_fixed_version_after_republication(exploration, mode):
    _, learner, _ = exploration
    first, live, content = publish(exploration, mode)
    finished = finish_for_unlock(learner, first)
    second, _, _ = publish(exploration)
    assert statuses(learner)[second] == 'active'
    republish(exploration, first, live, content, completionMode='assessment' if mode == 'learning' else 'learning')
    original = read(learner, first)
    assert original['versionId'] == finished['versionId'] and original['completionMode'] == mode
    assert original['status'] == ('completed' if mode == 'learning' else 'pending')
    assert statuses(learner)[second] == 'active'


@pytest.mark.parametrize('operation', ['archive', 'delete'])
def test_archived_or_deleted_predecessor_is_skipped_and_restore_keeps_owned_work(exploration, operation):
    staff, learner, _ = exploration
    first, live, _ = publish(exploration)
    second, _, _ = publish(exploration, 'assessment')
    third, _, _ = publish(exploration)
    body = dict(expected_revision=live['revision'])
    if operation == 'archive':
        body['archived'] = True
    result = assert_ok(post(staff, f'review-admin/tasks/{first}/{operation}', body))
    assert statuses(learner) == {second: 'active', third: 'locked'}
    owned = assert_ok(command(learner, read(learner, second), 'claim'))
    if operation == 'archive':
        assert_ok(post(staff, f'review-admin/tasks/{first}/archive', dict(expected_revision=result['revision'], archived=False)))
        assert statuses(learner)[first] == 'active'
    else:
        publish(exploration, order=1)
    assert read(learner, second)['assignmentId'] == owned['assignmentId']
    assert_ok(command(learner, owned, 'draft', answer='已领取任务的历史草稿继续保存。'))
    assert statuses(learner)[third] == 'locked'


def test_reordering_relocks_unclaimed_tasks_and_preserves_previously_owned_work(exploration):
    _, learner, _ = exploration
    old, _, _ = publish(exploration, 'assessment')
    owned = assert_ok(command(learner, read(learner, old), 'claim'))
    first, _, _ = publish(exploration, order=1)
    second, second_live, second_content = publish(exploration, order=2)
    assert statuses(learner) == {first: 'active', second: 'locked', old: 'active'}
    assert_ok(command(learner, owned, 'submit', answer='已有任务的提交历史继续有效。'))
    assert statuses(learner)[second] == 'locked'
    formerly_active = read(learner, first)
    republish(exploration, second, second_live, second_content, order=1)
    assert statuses(learner) == {second: 'active', first: 'locked', old: 'pending'}
    denied = command(learner, formerly_active, 'claim')
    assert denied.status_code == 409 and denied.json()['error']['code'] == 'JOURNEY_STAGE_LOCKED'
    finish_for_unlock(learner, second)
    assert statuses(learner)[first] == 'active'


def test_shared_material_is_readable_when_an_unlocked_course_references_it(exploration):
    staff, learner, _ = exploration
    file = assert_ok(staff[0].post('/api/v1/review-admin/exploration/materials?name=shared.txt',
        headers={'X-CSRF-Token': staff[1], 'Content-Type': 'text/plain'}, content=b'shared material'))
    publish(exploration, materials=[file])
    second, _, _ = publish(exploration, materials=[file])
    assert statuses(learner)[second] == 'locked'
    assert learner[0].get('/api/v1/me/exploration/materials/' + file['id']).content == b'shared material'


def test_concurrent_completion_and_next_claim_preserve_one_assignment(exploration):
    _, learner, _ = exploration
    first, _, _ = publish(exploration)
    second, _, _ = publish(exploration)
    first_task = assert_ok(command(learner, read(learner, first), 'readMaterial', index=0))
    locked = next(task for task in listing(learner) if task['id'] == second)
    start = Barrier(2)

    def complete():
        start.wait(timeout=10)
        return command(learner, first_task, 'completeLearning')

    def next_claim():
        start.wait(timeout=10)
        return command(learner, locked, 'claim')

    with ThreadPoolExecutor(max_workers=2) as pool:
        completed, claimed = pool.submit(complete), pool.submit(next_claim)
        assert_ok(completed.result(timeout=20))
        response = claimed.result(timeout=20)
        assert response.status_code in {200, 409}
    task = read(learner, second)
    assert task['status'] == 'active'
    if not task['claimed']:
        assert_ok(command(learner, task, 'claim'))
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(ExplorationWork).where(
            ExplorationWork.task_id == uuid.UUID(second))) == 1


def test_original_journey_submitted_milestone_survives_return_and_new_draft(exploration):
    from journey_api.errors import ApiError
    from journey_api.journey_service import completed_evidence_revision_ids, ensure_formal_assignment_is_current, submitted_assignment_ids
    from journey_api.models import (AssignmentStatus, Enrollment, EnrollmentStatus, JourneyCompletionPolicy,
        JourneyDefinition, JourneyDefinitionStatus, JourneyStageKind, JourneyStageVersion, JourneyVersion,
        Role, RoleAssignment, Submission, SubmissionDraft, SubmissionVersion, TaskDefinition, User)
    _, _, author = exploration
    courses = [publish(exploration, 'assessment') for _ in range(3)]
    with SessionLocal.begin() as session:
        organization = session.get(TaskDefinition, uuid.UUID(courses[0][0])).organization_id
        learner_id = session.scalar(select(User.id).join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(User.organization_id == organization, RoleAssignment.role == Role.LEARNER))
        definition = JourneyDefinition(id=uuid.uuid4(), organization_id=organization, stable_key='ORIGINAL-SEQUENCE-TEST',
            status=JourneyDefinitionStatus.PUBLISHED, revision=1, created_by=author)
        session.add(definition)
        session.flush()
        version = JourneyVersion(id=uuid.uuid4(), organization_id=organization, journey_definition_id=definition.id,
            version=1, title='旧旅程顺序规则对照', purpose='验证持久提交解锁事实。', change_summary='独立测试组织中的旧规则对照。',
            content_review_note='合成回归测试数据。', published_by=author, reviewed_by=author)
        session.add(version)
        session.flush()
        enrollment = Enrollment(id=uuid.uuid4(), organization_id=organization, learner_id=learner_id, reviewer_id=author,
            journey_version_id=version.id, status=EnrollmentStatus.ACTIVE, revision=1)
        session.add(enrollment)
        session.flush()
        assignments = []
        for index, (task_id, live, _content) in enumerate(courses):
            stage = JourneyStageVersion(id=uuid.uuid4(), organization_id=organization, journey_version_id=version.id,
                stable_key=f'ORIGINAL-{index}', position=index, stage_kind=JourneyStageKind.ASSESSMENT,
                completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED, task_version_id=uuid.UUID(live['versionId']),
                title='旧规则对照课程', short_description='旧规则对照')
            session.add(stage)
            session.flush()
            assignment = Assignment(id=uuid.uuid4(), organization_id=organization, enrollment_id=enrollment.id,
                task_definition_id=uuid.UUID(task_id), task_version_id=stage.task_version_id, journey_stage_version_id=stage.id,
                position=index + 1, status=AssignmentStatus.IN_PROGRESS if index == 0 else AssignmentStatus.AVAILABLE, revision=1)
            session.add(assignment)
            assignments.append(assignment)
        session.flush()
        with pytest.raises(ApiError, match='后续节点尚未开放'):
            ensure_formal_assignment_is_current(session, enrollment, assignments[1])
        submission = Submission(id=uuid.uuid4(), organization_id=organization, assignment_id=assignments[0].id, current_version_no=0)
        session.add(submission)
        session.flush()
        session.add(SubmissionVersion(id=uuid.uuid4(), submission_id=submission.id, version_no=1, body='已提交的真实固定版本。', created_by=learner_id))
        session.flush()
        submission.current_version_no = 1
        assignments[0].status = AssignmentStatus.SUBMITTED
        assert submitted_assignment_ids(session, enrollment) == {assignments[0].id}
        ensure_formal_assignment_is_current(session, enrollment, assignments[1])
        assignments[0].status = AssignmentStatus.NEEDS_REVISION
        ensure_formal_assignment_is_current(session, enrollment, assignments[1])
        assignments[0].status = AssignmentStatus.IN_PROGRESS
        session.add(SubmissionDraft(id=uuid.uuid4(), organization_id=organization, assignment_id=assignments[0].id,
            owner_id=learner_id, body='退回后的新草稿。', attachment_ids=[], revision=1))
        assert completed_evidence_revision_ids(session, enrollment) == {assignments[0].id}
        ensure_formal_assignment_is_current(session, enrollment, assignments[1])
        with pytest.raises(ApiError, match='后续节点尚未开放'):
            ensure_formal_assignment_is_current(session, enrollment, assignments[2])
