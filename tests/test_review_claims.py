import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, func
from journey_api.db import SessionLocal
from journey_api.models import Review, Evaluation, AuditEntry
from journey_api.review_admin_models import ReviewClaim, ReviewAdminAccess
from test_shared_learner_reviews import shared_pool, learner_provider, oauth_provider, new_submission, approval
from test_reviewer_workbench import client_for_linked_reviewer, create_other_org_review
from test_wp09_feishu_identity import assert_ok


def command(pair, review_id, action, revision=1, token=None):
    client, csrf = pair
    return client.post(f'/api/v1/review-admin/reviews/{review_id}/claim', headers={'X-CSRF-Token': csrf},
        json={'action': action, 'expected_revision': revision, 'token': token, 'expected_claim_version': 1})


def decide(pair, rid, lease):
    return pair[0].post(f'/api/v1/review-admin/reviews/{rid}/decision',
        headers={'X-CSRF-Token': pair[1], 'Idempotency-Key': str(uuid.uuid4())},
        json={'expected_revision': lease['revision'], 'claim_token': lease['token'], 'decision': 'APPROVE', 'reasons': []})


def test_simultaneous_claims_only_one_owner_and_no_endpoint_bypass(shared_pool):
    provider, peer, _, outsider = shared_pool
    rid = new_submission(provider)
    pairs = [client_for_linked_reviewer(peer), client_for_linked_reviewer(outsider)]
    detail = assert_ok(pairs[0][0].get(f'/api/v1/reviews/{rid}'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda p: command(p, rid, 'acquire'), pairs))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(i for i, r in enumerate(results) if r.status_code == 200)
    lease = assert_ok(results[winner]); loser = pairs[1-winner]
    assert results[1-winner].json()['error']['code'] == 'REVIEW_CLAIMED'
    for path in ['review-admin/reviews', 'reviews']:
        assert loser[0].get(f'/api/v1/{path}/{rid}').status_code == 409
    for action, body in [('start', {'expected_revision':lease['revision']}), ('finalize', approval(detail, lease['revision']))]:
        r = loser[0].post(f'/api/v1/reviews/{rid}/{action}', headers={'X-CSRF-Token': loser[1], 'Idempotency-Key': str(uuid.uuid4())}, json=body)
        assert r.status_code == 409 and r.json()['error']['code'] == 'REVIEW_CLAIMED'
    assert decide(loser, rid, lease).status_code == 409
    assert_ok(decide(pairs[winner], rid, lease))
    with SessionLocal() as s:
        assert s.scalar(select(func.count(Evaluation.id)).where(Evaluation.review_id == rid)) == 1
    row = next(r for r in assert_ok(loser[0].get('/api/v1/review-admin/reviews'))['items'] if r['id'] == str(rid))
    assert row['claim'] is None and row['actual_reviewer']['id'] == str([peer, outsider][winner])


def test_expiry_reclaim_and_old_token_cannot_renew_release_or_decide(shared_pool):
    provider, peer, _, outsider = shared_pool
    rid = new_submission(provider); a = client_for_linked_reviewer(peer); b = client_for_linked_reviewer(outsider)
    old = assert_ok(command(a, rid, 'acquire'))
    renewed = assert_ok(command(a, rid, 'renew', old['revision'], old['token']))
    assert renewed['claim']['started_at'] == old['claim']['started_at']
    assert renewed['claim']['expires_at'] >= old['claim']['expires_at']
    with SessionLocal.begin() as s:
        s.get(ReviewClaim, rid).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert command(a, rid, 'renew', old['revision'], old['token']).status_code == 409
    row = next(r for r in assert_ok(b[0].get('/api/v1/review-admin/reviews'))['items'] if r['id'] == str(rid))
    assert row['claim'] is None
    current = assert_ok(command(b, rid, 'acquire', old['revision']))
    assert current['token'] != old['token']
    assert decide(a, rid, old).status_code == 409
    assert command(a, rid, 'release', old['revision'], old['token']).status_code == 409
    released = assert_ok(command(b, rid, 'release', current['revision'], current['token']))
    again = assert_ok(command(b, rid, 'acquire', released['revision']))
    # Same actor's stale tab is fenced as well.
    assert command(b, rid, 'renew', again['revision'], current['token']).status_code == 409
    assert decide(b, rid, current).status_code == 409
    assert_ok(decide(b, rid, again))


def test_force_release_is_privileged_scoped_and_audited(shared_pool):
    provider, peer, _, outsider = shared_pool
    rid = new_submission(provider); a = client_for_linked_reviewer(peer); b = client_for_linked_reviewer(outsider)
    lease = assert_ok(command(a, rid, 'acquire'))
    assert command(b, rid, 'force_release', lease['revision']).status_code == 403
    with SessionLocal.begin() as s:
        org = s.get(Review, rid).organization_id
        s.add(ReviewAdminAccess(user_id=outsider, organization_id=org, access_role='super_admin',
            can_grant_super_admin=True, level='高级', domain='产品开发', granted_by=outsider))
    assert command(b, create_other_org_review(), 'force_release').status_code == 404
    released = assert_ok(command(b, rid, 'force_release', lease['revision']))
    assert released['claim'] is None
    assert decide(a, rid, lease).status_code == 409
    with SessionLocal() as s:
        assert s.scalar(select(func.count(AuditEntry.id)).where(AuditEntry.action == 'review.claim_force_released', AuditEntry.resource_id == str(rid))) == 1


def test_unclaimed_decision_and_revoked_owner_cannot_submit(shared_pool):
    provider, peer, _, _ = shared_pool
    rid = new_submission(provider); a = client_for_linked_reviewer(peer)
    assert decide(a, rid, {'revision':1,'token':None}).status_code == 409
    lease = assert_ok(command(a, rid, 'acquire'))
    with SessionLocal.begin() as s:
        s.add(ReviewAdminAccess(user_id=peer, organization_id=s.get(Review, rid).organization_id,
            access_role='admin', level='初级', domain='产品开发', granted_by=peer, revoked_at=datetime.now(UTC)))
    assert command(a, rid, 'renew', lease['revision'], lease['token']).status_code in {401, 403}
    assert decide(a, rid, lease).status_code in {401, 403}
