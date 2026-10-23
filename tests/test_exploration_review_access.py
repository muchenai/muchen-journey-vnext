import uuid
import pytest
from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.identity import utc_now
from journey_api.models import Assignment, Enrollment, Evaluation, Review, Role, RoleAssignment, User
from journey_api.review_admin_models import ReviewAdminAccess, ReviewAdminTask
from test_shared_learner_reviews import shared_pool, learner_provider, oauth_provider, new_submission
from test_wp09_feishu_identity import assert_ok
from test_reviewer_workbench import client_for_linked_reviewer, create_submission, create_other_org_review


def assigned_submission(provider):
    review_id = new_submission(provider)
    with SessionLocal.begin() as s:
        review = s.get(Review, review_id)
        assignment = s.get(Assignment, review.assignment_id)
        enrollment = s.get(Enrollment, assignment.enrollment_id)
        enrollment.review_assignment_mode = 'ASSIGNED'
        return review_id, enrollment.learner_id, enrollment.organization_id


def administrator(user_id, org, role):
    with SessionLocal.begin() as s:
        if not s.scalar(select(RoleAssignment.id).where(RoleAssignment.user_id == user_id, RoleAssignment.role == Role.REVIEWER)):
            s.add(RoleAssignment(id=uuid.uuid4(), organization_id=org, user_id=user_id, role=Role.REVIEWER))
        s.add(ReviewAdminAccess(user_id=user_id, organization_id=org, access_role=role,
                              level='初级', domain='产品开发', granted_by=user_id))
    return client_for_linked_reviewer(user_id)


@pytest.mark.parametrize('role', ['admin', 'super_admin'])
@pytest.mark.parametrize('own_submission', [False, True])
def test_every_admin_can_read_and_approve_old_assigned_exploration(shared_pool, role, own_submission):
    provider, _, _, outside_pool = shared_pool
    review_id, learner_id, org = assigned_submission(provider)
    user_id = learner_id if own_submission else outside_pool
    client, csrf = administrator(user_id, org, role)
    item = next(item for item in assert_ok(client.get('/api/v1/review-admin/reviews'))['items'] if item['id'] == str(review_id))
    assert item['camp'] == 'exploration'
    assert item['actual_reviewer'] is None and item['reviewed_at'] is None
    assert_ok(client.get(f'/api/v1/review-admin/reviews/{review_id}'))
    lease = assert_ok(client.post(f'/api/v1/review-admin/reviews/{review_id}/claim', headers={'X-CSRF-Token': csrf},
        json={'action': 'acquire', 'expected_revision': item['revision']}))
    result = client.post(f'/api/v1/review-admin/reviews/{review_id}/decision',
        headers={'X-CSRF-Token': csrf, 'Idempotency-Key': str(uuid.uuid4())},
        json={'expected_revision': lease['revision'], 'claim_token': lease['token'], 'decision': 'APPROVE', 'feedback': '已核对本次探索营提交的任务要求和学习记录。', 'reasons': []})
    assert assert_ok(result)['assignment_status'] in {'PASSED', 'COMPLETED'}
    with SessionLocal() as s:
        evaluation = s.scalar(select(Evaluation).where(Evaluation.review_id == review_id))
        assert evaluation.executor_id == user_id
        expected_reviewer = {'id': str(user_id), 'name': s.get(User, user_id).display_name}
        expected_time = s.get(Review, review_id).finalized_at.isoformat()
        # Visibility changes do not rewrite the original enrollment ownership.
        assert s.get(Enrollment, s.get(Assignment, s.get(Review, review_id).assignment_id).enrollment_id).review_assignment_mode == 'ASSIGNED'
    assert str(review_id) in {r['id'] for r in assert_ok(client.get('/api/v1/reviews/history'))['items']}
    finalized = assert_ok(client.get(f'/api/v1/review-admin/reviews/{review_id}'))
    listed = next(r for r in assert_ok(client.get('/api/v1/review-admin/reviews'))['items'] if r['id'] == str(review_id))
    version = next(v for v in finalized['submission_history'] if v['review_id'] == str(review_id))
    for record in [finalized, listed, version]:
        assert record['actual_reviewer'] == expected_reviewer
        assert record['reviewed_at'] == expected_time


def test_revoked_admin_and_other_org_cannot_access_exploration(shared_pool):
    provider, _, _, outsider = shared_pool
    review_id, _, org = assigned_submission(provider)
    client, csrf = administrator(outsider, org, 'admin')
    assert client.get(f'/api/v1/review-admin/reviews/{review_id}').status_code == 200
    assert client.get(f'/api/v1/review-admin/reviews/{create_other_org_review()}').status_code == 404
    with SessionLocal.begin() as s:
        s.get(ReviewAdminAccess, outsider).revoked_at = utc_now()
    assert client.get('/api/v1/review-admin/reviews').status_code in {401, 403}
    assert client.post(f'/api/v1/review-admin/reviews/{review_id}/decision',
        headers={'X-CSRF-Token': csrf, 'Idempotency-Key': str(uuid.uuid4())},
        json={'expected_revision': 1, 'decision': 'APPROVE', 'reasons': []}).status_code in {401, 403}


def test_explicit_camp_controls_custom_tasks_without_opening_novice_work(shared_pool):
    _, _, _, outsider = shared_pool
    flow = create_submission('camp-boundary-' + uuid.uuid4().hex)
    client, _ = client_for_linked_reviewer(outsider)
    url = f"/api/v1/review-admin/reviews/{flow['review_id']}"
    with SessionLocal.begin() as s:
        a = s.get(Assignment, uuid.UUID(flow['assignment_id']))
        task_id, org = a.task_definition_id, a.organization_id
        assert s.get(ReviewAdminTask, task_id) is None
        s.add(ReviewAdminTask(task_definition_id=task_id, organization_id=org,
                              content={'camp': 'novice'}, status='published'))
    try:
        assert client.get(url).status_code == 404
        with SessionLocal.begin() as s:
            s.get(ReviewAdminTask, task_id).content = {'camp': 'exploration'}
        assert client.get(url).status_code == 200
        item = next(r for r in assert_ok(client.get('/api/v1/review-admin/reviews'))['items'] if r['id'] == str(flow['review_id']))
        assert item['camp'] == 'exploration'
    finally:
        with SessionLocal.begin() as s:
            s.delete(s.get(ReviewAdminTask, task_id))
