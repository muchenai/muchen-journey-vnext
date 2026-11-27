"""Database-backed races for exploration claims and published camp boundaries."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock

import pytest
from sqlalchemy import event, func, select, text

from journey_api.db import SessionLocal, engine
from journey_api.exploration_models import ExplorationWork
from journey_api.models import Assignment, Enrollment, Role, TaskDefinition
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask
from test_dynamic_exploration import command, exploration, post, publish, read
from test_course_workspace import identity
from test_wp09_feishu_identity import assert_ok


def save(staff, task_id, revision, content):
    return staff[0].put(
        f'/api/v1/review-admin/tasks/{task_id}',
        headers={'X-CSRF-Token': staff[1]},
        json={'id': task_id, 'expected_revision': revision, 'content': content},
    )


def wait_for_database_lock(pid):
    """Confirm PostgreSQL is waiting before releasing the winning transaction."""
    deadline = time.monotonic() + 10
    with engine.connect() as connection:
        while time.monotonic() < deadline:
            blocked = connection.scalar(text('SELECT cardinality(pg_blocking_pids(:pid)) > 0'), {'pid': pid})
            if blocked:
                return
            time.sleep(0.02)
    pytest.fail(f'Expected database session {pid} to wait for the controlled task lock')


def test_concurrent_initial_claims_create_one_owned_assignment(exploration):
    _, learner, _ = exploration
    task_id, _, _ = publish(exploration)
    task = read(learner, task_id)
    start = Barrier(2)

    def first_claim():
        start.wait(timeout=10)
        return assert_ok(command(learner, task, 'claim'))

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: first_claim(), range(2)))

    assert claims[0]['assignmentId'] == claims[1]['assignmentId']
    assert claims[0]['revision'] == claims[1]['revision']
    assert all(item['claimed'] and item['status'] == 'active' for item in claims)
    with SessionLocal() as session:
        task_uuid = uuid.UUID(task_id)
        assert session.scalar(select(func.count()).select_from(ExplorationWork).where(
            ExplorationWork.task_id == task_uuid)) == 1
        assert session.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.novice_task_id == task_uuid)) == 1
        assert session.scalar(select(func.count()).select_from(Assignment).where(
            Assignment.task_definition_id == task_uuid)) == 1


@pytest.mark.parametrize('operation', ['archive', 'delete'])
def test_waiting_first_claim_cannot_overtake_archive_or_delete(exploration, monkeypatch, operation):
    if engine.dialect.name != 'postgresql':
        pytest.skip('This regression requires PostgreSQL row-lock ordering')

    from journey_api import exploration_routes, exploration_service

    staff, learner, _ = exploration
    task_id, live, _ = publish(exploration)
    task_uuid = uuid.UUID(task_id)
    task = read(learner, task_id)
    archive_reached_task = Event()
    claim_reached_context = Event()
    captured = {}
    capture_lock = Lock()
    original_context = exploration_service.context

    def capture_admin_lock(connection, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        if 'task_definitions' in sql and 'for update' in sql:
            with capture_lock:
                if 'admin_pid' not in captured:
                    captured['admin_pid'] = connection.connection.driver_connection.info.backend_pid
                    archive_reached_task.set()

    def capture_claim_context(session, actor, requested_task_id, **options):
        if requested_task_id == task_uuid:
            with capture_lock:
                if 'claim_pid' not in captured:
                    captured['claim_pid'] = session.connection().connection.driver_connection.info.backend_pid
                    claim_reached_context.set()
        return original_context(session, actor, requested_task_id, **options)

    monkeypatch.setattr(exploration_routes, 'context', capture_claim_context)
    monkeypatch.setattr(exploration_service, 'context', capture_claim_context)

    body = {'expected_revision': live['revision']}
    if operation == 'archive':
        body['archived'] = True

    with SessionLocal() as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.scalar(select(TaskDefinition.id).where(TaskDefinition.id == task_uuid).with_for_update())
        event.listen(engine, 'before_cursor_execute', capture_admin_lock)
        try:
            administrative = pool.submit(post, staff, f'review-admin/tasks/{task_id}/{operation}', body)
            assert archive_reached_task.wait(timeout=10), 'Administrative operation did not reach the task lock'
            wait_for_database_lock(captured['admin_pid'])
            claiming = pool.submit(command, learner, task, 'claim')
            assert claim_reached_context.wait(timeout=10), 'Claim did not reach the published task context'
            wait_for_database_lock(captured['claim_pid'])
        finally:
            blocker.rollback()
            event.remove(engine, 'before_cursor_execute', capture_admin_lock)

        assert_ok(administrative.result(timeout=20))
        denied = claiming.result(timeout=20)
        assert denied.status_code in {404, 409}, denied.text

    with SessionLocal() as session:
        profile = session.get(ReviewAdminTask, task_uuid)
        assert profile.status == ('archived' if operation == 'archive' else 'deleted')
        assert session.scalar(select(func.count()).select_from(ExplorationWork).where(
            ExplorationWork.task_id == task_uuid)) == 0
        assert session.scalar(select(func.count()).select_from(Enrollment).where(
            Enrollment.novice_task_id == task_uuid)) == 0

    listing = assert_ok(learner[0].get('/api/v1/me/exploration'))
    assert task_id not in {item['id'] for item in listing['items']}


@pytest.mark.parametrize('original_camp', ['exploration', 'novice'])
@pytest.mark.parametrize('exploration', ['FEISHU'], indirect=True)
def test_published_camp_stays_fixed_after_saving_an_editable_draft(exploration, original_camp):
    _, learner, _ = exploration
    configuration = {}
    if original_camp == 'novice':
        configuration = dict(camp='novice', domain='产品开发', difficulty='入门',
            publishingDepartment='开发部', badges=[{'id': 'product', 'weight': 100}])
    task_id, live, content = publish(exploration, **configuration)
    changed_camp = 'novice' if original_camp == 'exploration' else 'exploration'
    with SessionLocal() as session:
        org = session.get(TaskDefinition, uuid.UUID(task_id)).organization_id
    manager, _ = identity(org, Role.REVIEWER, '跨发布人管理任务的超级管理员', 'super_admin')
    staff = (manager, manager.headers['X-CSRF-Token'])

    edited = {**content, 'title': '已保存但尚未发布的课程修改'}
    draft = assert_ok(save(staff, task_id, live['revision'], edited))
    assert draft['status'] == 'published'

    attempted = {**edited, 'camp': changed_camp, 'status': 'draft', 'version': 0}
    if changed_camp == 'novice':
        attempted.update(domain='产品开发', difficulty='入门', publishingDepartment='开发部',
            badges=[{'id': 'product', 'weight': 100}])
    denied = save(staff, task_id, draft['revision'], attempted)
    assert denied.status_code == 409, denied.text
    assert denied.json()['error']['code'] == 'CAMP_FIXED'

    with SessionLocal() as session:
        profile = session.get(ReviewAdminTask, uuid.UUID(task_id))
        published = session.get(PublishedTaskContent, uuid.UUID(live['versionId']))
        assert profile.content['camp'] == published.content['camp'] == original_camp
        assert profile.content['title'] == edited['title']
        assert profile.revision == draft['revision']

    if original_camp == 'exploration':
        assert read(learner, task_id)['title'] == content['title']
    else:
        corporate, _ = identity(org, Role.LEARNER, '新手村学员')
        current = assert_ok(corporate.get(f'/api/v1/me/novice/tasks/{task_id}'))
        assert current['title'] == content['title']


@pytest.mark.parametrize('original_camp', ['exploration', 'novice'])
def test_legacy_saved_camp_change_cannot_bypass_the_publication_boundary(exploration, original_camp):
    staff, _, author = exploration
    configuration = {}
    if original_camp == 'novice':
        configuration = dict(camp='novice', domain='产品开发', difficulty='入门',
            publishingDepartment='开发部', badges=[{'id': 'product', 'weight': 100}])
    task_id, live, content = publish(exploration, **configuration)
    changed = {**content, 'camp': 'novice' if original_camp == 'exploration' else 'exploration'}
    if changed['camp'] == 'novice':
        changed.update(domain='产品开发', difficulty='入门', publishingDepartment='开发部',
            badges=[{'id': 'product', 'weight': 100}])
    else:
        changed.update(domain='', difficulty='', publishingDepartment='', badges=[])

    # A draft saved by the previous implementation must still respect the
    # immutable published camp when the current publication endpoint is called.
    with SessionLocal.begin() as session:
        profile = session.get(ReviewAdminTask, uuid.UUID(task_id))
        original_revision = profile.revision
        profile.content = changed
        profile.revision += 1
        saved_revision = profile.revision
    try:
        denied = post(staff, f'review-admin/tasks/{task_id}/publish', {
            'expected_revision': saved_revision,
            'reviewed_by': str(author),
            'verified_material_urls': [item['url'] for item in content['materials'] if item['type'] == 'link'],
        })
        assert denied.status_code == 409, denied.text
        assert denied.json()['error']['code'] == 'CAMP_FIXED'
        with SessionLocal() as session:
            published = session.get(PublishedTaskContent, uuid.UUID(live['versionId']))
            assert published.content['camp'] == original_camp
    finally:
        with SessionLocal.begin() as session:
            profile = session.get(ReviewAdminTask, uuid.UUID(task_id))
            profile.content = content
            profile.revision = original_revision
