import uuid
from sqlalchemy import select
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import credential_hash
from journey_api.models import ExternalIdentity, Role, RoleAssignment
from test_wp09_feishu_identity import oauth_provider, begin_oauth, callback, client_for, assert_ok
from test_learner_feishu_login import learner_provider, login
from test_shared_learner_reviews import shared_pool, new_submission
from test_review_admin import content


def test_feishu_review_operator_session_without_fixture_and_logout(shared_pool, monkeypatch):
    provider, reviewer_id, _, _ = shared_pool
    review_id = new_submission(provider)
    subject = 'ou_review_admin_' + uuid.uuid4().hex
    settings = get_settings()
    with SessionLocal.begin() as s:
        identity = s.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == reviewer_id))
        identity.subject = credential_hash(settings.identity_subject_secret,
            f'external:FEISHU:{settings.feishu_app_id}', subject)
        s.add(RoleAssignment(id=uuid.uuid4(), organization_id=identity.organization_id,
            user_id=reviewer_id, role=Role.OPERATOR))
    monkeypatch.setenv('ALLOW_FIXTURE_IDENTITY', 'false')
    get_settings.cache_clear()
    reviewer = client_for('real-review-admin-' + uuid.uuid4().hex)
    assert reviewer.get('/api/v1/review-admin/reviews', headers={'X-Fixture-Role':'REVIEWER'}).status_code == 401
    code = uuid.uuid4().hex
    provider.subjects[code] = subject
    state = begin_oauth(reviewer, '/review')
    session = assert_ok(callback(reviewer, code, state))
    assert session['safe_entry'] == '/review'
    principal = assert_ok(reviewer.get('/api/v1/session'))
    assert principal['user_id'] == str(reviewer_id)
    assert {'REVIEWER', 'OPERATOR'} <= set(principal['roles'])
    queue = assert_ok(reviewer.get('/api/v1/review-admin/reviews'))
    assert queue['actor']['id'] == str(reviewer_id)
    row = next(r for r in queue['items'] if r['id'] == str(review_id))
    assert assert_ok(reviewer.get('/api/v1/review-admin/members'))['actor_id'] == str(reviewer_id)
    payload = {'expected_revision': row['revision'], 'decision':'APPROVE',
        'feedback':'已核对本次任务的具体证据和行动记录，符合完成要求。', 'reasons':[]}
    url = f'/api/v1/review-admin/reviews/{review_id}/decision'
    assert reviewer.post(url, json=payload, headers={'Idempotency-Key':str(uuid.uuid4())}).status_code == 403
    headers = {'X-CSRF-Token':session['csrf_token'], 'Idempotency-Key':str(uuid.uuid4())}
    assert assert_ok(reviewer.post(url, json=payload, headers=headers))['assignment_status'] in {'PASSED','COMPLETED'}
    task_id = str(uuid.uuid4())
    assert_ok(reviewer.put(f'/api/v1/review-admin/tasks/{task_id}', headers=headers,
        json={'id':task_id, 'expected_revision':0, 'content':content()}))
    learner, response = login(provider, 'no-review-access-' + uuid.uuid4().hex, 'ou_learner_' + uuid.uuid4().hex)
    assert_ok(response)
    assert learner.get('/api/v1/review-admin/reviews').status_code == 403
    assert_ok(reviewer.post('/api/v1/session/logout', headers=headers))
    assert reviewer.get('/api/v1/review-admin/reviews').status_code == 401
