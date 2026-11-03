"""Complete artwork library through the durable administration/learner APIs."""
import uuid
import pytest
from journey_api.medal_catalog import BADGE_ARTWORKS
from test_novice_tasks import setup, post
from test_medal_economy import save, complete
from test_wp09_feishu_identity import assert_ok


def test_all_artworks_can_be_saved_without_automatic_publication(setup):
    staff, learner, *_ = setup
    before = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert len(BADGE_ARTWORKS) == 87
    assert {a['section'] for a in BADGE_ARTWORKS.values()} == {'points', 'delivery', 'general'}
    for index, (key, artwork) in enumerate(BADGE_ARTWORKS.items()):
        level = index % 3 + 1
        result = assert_ok(save(staff, str(uuid.uuid4()), dict(
            name=artwork['name'], artworkId=key, artworkLevel=level,
            themeId='untrusted', themeName='wrong', status='draft', costs=[])))
        assert result['artworkId'] == key and result['artworkLevel'] == level
        assert result['style'] == {1:'blue', 2:'purple', 3:'gold'}[level]
        assert result['themeId'] == artwork['categoryId']
        assert result['themeName'] == artwork['categoryName']
    assert assert_ok(learner[0].get('/api/v1/me/novice/medals')) == before


def test_delivery_publication_redemption_and_historical_artwork(setup):
    staff, learner, task_id, published, _ = setup
    key = str(uuid.uuid4())
    draft = dict(name='多语译匠', artworkId='delivery-multilingual-1', artworkLevel=2,
                 costs=[dict(badgeId='project', points=3)], stock=2, status='draft')
    row = assert_ok(save(staff, key, draft))
    row = assert_ok(save(staff, key, {**row, 'status':'published'}, row['revision']))
    listing = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert next(m for m in listing['medals'] if m['id'] == key)['artworkLevel'] == 2
    complete(staff, learner, task_id, published['versionId'])
    assert_ok(post(learner, f'me/novice/medals/{key}/redeem', {'expected_revision':row['revision']}))
    records = assert_ok(staff[0].get('/api/v1/review-admin/medals'))
    current = next(m for m in records['medals'] if m['id'] == key)
    record = next(r for r in records['redemptions'] if r['medalId'] == key)
    assert record['artworkId'] == draft['artworkId'] and record['artworkLevel'] == 2
    assert record['themeId'] == 'delivery-multilingual'
    assert record['costs'] == draft['costs'] and current['stock'] == 1
    assert_ok(save(staff, key, {**current, 'artworkId':'practice-1', 'artworkLevel':3,
                               'status':'unpublished'}, current['revision']))
    owned = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert not any(m['id'] == key for m in owned['medals'])
    receipt = next(r for r in owned['redemptions'] if r['medalId'] == key)
    assert receipt['artworkId'] == draft['artworkId'] and receipt['artworkLevel'] == 2
    assert receipt['costs'] == draft['costs']


@pytest.mark.parametrize('changes', [dict(artworkLevel=0), dict(artworkLevel=4),
    dict(artworkLevel=True), dict(artworkId='__proto__'), dict(costs=[], status='published')])
def test_invalid_artwork_configuration_is_rejected(setup, changes):
    staff, learner, *_ = setup
    data = dict(name='测试图标', artworkId='delivery-agent-1', artworkLevel=1,
                costs=[dict(badgeId='project', points=1)], status='draft')
    assert save(staff, str(uuid.uuid4()), {**data, **changes}).status_code == 422
    assert save(learner, str(uuid.uuid4()), data).status_code == 403
