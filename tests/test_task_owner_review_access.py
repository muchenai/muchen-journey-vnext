"""Author-only novice queues, shared exploration and explicit super authority."""
import uuid
import pytest
from sqlalchemy import select
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.identity import utc_now
from journey_api.models import (Assignment, Enrollment, Review, Evaluation, ReviewDelegation,
    Attachment, AttachmentStatus, AttachmentScanStatus, SubmissionVersionAttachment, SubmissionVersion)
from journey_api.review_admin_models import ReviewAdminTask, ReviewAdminAccess
from test_reviewer_workbench import (create_submission, create_linked_reviewer,
    client_for_linked_reviewer, create_other_org_review)
from test_exploration_review_access import administrator
from test_shared_learner_reviews import approval
from test_wp09_feishu_identity import assert_ok


@pytest.fixture
def scenario(monkeypatch):
    author = create_linked_reviewer('任务发布者 A')
    other = create_linked_reviewer('指定审核员 B')
    super_id = create_linked_reviewer('超级管理员 C')
    pairs = {"author": administrator(author, ORGANIZATION_ID, 'admin'),
             "other": administrator(other, ORGANIZATION_ID, 'admin'),
             "super": administrator(super_id, ORGANIZATION_ID, 'super_admin')}
    flow = create_submission('owner-boundary-' + uuid.uuid4().hex, reviewer_id=other, publisher_id=author)
    rid = flow['review_id']
    with SessionLocal.begin() as s:
        assignment = s.get(Assignment, uuid.UUID(flow['assignment_id']))
        task_id = assignment.task_definition_id
        s.add(ReviewAdminTask(task_definition_id=task_id, organization_id=ORGANIZATION_ID,
            status='published', content={'camp':'novice'}))
        # Even the old explicit delegation must not bypass author ownership.
        s.add(ReviewDelegation(id=uuid.uuid4(), review_id=rid, organization_id=ORGANIZATION_ID,
            reviewer_id=other, delegated_by=other, reason='test old assignment'))
    monkeypatch.setenv('FEISHU_LEARNER_SHARED_REVIEWER_IDS', str(other))
    monkeypatch.setenv('FEISHU_LEARNER_REVIEWER_ID', str(other))
    monkeypatch.setenv('FEISHU_LEARNER_ORGANIZATION_ID', str(ORGANIZATION_ID))
    get_settings.cache_clear()
    yield flow, pairs, task_id, super_id
    get_settings.cache_clear()


def post(pair, path, body):
    c, csrf = pair
    return c.post('/api/v1/' + path, json=body,
        headers={'X-CSRF-Token':csrf, 'Idempotency-Key':str(uuid.uuid4())})


@pytest.mark.parametrize('camp', ['novice', 'exploration'])
@pytest.mark.parametrize('who', ['author', 'other', 'super'])
def test_visibility_detail_claim_decision_and_history(scenario, camp, who):
    flow, pairs, task_id, _ = scenario
    rid = flow['review_id']; pair = pairs[who]; c = pair[0]
    with SessionLocal.begin() as s:
        s.get(ReviewAdminTask, task_id).content = {'camp':camp}
    allowed = camp == 'exploration' or who != 'other'
    for path in ['review-admin/reviews', 'reviews']:
        ids = {r['id'] for r in assert_ok(c.get('/api/v1/' + path))['items']}
        assert (str(rid) in ids) == allowed
        assert c.get(f'/api/v1/{path}/{rid}').status_code == (200 if allowed else 404)
    if not allowed:
        detail = assert_ok(pairs['author'][0].get(f'/api/v1/reviews/{rid}'))
        for path, body in [
            (f'review-admin/reviews/{rid}/claim', {'action':'acquire','expected_revision':1}),
            (f'review-admin/reviews/{rid}/decision', {'decision':'APPROVE','expected_revision':1}),
            (f'reviews/{rid}/start', {'expected_revision':1}),
            (f'reviews/{rid}/finalize', approval(detail, 1))]:
            assert post(pair, path, body).status_code == 404
        with SessionLocal() as s:
            assert s.get(Review, rid).revision == 1
            assert s.scalar(select(Evaluation).where(Evaluation.review_id == rid)) is None
        pair = pairs['author']
    detail = assert_ok(pair[0].get(f'/api/v1/reviews/{rid}'))
    lease = assert_ok(post(pair, f'review-admin/reviews/{rid}/claim', {'action':'acquire','expected_revision':1}))
    rubric = approval(detail, 1)['rubric_evaluations']
    assert_ok(post(pair, f'review-admin/reviews/{rid}/decision', {
        'decision':'APPROVE', 'expected_revision':lease['revision'], 'claim_token':lease['token'],
        'rubric_evaluations':rubric}))
    for viewer, expected in [('author', True), ('super', True), ('other', camp == 'exploration')]:
        client = pairs[viewer][0]
        history = assert_ok(client.get('/api/v1/reviews/history?limit=50'))['items']
        assert (str(rid) in {r['id'] for r in history}) == expected
        assert client.get(f'/api/v1/review-admin/reviews/{rid}').status_code == (200 if expected else 404)


def test_super_revocation_demotion_and_other_org_are_rechecked(scenario):
    flow, pairs, _, super_id = scenario
    c = pairs['super'][0]; path = f"/api/v1/reviews/{flow['review_id']}"
    assert c.get(path).status_code == 200
    assert c.get(f'/api/v1/reviews/{create_other_org_review()}').status_code == 404
    with SessionLocal.begin() as s:
        s.get(ReviewAdminAccess, super_id).access_role = 'admin'
    assert c.get(path).status_code == 404
    with SessionLocal.begin() as s:
        s.get(ReviewAdminAccess, super_id).revoked_at = utc_now()
    assert c.get(path).status_code in {401,403}


def test_attachment_uses_same_author_boundary(scenario, monkeypatch):
    from journey_api import submission_routes
    flow, pairs, _, _ = scenario
    attachment_id = uuid.uuid4()
    version_id = uuid.UUID(flow['submission']['submission_version_id'])
    submission_id = uuid.UUID(flow['submission']['submission_id'])
    with SessionLocal.begin() as s:
        s.add(Attachment(id=attachment_id, organization_id=ORGANIZATION_ID,
            owner_id=s.get(SubmissionVersion, version_id).created_by,
            assignment_id=uuid.UUID(flow['assignment_id']), purpose='SUBMISSION_EVIDENCE',
            original_filename='evidence.txt', storage_key='test/'+str(attachment_id),
            content_type='text/plain', size_bytes=8, sha256='a'*64,
            status=AttachmentStatus.READY, scan_status=AttachmentScanStatus.CLEAN))
        s.flush()
        s.add(SubmissionVersionAttachment(submission_id=submission_id, submission_version_id=version_id,
            attachment_id=attachment_id, organization_id=ORGANIZATION_ID,
            assignment_id=uuid.UUID(flow['assignment_id']), position=1))
    class Storage:
        def presign_download(self, key): return None
        def get(self, key): return b'evidence'
    monkeypatch.setattr(submission_routes, 'require_attachments_enabled', lambda:None)
    monkeypatch.setattr(submission_routes, 'get_attachment_storage', lambda:Storage())
    for who in ['author','super','other']:
        r = pairs[who][0].get(f'/api/v1/attachments/{attachment_id}/download')
        assert r.status_code == (404 if who == 'other' else 200)


def test_database_gate_rejects_other_author_even_if_application_check_regresses(scenario, monkeypatch):
    from journey_api import review_routes
    from sqlalchemy.exc import DBAPIError
    flow, pairs, _, _ = scenario
    rid = flow['review_id']; pair = pairs['other']
    # Simulate a future application-layer regression: the database must still
    # refuse a formal PASS outcome signed by an unauthorized ordinary reviewer.
    monkeypatch.setattr(review_routes, 'review_visibility', lambda actor:True)
    detail = assert_ok(pair[0].get(f'/api/v1/reviews/{rid}'))
    started = assert_ok(post(pair, f'reviews/{rid}/start', {'expected_revision':1}))
    with pytest.raises(DBAPIError, match='formal result requires fixed practice evidence'):
        post(pair, f'reviews/{rid}/finalize', approval(detail, started['review_revision']))
    with SessionLocal() as s:
        assert s.scalar(select(Evaluation).where(Evaluation.review_id == rid)) is None
