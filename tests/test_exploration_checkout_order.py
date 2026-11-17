"""The imported training sign-out remains the final real course before graduation."""
import copy
import uuid

import pytest
from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.exploration_models import ExplorationCatalogTask, ExplorationWork
from journey_api.exploration_service import TRAINING_CHECKOUT_TASK_KEY, effective_catalog_positions, normalize_catalog_order
from journey_api.models import Assignment, TaskDefinition, TaskVersion
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask
from test_dynamic_exploration import command, exploration, finish_for_unlock, post, publish, read
from test_exploration_sequence import listing, republish, statuses
from test_wp09_feishu_identity import assert_ok


def publish_checkout(exploration):
    """Give a synthetic course the same durable identity as the imported sign-out."""
    task_id, live, content = publish(exploration, 'checkin', title='培训签退')
    with SessionLocal.begin() as session:
        session.get(TaskDefinition, uuid.UUID(task_id)).stable_key = TRAINING_CHECKOUT_TASK_KEY
    live, content = republish(exploration, task_id, live, content)
    assert live['pinnedLast'] is True
    return task_id, live, content


def stored_order(task_id):
    with SessionLocal() as session:
        organization_id = session.get(TaskDefinition, uuid.UUID(task_id)).organization_id
        return [(str(row.task_id), row.position) for row in session.scalars(select(ExplorationCatalogTask)
            .join(ReviewAdminTask, ReviewAdminTask.task_definition_id == ExplorationCatalogTask.task_id)
            .where(ExplorationCatalogTask.organization_id == organization_id, ReviewAdminTask.status == 'published')
            .order_by(ExplorationCatalogTask.position))]


def assert_order(learner, expected):
    tasks = listing(learner)
    assert [(task['id'], task['order']) for task in tasks] == list(zip(expected, range(1, len(expected) + 1)))
    assert stored_order(expected[0]) == list(zip(expected, range(1, len(expected) + 1)))
    return tasks


def test_legacy_catalog_reads_correct_order_without_writes_and_gates_new_course_before_checkout(exploration):
    staff, learner, _ = exploration
    first, _, _ = publish(exploration)
    checkout, _, _ = publish_checkout(exploration)
    later, _, _ = publish(exploration)
    legacy_order = [first, checkout, later]
    with SessionLocal.begin() as session:
        for position, task_id in enumerate(legacy_order, 1):
            session.get(ExplorationCatalogTask, uuid.UUID(task_id)).position = position
    tasks = listing(learner)
    assert [(task['id'], task['order'], task['pinnedLast']) for task in tasks] == [
        (first, 1, False), (later, 2, False), (checkout, 3, True)]
    admin_tasks = assert_ok(staff[0].get('/api/v1/review-admin/tasks'))['items']
    assert {task['id']: task['publishedOrder'] for task in admin_tasks} == {first: 1, later: 2, checkout: 3}
    assert next(task for task in admin_tasks if task['id'] == checkout)['pinnedLast'] is True
    assert stored_order(first) == list(zip(legacy_order, [1, 2, 3]))
    with SessionLocal() as session:
        organization_id = session.get(TaskDefinition, uuid.UUID(first)).organization_id
        assert list(effective_catalog_positions(session, organization_id)) == list(map(uuid.UUID, [first, later, checkout]))
        assert not session.dirty and not session.new and not session.deleted
    assert finish_for_unlock(learner, first)['order'] == 1
    assert statuses(learner) == {first: 'completed', later: 'active', checkout: 'locked'}
    locked = next(task for task in listing(learner) if task['id'] == checkout)
    denied = command(learner, locked, 'claim')
    assert denied.status_code == 409 and denied.json()['error']['code'] == 'JOURNEY_STAGE_LOCKED'
    assert finish_for_unlock(learner, later)['order'] == 2
    assert read(learner, checkout)['order'] == 3
    assert finish_for_unlock(learner, checkout)['status'] == 'completed'
    # Every command above also returns effective order, without repairing the DB.
    assert stored_order(first) == list(zip(legacy_order, [1, 2, 3]))


@pytest.mark.parametrize('requested_order', [9999, 2, 3])
def test_insert_at_end_or_checkout_slot_is_persisted_before_checkout(exploration, requested_order):
    _, learner, _ = exploration
    first, _, _ = publish(exploration)
    checkout, _, _ = publish_checkout(exploration)
    added, live, _ = publish(exploration, order=requested_order)
    assert live['publishedOrder'] == 2 and live['pinnedLast'] is False
    assert_order(learner, [first, added, checkout])


def test_checkout_identity_survives_rename_mode_edit_and_requested_reorder(exploration):
    _, learner, _ = exploration
    checkout, live, content = publish_checkout(exploration)
    ordinary, _, _ = publish(exploration, 'checkin', title='培训签退', order=9999)
    first, _, _ = publish(exploration, title='普通学习课程', order=1)
    live, _ = republish(exploration, checkout, live, content, title='重命名的培训结束课程',
        completionMode='learning', order=1)
    assert live['pinnedLast'] is True and live['publishedOrder'] == 3
    tasks = assert_order(learner, [first, ordinary, checkout])
    assert [task['pinnedLast'] for task in tasks] == [False, False, True]
    assert tasks[-1]['title'] == '重命名的培训结束课程'
    assert tasks[-1]['completionMode'] == 'learning'


@pytest.mark.parametrize('archive_checkout', [False, True])
def test_archive_restore_and_normal_reorder_preserve_checkout_boundary(exploration, archive_checkout):
    staff, learner, _ = exploration
    first, first_live, first_content = publish(exploration)
    checkout, checkout_live, _ = publish_checkout(exploration)
    second, _, _ = publish(exploration)
    first_live, _ = republish(exploration, first, first_live, first_content, order=9999)
    assert_order(learner, [second, first, checkout])
    archived_id, live = (checkout, checkout_live) if archive_checkout else (first, first_live)
    archived = assert_ok(post(staff, f'review-admin/tasks/{archived_id}/archive',
        dict(expected_revision=live['revision'], archived=True)))
    added, _, _ = publish(exploration, order=9999)
    assert_order(learner, [second, first, added] if archive_checkout else [second, added, checkout])
    restored = assert_ok(post(staff, f'review-admin/tasks/{archived_id}/archive',
        dict(expected_revision=archived['revision'], archived=False)))
    assert_order(learner, [second, first, added, checkout])
    assert restored['publishedOrder'] == (4 if archive_checkout else 2)


def test_normalization_only_changes_positions_and_keeps_previously_completed_checkout_history(exploration):
    _, learner, _ = exploration
    first, _, _ = publish(exploration)
    checkout, _, _ = publish_checkout(exploration)
    finish_for_unlock(learner, first)
    completed = finish_for_unlock(learner, checkout)
    added, _, _ = publish(exploration)
    task_ids = list(map(uuid.UUID, [first, checkout, added]))
    with SessionLocal.begin() as session:
        for position, task_id in enumerate(task_ids, 1):
            session.get(ExplorationCatalogTask, task_id).position = position
    with SessionLocal() as session:
        before_content = {row.task_definition_id: (row.revision, copy.deepcopy(row.content))
            for row in session.scalars(select(ReviewAdminTask).where(ReviewAdminTask.task_definition_id.in_(task_ids)))}
        before_versions = {row.task_version_id: copy.deepcopy(row.content) for row in session.scalars(select(PublishedTaskContent)
            .join(TaskVersion, TaskVersion.id == PublishedTaskContent.task_version_id)
            .where(TaskVersion.task_definition_id.in_(task_ids)))}
        work = session.scalar(select(ExplorationWork).where(ExplorationWork.task_id == uuid.UUID(checkout)))
        assignment = session.get(Assignment, work.assignment_id)
        history = (work.assignment_id, work.completed_at, work.checkin_confirmed, assignment.revision, assignment.status)
        organization_id = work.organization_id
    with SessionLocal.begin() as session:
        normalize_catalog_order(session, organization_id)
        assert {type(row) for row in session.dirty} <= {ExplorationCatalogTask}
    assert_order(learner, [first, added, checkout])
    after = read(learner, checkout)
    assert after['status'] == 'completed' and after['assignmentId'] == completed['assignmentId']
    assert after['versionId'] == completed['versionId'] and after['activityRecords'] == completed['activityRecords']
    assert statuses(learner)[added] == 'active'
    with SessionLocal() as session:
        assert {row.task_definition_id: (row.revision, row.content) for row in session.scalars(select(ReviewAdminTask)
            .where(ReviewAdminTask.task_definition_id.in_(task_ids)))} == before_content
        assert {row.task_version_id: row.content for row in session.scalars(select(PublishedTaskContent)
            .join(TaskVersion, TaskVersion.id == PublishedTaskContent.task_version_id)
            .where(TaskVersion.task_definition_id.in_(task_ids)))} == before_versions
        work = session.scalar(select(ExplorationWork).where(ExplorationWork.task_id == uuid.UUID(checkout)))
        assignment = session.get(Assignment, work.assignment_id)
        assert (work.assignment_id, work.completed_at, work.checkin_confirmed, assignment.revision, assignment.status) == history


def test_owned_archived_course_stays_before_checkout_without_blocking_unlock(exploration):
    staff, learner, _ = exploration
    first, _, _ = publish(exploration)
    checkout, _, _ = publish_checkout(exploration)
    old, live, _ = publish(exploration, 'assessment')
    finish_for_unlock(learner, first)
    claimed = assert_ok(command(learner, read(learner, old), 'claim'))
    archived = assert_ok(post(staff, f'review-admin/tasks/{old}/archive',
        dict(expected_revision=live['revision'], archived=True)))
    # Simulate a retained historic position beyond the current published end.
    with SessionLocal.begin() as session:
        session.get(ExplorationCatalogTask, uuid.UUID(old)).position = 99
    added, _, _ = publish(exploration)
    tasks = listing(learner)
    expected = [first, added, old, checkout]
    assert [(task['id'], task['order']) for task in tasks] == list(zip(expected, [1, 2, 3, 4]))
    assert stored_order(first) == [(first, 1), (added, 2), (checkout, 3)]
    assert statuses(learner) == {first: 'completed', added: 'active', old: 'active', checkout: 'locked'}
    saved = assert_ok(command(learner, read(learner, old), 'draft', answer='历史归档任务继续保留草稿。'))
    assert saved['order'] == 3 and saved['assignmentId'] == claimed['assignmentId']
    assert finish_for_unlock(learner, added)['order'] == 2
    assert read(learner, checkout)['order'] == 4 and read(learner, checkout)['status'] == 'active'
    restored = assert_ok(post(staff, f'review-admin/tasks/{old}/archive',
        dict(expected_revision=archived['revision'], archived=False)))
    assert restored['publishedOrder'] == 3
    assert_order(learner, expected)
    assert read(learner, old)['assignmentId'] == claimed['assignmentId']
