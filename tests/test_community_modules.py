import base64
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.models import Review, User, RoleAssignment, Role, UserStatus, Organization, ExternalIdentity
from journey_api.community_models import CommunityState, KnowledgeFile, GuildContribution
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.seed import ORGANIZATION_ID
from test_exploration_review_access import administrator
from test_reviewer_workbench import create_linked_reviewer, create_submission
from test_novice_tasks import setup, post, claim, read
from test_wp09_feishu_identity import assert_ok


def admin():return administrator(create_linked_reviewer('独立库工会测试'),ORGANIZATION_ID,'admin')


def command(pair,module,action,payload=None,revision=None):
    return post(pair,f'review-admin/community/{module}',dict(action=action,payload=payload or {},expected_revision=revision))


def snapshot(pair,module):return assert_ok(command(pair,module,'snapshot'))['snapshot']


def change(pair,module,action,payload):return assert_ok(command(pair,module,action,payload,snapshot(pair,module)['revision']))


def test_knowledge_links_categories_shared_persistence_and_conflict():
    a,b=admin(),admin()
    cat=change(a,'knowledge','saveCategory',{'name':'资料'+uuid.uuid4().hex[:8]})['result']
    created=change(a,'knowledge','saveLink',dict(title='共享资料',url='https://example.com/doc',categoryId=cat['id'],description='公司资料'))['result']
    assert any(r['id']==created['id'] for r in snapshot(b,'knowledge')['items'])
    rev=snapshot(a,'knowledge')['revision']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda pair:command(pair,'knowledge','updateItem',{**created,'title':'同时编辑'},rev),[a,b]))
    assert sorted(r.status_code for r in results)==[200,409]
    change(b,'knowledge','removeCategory',{'id':cat['id']})
    assert next(r for r in snapshot(a,'knowledge')['items'] if r['id']==created['id'])['categoryId']=='uncategorized'
    assert command(a,'knowledge','saveLink',dict(title='危险链接',url='javascript:alert(1)'),snapshot(a,'knowledge')['revision']).status_code==422
    change(a,'knowledge','removeItem',{'id':created['id']})
    assert not any(r['id']==created['id'] for r in snapshot(b,'knowledge')['items'])


def test_file_chunks_roundtrip_size_limits_and_incomplete_visibility():
    a,b=admin(),admin()
    payload=b'abcd'*150000
    created=assert_ok(command(a,'knowledge','beginUpload',dict(fileName='测试.txt',size=len(payload))))['result']
    file_id=created['id'];step=created['chunkSize']
    assert not any(r['id']==file_id for r in snapshot(b,'knowledge')['items'])
    assert command(b,'knowledge','uploadChunk',dict(id=file_id,position=0,data=''),None).status_code==409
    assert command(a,'knowledge','completeUpload',dict(id=file_id),snapshot(a,'knowledge')['revision']).status_code==422
    for i,offset in enumerate(range(0,len(payload),step)):
        part=dict(id=file_id,position=i,data=base64.b64encode(payload[offset:offset+step]).decode())
        assert_ok(command(a,'knowledge','uploadChunk',part))
        assert_ok(command(a,'knowledge','uploadChunk',part))
    file=change(a,'knowledge','completeUpload',dict(id=file_id,categoryId='company'))['result']
    assert file['size']==len(payload)
    actual=b''.join(base64.b64decode(assert_ok(command(b,'knowledge','getChunk',dict(id=file_id,position=i)))['result']['data']) for i in range(2))
    assert actual==payload
    assert command(a,'knowledge','beginUpload',dict(fileName='too-big',size=100*1024*1024+1)).status_code==422
    change(b,'knowledge','removeItem',dict(id=file_id))
    assert command(a,'knowledge','getChunk',dict(id=file_id,position=0)).status_code==404


def test_permissions_csrf_and_cross_organization(monkeypatch):
    a=admin();flow=create_submission('community-auth-'+uuid.uuid4().hex);learner=flow['learner'],flow['csrf']
    assert command(learner,'knowledge','snapshot').status_code==403
    assert command(learner,'guild','snapshot').status_code==403
    assert a[0].post('/api/v1/review-admin/community/knowledge',json={'action':'snapshot'}).status_code==403
    org=uuid.uuid4();user=uuid.uuid4()
    with SessionLocal.begin() as s:
        s.add(Organization(id=org,name='独立测试组织'))
        s.flush()
        s.add(User(id=user,organization_id=org,display_name='隔离组织管理',status=UserStatus.ACTIVE))
        s.flush()
        s.add(RoleAssignment(id=uuid.uuid4(),organization_id=org,user_id=user,role=Role.REVIEWER))
        from datetime import datetime,UTC
        s.add(ExternalIdentity(id=uuid.uuid4(),organization_id=org,user_id=user,provider="FEISHU",subject=uuid.uuid4().hex,verified_at=datetime.now(UTC),revision=1))
    import test_reviewer_workbench
    with monkeypatch.context() as patch:
        patch.setattr(test_reviewer_workbench,'ORGANIZATION_ID',org)
        other=administrator(user,org,'admin')
    item=change(a,'knowledge','saveLink',dict(title='私有公司资料',url='https://example.com'))['result']
    assert not any(r['id']==item['id'] for r in snapshot(other,'knowledge')['items'])
    assert command(other,'knowledge','updateItem',{**item,'title':'越权'},snapshot(other,'knowledge')['revision']).status_code==404
    created=assert_ok(command(a,'knowledge','beginUpload',dict(fileName='a.txt',size=1)))['result']
    assert command(other,'knowledge','getChunk',dict(id=created['id'],position=0)).status_code==404
    with SessionLocal.begin() as s:
        row=s.scalar(select(ReviewAdminAccess).where(ReviewAdminAccess.user_id==user))
        from datetime import datetime,UTC
        row.revoked_at=datetime.now(UTC)
    assert command(other,'guild','snapshot').status_code==401


def test_certification_history_and_labs(setup):
    staff,learner,task_id,published,_=setup
    user_id=assert_ok(learner[0].get('/api/v1/session'))['user_id']
    p=dict(studentId=user_id,ability='data',level='初级',evidence='已完成能力测试')
    first=change(staff,'guild','grantCertification',p)['result']
    second=change(staff,'guild','grantCertification',{**p,'level':'高级'})['result']
    assert next(c for c in snapshot(staff,'guild')['certifications'] if c['id']==first['id'])['status']=='superseded'
    assert command(staff,'guild','revokeCertification',dict(id=second['id'],reason=' '),snapshot(staff,'guild')['revision']).status_code==422
    change(staff,'guild','revokeCertification',dict(id=second['id'],reason='需要重新认证'))
    lab=change(staff,'guild','saveLab',dict(title='真实环境入口',ability='data',description='',url='',taskId=task_id,status='draft'))['result']
    assert command(staff,'guild','setLabStatus',dict(id=lab['id'],status='published'),snapshot(staff,'guild')['revision']).status_code==422
    lab=change(staff,'guild','saveLab',{**lab,'url':'https://example.com/lab','description':'实验说明','status':'published'})['result']
    assert lab['status']=='published'
    assert change(staff,'guild','setLabStatus',dict(id=lab['id'],status='archived'))['result']['status']=='archived'


def finish_task(staff,learner,task_id,published,decision='APPROVE'):
    task=claim(learner,task_id,published['versionId'])
    submitted=assert_ok(post(learner,f"me/assignments/{task['assignmentId']}/submissions",{'expected_revision':task['revision'],'body':'我完成了材料学习与项目分析，整理了问题背景、验证依据和改进方案，并列出后续执行步骤与验收标准。'}))
    with SessionLocal() as s:rid=s.scalar(select(Review.id).where(Review.submission_version_id==uuid.UUID(submitted['submission_version_id'])))
    lease=assert_ok(post(staff,f'review-admin/reviews/{rid}/claim',dict(action='acquire',expected_revision=1)))
    body=dict(decision=decision,expected_revision=lease['revision'],claim_token=lease['token'],feedback='请补充详细说明' if decision!='APPROVE' else '',reasons=['其他'] if decision!='APPROVE' else [])
    result=post(staff,f'review-admin/reviews/{rid}/decision',body)
    assert_ok(result)
    return rid,body


def test_real_approval_credits_once_and_preserves_original_points(setup):
    staff,learner,task_id,published,_=setup
    rule=change(staff,'guild','saveRule',dict(taskId=task_id,points=12,enabled=True))['result']
    rid,body=finish_task(staff,learner,task_id,published)
    rows=[r for r in snapshot(staff,'guild')['contributions'] if r['taskId']==task_id]
    assert len(rows)==1 and rows[0]['points']==12
    post(staff,f'review-admin/reviews/{rid}/decision',body)
    change(staff,'guild','saveRule',dict(taskId=task_id,points=25,enabled=True))
    rows=[r for r in snapshot(staff,'guild')['contributions'] if r['taskId']==task_id]
    assert len(rows)==1 and rows[0]['points']==12


def test_no_backfill_for_existing_completions(setup):
    staff,learner,task_id,published,_=setup
    finish_task(staff,learner,task_id,published)
    change(staff,'guild','saveRule',dict(taskId=task_id,points=10,enabled=True))
    assert not any(r['taskId']==task_id for r in snapshot(staff,'guild')['contributions'])


def test_disabled_rule_and_rejection_do_not_credit(setup):
    staff,learner,task_id,published,_=setup
    change(staff,'guild','saveRule',dict(taskId=task_id,points=10,enabled=False))
    finish_task(staff,learner,task_id,published)
    assert not any(r['taskId']==task_id for r in snapshot(staff,'guild')['contributions'])
