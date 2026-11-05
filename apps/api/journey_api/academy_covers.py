"""Durable, best-effort academy covers with short database claims and source invalidation."""
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from journey_api.academy_cover_extract import CoverBusy, extract_link_cover, extract_video_cover
from journey_api.academy_models import AcademyCourse, AcademyCourseCover, AcademyVideo, AcademyVideoChunk
from journey_api.db import SessionLocal

logger = logging.getLogger(__name__)
FAILED_RETRY_AFTER = timedelta(hours=1)
CLAIM_LEASE = timedelta(minutes=3)
MAX_COVER_SIZE = 1024 * 1024
MAX_SOURCE_VIDEO_SIZE = 500 * 1024 * 1024


@dataclass(frozen=True)
class CoverSource:
    kind: str
    video_id: uuid.UUID | None
    organization_id: uuid.UUID
    url: str


def source_fingerprint(course):
    source = str(course.video_id or '') if course.kind == 'video' else course.content.get('url', '')
    # Version the extraction format independently of editable title/tag metadata.
    payload = json.dumps(['academy-cover-v1', course.kind, source], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def cached_course_cover(course_id, source_hash):
    with SessionLocal() as session:
        cached = session.get(AcademyCourseCover, course_id)
        if cached and cached.source_hash == source_hash and cached.status == 'ready' and cached.data and cached.sha256:
            return bytes(cached.data), cached.sha256
    return None


def course_cover_processing(course_id, source_hash):
    with SessionLocal() as session:
        cached = session.get(AcademyCourseCover, course_id)
        return bool(cached and cached.source_hash == source_hash and cached.status in ('new', 'processing')
                    and cached.attempted_at > datetime.now(UTC) - CLAIM_LEASE)


def _claim(course_id, expected_source):
    moment = datetime.now(UTC)
    with SessionLocal() as session:
        course = session.get(AcademyCourse, course_id)
        if not course:
            return None
        source_hash = source_fingerprint(course)
        if expected_source is not None and source_hash != expected_source:
            return None
        session.execute(insert(AcademyCourseCover).values(course_id=course_id, source_hash=source_hash,
            status='new', attempted_at=moment, updated_at=moment).on_conflict_do_nothing())
        cached = session.scalar(select(AcademyCourseCover).where(AcademyCourseCover.course_id == course_id).with_for_update())
        if cached.source_hash == source_hash:
            if cached.status == 'ready' and cached.data and cached.sha256:
                return None
            if cached.status == 'failed' and cached.attempted_at > moment - FAILED_RETRY_AFTER:
                return None
            if cached.status == 'processing' and cached.attempted_at > moment - CLAIM_LEASE:
                return None
        claim_id = uuid.uuid4()
        cached.source_hash = source_hash
        cached.status = 'processing'
        cached.claim_id = claim_id
        cached.data = None
        cached.sha256 = None
        cached.attempted_at = moment
        cached.updated_at = moment
        source = CoverSource(course.kind, course.video_id, course.organization_id, course.content.get('url', ''))
        session.commit()
    return source_hash, claim_id, source


def _video_cover(source):
    if not source.video_id:
        return None
    with TemporaryDirectory(prefix='academy-cover-') as temporary:
        path = Path(temporary) / 'source.media'
        with SessionLocal() as session:
            video = session.get(AcademyVideo, source.video_id)
            if (not video or not video.complete or video.organization_id != source.organization_id
                    or video.size > MAX_SOURCE_VIDEO_SIZE):
                return None
            total = 0
            expected_position = 0
            with path.open('wb') as output:
                for position, data in session.execute(select(AcademyVideoChunk.position, AcademyVideoChunk.data)
                        .where(AcademyVideoChunk.video_id == video.id).order_by(AcademyVideoChunk.position)
                        .execution_options(yield_per=1)):
                    total += len(data)
                    if position != expected_position or total > video.size:
                        return None
                    output.write(data)
                    expected_position += 1
            if total != video.size:
                return None
        # Decoder runs after the chunk read session has released its connection.
        return extract_video_cover(path)


def _complete(course_id, source_hash, claim_id, data, *, deferred=False):
    with SessionLocal() as session:
        cached = session.scalar(select(AcademyCourseCover).where(AcademyCourseCover.course_id == course_id).with_for_update())
        course = session.get(AcademyCourse, course_id)
        if (not cached or not course or cached.source_hash != source_hash or cached.claim_id != claim_id
                or source_fingerprint(course) != source_hash):
            return
        cached.status = 'new' if deferred else 'ready' if data else 'failed'
        cached.data = data
        cached.sha256 = hashlib.sha256(data).hexdigest() if data else None
        cached.claim_id = None
        cached.updated_at = datetime.now(UTC)
        session.commit()


def ensure_course_cover(course_id, expected_source=None):
    """Populate a source-versioned cache; optional work must never reject publication."""
    try:
        claim = _claim(course_id, expected_source)
        if claim is None:
            return
        source_hash, claim_id, source = claim
        try:
            data = _video_cover(source) if source.kind == 'video' else extract_link_cover(source.url)
            if not isinstance(data, bytes) or not data.startswith(b'\xff\xd8\xff') or len(data) > MAX_COVER_SIZE:
                data = None
        except CoverBusy:
            _complete(course_id, source_hash, claim_id, None, deferred=True)
            return
        except Exception:
            data = None
        _complete(course_id, source_hash, claim_id, data)
    except Exception:
        # Avoid logging course URLs, uploaded content or provider response bodies.
        logger.warning('Academy cover generation deferred for course %s', course_id)
