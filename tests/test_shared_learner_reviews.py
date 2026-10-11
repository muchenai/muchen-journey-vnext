import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID
from journey_api.identity import credential_hash
from journey_api.models import Evaluation, ExternalIdentity, Review
from test_learner_feishu_login import learner_provider, login
from test_wp09_feishu_identity import oauth_provider, assert_ok, begin_oauth, callback, client_for
from test_reviewer_workbench import create_linked_reviewer, client_for_linked_reviewer, create_submission, create_other_org_review


@pytest.fixture
def shared_pool(learner_provider, monkeypatch):
    peer = create_linked_reviewer('Shared review peer')
    excluded = create_linked_reviewer('Excluded review staff')
    outsider = create_linked_reviewer('Staff outside shared pool')
    monkeypatch.setenv('FEISHU_LEARNER_SHARED_REVIEWER_IDS', f'{REVIEWER_ID},{peer}')
    monkeypatch.setenv('REVIEWER_EXCLUDED_USER_IDS', str(excluded))
    get_settings.cache_clear()
    yield learner_provider, peer, excluded, outsider
    get_settings.cache_clear()


def new_submission(provider):
    learner, response = login(provider, 'shared-learner', 'ou_shared_' + uuid.uuid4().hex)
    csrf = assert_ok(response)['csrf_token']
    current = assert_ok(learner.get('/api/v1/me/current-action'))
    path = '/api/v1/me/assignments/' + current['resource_id']

    def command(url, body):
        return assert_ok(learner.post(url, json=body, headers={
            'X-CSRF-Token':csrf, 'Idempotency-Key':str(uuid.uuid4())}))

    detail = assert_ok(learner.get(path))
    for material in detail['learning_materials']:
        if material['required']:
            command(path + '/materials/' + material['key'] + '/complete', {'task_version':detail['task_version']})
    detail = assert_ok(learner.get(path))
    started = command(path + '/start', {'expected_revision':detail['revision']})
    submitted = command(path + '/submissions', {'expected_revision':started['revision'],
        'body':'学习记录包含事实来源、理解过程和具体行动，完成后继续提交下一关并等待人工审核。' * 3,
        'attachment_ids':[]})
    with SessionLocal() as session:
        review = session.scalar(select(Review).where(Review.submission_version_id == uuid.UUID(submitted['submission_version_id'])))
        return review.id


def review_command(client, csrf, review_id, action, body):
    return client.post(f'/api/v1/reviews/{review_id}/{action}', json=body,
        headers={'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid.uuid4())})


def approval(detail, revision):
    dimensions = []
    for dim in detail['rubric']['dimensions']:
        if dim.get('required'):
            item = {'dimension_key':dim['dimension_key'],'rating':'MEETS','feedback':'证据内容具体完整，可以核对本次学习和行动。'}
            if isinstance(dim.get('max_points'), int):
                item['score'] = dim['max_points']
            dimensions.append(item)
    return {'expected_revision':revision,'overall_decision':'APPROVE',
        'overall_feedback':'本次学习证据充分且完整，后续请继续保持具体的行动记录。','rubric_evaluations':dimensions}


def test_shared_peer_can_review_new_oauth_learner_and_actual_executor_is_retained(shared_pool):
    provider, peer_id, excluded_id, outsider_id = shared_pool
    review_id = new_submission(provider)
    peer, csrf = client_for_linked_reviewer(peer_id)
    queue = assert_ok(peer.get('/api/v1/reviews'))['items']
    assert str(review_id) in {item['id'] for item in queue}
    detail = assert_ok(peer.get(f'/api/v1/reviews/{review_id}'))
    started = assert_ok(review_command(peer, csrf, review_id, 'start', {'expected_revision':detail['revision']}))
    assert_ok(review_command(peer, csrf, review_id, 'finalize', approval(detail, started['review_revision'])))
    with SessionLocal() as session:
        evaluation = session.scalar(select(Evaluation).where(Evaluation.review_id == review_id))
        assert evaluation.executor_id == peer_id
        assert evaluation.created_by == peer_id
        assert evaluation.reviewer_id == REVIEWER_ID
    assert str(review_id) in {item['id'] for item in assert_ok(peer.get('/api/v1/reviews/history'))['items']}
    excluded, _ = client_for_linked_reviewer(excluded_id)
    assert excluded.get('/api/v1/reviews').status_code in (401,403)
    outsider, _ = client_for_linked_reviewer(outsider_id)
    assert outsider.get(f'/api/v1/reviews/{review_id}').status_code == 404


def test_shared_scope_does_not_expose_old_assigned_or_other_organization_reviews(shared_pool):
    _, peer_id, _, _ = shared_pool
    old = create_submission('old-assigned-stays-private')
    peer, _ = client_for_linked_reviewer(peer_id)
    assert peer.get(f"/api/v1/reviews/{old['review_id']}").status_code == 404
    assert peer.get(f'/api/v1/reviews/{create_other_org_review()}').status_code == 404


def test_two_shared_reviewers_cannot_create_two_final_results(shared_pool, monkeypatch):
    provider, peer_id, _, _ = shared_pool
    second_id = create_linked_reviewer('Second concurrent shared reviewer')
    monkeypatch.setenv('FEISHU_LEARNER_SHARED_REVIEWER_IDS', f'{REVIEWER_ID},{peer_id},{second_id}')
    get_settings.cache_clear()
    review_id = new_submission(provider)
    first, first_csrf = client_for_linked_reviewer(peer_id)
    second, second_csrf = client_for_linked_reviewer(second_id)
    detail = assert_ok(first.get(f'/api/v1/reviews/{review_id}'))
    started = assert_ok(review_command(first, first_csrf, review_id, 'start', {'expected_revision':detail['revision']}))
    body = approval(detail, started['review_revision'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda pair: review_command(pair[0],pair[1],review_id,'finalize',body),
            [(first,first_csrf),(second,second_csrf)]))
    assert sorted(r.status_code for r in responses) == [200,409]
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Evaluation.id)).where(Evaluation.review_id == review_id)) == 1


def test_excluded_staff_cannot_oauth_into_review_but_can_still_use_learner_entry(shared_pool):
    provider, _, excluded_id, _ = shared_pool
    subject = 'ou_excluded_' + uuid.uuid4().hex
    settings = get_settings()
    with SessionLocal.begin() as session:
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == excluded_id))
        identity.subject = credential_hash(settings.identity_subject_secret, 'external:FEISHU:cli_test', subject)
    reviewer = client_for('excluded-oauth-entry')
    state = begin_oauth(reviewer, '/review')
    code = uuid.uuid4().hex
    provider.subjects[code] = subject
    assert callback(reviewer, code, state).status_code == 403
    learner, result = login(provider, 'excluded-learner-entry', subject)
    assert assert_ok(result)['safe_entry'] == '/app'
    roles = assert_ok(learner.get('/api/v1/session'))['roles']
    assert 'LEARNER' in roles
    assert 'REVIEWER' not in roles
    assert learner.get('/api/v1/reviews').status_code == 403


def test_disabling_shared_mode_returns_to_assigned_visibility(shared_pool, monkeypatch):
    provider, peer_id, _, _ = shared_pool
    review_id = new_submission(provider)
    peer, _ = client_for_linked_reviewer(peer_id)
    assert peer.get(f'/api/v1/reviews/{review_id}').status_code == 200
    monkeypatch.setenv('FEISHU_LEARNER_SHARED_REVIEWER_IDS', '')
    get_settings.cache_clear()
    assert peer.get(f'/api/v1/reviews/{review_id}').status_code == 404
