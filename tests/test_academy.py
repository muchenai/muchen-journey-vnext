"""AI Academy publishing crosses real admin/learner sessions and durable media storage."""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from starlette.requests import Request
from sqlalchemy import select

from journey_api.academy_models import AcademyCourse, AcademyLearningRecord, AcademyVideo
from journey_api.academy_routes import CHUNK_SIZE, MAX_VIDEO_SIZE, TAGS, video_response
from journey_api.auth import Actor
from journey_api.config import get_settings
from journey_api.db import SessionLocal, engine
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
from journey_api.models import ExternalIdentity, IdentitySession, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_models import ReviewAdminAccess
from test_exploration_review_access import administrator
from test_reviewer_workbench import client_for, create_linked_reviewer
from test_wp09_feishu_identity import assert_ok, create_role_user

OPS = '/api/v1/ops/academy'
ME = '/api/v1/me/academy'


@pytest.fixture(autouse=True)
def no_external_cover_io(monkeypatch):
    from journey_api import academy_covers
    monkeypatch.setattr(academy_covers, 'extract_link_cover', lambda _url: None)
    monkeypatch.setattr(academy_covers, 'extract_video_cover', lambda _path: None)


@pytest.fixture
def academy():
    staff = administrator(create_linked_reviewer('学院管理员'), ORGANIZATION_ID, 'admin')
    return staff, academy_learner()


def academy_learner():
    # Academy scenarios need a real learner session, not a submitted exploration
    # task. Review history cannot be deleted, so do not create unrelated pending
    # reviews that would leak into the shared review queue used by later suites.
    user_id = create_role_user(Role.LEARNER)
    settings = get_settings()
    token, csrf = uuid.uuid4().hex + uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
    with SessionLocal.begin() as session:
        session.add(IdentitySession(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
            user_id=user_id, role=Role.LEARNER,
            token_hash=credential_hash(settings.session_secret, 'session', token),
            csrf_token_hash=credential_hash(settings.session_secret, 'csrf', csrf),
            expires_at=datetime.now(UTC) + timedelta(minutes=30)))
    learner = client_for('academy-learner-' + str(user_id))
    learner.cookies.set(SESSION_COOKIE, token)
    learner.cookies.set(CSRF_COOKIE, csrf)
    return learner, csrf


def write(pair, method, path, data):
    return pair[0].request(method.upper(), path, json=data, headers={'X-CSRF-Token': pair[1]})


def new_course(staff, **overrides):
    payload = dict(id=str(uuid.uuid4()), type='link', title='AI 课程 ' + uuid.uuid4().hex[:8],
                   summary='可在不同浏览器学习的真实课程。', url='https://example.com/course',
                   tags=[TAGS[0], TAGS[2]], minutes=18)
    payload.update(overrides)
    return assert_ok(write(staff, 'post', OPS + '/courses', payload))


def upload(staff, content, name='真实课程.mp4'):
    started = assert_ok(write(staff, 'post', OPS + '/uploads', dict(fileName=name, size=len(content))))
    for index, offset in enumerate(range(0, len(content), started['chunkSize'])):
        response = staff[0].put(OPS + f'/uploads/{started["id"]}/chunks/{index}',
            content=content[offset:offset + started['chunkSize']], headers={'X-CSRF-Token': staff[1], 'Content-Type':'application/octet-stream'})
        assert_ok(response)
    return started


def published(learner):
    return assert_ok(learner[0].get(ME))['courses']


def test_real_course_publication_edit_visibility_and_revision(academy):
    staff, learner = academy
    course = new_course(staff)
    listed = next(c for c in published(learner) if c['id'] == course['id'])
    assert listed['title'] == course['title'] and listed['tags'] == [TAGS[0], TAGS[2]]
    assert listed['author']['name'] and not listed['demo']
    assert len(assert_ok(staff[0].get(OPS))['tags']) == 20
    url = OPS + '/courses/' + course['id']
    edited = assert_ok(write(staff, 'patch', url, dict(expected_revision=course['revision'], title='更新后的课程', tags=[TAGS[10]])))
    assert next(c for c in published(learner) if c['id'] == course['id'])['title'] == '更新后的课程'
    assert write(staff, 'patch', url, dict(expected_revision=course['revision'], title='旧页面编辑')).status_code == 409
    hidden = assert_ok(write(staff, 'post', url + '/visibility', dict(expected_revision=edited['revision'], visible=False)))
    assert not any(c['id'] == course['id'] for c in published(learner))
    assert learner[0].get(ME + '/courses/' + course['id']).status_code == 404
    restored = assert_ok(write(staff, 'post', url + '/visibility', dict(expected_revision=hidden['revision'], visible=True)))
    assert restored['visibility'] == 'published'
    assert any(c['id'] == course['id'] for c in published(learner))


def test_video_integrity_chunk_retry_and_authenticated_range_delivery(academy):
    staff, learner = academy
    content = b'\x00\x00\x00\x18ftypmp42' + b'x' * (CHUNK_SIZE+200)
    started = upload(staff, content)
    upload_path = OPS + '/uploads/' + started['id']
    assert write(staff, 'post', OPS + '/courses', dict(type='video', title='未完成', summary='未完成的上传不能发布', uploadId=started['id'])).status_code == 422
    # Retries of the exact same segment are idempotent; changed bytes are rejected.
    segment_path = upload_path + '/chunks/0'
    assert_ok(staff[0].put(segment_path, content=content[:CHUNK_SIZE], headers={'X-CSRF-Token':staff[1]}))
    assert staff[0].put(segment_path, content=b'z'*CHUNK_SIZE, headers={'X-CSRF-Token':staff[1]}).status_code == 409
    finished = assert_ok(write(staff, 'post', upload_path + '/complete', {}))
    assert finished['size'] == len(content)
    assert_ok(write(staff, 'post', upload_path + '/complete', {}))
    course = new_course(staff, type='video', url='', uploadId=started['id'])
    media = ME + '/courses/' + course['id'] + '/video'
    full = learner[0].get(media)
    assert full.status_code == 200 and full.content == content
    assert full.headers['content-type'] == 'video/mp4'
    partial = learner[0].get(media, headers={'Range':f'bytes={CHUNK_SIZE-4}-{CHUNK_SIZE+6}'})
    assert partial.status_code == 206 and partial.content == content[CHUNK_SIZE-4:CHUNK_SIZE+7]
    assert partial.headers['content-range'] == f'bytes {CHUNK_SIZE-4}-{CHUNK_SIZE+6}/{len(content)}'
    suffix = learner[0].get(media, headers={'Range':'bytes=-10'})
    assert suffix.status_code == 206 and suffix.content == content[-10:]
    assert learner[0].head(media).headers['content-length'] == str(len(content))
    assert learner[0].get(media, headers={'Range':'bytes=99999999-'}).status_code == 416
    assert learner[0].get(media, headers={'Range':'bytes=0-1,4-5'}).status_code == 416
    assert learner[0].get(media, headers={'Range':'bytes='+'9'*5000+'-'}).status_code == 416
    assert write(staff, 'delete', upload_path, {}).status_code == 409
    assert_ok(write(staff, 'post', OPS + '/courses/' + course['id'] + '/visibility',
                    dict(expected_revision=course['revision'], visible=False)))
    assert learner[0].get(media).status_code == 404
    assert staff[0].get(OPS + '/courses/' + course['id'] + '/video').content == content


def test_upload_validation_aborts_incomplete_or_disguised_media(academy):
    staff, learner = academy
    for size in [0, -1, MAX_VIDEO_SIZE+1, True]:
        assert write(staff, 'post', OPS + '/uploads', dict(fileName='test.mp4', size=size)).status_code == 422
    assert write(staff, 'post', OPS + '/uploads', dict(fileName='../test.mp4', size=12)).status_code == 422
    started = assert_ok(write(staff, 'post', OPS + '/uploads', dict(fileName='test.mp4',size=32)))
    path = OPS + '/uploads/' + started['id']
    assert write(staff, 'post', path + '/complete', {}).status_code == 422
    assert staff[0].put(path+'/chunks/0',content=b'a'*33,headers={'X-CSRF-Token':staff[1]}).status_code == 413
    assert staff[0].put(path+'/chunks/0',content=b'a'*31,headers={'X-CSRF-Token':staff[1]}).status_code == 422
    assert_ok(staff[0].put(path+'/chunks/0',content=b'<html>' + b'a'*26,headers={'X-CSRF-Token':staff[1]}))
    assert write(staff,'post',path+'/complete',{}).status_code == 422
    assert_ok(write(staff,'delete',path,{}))
    assert write(staff,'post',path+'/complete',{}).status_code == 404
    assert write(learner,'post',OPS+'/uploads',dict(fileName='test.mp4',size=12)).status_code == 403


def test_slow_video_consumer_does_not_hold_database_connection(academy):
    staff, _ = academy
    content = b'\x00\x00\x00\x18ftypmp42' + b'x'*(CHUNK_SIZE+20)
    started = upload(staff,content)
    assert_ok(write(staff,'post',OPS+'/uploads/'+started['id']+'/complete',{}))
    course = new_course(staff,type='video',url='',uploadId=started['id'])
    actor = Actor(uuid.UUID(course['author']['id']),ORGANIZATION_ID,frozenset({Role.REVIEWER}),'学院管理员')
    request = Request({'type':'http','method':'GET','path':'/','headers':[]})
    with SessionLocal() as session:
        response = video_response(session,actor,uuid.UUID(course['id']),request,public=False)
        baseline = engine.pool.checkedout()

        async def consume_slowly():
            iterator = response.body_iterator
            try:
                first = await anext(iterator)
                assert first == content[:CHUNK_SIZE]
                # The download has yielded and may wait indefinitely on a client.
                assert engine.pool.checkedout() == baseline
                second = await anext(iterator)
                assert first+second == content
                assert engine.pool.checkedout() == baseline
            finally:
                await iterator.aclose()

        asyncio.run(consume_slowly())


def test_share_review_rejection_resubmit_and_approval_publishes(academy):
    staff, learner = academy
    share = assert_ok(write(learner, 'post', ME + '/shares', dict(title='工作流经验',summary='展示人工核查方法',
        url='https://example.com/share',tags=[TAGS[3]],minutes=10)))
    share_path = ME + '/shares/' + share['id']
    review_path = OPS + '/shares/' + share['id'] + '/review'
    assert share['status'] == 'pending'
    assert not any(c['id'] == share['id'] for c in published(learner))
    assert any(s['id'] == share['id'] for s in assert_ok(staff[0].get(OPS))['shares'])
    assert write(staff,'post',review_path,dict(expected_revision=1,decision='rejected',reason=' ')).status_code == 422
    rejected = assert_ok(write(staff,'post',review_path,dict(expected_revision=1,decision='rejected',reason='补充核查来源')))
    own = next(s for s in assert_ok(learner[0].get(ME))['shares'] if s['id'] == share['id'])
    assert own['status'] == 'rejected' and own['reason'] == '补充核查来源'
    revised = assert_ok(write(learner,'patch',share_path,dict(expected_revision=rejected['revision'],summary='已补充来源与核验步骤')))
    assert revised['status'] == 'pending' and revised['reason'] == ''
    approved = assert_ok(write(staff,'post',review_path,dict(expected_revision=revised['revision'],decision='approved')))
    assert approved['status'] == 'approved'
    public = next(c for c in published(learner) if c['id'] == share['id'])
    assert public['type'] == 'share' and public['summary'] == '已补充来源与核验步骤'
    assert public['tags'] == [TAGS[3]]  # Older clients omit review tags and retain the author's selection.
    assert write(staff,'post',review_path,dict(expected_revision=revised['revision'],decision='approved')).status_code == 409
    assert write(learner,'patch',share_path,dict(expected_revision=approved['revision'],title='未经复核的修改')).status_code == 409


def test_share_approval_tags_are_published_atomically_for_learner_filtering(academy):
    staff, learner = academy
    share = assert_ok(write(learner, 'post', ME + '/shares', dict(title='员工 AI 实践',
        summary='由管理员在发布时归类', url='https://example.com/tagged-share', tags=[TAGS[0]])))
    path = OPS + '/shares/' + share['id'] + '/review'
    command = dict(expected_revision=share['revision'], decision='approved')
    for invalid in [['不存在的标签'], [TAGS[0]] * 21, [123], 'AI 入门']:
        assert write(staff, 'post', path, {**command, 'tags': invalid}).status_code == 422
        unchanged = next(s for s in assert_ok(staff[0].get(OPS))['shares'] if s['id'] == share['id'])
        assert unchanged['status'] == 'pending' and unchanged['visibility'] == 'unpublished'
        assert unchanged['revision'] == share['revision'] and unchanged['tags'] == [TAGS[0]]
        assert unchanged['reviewedAt'] is None and unchanged['reviewedBy'] is None
        assert not any(c['id'] == share['id'] for c in published(learner))
    selected = [TAGS[10], TAGS[2], TAGS[10]]
    approved = assert_ok(write(staff, 'post', path, {**command, 'tags': selected}))
    assert approved['status'] == 'approved' and approved['revision'] == share['revision'] + 1
    assert approved['tags'] == [TAGS[2], TAGS[10]]
    courses = published(learner)
    assert share['id'] in {c['id'] for c in courses if TAGS[10] in c['tags']}
    assert share['id'] not in {c['id'] for c in courses if TAGS[0] in c['tags']}
    own = next(s for s in assert_ok(learner[0].get(ME))['shares'] if s['id'] == share['id'])
    assert own['tags'] == approved['tags']
    # Retrying a processed review cannot change the published labels or revision.
    assert write(staff, 'post', path, {**command, 'tags': [TAGS[5]]}).status_code == 409
    assert assert_ok(learner[0].get(ME + '/courses/' + share['id']))['tags'] == approved['tags']


def test_review_tags_only_replace_content_on_approval_and_can_be_cleared(academy):
    staff, learner = academy
    share = assert_ok(write(learner, 'post', ME + '/shares', dict(title='待补充的实践',
        summary='驳回不修改课程标签', url='https://example.com/review-tags', tags=[TAGS[4]])))
    path = OPS + '/shares/' + share['id'] + '/review'
    rejected = assert_ok(write(staff, 'post', path, dict(expected_revision=share['revision'],
        decision='rejected', reason='请补充操作步骤', tags=[TAGS[8]])))
    assert rejected['tags'] == [TAGS[4]] and rejected['status'] == 'rejected'
    revised = assert_ok(write(learner, 'patch', ME + '/shares/' + share['id'],
        dict(expected_revision=rejected['revision'], summary='已补充操作步骤')))
    approved = assert_ok(write(staff, 'post', path,
        dict(expected_revision=revised['revision'], decision='approved', tags=[])))
    assert approved['tags'] == []
    assert assert_ok(learner[0].get(ME + '/courses/' + share['id']))['tags'] == []


def test_favorites_and_learning_are_durable_and_per_learner(academy):
    staff, learner = academy
    course = new_course(staff)
    base = ME + '/courses/' + course['id']
    assert_ok(write(learner,'post',base+'/favorite',dict(saved=True)))
    assert_ok(write(learner,'post',base+'/favorite',dict(saved=True)))
    record = assert_ok(write(learner,'post',base+'/progress',dict(completed=True)))
    assert record['favorite'] is True and record['completed'] is True and record['progress'] == 100
    record = assert_ok(write(learner,'post',base+'/progress',dict(seconds=10,duration=100)))
    assert record['completed'] is True and record['progress'] == 100
    other = academy_learner()
    untouched = next(c for c in published(other) if c['id'] == course['id'])
    assert untouched['favorite'] is False and untouched['completed'] is False and untouched['progress'] == 0
    with SessionLocal() as session:
        assert session.scalar(select(AcademyLearningRecord).where(AcademyLearningRecord.course_id == uuid.UUID(course['id']))).favorite is True
    assert_ok(write(learner,'post',base+'/favorite',dict(saved=False)))
    assert next(c for c in published(learner) if c['id'] == course['id'])['favorite'] is False
    assert write(learner,'post',base+'/progress',dict(seconds=-1,duration=100)).status_code == 422
    assert write(learner,'post',base+'/progress',dict(seconds=101,duration=100)).status_code == 422


def test_video_checkpoint_resume_and_completion_threshold(academy):
    staff, learner = academy
    started = upload(staff,b'\x00\x00\x00\x18ftypmp42' + b'a'*32)
    assert_ok(write(staff,'post',OPS+'/uploads/'+started['id']+'/complete',{}))
    course = new_course(staff,type='video',url='',uploadId=started['id'])
    progress_path = ME + '/courses/' + course['id'] + '/progress'
    incomplete = assert_ok(write(learner,'post',progress_path,dict(seconds=20,duration=100,completed=True)))
    assert incomplete['progress'] == 20 and incomplete['completed'] is False and incomplete['seconds'] == 20
    revisited = assert_ok(write(learner,'post',progress_path,dict(seconds=10,duration=100)))
    assert revisited['progress'] == 20 and revisited['seconds'] == 10
    complete = assert_ok(write(learner,'post',progress_path,dict(seconds=90,duration=100)))
    assert complete['completed'] is True and complete['progress'] == 100
    assert_ok(write(learner,'post',ME+'/courses/'+course['id']+'/favorite',dict(saved=True)))
    replacement = upload(staff,b'\x00\x00\x00\x18ftypmp42' + b'b'*40)
    assert_ok(write(staff,'post',OPS+'/uploads/'+replacement['id']+'/complete',{}))
    replaced = assert_ok(write(staff,'patch',OPS+'/courses/'+course['id'],dict(
        expected_revision=course['revision'],uploadId=replacement['id'])))
    reset = assert_ok(learner[0].get(ME+'/courses/'+course['id']))
    assert reset['completed'] is False and reset['progress'] == 0 and reset['favorite'] is True
    assert write(learner,'post',progress_path,dict(seconds=99,duration=100,expected_revision=course['revision'])).status_code == 409
    assert_ok(write(learner,'post',progress_path,dict(seconds=20,duration=100,expected_revision=replaced['revision'])))


def test_permissions_csrf_own_shares_and_cross_organization(academy, monkeypatch):
    staff, learner = academy
    course = new_course(staff)
    assert learner[0].get(OPS).status_code == 403
    assert learner[0].post(ME+'/shares',json=dict(title='x',summary='x',url='https://example.com')).status_code == 403
    assert staff[0].get(ME).status_code in (401,403)
    assert staff[0].post(OPS+'/courses',json=dict(type='link',title='x',summary='x',url='https://example.com')).status_code == 403
    share = assert_ok(write(learner,'post',ME+'/shares',dict(title='我的分享',summary='仅本人可见',url='https://example.com')))
    other_learner = academy_learner()
    assert not any(s['id'] == share['id'] for s in assert_ok(other_learner[0].get(ME))['shares'])
    assert write(other_learner,'patch',ME+'/shares/'+share['id'],dict(expected_revision=share['revision'],title='越权')).status_code == 404
    org, user = uuid.uuid4(), uuid.uuid4()
    with SessionLocal.begin() as s:
        s.add(Organization(id=org,name='学院隔离组织'));s.flush()
        s.add(User(id=user,organization_id=org,display_name='学院隔离管理员',status=UserStatus.ACTIVE));s.flush()
        s.add(RoleAssignment(id=uuid.uuid4(),organization_id=org,user_id=user,role=Role.REVIEWER))
        s.add(ExternalIdentity(id=uuid.uuid4(),organization_id=org,user_id=user,provider='FEISHU',subject=uuid.uuid4().hex,verified_at=datetime.now(UTC),revision=1))
    import test_reviewer_workbench
    with monkeypatch.context() as patch:
        patch.setattr(test_reviewer_workbench,'ORGANIZATION_ID',org)
        other = administrator(user,org,'admin')
    assert not any(c['id'] == course['id'] for c in assert_ok(other[0].get(OPS))['courses'])
    assert write(other,'patch',OPS+'/courses/'+course['id'],dict(expected_revision=course['revision'],title='越权')).status_code == 404
    pending = assert_ok(write(staff,'post',OPS+'/uploads',dict(fileName='private.mp4',size=12)))
    assert write(other,'post',OPS+'/uploads/'+pending['id']+'/complete',{}).status_code == 404


def test_create_retry_is_idempotent_and_invalid_metadata_cannot_publish(academy):
    staff, learner = academy
    payload = dict(id=str(uuid.uuid4()),type='link',title='重试幂等',summary='稳定请求编号',url='https://example.com',tags=[TAGS[0]])
    first = assert_ok(write(staff,'post',OPS+'/courses',payload))
    second = assert_ok(write(staff,'post',OPS+'/courses',payload))
    assert first['id'] == second['id'] and second['revision'] == 1
    assert write(staff,'post',OPS+'/courses',{**payload,'title':'冲突内容'}).status_code == 409
    concurrent_payload = {**payload, 'id':str(uuid.uuid4()), 'title':'并发重试'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(pool.map(lambda _: write(staff,'post',OPS+'/courses',concurrent_payload),range(2)))
    assert [r.status_code for r in concurrent] == [200,200]
    assert len({assert_ok(r)['id'] for r in concurrent}) == 1
    for invalid in [dict(title=' '),dict(tags=['不存在']),dict(url='javascript:alert(1)'),dict(url='https://user:password@example.com'),dict(minutes=0)]:
        assert write(staff,'post',OPS+'/courses',{**payload,'id':str(uuid.uuid4()),**invalid}).status_code == 422
    share_payload = dict(id=str(uuid.uuid4()),title='分享重试',summary='相同请求只创建一次',url='https://example.com')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(learner,'post',ME+'/shares',share_payload),range(2)))
    assert [r.status_code for r in results] == [200,200]
    assert len({assert_ok(r)['id'] for r in results}) == 1


def test_dual_role_user_must_use_staff_entry_for_academy_management(academy):
    staff, learner = academy
    course = new_course(staff)
    share = assert_ok(write(learner,'post',ME+'/shares',dict(title='双身份学员',summary='学员入口保持隔离',url='https://example.com')))
    learner_id = uuid.UUID(share['author']['id'])
    with SessionLocal.begin() as session:
        session.add(RoleAssignment(id=uuid.uuid4(),organization_id=ORGANIZATION_ID,user_id=learner_id,role=Role.REVIEWER))
        session.add(ReviewAdminAccess(user_id=learner_id,organization_id=ORGANIZATION_ID,
            access_role='admin',level='初级',domain='产品开发',granted_by=uuid.UUID(course['author']['id'])))
    assert learner[0].get(OPS).status_code == 403
    assert learner[0].get(OPS,headers={'X-Journey-Session-Scope':'learner'}).status_code == 403
    assert write(learner,'post',OPS+'/courses',dict(type='link',title='禁止跨入口发布',summary='不能使用学员会话管理',url='https://example.com')).status_code == 403
    assert learner[0].get(OPS+'/courses/'+course['id']+'/video').status_code == 403
    assert any(c['id'] == course['id'] for c in published(learner))
