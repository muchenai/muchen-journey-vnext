import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func
from journey_api.db import SessionLocal
from journey_api.seed import ORGANIZATION_ID
from journey_api.models import TaskVersion
from journey_api.review_admin_models import TaskPublicationRequest
from test_review_admin import content
from test_reviewer_workbench import create_linked_reviewer, create_submission
from test_exploration_review_access import administrator
from test_novice_tasks import post
from test_wp09_feishu_identity import assert_ok

def setup_flow():
    owner_id = create_linked_reviewer('发布审批测试作者')
    owner = administrator(owner_id, ORGANIZATION_ID, 'admin')
    boss_id = create_linked_reviewer('发布审批测试主管')
    boss = administrator(boss_id, ORGANIZATION_ID, 'super_admin')
    task_id = str(uuid.uuid4())
    data = content()
    saved = save(owner, task_id, 0, data)
    return owner, boss, task_id, data, saved

def save(pair, task_id, revision, data):
    return assert_ok(pair[0].put('/api/v1/review-admin/tasks/'+task_id,
        headers={'X-CSRF-Token':pair[1]}, json={'id':task_id,'expected_revision':revision,'content':data}))

def submit(pair, task_id, revision):
    return post(pair, f'review-admin/tasks/{task_id}/submit-publication',
        {'expected_revision':revision,'verified_material_urls':['https://example.com/material']})

def request_for(pair, task_id):
    rows = assert_ok(pair[0].get('/api/v1/review-admin/publications'))['items']
    return next(r for r in rows if r['taskId'] == task_id)

def decision(pair, row, state='approved', comment=''):
    return post(pair, f"review-admin/publications/{row['id']}/decision",
        {'expected_revision':row['revision'],'decision':state,'comment':comment})

def test_ordinary_submission_super_approval_concurrency_and_free_claim():
    owner,boss,task_id,data,saved = setup_flow()
    assert post(owner, f'review-admin/tasks/{task_id}/publish',
        {'expected_revision':saved['revision'],'reviewed_by':str(uuid.uuid4()),'verified_material_urls':[]}).status_code == 403
    flow = create_submission('approval-learner-'+uuid.uuid4().hex)
    learner = flow['learner'],flow['csrf']
    assert learner[0].get('/api/v1/me/novice/tasks/'+task_id).status_code == 404
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _:submit(owner,task_id,saved['revision']), range(2)))
    assert all(r.status_code == 200 for r in responses)
    pending = request_for(boss,task_id)
    assert pending['status'] == 'pending'
    assert learner[0].get('/api/v1/me/novice/tasks/'+task_id).status_code == 404
    assert decision(owner,pending).status_code == 403
    blocked = owner[0].put('/api/v1/review-admin/tasks/'+task_id,headers={'X-CSRF-Token':owner[1]},
        json={'id':task_id,'expected_revision':saved['revision'],'content':{**data,'title':'不应改变的内容'}})
    assert blocked.status_code == 409
    other = administrator(create_linked_reviewer('无关管理员'),ORGANIZATION_ID,'admin')
    assert all(r['taskId'] != task_id for r in assert_ok(other[0].get('/api/v1/review-admin/publications'))['items'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:decision(boss,pending), range(2)))
    assert sorted(r.status_code for r in results) == [200,409]
    visible = assert_ok(learner[0].get('/api/v1/me/novice/tasks/'+task_id))
    assert visible['title'] == data['title'] and visible['unlockTaskPoints'] == 0
    assert_ok(post(learner,f'me/novice/tasks/{task_id}/claim',{'version_id':visible['versionId']}))
    with SessionLocal() as session:
        assert session.scalar(select(func.count(TaskVersion.id)).where(TaskVersion.task_definition_id==uuid.UUID(task_id))) == 1
        assert session.scalar(select(func.count(TaskPublicationRequest.id)).where(TaskPublicationRequest.task_id==uuid.UUID(task_id))) == 1

def test_return_reason_resubmit_and_existing_live_version_stays_visible():
    owner,boss,task_id,data,saved = setup_flow()
    assert_ok(submit(owner,task_id,saved['revision']))
    first = request_for(boss,task_id)
    assert decision(boss,first,'rejected',' ').status_code == 422
    assert_ok(decision(boss,first,'rejected','补充学习材料说明'))
    saved = save(owner,task_id,saved['revision'],{**data,'title':'修改后提交审批的任务'})
    assert_ok(submit(owner,task_id,saved['revision']))
    second = request_for(boss,task_id)
    assert first['id'] != second['id']
    assert_ok(decision(boss,second))
    flow=create_submission('approval-version-'+uuid.uuid4().hex)
    learner=flow['learner'],flow['csrf']
    original=assert_ok(learner[0].get('/api/v1/me/novice/tasks/'+task_id))
    saved=save(owner,task_id,saved['revision'],{**data,'title':'等待审核的任务更新'})
    assert_ok(submit(owner,task_id,saved['revision']))
    waiting=assert_ok(learner[0].get('/api/v1/me/novice/tasks/'+task_id))
    assert waiting['title']==original['title'] and waiting['versionId']==original['versionId']
    assert_ok(decision(boss,request_for(boss,task_id),'rejected','请完善任务要求'))
    assert assert_ok(learner[0].get('/api/v1/me/novice/tasks/'+task_id))['versionId']==original['versionId']

def test_challenge_new_rules_have_no_cost_and_twenty_percent_weights():
    owner,boss,task_id,data,saved=setup_flow()
    boss_id=str(assert_ok(boss[0].get('/api/v1/review-admin/reviews'))['actor']['id'])
    another=str(uuid.uuid4())
    challenge={**data,'difficulty':'挑战','unlockTaskPoints':999,'badges':[{'id':'product','weight':60},{'id':'data','weight':40}]}
    saved=save(boss,another,0,challenge)
    assert saved['unlockTaskPoints']==0 and saved['rewardRulesVersion']==3 and saved['taskPoints']==0
    published=assert_ok(post(boss,f'review-admin/tasks/{another}/publish',{'expected_revision':saved['revision'],
        'reviewed_by':boss_id,'verified_material_urls':['https://example.com/material']}))
    flow=create_submission('free-challenge-'+uuid.uuid4().hex)
    learner=flow['learner'],flow['csrf']
    assert_ok(post(learner,f'me/novice/tasks/{another}/claim',{'version_id':published['versionId']}))
    invalid=boss[0].put('/api/v1/review-admin/tasks/'+another,headers={'X-CSRF-Token':boss[1]},
        json={'id':another,'expected_revision':saved['revision'],'content':{**challenge,'badges':[{'id':'product','weight':50},{'id':'data','weight':50}]}})
    assert invalid.status_code==422

def test_generic_publish_cannot_bypass_approval_and_revoked_author_stays_unpublished():
    from journey_api.review_admin_routes import task_content_for_publish
    from journey_api.review_admin_models import ReviewAdminAccess
    from journey_api.identity import utc_now
    owner,boss,task_id,data,saved=setup_flow()
    boss_id=assert_ok(boss[0].get('/api/v1/review-admin/reviews'))['actor']['id']
    body=task_content_for_publish(data)
    bypass=owner[0].post(f'/api/v1/ops/task-definitions/{task_id}/publish',
        headers={'X-CSRF-Token':owner[1], 'Idempotency-Key':str(uuid.uuid4())},
        json={**body,'expected_revision':saved['definitionRevision'],'reviewed_by':boss_id,
              'verified_material_urls':['https://example.com/material']})
    assert bypass.status_code==403
    assert_ok(submit(owner,task_id,saved['revision']))
    pending=request_for(boss,task_id)
    with SessionLocal.begin() as session:
        access=session.get(ReviewAdminAccess, uuid.UUID(pending['submittedBy']['id']))
        access.revoked_at=utc_now()
    denied=decision(boss,pending)
    assert denied.status_code==409 and denied.json()['error']['code']=='AUTHOR_UNAVAILABLE'
    assert request_for(boss,task_id)['status']=='pending'
    with SessionLocal() as session:
        assert session.scalar(select(func.count(TaskVersion.id)).where(TaskVersion.task_definition_id==uuid.UUID(task_id)))==0
