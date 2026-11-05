"""Real AI Academy publication and learning; media never depends on browser storage."""
import hashlib
import math
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from journey_api.academy_models import AcademyCourse, AcademyLearningRecord, AcademyVideo, AcademyVideoChunk
from journey_api.academy_covers import cached_course_cover, course_cover_processing, ensure_course_cover, source_fingerprint
from journey_api.auth import Actor, get_actor, get_learner_actor
from journey_api.db import SessionLocal, get_db
from journey_api.errors import ApiError
from journey_api.identity import add_audit
from journey_api.models import Role, User
from journey_api.review_admin_access import require_publisher
from journey_api.review_admin_routes import envelope

def require_staff_entry(request: Request, actor: Actor = Depends(get_actor)):
    if (request.headers.get('X-Journey-Session-Scope') == 'learner'
            or actor.entry_role not in {Role.REVIEWER, Role.OPERATOR, Role.CONTENT_EDITOR}):
        raise ApiError(403, 'FORBIDDEN', '请从管理端登录后管理 AI 学院。')


admin_router = APIRouter(prefix='/api/v1/ops/academy', dependencies=[Depends(require_staff_entry)])
learner_router = APIRouter(prefix='/api/v1/me/academy')
CHUNK_SIZE = 512 * 1024
MAX_VIDEO_SIZE = 500 * 1024 * 1024
TAGS = (
    'AI 入门', 'AI 工具推荐', '怎么问 AI', 'AI 使用避坑', 'AIGC 创意玩法',
    'AI 写文案', 'AI 做图片', 'AI 做视频', 'AI 配音与音乐', 'AI 做 PPT',
    'AI 做表格', 'AI 写邮件', 'AI 整理会议纪要', 'AI 写周报与总结', 'AI 查资料',
    'AI 读文档', 'AI 翻译', 'AI 做计划', 'AI 辅助学习', 'AI 日常妙用',
)
VIDEO_TYPES = {'mp4': 'video/mp4', 'm4v': 'video/mp4', 'mov': 'video/quicktime',
               'webm': 'video/webm', 'ogv': 'video/ogg', 'ogg': 'video/ogg'}


def fail(message, status=422):
    code = {404: 'ACADEMY_NOT_FOUND', 409: 'ACADEMY_CONFLICT', 403: 'FORBIDDEN', 413: 'ACADEMY_TOO_LARGE'}.get(status, 'ACADEMY_INVALID')
    raise ApiError(status, code, message)


def now():
    return datetime.now(UTC)


def iso(value):
    return value.isoformat() if value else None


def audit(session, request, actor, action, resource_id):
    add_audit(session, request_id=request.state.request_id, action=action,
              resource_type='academy', result='SUCCESS', organization_id=actor.organization_id,
              actor_id=actor.id, resource_id=resource_id, details={})


def metadata(payload, previous=None, *, external=True):
    data = dict(previous or {})
    for key in ('title', 'summary', 'url', 'minutes', 'tags'):
        if key in payload:
            data[key] = payload[key]
    for key, label, limit in [('title', '课程名称', 100), ('summary', '课程简介', 1200)]:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            fail(f'{label}需为 1～{limit} 个字。')
        data[key] = value.strip()
    minutes = data.get('minutes', 15)
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes <= 0 or minutes > 43200:
        fail('预计时长需大于 0 且不能超过 43200 分钟。')
    data['minutes'] = round(minutes, 1)
    if data['minutes'] <= 0:
        fail('预计时长至少为 0.1 分钟。')
    tags = data.get('tags', [])
    if not isinstance(tags, list) or len(tags) > len(TAGS) or any(not isinstance(t, str) or t not in TAGS for t in tags):
        fail('请选择有效的课程标签。')
    data['tags'] = [t for t in TAGS if t in tags]
    url = data.get('url', '')
    if external:
        if not isinstance(url, str) or not url or len(url) > 4000 or re.search(r'[\s\\\x00-\x1f\x7f]', url):
            fail('请填写有效的 HTTP 或 HTTPS 课程链接。')
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError()
            parsed.port
        except ValueError:
            fail('课程链接格式无效，不能包含账号或密码。')
        data['url'] = url
    else:
        data['url'] = ''
    return data


def public_conditions():
    return (AcademyCourse.visibility == 'published',
            or_(AcademyCourse.kind != 'share', AcademyCourse.review_status == 'approved'))


def course_row(session, actor, course_id, *, public=False, lock=False):
    query = select(AcademyCourse).where(AcademyCourse.id == course_id,
                                      AcademyCourse.organization_id == actor.organization_id)
    if public:
        query = query.where(*public_conditions())
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(query)
    if not row:
        fail('课程不存在或已下架。', 404)
    return row


def check_revision(row, revision):
    if row.revision != revision:
        fail('内容已被更新，请刷新后重试。', 409)


def course_view(row, record=None, *, share=False, staff=False):
    data = dict(row.content)
    data.update(id=str(row.id), type=row.kind, courseId=str(row.id), revision=row.revision,
                author={'id': str(row.author_id), 'name': row.content.get('authorName', '学员')},
                status=row.review_status if share else 'published', visibility=row.visibility,
                createdAt=iso(row.created_at), updatedAt=iso(row.updated_at), demo=False,
                linkState='active', category='员工实践' if row.kind == 'share' else '视频课程' if row.kind == 'video' else 'AI 学习')
    data.pop('authorName', None)
    scope = 'ops' if staff else 'me'
    data['coverUrl'] = f'/api/v1/{scope}/academy/courses/{row.id}/cover?source={source_fingerprint(row)}'
    if share:
        data.update(reason=row.review_reason, reviewedAt=iso(row.reviewed_at),
                    reviewedBy=str(row.reviewed_by) if row.reviewed_by else None)
    if row.kind == 'video':
        scope = 'ops' if staff else 'me'
        data['videoUrl'] = f'/api/v1/{scope}/academy/courses/{row.id}/video'
    data.update(progress=record.progress if record else 0,
                completed=record.completed if record else False,
                favorite=record.favorite if record else False,
                saved=record.favorite if record else False,
                seconds=record.seconds if record else 0,
                duration=record.duration if record else 0)
    return data


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CourseCreate(Command):
    id: uuid.UUID | None = None
    type: Literal['link', 'video']
    title: str
    summary: str
    url: str = ''
    minutes: float = Field(default=15, gt=0, le=43200, allow_inf_nan=False)
    tags: list[str] = Field(default_factory=list, max_length=20)
    uploadId: uuid.UUID | None = None


class CourseUpdate(Command):
    expected_revision: int = Field(ge=1)
    type: Literal['link', 'video', 'share'] | None = None
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    minutes: float | None = Field(default=None, gt=0, le=43200, allow_inf_nan=False)
    tags: list[str] | None = Field(default=None, max_length=20)
    uploadId: uuid.UUID | None = None


class Visibility(Command):
    expected_revision: int = Field(ge=1)
    visible: bool = Field(strict=True)


class Review(Command):
    expected_revision: int = Field(ge=1)
    decision: Literal['approved', 'rejected']
    reason: str = Field(default='', max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)


class ShareCreate(Command):
    id: uuid.UUID | None = None
    title: str
    summary: str
    url: str
    minutes: float = Field(default=15, gt=0, le=43200, allow_inf_nan=False)
    tags: list[str] = Field(default_factory=list, max_length=20)


class Favorite(Command):
    saved: bool = Field(strict=True)


class Progress(Command):
    expected_revision: int | None = Field(default=None, ge=1)
    seconds: float = Field(default=0, ge=0, le=2592000, allow_inf_nan=False)
    duration: float = Field(default=0, ge=0, le=2592000, allow_inf_nan=False)
    completed: bool = Field(default=False, strict=True)


def bound_video(session, actor, video_id, course_id=None):
    video = session.scalar(select(AcademyVideo).where(AcademyVideo.id == video_id,
        AcademyVideo.organization_id == actor.organization_id).with_for_update())
    if not video or not video.complete:
        fail('视频不存在或尚未上传完成。', 422)
    if video.created_by != actor.id:
        fail('只能使用自己上传的视频。', 403)
    other = session.scalar(select(AcademyCourse.id).where(AcademyCourse.video_id == video.id,
        AcademyCourse.id != course_id))
    if other:
        fail('视频已用于其他课程，请重新上传。', 409)
    return video


def add_video_metadata(data, video):
    data.update(videoName=video.file_name, videoSize=video.size, mimeType=video.mime_type)


@admin_router.get('')
def admin_listing(request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    rows = list(session.scalars(select(AcademyCourse).where(AcademyCourse.organization_id == actor.organization_id)
                               .order_by(AcademyCourse.created_at.desc(), AcademyCourse.id)))
    courses = [course_view(row, staff=True) for row in rows if row.kind != 'share' or row.review_status == 'approved']
    shares = [course_view(row, share=True, staff=True) for row in rows if row.kind == 'share']
    published = sum(c['visibility'] == 'published' for c in courses)
    return envelope(request, dict(courses=courses, shares=shares, tags=list(TAGS),
        stats=dict(total=len(courses), published=published, unpublished=len(courses)-published,
                   pending=sum(s['status'] == 'pending' for s in shares))))


@admin_router.post('/courses')
def create_course(command: CourseCreate, request: Request, background_tasks: BackgroundTasks, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    # require_publisher locks this author's User row, serializing create retries.
    require_publisher(session, actor)
    data = metadata(command.model_dump(), external=command.type != 'video')
    course_id = command.id or uuid.uuid4()
    existing = session.get(AcademyCourse, course_id)
    if existing:
        if (existing.organization_id != actor.organization_id or existing.author_id != actor.id or existing.kind != command.type
            or any(existing.content.get(k) != v for k, v in data.items()) or existing.video_id != command.uploadId):
            fail('创建请求已使用，请刷新后重试。', 409)
        return envelope(request, course_view(existing, staff=True))
    video = None
    if command.type == 'video':
        if command.uploadId is None:
            fail('请先上传完整的视频文件。')
        video = bound_video(session, actor, command.uploadId, course_id)
        add_video_metadata(data, video)
    elif command.uploadId:
        fail('外链课程不能绑定视频。')
    data['authorName'] = actor.display_name
    row = AcademyCourse(id=course_id, organization_id=actor.organization_id, author_id=actor.id,
        kind=command.type, visibility='published', content=data, revision=1,
        video_id=video.id if video else None, review_reason='', created_at=now(), updated_at=now())
    session.add(row)
    audit(session, request, actor, 'ACADEMY_COURSE_PUBLISHED', row.id)
    session.commit()
    background_tasks.add_task(ensure_course_cover, row.id, source_fingerprint(row))
    return envelope(request, course_view(row, staff=True))


@admin_router.patch('/courses/{course_id}')
def update_course(course_id: uuid.UUID, command: CourseUpdate, request: Request, background_tasks: BackgroundTasks,
                  actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    row = course_row(session, actor, course_id, lock=True)
    if row.kind == 'share' and row.review_status != 'approved':
        fail('待审核的分享请在分享审核中处理。', 409)
    check_revision(row, command.expected_revision)
    previous_source = source_fingerprint(row)
    if command.type is not None and command.type != row.kind:
        fail('不能更改课程内容类型。')
    data = metadata(command.model_dump(exclude_unset=True), row.content, external=row.kind != 'video')
    if command.uploadId:
        if row.kind != 'video':
            fail('外链课程不能绑定视频。')
        video = bound_video(session, actor, command.uploadId, row.id)
        if row.video_id != video.id:
            session.execute(update(AcademyLearningRecord).where(
                AcademyLearningRecord.organization_id == actor.organization_id,
                AcademyLearningRecord.course_id == row.id).values(
                    seconds=0, duration=0, progress=0, completed=False, updated_at=now()))
        row.video_id = video.id
        add_video_metadata(data, video)
    row.content = data
    row.revision += 1
    row.updated_at = now()
    audit(session, request, actor, 'ACADEMY_COURSE_UPDATED', row.id)
    session.commit()
    if previous_source != source_fingerprint(row):
        background_tasks.add_task(ensure_course_cover, row.id, source_fingerprint(row))
    return envelope(request, course_view(row, staff=True))


@admin_router.post('/courses/{course_id}/visibility')
def visibility(course_id: uuid.UUID, command: Visibility, request: Request, background_tasks: BackgroundTasks,
               actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    row = course_row(session, actor, course_id, lock=True)
    check_revision(row, command.expected_revision)
    if row.kind == 'share' and row.review_status != 'approved':
        fail('分享需要审核通过后才能上架。', 409)
    row.visibility = 'published' if command.visible else 'unpublished'
    row.revision += 1
    row.updated_at = now()
    audit(session, request, actor, 'ACADEMY_COURSE_PUBLISHED' if command.visible else 'ACADEMY_COURSE_UNPUBLISHED', row.id)
    session.commit()
    if command.visible:
        background_tasks.add_task(ensure_course_cover, row.id, source_fingerprint(row))
    return envelope(request, course_view(row, staff=True))


@admin_router.post('/shares/{course_id}/review')
def review_share(course_id: uuid.UUID, command: Review, request: Request, background_tasks: BackgroundTasks,
                 actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    row = course_row(session, actor, course_id, lock=True)
    check_revision(row, command.expected_revision)
    if row.kind != 'share' or row.review_status != 'pending':
        fail('这条分享已经处理，请刷新列表。', 409)
    if command.decision == 'rejected' and not command.reason.strip():
        fail('驳回时必须填写理由。')
    reviewed_content = metadata({'tags': command.tags}, row.content) if command.tags is not None else None
    if command.decision == 'approved' and reviewed_content is not None:
        row.content = reviewed_content
    row.review_status = command.decision
    row.visibility = 'published' if command.decision == 'approved' else 'unpublished'
    row.review_reason = command.reason.strip() if command.decision == 'rejected' else ''
    row.reviewed_by = actor.id
    row.reviewed_at = now()
    row.updated_at = now()
    row.revision += 1
    audit(session, request, actor, 'ACADEMY_SHARE_' + command.decision.upper(), row.id)
    session.commit()
    if command.decision == 'approved':
        background_tasks.add_task(ensure_course_cover, row.id, source_fingerprint(row))
    return envelope(request, course_view(row, share=True, staff=True))


@learner_router.get('')
def learner_listing(request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    rows = list(session.scalars(select(AcademyCourse).where(AcademyCourse.organization_id == actor.organization_id,
        *public_conditions()).order_by(AcademyCourse.created_at.desc(), AcademyCourse.id)))
    records = {r.course_id: r for r in session.scalars(select(AcademyLearningRecord).where(
        AcademyLearningRecord.organization_id == actor.organization_id, AcademyLearningRecord.user_id == actor.id))}
    courses = [course_view(row, records.get(row.id)) for row in rows]
    shares = [course_view(row, share=True) for row in session.scalars(select(AcademyCourse).where(
        AcademyCourse.organization_id == actor.organization_id, AcademyCourse.kind == 'share',
        AcademyCourse.author_id == actor.id).order_by(AcademyCourse.created_at.desc()))]
    return envelope(request, dict(courses=courses, shares=shares, tags=list(TAGS),
        stats=dict(total=len(courses), completed=sum(c['completed'] for c in courses),
                   favorites=sum(c['favorite'] for c in courses), pending=sum(s['status'] == 'pending' for s in shares))))


@learner_router.get('/courses/{course_id}')
def learner_course(course_id: uuid.UUID, request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    row = course_row(session, actor, course_id, public=True)
    record = session.get(AcademyLearningRecord, (actor.organization_id, actor.id, row.id))
    return envelope(request, course_view(row, record))


@learner_router.post('/shares')
def submit_share(command: ShareCreate, request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    # Serialize a learner's repeated submit request so its stable ID is idempotent.
    session.scalar(select(User.id).where(User.id == actor.id, User.organization_id == actor.organization_id).with_for_update())
    data = metadata(command.model_dump())
    share_id = command.id or uuid.uuid4()
    existing = session.get(AcademyCourse, share_id)
    if existing:
        if (existing.organization_id != actor.organization_id or existing.author_id != actor.id or existing.kind != 'share'
            or any(existing.content.get(k) != v for k, v in data.items())):
            fail('提交请求已使用，请刷新后重试。', 409)
        return envelope(request, course_view(existing, share=True))
    data['authorName'] = actor.display_name
    row = AcademyCourse(id=share_id, organization_id=actor.organization_id, author_id=actor.id,
        kind='share', visibility='unpublished', review_status='pending', review_reason='',
        content=data, revision=1, created_at=now(), updated_at=now())
    session.add(row)
    audit(session, request, actor, 'ACADEMY_SHARE_SUBMITTED', row.id)
    session.commit()
    return envelope(request, course_view(row, share=True))


@learner_router.patch('/shares/{course_id}')
def resubmit_share(course_id: uuid.UUID, command: CourseUpdate, request: Request,
                   actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    row = course_row(session, actor, course_id, lock=True)
    if row.kind != 'share' or row.author_id != actor.id:
        fail('分享不存在。', 404)
    check_revision(row, command.expected_revision)
    if row.review_status != 'rejected':
        fail('仅已驳回的分享可以修改后重新提交。', 409)
    if command.uploadId or command.type not in (None, 'share'):
        fail('员工分享请提交外部课程链接。')
    row.content = metadata(command.model_dump(exclude_unset=True), row.content)
    row.review_status = 'pending'
    row.review_reason = ''
    row.reviewed_by = None
    row.reviewed_at = None
    row.visibility = 'unpublished'
    row.updated_at = now()
    row.revision += 1
    audit(session, request, actor, 'ACADEMY_SHARE_RESUBMITTED', row.id)
    session.commit()
    return envelope(request, course_view(row, share=True))


def record_row(session, actor, course_id):
    values = dict(organization_id=actor.organization_id, user_id=actor.id, course_id=course_id,
                  favorite=False, seconds=0, duration=0, progress=0, completed=False, updated_at=now())
    session.execute(insert(AcademyLearningRecord).values(**values).on_conflict_do_nothing())
    return session.scalar(select(AcademyLearningRecord).where(AcademyLearningRecord.organization_id == actor.organization_id,
        AcademyLearningRecord.user_id == actor.id, AcademyLearningRecord.course_id == course_id)
        .with_for_update().execution_options(populate_existing=True))


@learner_router.post('/courses/{course_id}/favorite')
def favorite(course_id: uuid.UUID, command: Favorite, request: Request,
             actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    course_row(session, actor, course_id, public=True, lock=True)
    record = record_row(session, actor, course_id)
    record.favorite = command.saved
    record.updated_at = now()
    session.commit()
    return envelope(request, dict(id=str(course_id), saved=record.favorite, favorite=record.favorite))


@learner_router.post('/courses/{course_id}/progress')
def progress(course_id: uuid.UUID, command: Progress, request: Request,
             actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    row = course_row(session, actor, course_id, public=True, lock=True)
    if command.expected_revision is not None:
        check_revision(row, command.expected_revision)
    if command.seconds > command.duration and command.duration > 0:
        fail('播放进度不能超过视频总时长。')
    if row.kind == 'video' and command.duration <= 0:
        fail('请在视频加载完成后保存进度。')
    record = record_row(session, actor, course_id)
    duration = command.duration or row.content.get('minutes', 15) * 60
    current_progress = min(100, command.seconds / duration * 100)
    # Completion is self-paced learning, not a task evaluation or a reward grant.
    completed = current_progress >= 90 if row.kind == 'video' else command.completed
    record.completed = record.completed or completed
    record.seconds = command.seconds
    record.duration = duration
    record.progress = 100 if record.completed else max(record.progress, round(current_progress, 2))
    record.updated_at = now()
    session.commit()
    return envelope(request, course_view(row, record))


class UploadCreate(Command):
    fileName: str = Field(min_length=1, max_length=255)
    size: int = Field(strict=True, gt=0, le=MAX_VIDEO_SIZE)
    mimeType: str | None = Field(default=None, max_length=100)


def upload_row(session, actor, upload_id):
    row = session.scalar(select(AcademyVideo).where(AcademyVideo.id == upload_id,
        AcademyVideo.organization_id == actor.organization_id).with_for_update())
    if not row:
        fail('上传记录不存在。', 404)
    if row.created_by != actor.id:
        fail('只能操作自己上传的视频。', 403)
    return row


@admin_router.post('/uploads')
def begin_upload(command: UploadCreate, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    name = command.fileName.strip()
    extension = name.rsplit('.', 1)[-1].lower()
    if extension not in VIDEO_TYPES or re.search(r'[\x00-\x1f\x7f/\\]', name):
        fail('请选择 MP4、WebM、MOV 或 Ogg 视频文件。')
    # Only the current uploader's abandoned, unreferenced uploads are collectible.
    unbound = ~select(AcademyCourse.id).where(AcademyCourse.video_id == AcademyVideo.id).exists()
    session.execute(delete(AcademyVideo).where(AcademyVideo.organization_id == actor.organization_id,
        AcademyVideo.created_by == actor.id, AcademyVideo.created_at < now()-timedelta(days=1), unbound))
    unfinished = session.scalar(select(func.count()).select_from(AcademyVideo).where(
        AcademyVideo.organization_id == actor.organization_id, AcademyVideo.created_by == actor.id, unbound))
    if unfinished >= 10:
        fail('未使用的上传过多，请取消多余上传后重试。', 409)
    row = AcademyVideo(id=uuid.uuid4(), organization_id=actor.organization_id, created_by=actor.id,
        file_name=name, mime_type=VIDEO_TYPES[extension], size=command.size, complete=False)
    session.add(row)
    session.commit()
    return envelope(request, dict(id=str(row.id), chunkSize=CHUNK_SIZE, maxSize=MAX_VIDEO_SIZE))


@admin_router.put('/uploads/{upload_id}/chunks/{position}', openapi_extra={
    'requestBody': {'required': True, 'content': {'application/octet-stream': {
        'schema': {'type': 'string', 'format': 'binary'}}}}})
async def upload_chunk(upload_id: uuid.UUID, position: int, request: Request,
                       actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    row = upload_row(session, actor, upload_id)
    if row.complete:
        fail('视频已经上传完成。', 409)
    if position < 0 or position >= math.ceil(row.size / CHUNK_SIZE):
        fail('视频分段编号无效。')
    expected = min(CHUNK_SIZE, row.size-position*CHUNK_SIZE)
    payload = bytearray()
    async for part in request.stream():
        if len(payload)+len(part) > expected:
            fail('视频分段大小不匹配。', 413)
        payload.extend(part)
    if len(payload) != expected:
        fail('视频分段未完整上传。')
    previous = session.get(AcademyVideoChunk, (row.id, position))
    if previous is not None and previous.data != bytes(payload):
        fail('重复上传的分段内容不一致。', 409)
    if previous is None:
        session.add(AcademyVideoChunk(video_id=row.id, position=position, data=bytes(payload)))
    session.commit()
    return envelope(request, dict(id=str(row.id), position=position, received=expected))


def media_signature(data, mime):
    if mime in ('video/mp4', 'video/quicktime'):
        return len(data) >= 12 and data[4:8] == b'ftyp'
    if mime == 'video/webm':
        return data.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in data[:4096].lower()
    if mime == 'video/ogg':
        return data.startswith(b'OggS') and b'theora' in data[:65536]
    return False


@admin_router.post('/uploads/{upload_id}/complete')
def complete_upload(upload_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    row = upload_row(session, actor, upload_id)
    if not row.complete:
        digest = hashlib.sha256()
        total = 0
        expected_count = math.ceil(row.size / CHUNK_SIZE)
        count = 0
        for position, data in session.execute(select(AcademyVideoChunk.position, AcademyVideoChunk.data)
            .where(AcademyVideoChunk.video_id == row.id).order_by(AcademyVideoChunk.position).execution_options(yield_per=1)):
            expected_size = min(CHUNK_SIZE, row.size-position*CHUNK_SIZE)
            if position != count or len(data) != expected_size:
                fail('视频未完整上传，请重试。')
            if position == 0 and not media_signature(data, row.mime_type):
                fail('文件内容不是有效的 MP4、WebM 或 Ogg 视频。')
            digest.update(data)
            total += len(data)
            count += 1
        if count != expected_count or total != row.size:
            fail('视频未完整上传，请重试。')
        row.complete = True
        row.sha256 = digest.hexdigest()
        session.commit()
    return envelope(request, dict(id=str(row.id), fileName=row.file_name, size=row.size, mimeType=row.mime_type))


@admin_router.delete('/uploads/{upload_id}')
def cancel_upload(upload_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    row = upload_row(session, actor, upload_id)
    if session.scalar(select(AcademyCourse.id).where(AcademyCourse.video_id == row.id)):
        fail('课程正在使用该视频，不能取消。', 409)
    session.delete(row)
    session.commit()
    return envelope(request, dict(id=str(upload_id), cancelled=True))


def video_response(session, actor, course_id, request, *, public):
    course = course_row(session, actor, course_id, public=public)
    if course.kind != 'video' or not course.video_id:
        fail('该课程没有视频。', 404)
    video = session.scalar(select(AcademyVideo).where(AcademyVideo.id == course.video_id,
        AcademyVideo.organization_id == actor.organization_id, AcademyVideo.complete.is_(True)))
    if not video:
        fail('视频不存在或尚未上传完成。', 404)
    size = video.size
    start, end, status = 0, size-1, 200
    etag = '"' + (video.sha256 or str(video.id)) + '"'
    range_header = request.headers.get('range')
    if range_header and request.headers.get('if-range', etag) == etag:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip()) if len(range_header) <= 128 else None
        if not match or not any(match.groups()):
            return Response(status_code=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size-1) if last else size-1
        else:
            suffix = int(last)
            start = max(0, size-suffix)
        if start > end or start >= size or (not first and int(last) == 0):
            return Response(status_code=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
        status = 206
    headers = {'Accept-Ranges': 'bytes', 'Content-Length': str(end-start+1), 'ETag': etag,
        'Content-Disposition': "inline; filename*=UTF-8''" + quote(video.file_name),
        'Content-Type': video.mime_type, 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'}
    if status == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    if request.method == 'HEAD':
        return Response(status_code=status, headers=headers)
    video_id = video.id
    # Release auth locks before a potentially long playback download.
    session.rollback()

    def chunks():
        with SessionLocal() as stream_session:
            for position in range(start // CHUNK_SIZE, end // CHUNK_SIZE + 1):
                data = stream_session.scalar(select(AcademyVideoChunk.data).where(
                    AcademyVideoChunk.video_id == video_id, AcademyVideoChunk.position == position))
                if data is None:
                    raise RuntimeError('Published academy video chunk is missing')
                lower = max(0, start-position*CHUNK_SIZE)
                upper = min(len(data), end-position*CHUNK_SIZE+1)
                # Network backpressure must not retain a connection from the DB pool.
                stream_session.rollback()
                yield data[lower:upper]
    return StreamingResponse(chunks(), status_code=status, headers=headers)


@admin_router.get('/courses/{course_id}/video')
@admin_router.head('/courses/{course_id}/video')
def admin_video(course_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    return video_response(session, actor, course_id, request, public=False)


@learner_router.get('/courses/{course_id}/video')
@learner_router.head('/courses/{course_id}/video')
def learner_video(course_id: uuid.UUID, request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    return video_response(session, actor, course_id, request, public=True)


def cover_response(session, actor, course_id, request, *, public):
    course = course_row(session, actor, course_id, public=public)
    fingerprint = source_fingerprint(course)
    requested_source = request.query_params.get('source')
    headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
    if requested_source is not None and requested_source != fingerprint:
        return Response(status_code=404, headers=headers)
    # Optional network/media work must not hold the request's read transaction.
    session.rollback()
    cached = cached_course_cover(course_id, fingerprint)
    if cached is None and request.method != 'HEAD':
        ensure_course_cover(course_id, fingerprint)
        cached = cached_course_cover(course_id, fingerprint)
    # A concurrent edit, unpublish or review must take effect before returning bytes.
    current = course_row(session, actor, course_id, public=public)
    if source_fingerprint(current) != fingerprint:
        return Response(status_code=404, headers=headers)
    if cached is None:
        if request.method != 'HEAD' and course_cover_processing(course_id, fingerprint):
            return Response(status_code=425, headers={**headers, 'Retry-After': '2'})
        return Response(status_code=404, headers=headers)
    data, digest = cached
    etag = '"' + digest + '"'
    headers.update({'Cache-Control': 'private, no-cache', 'Content-Type': 'image/jpeg', 'ETag': etag})
    validators = [item.strip().removeprefix('W/') for item in request.headers.get('If-None-Match', '').split(',')]
    if etag in validators or '*' in validators:
        return Response(status_code=304, headers=headers)
    headers['Content-Length'] = str(len(data))
    return Response(content=b'' if request.method == 'HEAD' else data, headers=headers)


@admin_router.get('/courses/{course_id}/cover')
@admin_router.head('/courses/{course_id}/cover')
def admin_cover(course_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    return cover_response(session, actor, course_id, request, public=False)


@learner_router.get('/courses/{course_id}/cover')
@learner_router.head('/courses/{course_id}/cover')
def learner_cover(course_id: uuid.UUID, request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    return cover_response(session, actor, course_id, request, public=True)
