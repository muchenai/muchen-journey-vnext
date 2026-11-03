"""Real project36 shop transactions; fixtures run only in an isolated test DB."""
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.medal_catalog import PROJECT36_MEDALS, install_project36_medals
from journey_api.review_admin_models import MedalDefinition, MedalRedemption, PublishedTaskContent
from test_novice_tasks import setup, post
from test_medal_economy import save, complete
from test_wp09_feishu_identity import assert_ok


def test_import_exactly_six_without_wallet_or_ownership_and_preserve_edits(setup):
    staff, learner, *_ = setup
    owner = uuid.UUID(assert_ok(staff[0].get('/api/v1/review-admin/reviews'))['actor']['id'])
    before = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    with SessionLocal() as session:
        created = install_project36_medals(session, ORGANIZATION_ID, owner)
        assert len(created) == 6
        session.commit()
    result = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert result['wallet'] == before['wallet'] and result['redemptions'] == before['redemptions']
    products = [m for m in result['medals'] if m['id'] in created]
    assert len(products) == 6
    for template in PROJECT36_MEDALS:
        actual = next(m for m in products if m['artworkId'] == template['artworkId'])
        for field in ['name', 'description', 'costs', 'style']:
            assert actual[field] == template[field]
        assert actual['stock'] is None and actual['redemptionLimit'] == 1
    changed = products[0]
    assert_ok(save(staff, changed['id'], {**changed, 'status': 'unpublished'}, changed['revision']))
    with SessionLocal() as session:
        assert install_project36_medals(session, ORGANIZATION_ID, owner) == []
        assert session.get(MedalDefinition, uuid.UUID(changed['id'])).content['status'] == 'unpublished'
        session.rollback()


def test_builtin_validation_and_admin_edit_round_trip(setup):
    staff, learner, *_ = setup
    template = {**PROJECT36_MEDALS[1], 'status': 'published', 'stock': None}
    saved = assert_ok(save(staff, str(uuid.uuid4()), template))
    assert saved['artworkId'] == 'tech-1' and saved['style'] == 'purple'
    edited = assert_ok(save(staff, saved['id'], {**saved, 'description': '管理员更新简介'}, saved['revision']))
    assert edited['artworkId'] == 'tech-1' and edited['costs'] == template['costs']
    for unknown in ['missing-artwork', '../../file', 'https://example.com/image.svg']:
        assert save(staff, str(uuid.uuid4()), {**template, 'artworkId': unknown}).status_code == 422
    assert save(learner, str(uuid.uuid4()), template).status_code == 403


def test_real_multitype_debit_retry_snapshot_and_delisting(setup):
    staff, learner, task_id, publication, content = setup
    product = assert_ok(save(staff, str(uuid.uuid4()), {
        **PROJECT36_MEDALS[0], 'status': 'published', 'stock': None,
    }))
    path = f'me/novice/medals/{product["id"]}/redeem'
    command = {'expected_revision': product['revision']}
    assert post(learner, path, command).json()['error']['code'] == 'INSUFFICIENT_POINTS'

    # Earn actual wallet credits from completed assignments, without mocking the
    # wallet or touching the interactive DB. These are isolated historic reward
    # snapshots: four approvals earn exactly 20 product points.
    def earn(kind, weight, other_kind, other_weight):
        key = str(uuid.uuid4())
        draft = {**content, 'badges': [{'id': kind, 'weight': weight}, {'id': other_kind, 'weight': other_weight}], 'difficulty': '挑战'}
        saved = assert_ok(staff[0].put('/api/v1/review-admin/tasks/' + key,
            headers={'X-CSRF-Token': staff[1]}, json={'id': key, 'expected_revision': 0, 'content': draft}))
        owner = assert_ok(staff[0].get('/api/v1/review-admin/reviews'))['actor']['id']
        published = assert_ok(post(staff, f'review-admin/tasks/{key}/publish', {
            'expected_revision': saved['revision'], 'reviewed_by': owner,
            'verified_material_urls': ['https://example.com/material'],
        }))
        complete(staff, learner, key, published['versionId'])

    earn('product', 80, 'project', 20)
    earn('product', 80, 'project', 20)
    before = assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
    assert before['badgeBalances']['product'] >= 20
    assert before['badgeBalances']['data'] == 0
    # Enough total points is not enough: every specified type is required.
    assert post(learner, path, command).status_code == 409
    assert assert_ok(learner[0].get('/api/v1/me/novice/wallet')) == before
    earn('data', 80, 'project', 20)
    before = assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: assert_ok(post(learner, path, command)), range(2)))
    assert receipts[0]['id'] == receipts[1]['id']
    after = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert after['wallet']['badgeBalances']['product'] == before['badgeBalances']['product'] - 20
    assert after['wallet']['badgeBalances']['data'] == before['badgeBalances']['data'] - 10
    assert after['wallet']['xp'] == before['xp']
    assert after['wallet']['badgeBalances']['project'] == before['badgeBalances']['project']
    record = next(r for r in after['redemptions'] if r['medalId'] == product['id'])
    assert record['artworkId'] == 'product-1' and record['style'] == 'blue'
    assert record['costs'] == PROJECT36_MEDALS[0]['costs']
    assert_ok(save(staff, product['id'], {**product, 'artworkId': 'tech-1', 'style': 'purple', 'status': 'unpublished'}, product['revision']))
    reloaded = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert not any(m['id'] == product['id'] for m in reloaded['medals'])
    assert next(r for r in reloaded['redemptions'] if r['medalId'] == product['id']) == record
    assert assert_ok(post(learner, path, command))['alreadyRedeemed']
    assert assert_ok(learner[0].get('/api/v1/me/novice/wallet')) == after['wallet']
