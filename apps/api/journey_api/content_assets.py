"""Chunked private files for course chapters and task materials."""
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from journey_api.academy_routes import require_staff_entry
from journey_api.auth import Actor, get_actor
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.exploration_models import ExplorationMaterial, ExplorationMaterialChunk
from journey_api.review_admin_access import require_publisher
from journey_api.review_admin_routes import envelope
from journey_api.video_limits import MAX_VIDEO_SIZE, VIDEO_TYPES, media_signature

router = APIRouter(prefix="/api/v1/review-admin/content-assets", dependencies=[Depends(require_staff_entry)])
CHUNK_SIZE = 2 * 1024 * 1024
MAX_DOCUMENT_SIZE = 100 * 1024 * 1024
DOCUMENT_TYPES = {"pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown",
    "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
INLINE_TYPES = set(VIDEO_TYPES.values()) | {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp"}


class Upload(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    size: int = Field(strict=True, gt=0, le=MAX_VIDEO_SIZE)
    purpose: Literal["course", "exploration", "novice"]


def require_course_asset(session, actor, asset_id):
    row = session.get(ExplorationMaterial, uuid.UUID(str(asset_id)))
    if not row or row.organization_id != actor.organization_id or row.purpose != "course" or not row.complete:
        raise ApiError(404, "ASSET_NOT_FOUND", "课程文件不存在。")
    return row


def description(row):
    return dict(id=str(row.id), name=row.name, mime=row.mime, size=row.size, type=row.kind,
        url="exploration-material:" + str(row.id), sha256=row.sha256)


@router.post("")
def begin(command: Upload, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_publisher(session, actor)
    name = command.name.strip()
    ext = name.rsplit(".", 1)[-1].lower()
    if not name or re.search(r"[\\/\x00-\x1f\x7f]", name):
        raise ApiError(422, "INVALID_FILE", "文件名无效。")
    mime = VIDEO_TYPES.get(ext)
    if not mime:
        if command.purpose != "course" or ext not in DOCUMENT_TYPES:
            raise ApiError(422, "INVALID_FILE", "不支持该文件类型。")
        if command.size > MAX_DOCUMENT_SIZE:
            raise ApiError(413, "FILE_TOO_LARGE", "非视频文件最多 100 MB。")
        mime = DOCUMENT_TYPES[ext]
    active = (ExplorationMaterial.uploaded_by == actor.id, ExplorationMaterial.complete.is_(False))
    session.execute(delete(ExplorationMaterial).where(*active, ExplorationMaterial.created_at < datetime.now(UTC) - timedelta(days=1)))
    if session.scalar(select(func.count()).select_from(ExplorationMaterial).where(*active)) >= 20:
        raise ApiError(409, "TOO_MANY_UPLOADS", "未完成的上传过多。")
    row = ExplorationMaterial(id=uuid.uuid4(), organization_id=actor.organization_id, uploaded_by=actor.id,
        name=name, kind="image" if mime.startswith("image/") else "file", mime=mime, size=command.size,
        sha256="", content=b"", purpose=command.purpose, complete=False, chunked=True)
    session.add(row)
    session.commit()
    return envelope(request, dict(id=str(row.id), chunkSize=CHUNK_SIZE))


def upload_row(session, actor, asset_id):
    row = session.scalar(select(ExplorationMaterial).where(ExplorationMaterial.id == asset_id,
        ExplorationMaterial.organization_id == actor.organization_id, ExplorationMaterial.uploaded_by == actor.id,
        ExplorationMaterial.chunked.is_(True)).with_for_update())
    if not row:
        raise ApiError(404, "ASSET_NOT_FOUND", "上传记录不存在。")
    require_publisher(session, actor)
    return row


@router.put("/{asset_id}/chunks/{position}")
async def put_chunk(asset_id: uuid.UUID, position: int, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    row = upload_row(session, actor, asset_id)
    expected = min(CHUNK_SIZE, row.size - position * CHUNK_SIZE)
    if row.complete or position < 0 or expected <= 0:
        raise ApiError(409, "INVALID_CHUNK", "上传已结束或分片编号无效。")
    data = bytearray()
    async for piece in request.stream():
        if len(data) + len(piece) > expected:
            raise ApiError(413, "INVALID_CHUNK", "分片过大。")
        data.extend(piece)
    if len(data) != expected:
        raise ApiError(422, "INVALID_CHUNK", "分片长度不符。")
    previous = session.get(ExplorationMaterialChunk, (row.id, position))
    if previous and previous.data != data:
        raise ApiError(409, "CHUNK_CONFLICT", "分片内容冲突。")
    if not previous:
        session.add(ExplorationMaterialChunk(material_id=row.id, position=position, data=bytes(data)))
    session.commit()
    return envelope(request, {"position": position})


@router.post("/{asset_id}/complete")
def complete(asset_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    row = upload_row(session, actor, asset_id)
    if not row.complete:
        digest = hashlib.sha256()
        size = 0
        parts = select(ExplorationMaterialChunk.position, ExplorationMaterialChunk.data).where(
            ExplorationMaterialChunk.material_id == row.id).order_by(ExplorationMaterialChunk.position).execution_options(yield_per=1)
        with session.execute(parts) as result:
            for index, (position, data) in enumerate(result):
                if position != index or len(data) != min(CHUNK_SIZE, row.size - size):
                    raise ApiError(422, "INVALID_CHUNK", "文件分片不完整。")
                if position == 0 and row.mime in VIDEO_TYPES.values() and not media_signature(data, row.mime):
                    raise ApiError(422, "INVALID_VIDEO", "文件内容与视频格式不匹配。")
                if position == 0 and row.mime == "image/gif" and not data.startswith((b"GIF87a", b"GIF89a")):
                    raise ApiError(422, "INVALID_IMAGE", "文件内容与 GIF 格式不匹配。")
                size += len(data)
                digest.update(data)
        if size != row.size:
            raise ApiError(422, "INVALID_CHUNK", "文件尚未上传完整。")
        row.sha256 = digest.hexdigest()
        row.complete = True
        session.commit()
    return envelope(request, description(row))


@router.delete("/{asset_id}")
def cancel(asset_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    row = upload_row(session, actor, asset_id)
    if not row.complete:
        session.delete(row)
        session.commit()
    return envelope(request, {"id": str(asset_id)})


def read_material_prefix(session, row, limit):
    if limit <= 0:
        return b""
    if not row.chunked:
        return session.scalar(select(func.substr(ExplorationMaterial.content, 1, limit)).where(ExplorationMaterial.id == row.id))
    data = bytearray()
    for position in range((min(row.size, limit) + CHUNK_SIZE - 1) // CHUNK_SIZE):
        piece = session.get(ExplorationMaterialChunk, (row.id, position))
        data.extend(piece.data[:limit-len(data)])
    return bytes(data)


def file_response(request, session, *, size, name, mime, chunk_size, read, inline, digest=None):
    show = inline and mime in INLINE_TYPES and not re.search(r"\.(?:svgz?|html?|xhtml)$", name, re.I)
    disposition = "inline" if show else "attachment"
    headers = {"Accept-Ranges": "bytes", "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(name, safe=""),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if digest:
        headers["ETag"] = '"' + digest + '"'
    start, end, status = 0, size - 1, 200
    value = request.headers.get("range")
    if value:
        match = re.fullmatch(r"bytes=(\d{0,19})-(\d{0,19})", value)
        if not match or not any(match.groups()):
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        left, right = match.groups()
        start = int(left) if left else max(0, size - int(right))
        end = min(end, int(right)) if left and right else end
        if start >= size or end < start:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        status = 206
    headers["Content-Length"] = str(end - start + 1)
    args = dict(status_code=status, media_type=mime if show else "application/octet-stream", headers=headers)
    if request.method == "HEAD" or size == 0:
        return Response(**args)
    engine = session.get_bind()
    session.rollback()  # Release authorization locks before network backpressure.
    def stream():
        for pos in range(start // chunk_size, end // chunk_size + 1):
            lo = max(0, start - pos * chunk_size)
            hi = min(chunk_size, end - pos * chunk_size + 1)
            with Session(engine) as reader:
                data = read(reader, pos, lo, hi)
            if data is None or len(data) != hi - lo:
                raise RuntimeError("Published file chunk is missing or truncated")
            yield data
    return StreamingResponse(stream(), **args)


def material_response(request, session, row, inline=True):
    asset_id, chunked = row.id, row.chunked
    def read(reader, pos, lo, hi):
        if chunked:
            return reader.scalar(select(func.substr(ExplorationMaterialChunk.data, lo + 1, hi - lo)).where(
                ExplorationMaterialChunk.material_id == asset_id, ExplorationMaterialChunk.position == pos))
        return reader.scalar(select(func.substr(ExplorationMaterial.content, pos * CHUNK_SIZE + lo + 1, hi - lo)).where(
            ExplorationMaterial.id == asset_id))
    return file_response(request, session, size=row.size, name=row.name, mime=row.mime, chunk_size=CHUNK_SIZE,
        read=read, inline=inline, digest=row.sha256)


@router.get("/{asset_id}")
@router.head("/{asset_id}")
def staff_file(asset_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    row = require_course_asset(session, actor, asset_id)
    from journey_api.course_workspace_routes import can_view_staff_asset
    if row.uploaded_by != actor.id and not can_view_staff_asset(session, actor, asset_id):
        raise ApiError(404, "ASSET_NOT_FOUND", "课程文件不存在。")
    return material_response(request, session, row)

def knowledge_response(request, session, file):
    from journey_api.community_models import KnowledgeChunk
    from journey_api.community_routes import CHUNK_SIZE as knowledge_chunk_size

    file_id = file.id
    def read(reader, pos, lo, hi):
        return reader.scalar(select(func.substr(KnowledgeChunk.data, lo + 1, hi - lo)).where(
            KnowledgeChunk.file_id == file_id, KnowledgeChunk.position == pos))
    return file_response(request, session, size=file.size, name=file.metadata_json["fileName"],
        mime=file.metadata_json.get("mimeType", "application/octet-stream"), chunk_size=knowledge_chunk_size,
        read=read, inline=request.query_params.get("inline") == "1")


@router.get("/knowledge/{file_id}")
@router.head("/knowledge/{file_id}")
def staff_knowledge_file(file_id: uuid.UUID, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    from journey_api.community_routes import get_file
    require_publisher(session, actor)
    file = get_file(session, actor, str(file_id))
    if not file.complete:
        raise ApiError(404, "NOT_FOUND", "知识库文件不存在。")
    return knowledge_response(request, session, file)
