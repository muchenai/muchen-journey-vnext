"""Reward catalogs are independent of task directions and keep their server IDs."""
import uuid
import pytest
from pydantic import ValidationError
from journey_api.review_admin_routes import TaskContent, DOMAINS
from journey_api.novice_economy import POINT_NAMES, POINT_TYPES
from test_review_admin import content
from test_novice_tasks import setup, post, read
from test_medal_economy import complete, save, medal
from test_wp09_feishu_identity import assert_ok

NEW_TYPES = {
    'it-service': 'IT服务', 'talent-acquisition': '人才开发', 'talent-development': '人才发展',
    'customer-growth': '客户增长', 'hr-compensation': '人事薪酬', 'finance-compliance': '财法合规',
    'organization-development': '组织发展', 'intelligent-solutions': '智能产品方案',
    'workplace': '行政职场', 'business-operations': '综合经营',
}

@pytest.mark.parametrize('badge_id', NEW_TYPES)
def test_new_point_types_validate_without_adding_task_directions(badge_id):
    assert len(POINT_TYPES) == 18
    assert len(DOMAINS) == 8
    assert POINT_NAMES[badge_id] == NEW_TYPES[badge_id]
    data = content()
    data['badges'] = [{'id': badge_id, 'weight': 100}]
    assert TaskContent(**data).model_dump()['badges'] == data['badges']
    with pytest.raises(ValidationError):
        TaskContent(**{**data, 'domain': NEW_TYPES[badge_id]})

def test_new_types_save_publish_reopen_and_award_real_balance(setup):
    staff, learner, _, _, _ = setup
    for index, (badge_id, label) in enumerate(NEW_TYPES.items()):
        task_id = str(uuid.uuid4())
        data = {**content(), 'title': label + '奖励类型验证', 'badges': [{'id': badge_id, 'weight': 100}]}
        draft = assert_ok(staff[0].put('/api/v1/review-admin/tasks/' + task_id,
            headers={'X-CSRF-Token': staff[1]}, json={'id': task_id, 'expected_revision': 0, 'content': data}))
        assert draft['badges'] == data['badges']
        published = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish',
            {'expected_revision': draft['revision'], 'reviewed_by': draft['authorId'],
             'verified_material_urls': ['https://example.com/material']}))
        assert read(learner, task_id)['badges'] == [[label, 100]]
        if index == 0:
            complete(staff, learner, task_id, published['versionId'])
            balance = assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
            assert balance['badgeBalances'][badge_id] == 5
            result = assert_ok(save(staff, str(uuid.uuid4()), {**medal(), 'costs': [{'badgeId': badge_id, 'points': 3}]}))
            assert result['costs'] == [{'badgeId': badge_id, 'points': 3}]
