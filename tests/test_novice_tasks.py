"""Published tasks use real learner assignments, without stealing exploration state."""
import base64
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.models import Assignment, Enrollment, Review, SubmissionVersion, Submission
from journey_api.review_admin_models import PublishedTaskContent
from test_reviewer_workbench import create_submission, create_linked_reviewer
from test_exploration_review_access import administrator
from test_review_admin import content
from test_wp09_feishu_identity import assert_ok


def post(pair, path, body):
    client, csrf = pair
    return client.post('/api/v1/' + path, json=body,
        headers={'X-CSRF-Token':csrf, 'Idempotency-Key':str(uuid.uuid4())})


@pytest.fixture
def setup():
    author = create_linked_reviewer('新手村发布人')
    staff = administrator(author, ORGANIZATION_ID, 'super_admin')
    task_id = str(uuid.uuid4())
    data = content()
    data.update(domain='项目管理', badges=[{'id':'project','weight':100}])
    file_bytes = b'local practice material'
    data['materials'].append({'id':'file','type':'file','name':'学习资料.txt', 'mime':'text/plain',
        'size':len(file_bytes),'url':'data:text/plain;base64,'+base64.b64encode(file_bytes).decode()})
    png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
    data['materials'].append({'id':'image','type':'image','name':'学习图片.png','mime':'image/png',
        'size':len(base64.b64decode(png)),'url':'data:image/png;base64,'+png})
    draft = assert_ok(staff[0].put(f'/api/v1/review-admin/tasks/{task_id}',
        headers={'X-CSRF-Token':staff[1]}, json={'id':task_id,'expected_revision':0,'content':data}))
    published = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish',
        {'expected_revision':draft['revision'],'reviewed_by':str(author),'verified_material_urls':['https://example.com/material']}))
    flow = create_submission('novice-'+uuid.uuid4().hex)
    learner = flow['learner'], flow['csrf']
    return staff, learner, task_id, published, data


def read(pair, task_id):
    return assert_ok(pair[0].get(f'/api/v1/me/novice/tasks/{task_id}'))


def claim(pair, task_id, version_id):
    return assert_ok(post(pair, f'me/novice/tasks/{task_id}/claim', {'version_id':version_id}))


def test_mapping_materials_repeat_claim_and_exploration_isolation(setup):
    staff, learner, task_id, published, data = setup
    old_current = assert_ok(learner[0].get('/api/v1/me/current-action'))
    old_enrollments = assert_ok(learner[0].get('/api/v1/me/enrollments'))
    listing = assert_ok(learner[0].get('/api/v1/me/novice/tasks'))
    assert len(listing['directions']) == 8 and 'AI 能力' in listing['directions']
    task = next(t for t in listing['items'] if t['id'] == task_id)
    assert task['title'] == data['title'] and task['category'] == '项目管理'
    assert task['badges'] == [['项目管理',100]] and task['materials'][0]['url'] == data['materials'][0]['url']
    assert 'base64' not in str(task)
    material = assert_ok(learner[0].get(f'/api/v1/me/novice/tasks/{task_id}/materials/1'))
    assert base64.b64decode(material['data']) == b'local practice material'
    assert len(task['materials']) == 3
    image = assert_ok(learner[0].get(f'/api/v1/me/novice/tasks/{task_id}/materials/2'))
    assert image['mime'] == 'image/png' and image['name'] == '学习图片.png'
    assert image['data'] == data['materials'][2]['url'].split(',',1)[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _:claim(learner,task_id,published['versionId']), range(2)))
    assert claims[0]['assignmentId'] == claims[1]['assignmentId']
    assert claims[0]['status'] == 'active'
    assert assert_ok(learner[0].get('/api/v1/me/current-action')) == old_current
    assert assert_ok(learner[0].get('/api/v1/me/enrollments')) == old_enrollments
    other = create_submission('novice-other-'+uuid.uuid4().hex)
    other_pair = other['learner'], other['csrf']
    assert read(other_pair, task_id)['status'] == 'available'
    other_claim = claim(other_pair, task_id, published['versionId'])
    assert other_claim['assignmentId'] != claims[0]['assignmentId']
    assert other_pair[0].get('/api/v1/me/assignments/'+claims[0]['assignmentId']).status_code == 404


def test_draft_return_resubmit_approval_and_author_permissions(setup):
    staff, learner, task_id, published, _ = setup
    task = claim(learner, task_id, published['versionId'])
    assignment = task['assignmentId']
    text = '我完成了材料学习与项目分析，整理了问题背景、验证依据和改进方案，并列出后续执行步骤与验收标准。'
    assert_ok(learner[0].put(f'/api/v1/me/assignments/{assignment}/draft',
        headers={'X-CSRF-Token':learner[1], 'Idempotency-Key':str(uuid.uuid4())},
        json={'expected_revision':task['revision'],'body':text}))
    assert read(learner, task_id)['answer'] == text
    for decision in ['REQUEST_REVISION','APPROVE']:
        task = read(learner, task_id)
        submitted = assert_ok(post(learner, f'me/assignments/{assignment}/submissions',
            {'expected_revision':task['revision'],'body':text}))
        assert read(learner, task_id)['status'] == 'pending'
        with SessionLocal() as session:
            review_id = session.scalar(select(Review.id).where(Review.submission_version_id == uuid.UUID(submitted['submission_version_id'])))
        other = administrator(create_linked_reviewer('无关发布人'), ORGANIZATION_ID,'admin')
        assert other[0].get(f'/api/v1/review-admin/reviews/{review_id}').status_code == 404
        lease = assert_ok(post(staff,f'review-admin/reviews/{review_id}/claim',{'action':'acquire','expected_revision':1}))
        assert_ok(post(staff,f'review-admin/reviews/{review_id}/decision',{
            'decision':decision,'expected_revision':lease['revision'],'claim_token':lease['token'],
            'feedback':'请补充验收依据' if decision == 'REQUEST_REVISION' else '',
            'reasons':['依据或论证不足'] if decision == 'REQUEST_REVISION' else []}))
        actual = read(learner, task_id)
        assert actual['status'] == ('returned' if decision == 'REQUEST_REVISION' else 'completed')
        assert actual['feedback']['text']
    with SessionLocal() as session:
        assert session.scalar(select(func.count(SubmissionVersion.id)).join(Submission).where(Submission.assignment_id == uuid.UUID(assignment))) == 2
    assert post(learner, f'me/assignments/{assignment}/submissions',
        {'expected_revision':actual['revision'],'body':text}).status_code in {404,409}


def test_unpublished_archive_and_fixed_version(setup):
    staff, learner, task_id, published, data = setup
    task = claim(learner, task_id, published['versionId'])
    other = create_submission('novice-unclaimed-'+uuid.uuid4().hex)
    other_pair = other['learner'],other['csrf']
    assert_ok(post(staff,f'review-admin/tasks/{task_id}/archive',{'expected_revision':published['revision'],'archived':True}))
    assert post(other_pair,f'me/novice/tasks/{task_id}/claim',{'version_id':published['versionId']}).status_code == 404
    assert other_pair[0].get(f'/api/v1/me/novice/tasks/{task_id}/materials/1').status_code == 404
    assert read(learner,task_id)['assignmentId'] == task['assignmentId']
    changed = {**data,'title':'修改后的新版任务标题'}
    saved = assert_ok(staff[0].put(f'/api/v1/review-admin/tasks/{task_id}',
        headers={'X-CSRF-Token':staff[1]},json={'id':task_id,'expected_revision':published['revision']+1,'content':changed}))
    assert other_pair[0].get(f'/api/v1/me/novice/tasks/{task_id}').status_code == 404
    assert read(learner,task_id)['title'] == data['title']
    fresh = assert_ok(post(staff,f'review-admin/tasks/{task_id}/publish',{'expected_revision':saved['revision'],
        'reviewed_by':published['authorId'],'verified_material_urls':['https://example.com/material']}))
    assert read(other_pair,task_id)['title'] == changed['title']
    assert read(learner,task_id)['versionId'] == published['versionId']
    assert post(other_pair,f'me/novice/tasks/{task_id}/claim',{'version_id':published['versionId']}).status_code == 409
    assert claim(other_pair,task_id,fresh['versionId'])['title'] == changed['title']


def test_saving_update_and_creating_another_task_preserves_live_catalog(setup):
    staff, learner, task_id, published, data = setup
    claimed = claim(learner, task_id, published['versionId'])
    other = create_submission('novice-draft-visibility-'+uuid.uuid4().hex)
    other_pair = other['learner'], other['csrf']
    changed = {**data, 'title':'另一个方向的新标题', 'domain':'数据交付'}
    saved = assert_ok(staff[0].put(f'/api/v1/review-admin/tasks/{task_id}',
        headers={'X-CSRF-Token':staff[1]}, json={'id':task_id,'expected_revision':published['revision'],'content':changed}))
    assert saved['status'] == 'published'
    # Draft changes do not leak to learners, and the live task stays discoverable.
    before = read(other_pair, task_id)
    assert before['title'] == data['title'] and before['category'] == data['domain']
    catalog = assert_ok(other_pair[0].get('/api/v1/me/novice/tasks'))['items']
    assert task_id in {t['id'] for t in catalog}
    assert before['versionId'] == published['versionId']
    fresh = assert_ok(post(staff, f'review-admin/tasks/{task_id}/publish',
        {'expected_revision':saved['revision'],'reviewed_by':published['authorId'],
         'verified_material_urls':['https://example.com/material']}))
    assert read(other_pair,task_id)['category'] == '数据交付'
    assert read(learner,task_id)['versionId'] == claimed['versionId']
    # Copy/new task gets its own ID, can coexist with the updated original, and starts unpublished.
    new_id = str(uuid.uuid4())
    copied = assert_ok(staff[0].put(f'/api/v1/review-admin/tasks/{new_id}',
        headers={'X-CSRF-Token':staff[1]}, json={'id':new_id,'expected_revision':0,'content':changed}))
    assert copied['status']=='draft'
    assert other_pair[0].get(f'/api/v1/me/novice/tasks/{new_id}').status_code==404
    assert read(other_pair,task_id)['versionId']==fresh['versionId']
    assert_ok(post(staff,f'review-admin/tasks/{new_id}/publish',{'expected_revision':copied['revision'],
        'reviewed_by':published['authorId'],'verified_material_urls':['https://example.com/material']}))
    items=assert_ok(other_pair[0].get('/api/v1/me/novice/tasks'))['items']
    assert {task_id,new_id}<={item['id'] for item in items}
