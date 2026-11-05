"""Generated images retain course authorization, revision semantics and durable fallback."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from starlette.requests import Request

from journey_api import academy_covers as covers
from journey_api.academy_models import AcademyCourse, AcademyCourseCover
from journey_api.academy_routes import cover_response
from journey_api.auth import Actor
from journey_api.db import SessionLocal, engine
from journey_api.errors import ApiError
from journey_api.main import app
from journey_api.models import Role
from test_academy import academy, new_course, published, upload, write, ME, OPS
from test_wp09_feishu_identity import assert_ok

JPEG = b'\xff\xd8\xff' + b'cached-decoder-output' + b'\xff\xd9'


@pytest.fixture(autouse=True)
def generated(monkeypatch):
    calls = []
    def extract(url):
        calls.append(url)
        return JPEG
    monkeypatch.setattr(covers, 'extract_link_cover', extract)
    monkeypatch.setattr(covers, 'extract_video_cover', lambda _path: JPEG)
    return calls


def learner_cover(course):
    return course['coverUrl'].replace('/ops/', '/me/')


def clear_cover(course):
    with SessionLocal.begin() as session:
        session.execute(delete(AcademyCourseCover).where(AcademyCourseCover.course_id == uuid.UUID(course['id'])))


def test_busy_decoder_releases_claim_without_caching_a_failure(academy, monkeypatch):
    staff, learner = academy
    course = new_course(staff)
    clear_cover(course)
    def busy(_url):
        raise covers.CoverBusy('busy')
    monkeypatch.setattr(covers, 'extract_link_cover', busy)
    assert learner[0].get(learner_cover(course)).status_code == 425
    with SessionLocal() as session:
        cached = session.get(AcademyCourseCover, uuid.UUID(course['id']))
        assert cached.status == 'new' and cached.claim_id is None
    monkeypatch.setattr(covers, 'extract_link_cover', lambda _url: JPEG)
    assert learner[0].get(learner_cover(course)).content == JPEG


def test_published_cover_persists_revalidates_and_head_never_sends_body(academy, generated):
    staff, learner = academy
    course = new_course(staff)
    assert len(generated) == 1
    listed = next(item for item in published(learner) if item['id'] == course['id'])
    assert listed['coverUrl'] == learner_cover(course)
    assert len(listed['coverUrl'].split('source=')[1]) == 64
    response = learner[0].get(listed['coverUrl'])
    assert response.status_code == 200 and response.content == JPEG
    assert response.headers['content-type'] == 'image/jpeg'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-length'] == str(len(JPEG))
    head = learner[0].head(listed['coverUrl'])
    assert head.status_code == 200 and not head.content
    assert head.headers['content-length'] == str(len(JPEG))
    unchanged = learner[0].get(listed['coverUrl'], headers={'If-None-Match': response.headers['etag']})
    assert unchanged.status_code == 304 and not unchanged.content
    assert len(generated) == 1
    with SessionLocal() as session:
        cached = session.get(AcademyCourseCover, uuid.UUID(course['id']))
        assert cached.status == 'ready' and cached.data == JPEG and cached.claim_id is None


def test_metadata_edits_keep_cover_but_url_changes_replace_source_and_fail_cleanly(academy, generated, monkeypatch):
    staff, learner = academy
    course = new_course(staff)
    path = OPS + '/courses/' + course['id']
    renamed = assert_ok(write(staff, 'patch', path, {'expected_revision': course['revision'], 'title': '改名称不重新取图'}))
    assert renamed['coverUrl'] == course['coverUrl'] and len(generated) == 1
    monkeypatch.setattr(covers, 'extract_link_cover', lambda _url: None)
    edited = assert_ok(write(staff, 'patch', path, {'expected_revision': renamed['revision'], 'url': 'https://example.com/no-image'}))
    assert edited['coverUrl'] != course['coverUrl']
    assert learner[0].get(learner_cover(course)).status_code == 404
    assert learner[0].get(learner_cover(edited)).status_code == 404
    with SessionLocal() as session:
        cached = session.get(AcademyCourseCover, uuid.UUID(course['id']))
        assert cached.status == 'failed' and cached.data is None


def test_unpublished_cross_organization_and_wrong_entry_cannot_read_cached_cover(academy):
    staff, learner = academy
    course = new_course(staff)
    uri = learner_cover(course)
    assert TestClient(app, base_url='http://localhost').get(uri).status_code == 401
    assert learner[0].get(course['coverUrl']).status_code == 403
    with SessionLocal() as session:
        foreign = Actor(uuid.uuid4(), uuid.uuid4(), frozenset({Role.LEARNER}), '另一组织')
        request = Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': [], 'query_string': b''})
        with pytest.raises(ApiError) as error:
            cover_response(session, foreign, uuid.UUID(course['id']), request, public=True)
        assert error.value.status_code == 404
    etag = learner[0].get(uri).headers['etag']
    assert_ok(write(staff, 'post', OPS + '/courses/' + course['id'] + '/visibility', {'expected_revision': course['revision'], 'visible': False}))
    assert learner[0].get(uri, headers={'If-None-Match': etag}).status_code == 404
    assert learner[0].head(uri).status_code == 404
    assert staff[0].get(course['coverUrl']).content == JPEG


def test_failure_is_negative_cached_without_breaking_publication_and_can_retry(academy, monkeypatch):
    staff, learner = academy
    attempts = []
    def unavailable(url):
        attempts.append(url)
        raise RuntimeError('provider is unavailable')
    monkeypatch.setattr(covers, 'extract_link_cover', unavailable)
    course = new_course(staff)
    assert len(attempts) == 1
    uri = learner_cover(course)
    assert learner[0].get(uri).status_code == 404
    assert learner[0].get(uri).status_code == 404
    assert len(attempts) == 1
    with SessionLocal.begin() as session:
        cached = session.get(AcademyCourseCover, uuid.UUID(course['id']))
        cached.attempted_at = datetime.now(UTC) - timedelta(hours=2)
    monkeypatch.setattr(covers, 'extract_link_cover', lambda _url: JPEG)
    assert learner[0].get(uri).content == JPEG


def test_existing_course_head_does_not_generate_get_backfills_without_request_db_lock(academy, generated, monkeypatch):
    staff, learner = academy
    course = new_course(staff)
    clear_cover(course)
    baseline = engine.pool.checkedout()
    def extract(_url):
        assert engine.pool.checkedout() == baseline
        return JPEG
    monkeypatch.setattr(covers, 'extract_link_cover', extract)
    assert learner[0].head(learner_cover(course)).status_code == 404
    with SessionLocal() as session:
        assert session.get(AcademyCourseCover, uuid.UUID(course['id'])) is None
    assert learner[0].get(learner_cover(course)).content == JPEG


def test_pending_claim_is_retryable_and_only_one_concurrent_decoder_runs(academy, monkeypatch):
    staff, learner = academy
    course = new_course(staff)
    clear_cover(course)
    started, finish = Event(), Event()
    attempts = []
    def slow(url):
        attempts.append(url)
        started.set()
        assert finish.wait(10)
        return JPEG
    monkeypatch.setattr(covers, 'extract_link_cover', slow)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(covers.ensure_course_cover, uuid.UUID(course['id']))
        assert started.wait(5)
        try:
            retry = learner[0].get(learner_cover(course))
            assert retry.status_code == 425 and retry.headers['retry-after'] == '2'
            second = executor.submit(covers.ensure_course_cover, uuid.UUID(course['id']))
            second.result(timeout=5)
            assert len(attempts) == 1
        finally:
            finish.set()
        first.result(timeout=5)
    assert learner[0].get(learner_cover(course)).content == JPEG


def test_expired_claim_and_changed_source_cannot_be_overwritten_by_old_generator(academy):
    staff, learner = academy
    course = new_course(staff)
    clear_cover(course)
    course_id = uuid.UUID(course['id'])
    original_hash, original_token, _ = covers._claim(course_id, None)
    with SessionLocal.begin() as session:
        session.get(AcademyCourseCover, course_id).attempted_at = datetime.now(UTC) - timedelta(minutes=4)
    new_hash, new_token, _ = covers._claim(course_id, original_hash)
    assert new_token != original_token
    covers._complete(course_id, new_hash, new_token, JPEG)
    covers._complete(course_id, original_hash, original_token, b'old-data')
    assert covers.cached_course_cover(course_id, new_hash)[0] == JPEG
    with SessionLocal.begin() as session:
        row = session.get(AcademyCourse, course_id)
        row.content = {**row.content, 'url': 'https://example.com/replacement'}
    assert covers._claim(course_id, original_hash) is None
    changed_hash, changed_token, _ = covers._claim(course_id, None)
    assert changed_hash != original_hash
    covers._complete(course_id, original_hash, original_token, JPEG)
    assert covers.cached_course_cover(course_id, changed_hash) is None
    covers._complete(course_id, changed_hash, changed_token, JPEG + b'new')
    assert learner[0].get(learner_cover(course)).status_code == 404


def test_uploaded_video_is_streamed_to_temporary_file_and_decoded_after_db_release(academy, monkeypatch):
    staff, learner = academy
    content = b'\x00\x00\x00\x18ftypmp42' + b'x' * 600000
    started = upload(staff, content)
    assert_ok(write(staff, 'post', OPS + '/uploads/' + started['id'] + '/complete', {}))
    paths = []
    baseline = engine.pool.checkedout()
    def extract(path):
        paths.append(path)
        assert path.read_bytes() == content
        assert engine.pool.checkedout() == baseline
        return JPEG
    monkeypatch.setattr(covers, 'extract_video_cover', extract)
    course = new_course(staff, type='video', url='', uploadId=started['id'])
    assert len(paths) == 1 and not paths[0].exists()
    assert learner[0].get(learner_cover(course)).content == JPEG


def test_employee_share_only_generates_after_approval(academy, generated):
    staff, learner = academy
    share = assert_ok(write(learner, 'post', ME + '/shares', dict(title='员工视频分享', summary='审核后显示封面', url='https://example.com/share')))
    assert generated == []
    assert learner[0].get(share['coverUrl']).status_code == 404
    approved = assert_ok(write(staff, 'post', OPS + '/shares/' + share['id'] + '/review', dict(expected_revision=share['revision'], decision='approved')))
    assert len(generated) == 1
    assert learner[0].get(learner_cover(approved)).content == JPEG
