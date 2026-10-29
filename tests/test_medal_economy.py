import base64
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func
from journey_api.db import SessionLocal
from journey_api.models import Review
from journey_api.review_admin_models import MedalRedemption, NoviceUnlockDebit
from journey_api.novice_economy import rewards
from test_novice_tasks import setup, post, read, claim
from test_wp09_feishu_identity import assert_ok
from test_reviewer_workbench import create_submission

def save(staff, medal_id, data, revision=0):
    return staff[0].put('/api/v1/review-admin/medals/'+medal_id,
        headers={'X-CSRF-Token':staff[1]},json={'expected_revision':revision,'content':data})

def medal(**changes):
    return dict(name='隔离测试徽章',description='真实接口测试',style='blue',image='',
        costs=[{'badgeId':'project','points':3}],stock=1,status='published',**changes)

def complete(staff, learner, task_id, version):
    task=claim(learner,task_id,version)
    result=assert_ok(post(learner,f'me/assignments/{task["assignmentId"]}/submissions',
        {'expected_revision':task['revision'],'body':'这是用于隔离测试的完整学习提交，包含问题背景分析、学习材料说明、实际执行步骤和可验证的结果与验收依据。'}))
    with SessionLocal() as session:
        review_id=session.scalar(select(Review.id).where(Review.submission_version_id==uuid.UUID(result['submission_version_id'])))
    lease=assert_ok(post(staff,f'review-admin/reviews/{review_id}/claim',{'action':'acquire','expected_revision':1}))
    assert_ok(post(staff,f'review-admin/reviews/{review_id}/decision',
        {'decision':'APPROVE','expected_revision':lease['revision'],'claim_token':lease['token'],'feedback':'','reasons':[]}))

def test_medal_persistence_revision_permissions_and_images(setup):
    staff, learner, *_=setup
    medal_id=str(uuid.uuid4())
    data=medal()
    assert save(learner,medal_id,data).status_code==403
    saved=assert_ok(save(staff,medal_id,data))
    assert saved['revision']==1
    assert save(staff,medal_id,{**data,'name':'过期修改'}).status_code==409
    changed=assert_ok(save(staff,medal_id,{**data,'status':'unpublished'},1))
    assert changed['revision']==2
    listing=assert_ok(staff[0].get('/api/v1/review-admin/medals'))
    assert next(m for m in listing['medals'] if m['id']==medal_id)['status']=='unpublished'
    for bad in [dict(costs=[{'badgeId':'project','points':1.5}]),dict(costs=[]),dict(stock=-1),dict(name=' '),dict(costs=[{'badgeId':'unknown','points':1}])]:
        assert save(staff,str(uuid.uuid4()),{**data,**bad}).status_code==422
    for source in ['<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                   '<!DOCTYPE svg [<!ENTITY a SYSTEM "file:///etc/passwd">]><svg>&a;</svg>',
                   '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://evil.example/x)"/></svg>']:
        image='data:image/svg+xml;base64,'+base64.b64encode(source.encode()).decode()
        assert save(staff,str(uuid.uuid4()),{**data,'image':image}).status_code==422
    image='data:image/svg+xml;base64,'+base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="blue"/></svg>').decode()
    assert_ok(save(staff,str(uuid.uuid4()),{**data,'image':image}))

def test_redemption_concurrent_retry_and_historical_prices(setup):
    staff, learner, task_id, published, _=setup
    medal_id=str(uuid.uuid4())
    saved=assert_ok(save(staff,medal_id,medal()))
    assert post(learner,f'me/novice/medals/{medal_id}/redeem',{'expected_revision':1}).status_code==409
    complete(staff,learner,task_id,published['versionId'])
    before=assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
    assert before['badgeBalances']['project']==5
    def redeem(_): return assert_ok(post(learner,f'me/novice/medals/{medal_id}/redeem',{'expected_revision':saved['revision']}))
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(redeem,range(2)))
    assert results[0]['id']==results[1]['id']
    after=assert_ok(learner[0].get('/api/v1/me/novice/wallet'))
    assert after['badgeBalances']['project']==2 and after['taskPoints']==0
    listing=assert_ok(staff[0].get('/api/v1/review-admin/medals'))
    current=next(m for m in listing['medals'] if m['id']==medal_id)
    assert current['stock']==0
    assert_ok(save(staff,medal_id,{**current,'name':'新名称','costs':[{'badgeId':'project','points':4}],'status':'unpublished'},current['revision']))
    records=assert_ok(staff[0].get('/api/v1/review-admin/medals'))['redemptions']
    record=next(r for r in records if r['medalId']==medal_id)
    assert record['medalName']=='隔离测试徽章' and record['costs'][0]['points']==3
    assert redeem(0)['alreadyRedeemed']

def test_challenge_free_claim_once_and_no_new_task_points(setup):
    staff, learner, task_id, published, content=setup
    complete(staff,learner,task_id,published['versionId'])
    new_id=str(uuid.uuid4())
    data={**content,'difficulty':'挑战','unlockTaskPoints':5,'badges':[{'id':'product','weight':60},{'id':'data','weight':40}]}
    saved=assert_ok(staff[0].put('/api/v1/review-admin/tasks/'+new_id,headers={'X-CSRF-Token':staff[1]},
        json={'id':new_id,'expected_revision':0,'content':data}))
    author=assert_ok(staff[0].get('/api/v1/review-admin/reviews'))['actor']['id']
    published=assert_ok(post(staff,f'review-admin/tasks/{new_id}/publish',{'expected_revision':saved['revision'],'reviewed_by':author,'verified_material_urls':['https://example.com/material']}))
    detail=read(learner,new_id)
    assert detail['unlockTaskPoints']==0 and detail['experience']==150 and detail['points']==0
    assert detail['rewardAllocations']==[{'id':'product','points':9},{'id':'data','points':6}]
    outsider=create_submission('no-points-'+uuid.uuid4().hex)
    pair=outsider['learner'],outsider['csrf']
    assert post(pair,f'me/novice/tasks/{new_id}/claim',{'version_id':published['versionId']}).status_code==200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:claim(learner,new_id,published['versionId']),range(2)))
    assert results[0]['assignmentId']==results[1]['assignmentId']
    assert assert_ok(learner[0].get('/api/v1/me/novice/wallet'))['taskPoints']==0
    with SessionLocal() as session:
        from journey_api.models import Enrollment
        assert session.scalar(select(func.count()).select_from(NoviceUnlockDebit).join(Enrollment,Enrollment.id==NoviceUnlockDebit.enrollment_id).where(Enrollment.novice_task_id==uuid.UUID(new_id))) == 0
    complete(staff,learner,new_id,published['versionId'])
    assert assert_ok(learner[0].get('/api/v1/me/novice/wallet'))['taskPoints']==0

def test_reward_allocation_and_historical_schedule():
    for total_difficulty in ['入门','进阶','挑战']:
        for ratio in range(10,100,10):
            r=rewards({'difficulty':total_difficulty,'rewardRulesVersion':2,'badges':[{'id':'product','weight':ratio},{'id':'data','weight':100-ratio}]})
            assert sum(b['points'] for b in r['allocations'])==r['totalPoints']
            assert all(isinstance(b['points'],int) for b in r['allocations'])
    assert rewards({'difficulty':'挑战'})['xp']==200
