import uuid
import pytest
from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID
from journey_api.models import Review, ReviewStatus
from journey_api.review_admin_models import ReviewAdminDecision
from test_reviewer_workbench import create_submission, client_for, assert_ok, REVIEWER_HEADERS, OPERATOR_HEADERS


def content():
    return {'title':'本地新版审核联调任务','summary':'阅读任务材料后，提出有依据的具体改进建议。','camp':'novice','domain':'产品开发','difficulty':'入门',
        'badges':[{'id':'product','weight':100}], 'materials':[{'id':'source','name':'测试学习材料','type':'link','url':'https://example.com/material'}],
        'reviewMode':'manual','passScore':60,'rubric':[],'rubricAttachments':[]}


def claim(c, review_id, revision=1):
    result = assert_ok(c.post(f'/api/v1/review-admin/reviews/{review_id}/claim', headers=REVIEWER_HEADERS,
        json={'action': 'acquire', 'expected_revision': revision}))
    return {'claim_token': result['token'], 'expected_revision': result['revision']}


def test_real_learner_submission_appears_and_review_syncs_back():
    flow=create_submission('new-admin-'+uuid.uuid4().hex[:8])
    c=client_for('admin-review-'+uuid.uuid4().hex)
    data=assert_ok(c.get('/api/v1/review-admin/reviews',headers=REVIEWER_HEADERS))
    item=next(r for r in data['items'] if r['id']==str(flow['review_id']))
    assert item['assignment_id']==flow['assignment_id']
    assert item['decision'] is None
    key=str(uuid.uuid4())
    payload={'expected_revision':item['revision'],'decision':'APPROVE','feedback':'已逐项核对提交中的事实与行动，本次任务符合完成要求。','reasons':[],'score':None}
    payload.update(claim(c, item['id'], item['revision']))
    result=assert_ok(c.post(f"/api/v1/review-admin/reviews/{item['id']}/decision",headers={**REVIEWER_HEADERS,'Idempotency-Key':key},json=payload))
    assert result['assignment_status'] in {'PASSED','COMPLETED'}
    assert_ok(c.post(f"/api/v1/review-admin/reviews/{item['id']}/decision",headers={**REVIEWER_HEADERS,'Idempotency-Key':key},json=payload))
    latest=assert_ok(c.get('/api/v1/review-admin/reviews',headers=REVIEWER_HEADERS))
    row=next(r for r in latest['items'] if r['id']==item['id'])
    assert row['decision']=='PASS'
    learner=assert_ok(flow['learner'].get(f"/api/v1/me/assignments/{flow['assignment_id']}"))
    assert learner['status'] in {'PASSED','COMPLETED'}
    with SessionLocal() as session:
        assert session.get(ReviewAdminDecision,flow['review_id']) is not None


def test_invalid_return_keeps_review_pending():
    flow=create_submission('admin-return-'+uuid.uuid4().hex[:8])
    c=client_for('admin-return-reviewer')
    payload={'expected_revision':1,'decision':'REQUEST_REVISION','feedback':'太短','reasons':[]}
    response=c.post(f"/api/v1/review-admin/reviews/{flow['review_id']}/decision",headers={**REVIEWER_HEADERS,'Idempotency-Key':str(uuid.uuid4())},json=payload)
    assert response.status_code==422
    with SessionLocal() as session:
        assert session.get(Review,flow['review_id']).status==ReviewStatus.ASSIGNED
    payload.update(feedback='请补充事实依据及验证方案，以便我们核对实际效果。',reasons=['依据或论证不足'])
    payload.update(claim(c, flow['review_id']))
    result=assert_ok(c.post(f"/api/v1/review-admin/reviews/{flow['review_id']}/decision",headers={**REVIEWER_HEADERS,'Idempotency-Key':str(uuid.uuid4())},json=payload))
    assert result['assignment_status']=='NEEDS_REVISION'


def test_approval_with_return_reason_is_rejected_before_any_review_write():
    flow=create_submission('conflicting-decision-'+uuid.uuid4().hex[:8])
    c=client_for('conflicting-decision-reviewer')
    url=f"/api/v1/review-admin/reviews/{flow['review_id']}/decision"
    headers={**REVIEWER_HEADERS,'Idempotency-Key':str(uuid.uuid4())}
    payload={'expected_revision':1,'decision':'APPROVE','feedback':'已核对全部任务要求和本次提交材料。','reasons':['答案错误']}
    before=assert_ok(flow['learner'].get(f"/api/v1/me/assignments/{flow['assignment_id']}"))
    response=c.post(url,headers=headers,json=payload)
    assert response.status_code==422
    assert '取消勾选' in response.json()['error']['message']
    with SessionLocal() as session:
        review=session.get(Review,flow['review_id'])
        assert review.status==ReviewStatus.ASSIGNED and review.revision==1
        assert session.get(ReviewAdminDecision,flow['review_id']) is None
    assert assert_ok(flow['learner'].get(f"/api/v1/me/assignments/{flow['assignment_id']}"))==before
    payload['reasons']=[]
    payload.update(claim(c, flow['review_id']))
    result=assert_ok(c.post(url,headers=headers,json=payload))
    assert result['assignment_status'] in {'PASSED','COMPLETED'}


@pytest.mark.parametrize('corrected_feedback', ['已核对全部要求符合标准', ''])
def test_short_approval_feedback_returns_validation_error_without_starting_review(corrected_feedback):
    flow=create_submission('short-approval-'+uuid.uuid4().hex[:8])
    c=client_for('short-approval-reviewer-'+uuid.uuid4().hex)
    url=f"/api/v1/review-admin/reviews/{flow['review_id']}/decision"
    headers={**REVIEWER_HEADERS,'Idempotency-Key':str(uuid.uuid4())}
    payload={'expected_revision':1,'decision':'APPROVE','feedback':' 写得好写得好写得好 ','score':85,'reasons':[]}
    response=c.post(url,headers=headers,json=payload)
    assert response.status_code==422
    assert response.json()['error']['code']=='VALIDATION_FAILED'
    assert '10' in response.json()['error']['message']
    with SessionLocal() as session:
        review=session.get(Review,flow['review_id'])
        assert review.status==ReviewStatus.ASSIGNED and review.revision==1
        assert session.get(ReviewAdminDecision,flow['review_id']) is None
    payload['feedback']=corrected_feedback
    payload.update(claim(c, flow['review_id']))
    result=assert_ok(c.post(url,headers=headers,json=payload))
    assert result['assignment_status'] in {'PASSED','COMPLETED'}


def test_invalid_dimension_form_returns_validation_error_before_review_start():
    flow=create_submission('invalid-dimension-'+uuid.uuid4().hex[:8])
    c=client_for('invalid-dimension-reviewer')
    response=c.post(f"/api/v1/review-admin/reviews/{flow['review_id']}/decision",
        headers={**REVIEWER_HEADERS,'Idempotency-Key':str(uuid.uuid4())},json={
            'expected_revision':1,'decision':'APPROVE','feedback':'已核对所有任务要求和提交材料。',
            'rubric_evaluations':[{'dimension_key':'task_completion','rating':'INVALID','feedback':'不符合格式'}]})
    assert response.status_code==422
    assert response.json()['error']['code']=='VALIDATION_FAILED'
    with SessionLocal() as session:
        review=session.get(Review,flow['review_id'])
        assert review.status==ReviewStatus.ASSIGNED and review.revision==1


def test_task_draft_publish_and_archive_use_real_version():
    c=client_for('admin-editor')
    task_id=str(uuid.uuid4())
    body={'id':task_id,'expected_revision':0,'content':content()}
    assert c.put(f'/api/v1/review-admin/tasks/{task_id}',headers=REVIEWER_HEADERS,json={**body,'content':{**content(),'difficulty':'挑战'}}).status_code==403
    draft=assert_ok(c.put(f'/api/v1/review-admin/tasks/{task_id}',headers=OPERATOR_HEADERS,json=body))
    assert draft['revision']==1 and draft['status']=='draft'
    assert c.put(f'/api/v1/review-admin/tasks/{task_id}',headers=OPERATOR_HEADERS,json=body).status_code==409
    published=assert_ok(c.post(f'/api/v1/review-admin/tasks/{task_id}/publish',headers={**OPERATOR_HEADERS,'Idempotency-Key':str(uuid.uuid4())},json={
        'expected_revision':1,'reviewed_by':str(REVIEWER_ID),'verified_material_urls':['https://example.com/material']}))
    assert published['version']==1 and published['status']=='published'
    archived=assert_ok(c.post(f'/api/v1/review-admin/tasks/{task_id}/archive',headers=OPERATOR_HEADERS,json={'expected_revision':1,'archived':True}))
    assert archived['status']=='archived' and archived['versionId']==published['versionId']
    restored=assert_ok(c.post(f'/api/v1/review-admin/tasks/{task_id}/archive',headers=OPERATOR_HEADERS,json={'expected_revision':2,'archived':False}))
    assert restored['status']=='published'


def test_learner_cannot_read_admin_data_or_save_certification():
    flow=create_submission('admin-isolation-'+uuid.uuid4().hex[:8])
    for path in ('tasks','reviews','members'):
        assert flow['learner'].get('/api/v1/review-admin/'+path).status_code==403
    c=client_for('admin-certification')
    assert c.get('/api/v1/review-admin/members',headers=OPERATOR_HEADERS).status_code==403
    command={'expected_revision':0,'domain':'产品开发','level':'中级'}
    assert c.put(f'/api/v1/review-admin/members/{REVIEWER_ID}/certification',headers=REVIEWER_HEADERS,json=command).status_code==403
    assert c.put(f'/api/v1/review-admin/members/{REVIEWER_ID}/certification',headers=OPERATOR_HEADERS,json=command).status_code==403

def test_admin_detail_and_queue_use_only_saved_ai_for_current_document():
    from test_review_ai_self_checks import seed_check
    token=uuid.uuid4().hex
    flow=create_submission('admin-ai-'+uuid.uuid4().hex[:8],body='本次学习任务的答题链接为：https://test.feishu.cn/docx/'+token)
    with SessionLocal.begin() as session:
        seed_check(session,flow,token)
    c=client_for('admin-ai-reader')
    detail=assert_ok(c.get(f"/api/v1/review-admin/reviews/{flow['review_id']}",headers=REVIEWER_HEADERS))
    assert detail['document_ai_checks'][0]['status']=='COMPLETED'
    assert 'task_learning_materials' in detail
    queue=assert_ok(c.get('/api/v1/review-admin/reviews',headers=REVIEWER_HEADERS))
    row=next(r for r in queue['items'] if r['id']==str(flow['review_id']))
    assert row['ai_statuses']==['COMPLETED']
