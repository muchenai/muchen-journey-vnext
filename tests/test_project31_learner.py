import uuid
from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.review_admin_models import ReviewAdminTask
from test_novice_tasks import setup, read, claim
from test_medal_economy import save, medal, complete
from test_reviewer_workbench import create_submission
from test_wp09_feishu_identity import assert_ok


def test_task_department_comes_from_published_version_not_draft_or_rewards(setup):
    staff, learner, task_id, published, data = setup
    with SessionLocal() as session:
        draft = session.scalar(select(ReviewAdminTask).where(ReviewAdminTask.task_definition_id == uuid.UUID(task_id)))
        draft.content = {**draft.content, 'publishingDepartment': '多语种数据交付线'}
        session.commit()
    task = read(learner, task_id)
    assert task['publishingDepartment'] == data['publishingDepartment']
    assert task['publishingDepartment'] != '多语种数据交付线'
    assert task['category'] == '项目管理'
    assert claim(learner, task_id, published['versionId'])['publishingDepartment'] == data['publishingDepartment']


def test_learner_medals_include_only_published_and_own_redemptions(setup):
    staff, learner, task_id, published, _ = setup
    medal_id, hidden_id = str(uuid.uuid4()), str(uuid.uuid4())
    assert_ok(save(staff, medal_id, medal()))
    assert_ok(save(staff, hidden_id, {**medal(), 'status':'draft'}))
    before = assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert medal_id in [m['id'] for m in before['medals']]
    assert hidden_id not in [m['id'] for m in before['medals']]
    assert before['redemptions'] == []
    complete(staff, learner, task_id, published['versionId'])
    from test_novice_tasks import post
    assert_ok(post(learner, f'me/novice/medals/{medal_id}/redeem', {'expected_revision':1}))
    listing=assert_ok(staff[0].get('/api/v1/review-admin/medals'))
    current=next(m for m in listing['medals'] if m['id']==medal_id)
    assert_ok(save(staff,medal_id,{**current,'name':'changed','status':'unpublished'},current['revision']))
    after=assert_ok(learner[0].get('/api/v1/me/novice/medals'))
    assert medal_id not in [m['id'] for m in after['medals']]
    assert after['redemptions'][0]['medalName']=='隔离测试徽章'
    assert after['wallet']['badgeBalances']['project']==2
    other=create_submission('medal-reader-'+uuid.uuid4().hex)
    assert assert_ok(other['learner'].get('/api/v1/me/novice/medals'))['redemptions']==[]
