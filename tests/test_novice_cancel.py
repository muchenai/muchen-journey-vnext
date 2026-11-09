"""Cancelling a claim retains evidence and never withdraws a submitted review."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event, func, select

from journey_api.db import SessionLocal, engine
from journey_api.models import Assignment, AssignmentStatus, AuditEntry, Enrollment, EnrollmentStatus, Organization, Submission, SubmissionDraft
from journey_api.review_admin_models import NoviceUnlockDebit
from test_guild_certification import account
from test_novice_tasks import setup, claim, post, read
from test_reviewer_workbench import create_submission
from test_wp09_feishu_identity import assert_ok

TEXT = "我完成了材料学习与项目分析，整理了问题背景、验证依据和改进方案，并列出后续执行步骤与验收标准。"


def cancel(pair, task_id, revision, key=None):
    return pair[0].post(f'/api/v1/me/novice/tasks/{task_id}/cancel',
        headers={'X-CSRF-Token': pair[1], 'Idempotency-Key': key or str(uuid.uuid4())},
        json={'expected_revision': revision})


def reclaim(pair, task_id, task):
    return post(pair, f'me/novice/tasks/{task_id}/claim',
        {'version_id': task['versionId'], 'expected_revision': task['revision']})


def test_cancel_retains_draft_history_wallet_and_requires_explicit_fresh_reclaim(setup):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    before = assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
    aid = task['assignmentId']
    assert_ok(learner[0].put(f'/api/v1/me/assignments/{aid}/draft',
        headers={'X-CSRF-Token':learner[1], 'Idempotency-Key':str(uuid.uuid4())},
        json={'expected_revision':task['revision'], 'body':TEXT}))
    key = str(uuid.uuid4())
    cancelled = assert_ok(cancel(learner, task_id, task['revision'], key))
    assert cancelled['status'] == 'available' and cancelled['answer'] == TEXT and not cancelled['claimed']
    assert cancelled['assignmentId'] == aid and cancelled['revision'] == task['revision'] + 1
    assert read(learner, task_id)['answer'] == TEXT
    assert cancel(learner, task_id, cancelled['revision']).status_code == 409
    assert post(learner, f'me/novice/tasks/{task_id}/claim', {'version_id':task['versionId']}).status_code == 409
    assert reclaim(learner, task_id, task).status_code == 409
    reopened = assert_ok(reclaim(learner, task_id, cancelled))
    assert reopened['status'] == 'active' and reopened['answer'] == TEXT and reopened['claimed']
    assert reopened['assignmentId'] == aid and reopened['revision'] == cancelled['revision'] + 1
    # A delayed retry of the original cancellation must not cancel the new claim.
    assert_ok(cancel(learner, task_id, task['revision'], key))
    assert read(learner, task_id)['status'] == 'active'
    assert cancel(learner, task_id, reopened['revision'], key).status_code == 409
    assert assert_ok(learner[0].get('/api/v1/me/novice/wallet')) == before
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(aid))
        assert session.scalar(select(func.count(Assignment.id)).where(Assignment.enrollment_id == assignment.enrollment_id)) == 1
        assert session.scalar(select(func.count(SubmissionDraft.id)).where(SubmissionDraft.assignment_id == assignment.id)) == 1
        assert session.scalar(select(func.count(NoviceUnlockDebit.enrollment_id)).where(NoviceUnlockDebit.enrollment_id == assignment.enrollment_id)) == 0
        actions = session.scalars(select(AuditEntry.action).where(AuditEntry.resource_id == assignment.id)).all()
        assert actions.count('novice.cancel') == 1 and actions.count('novice.reclaim') == 1


@pytest.mark.parametrize('status', [AssignmentStatus.AVAILABLE, AssignmentStatus.SUBMITTED, AssignmentStatus.IN_REVIEW,
    AssignmentStatus.NEEDS_REVISION, AssignmentStatus.COMPLETED, AssignmentStatus.CANCELLED])
def test_only_in_progress_can_cancel_no_other_state_changes(setup, status):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    with SessionLocal.begin() as session:
        session.get(Assignment, uuid.UUID(task['assignmentId'])).status = status
    response = cancel(learner, task_id, task['revision'])
    assert response.status_code == 409
    with SessionLocal() as session:
        item = session.get(Assignment, uuid.UUID(task['assignmentId']))
        assert item.status == status and item.revision == task['revision']


def test_cancel_rejects_other_users_organizations_staff_and_unclaimed_tasks(setup):
    staff, learner, task_id, publication, _ = setup
    assert cancel(learner, task_id, 1).status_code == 404
    task = claim(learner, task_id, publication['versionId'])
    flow = create_submission('cancel-other-' + uuid.uuid4().hex)
    assert cancel((flow['learner'], flow['csrf']), task_id, task['revision']).status_code == 404
    org = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=org, name='取消接取隔离测试'))
    other = account(org)
    assert cancel((other['client'],other['csrf']), task_id, task['revision']).status_code == 404
    assert cancel(staff, task_id, task['revision']).status_code in (401,403)
    assert read(learner, task_id)['status'] == 'active'


def test_cancel_validates_revision_and_prevents_stale_draft_and_submit(setup):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    for revision in [0, -1, True, '1', 1.5]:
        assert cancel(learner, task_id, revision).status_code == 422
    assert cancel(learner, task_id, task['revision'] + 1).status_code == 409
    cancelled = assert_ok(cancel(learner, task_id, task['revision']))
    for revision in [task['revision'], cancelled['revision']]:
        assert learner[0].put(f'/api/v1/me/assignments/{task["assignmentId"]}/draft',
            headers={'X-CSRF-Token':learner[1], 'Idempotency-Key':str(uuid.uuid4())},
            json={'expected_revision':revision, 'body':TEXT}).status_code == 409
        assert post(learner, f'me/assignments/{task["assignmentId"]}/submissions',
            {'expected_revision':revision,'body':TEXT}).status_code == 409
    assert read(learner, task_id)['answer'] == ''


def test_archived_task_can_be_cancelled_but_not_reclaimed_and_admin_cancel_cannot_reopen(setup):
    staff, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    assert_ok(post(staff, f'review-admin/tasks/{task_id}/archive', {'expected_revision':publication['revision'], 'archived':True}))
    cancelled = assert_ok(cancel(learner, task_id, task['revision']))
    assert cancelled['status'] == 'unavailable' and not cancelled['claimed']
    assert reclaim(learner, task_id, cancelled).status_code == 404
    # An operator cancellation has no learner cancellation audit for this revision.
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        assignment.revision += 1
        session.get(Enrollment, assignment.enrollment_id).status = EnrollmentStatus.CANCELLED
    assert reclaim(learner, task_id, read(learner, task_id)).status_code == 409


def test_cancel_and_submit_are_serialized_without_lost_review(setup):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(cancel, learner, task_id, task['revision'])
        two = pool.submit(post, learner, f'me/assignments/{task["assignmentId"]}/submissions', {'expected_revision':task['revision'],'body':TEXT})
        results = [one.result(), two.result()]
    assert sorted(result.status_code for result in results) == [200,409]
    state = read(learner, task_id)
    with SessionLocal() as session:
        submission = session.scalar(select(Submission).where(Submission.assignment_id == uuid.UUID(task['assignmentId'])))
        assert (state['status'] == 'pending') == (submission is not None)
        assert state['status'] in ('pending','available')


def test_repeated_cancel_and_stale_reclaim_do_not_reactivate_new_cycle(setup):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: cancel(learner, task_id, task['revision'], key), range(2)))
    assert all(response.status_code == 200 for response in results)
    first = read(learner, task_id)
    reopened = assert_ok(reclaim(learner, task_id, first))
    second = assert_ok(cancel(learner, task_id, reopened['revision']))
    assert second['revision'] == first['revision'] + 2
    assert reclaim(learner, task_id, first).status_code == 409
    assert read(learner, task_id)['status'] == 'available'


def test_legacy_unlock_debit_is_preserved_without_refund_or_duplicate_charge(setup):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task['assignmentId']))
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        session.add(NoviceUnlockDebit(enrollment_id=enrollment.id, organization_id=enrollment.organization_id,
            user_id=enrollment.learner_id, amount=5))
    before = assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
    cancelled = assert_ok(cancel(learner, task_id, task['revision']))
    assert cancelled['unlockTaskPoints'] == 0
    assert_ok(reclaim(learner, task_id, cancelled))
    assert assert_ok(learner[0].get('/api/v1/me/novice/wallet')) == before
    with SessionLocal() as session:
        debit = session.get(NoviceUnlockDebit, enrollment.id)
        assert debit.amount == 5


def test_reclaim_requires_fixed_version_and_learner_cancellation_proof(setup):
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    with SessionLocal.begin() as session:
        session.get(Assignment, uuid.UUID(task['assignmentId'])).status = AssignmentStatus.CANCELLED
    assert read(learner, task_id)['status'] == 'unavailable'
    assert reclaim(learner, task_id, task).status_code == 409
    with SessionLocal.begin() as session:
        session.get(Assignment, uuid.UUID(task['assignmentId'])).status = AssignmentStatus.IN_PROGRESS
    cancelled = assert_ok(cancel(learner, task_id, task['revision']))
    assert reclaim(learner, task_id, {**cancelled, 'versionId':str(uuid.uuid4())}).status_code == 409
    assert read(learner, task_id)['status'] == 'available'


@pytest.mark.parametrize('operation', ['draft', 'submit'])
def test_cancel_user_lock_does_not_block_concurrent_submission_foreign_keys(setup, operation):
    """Hold the real cancellation account lock while the canonical writer commits.

    FOR UPDATE would block its User FK KEY SHARE after taking Enrollment, making
    this deterministic ordering deadlock once cancellation proceeds to Enrollment.
    """
    _, learner, task_id, publication, _ = setup
    task = claim(learner, task_id, publication['versionId'])
    user_locked, release_cancel = Event(), Event()

    def pause_after_account_lock(conn, cursor, statement, parameters, context, executemany):
        if 'SELECT users.id' in statement and 'FOR ' in statement and not user_locked.is_set():
            user_locked.set()
            assert release_cancel.wait(8), 'Timed out waiting to release the cancellation lock'

    def canonical_write():
        payload = {'expected_revision':task['revision'], 'body':TEXT}
        if operation == 'submit':
            return post(learner, f'me/assignments/{task["assignmentId"]}/submissions', payload)
        return learner[0].put(f'/api/v1/me/assignments/{task["assignmentId"]}/draft',
            headers={'X-CSRF-Token':learner[1], 'Idempotency-Key':str(uuid.uuid4())}, json=payload)

    event.listen(engine, 'after_cursor_execute', pause_after_account_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cancellation = pool.submit(cancel, learner, task_id, task['revision'])
            try:
                assert user_locked.wait(3), 'Cancellation never acquired the account lock'
                write = pool.submit(canonical_write).result(timeout=3)
                assert write.status_code == 200, write.text
            finally:
                release_cancel.set()
            response = cancellation.result(timeout=3)
            assert response.status_code == (409 if operation == 'submit' else 200)
    finally:
        release_cancel.set()
        event.remove(engine, 'after_cursor_execute', pause_after_account_lock)
    actual = read(learner, task_id)
    assert actual['status'] == ('pending' if operation == 'submit' else 'available')
    assert actual['answer'] == TEXT
