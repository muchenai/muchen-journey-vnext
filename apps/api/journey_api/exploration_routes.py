"""Authenticated command adapter for the exploration learner interface."""
import hashlib
import re
import uuid
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from journey_api.auth import Actor, get_actor, get_learner_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.exploration_models import ExplorationMaterial, ExplorationSelfCheck, ExplorationWork
from journey_api.exploration_service import (MAX_MATERIAL_BYTES, catalog, claim, context, material_metadata,
    effective_catalog_positions, lock_catalog, progress_for, task_view, treasure_view, unlocked_task_ids, unlock_graduation)
from journey_api.idempotency import find_replay, store_result
from journey_api.models import Assignment, AssignmentStatus, Enrollment, EnrollmentStatus, Role, User
from journey_api.review_admin_access import require_super
from journey_api.review_admin_models import ReviewAdminTask
from journey_api.review_admin_routes import audit, envelope

router = APIRouter(prefix="/api/v1")


class ExplorationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str
    taskId: uuid.UUID | None = None
    id: str | None = None
    payload: dict = Field(default_factory=dict)
    revision: int | None = None
    versionId: uuid.UUID | None = None
    answer: str = Field(default="", max_length=8000)
    key: str | None = None
    idempotencyKey: str | None = None
    index: int | None = None
    checkinConfirmed: bool = False


def lock_learner(session, actor):
    require_role(actor, Role.LEARNER)
    session.scalar(select(User.id).where(User.id == actor.id, User.organization_id == actor.organization_id).with_for_update(key_share=True))


def reject_cancel(command):
    if command == "cancel":
        raise ApiError(409, "EXPLORATION_CANCEL_NOT_ALLOWED", "探索营任务接取后不能取消。")


def snapshot(session, actor):
    unlocked = unlocked_task_ids(session, actor)
    positions = effective_catalog_positions(session, actor.organization_id, user_id=actor.id)
    visible = set(positions)
    owned = session.scalars(select(ExplorationWork.task_id).where(ExplorationWork.organization_id == actor.organization_id,
        ExplorationWork.user_id == actor.id))
    visible.update(owned)
    items = []
    for task_id in visible:
        profile = session.get(ReviewAdminTask, task_id)
        if profile and profile.status != "deleted":
            items.append(task_view(session, actor, task_id, allow_locked=True, unlocked_ids=unlocked, catalog_positions=positions))
    return dict(items=sorted(items, key=lambda item: (item["order"], item["id"])), wallet={"taskPoints": 0}, treasures=treasure_view(session, actor))


def self_check_record(row):
    from journey_api.exploration_ai_self_check import record
    return record(row)


def self_check_history(session, actor, task_id):
    *_, assignment, version, _snapshot = context(session, actor, task_id)
    rows = session.scalars(select(ExplorationSelfCheck).where(ExplorationSelfCheck.organization_id == actor.organization_id,
        ExplorationSelfCheck.user_id == actor.id, ExplorationSelfCheck.assignment_id == assignment.id)
        .order_by(ExplorationSelfCheck.created_at.desc())) if assignment else []
    from journey_api.exploration_ai_self_check import refresh_document_record
    items = []
    for row in rows:
        if (row.details or {}).get("canonicalRecordId"):
            continue
        refresh_document_record(session, row)
        items.append(self_check_record(row))
    return {"items": items}


def self_check_response(session, actor, task_id, row):
    return {"record": self_check_record(row), **self_check_history(session, actor, task_id),
        "task": task_view(session, actor, task_id)}


@router.get("/me/exploration")
def read_exploration(request: Request, command: str = "learnerSnapshot", taskId: uuid.UUID | None = None,
    task: uuid.UUID | None = None, index: int | None = None, group: Literal["learning", "task"] = "learning",
    actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    lock_learner(session, actor)
    lock_catalog(session, actor)
    task_id = taskId or task
    if command == "learnerSnapshot":
        result = snapshot(session, actor)
    elif command == "treasures":
        result = {"treasures": treasure_view(session, actor)}
    elif task_id and command in {"task", "learnerTask"}:
        result = task_view(session, actor, task_id)
    elif task_id and command == "selfCheckHistory":
        result = self_check_history(session, actor, task_id)
    elif task_id and command == "material" and index is not None:
        result = material_metadata(session, actor, task_id, index, group)
    else:
        raise ApiError(422, "INVALID_REQUEST", "探索营读取参数不完整。")
    session.commit()
    return envelope(request, result)


@router.post("/me/exploration")
def write_exploration(body: ExplorationCommand, request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    lock_learner(session, actor)
    # Apply the current rule before replay: a historical successful cancellation
    # must not reappear as a successful response after cancellation is disabled.
    reject_cancel(body.command)
    key = body.key or body.idempotencyKey or idempotency_key
    if not key:
        raise ApiError(400, "INVALID_REQUEST", "请提供本次操作的请求标识。")
    payload = body.model_dump(mode="json", exclude={"key", "idempotencyKey"})
    replay = find_replay(session, actor_id=actor.id, command="exploration." + body.command, key=key, payload=payload)
    if replay is not None:
        if body.command in {"unlockGraduation", "ackTreasure", "acknowledgeTreasure"}:
            current = {"treasures": treasure_view(session, actor), "idempotency_replay": True}
            session.commit()
            return envelope(request, current)
        return envelope(request, replay)
    if body.command == "selfCheck":
        # The attempt row is durable before model/network work, unlike a final
        # response cache. It also handles concurrent retransmissions and keeps
        # comment state fresh after a RUNNING/SENDING response was returned.
        from journey_api.exploration_ai_self_check import replay as self_check_replay
        previous = self_check_replay(session, actor, body, key)
        if previous is not None:
            complete_scored_attempt(session, actor, body, request, previous)
        result = (self_check_response(session, actor, body.taskId, previous) if previous is not None
            else task_command(session, actor, body, request, key))
        audit(session, request, actor, "exploration.selfCheck", body.taskId or actor.id)
        session.commit()
        return envelope(request, result)
    if body.command == "unlockGraduation":
        result = {"treasures": unlock_graduation(session, actor)}
    elif body.command in {"ackTreasure", "acknowledgeTreasure"}:
        progress = progress_for(session, actor)
        game = dict(progress.treasures)
        drops = [dict(drop) for drop in game["drops"]]
        drop = next((drop for drop in drops if drop["id"] == (body.id or body.payload.get("id"))), None)
        if drop is None:
            raise ApiError(404, "NOT_FOUND", "没有找到该宝藏记录。")
        drop["acknowledgedAt"] = drop.get("acknowledgedAt") or datetime.now(UTC).isoformat()
        game["drops"], progress.treasures = drops, game
        result = {"treasures": treasure_view(session, actor)}
    else:
        result = task_command(session, actor, body, request, key)
    audit(session, request, actor, "exploration." + body.command, body.taskId or actor.id)
    store_result(session, actor_id=actor.id, command="exploration." + body.command, key=key, payload=payload, response=result)
    session.commit()
    return envelope(request, result)


def task_command(session, actor, body, request, key):
    reject_cancel(body.command)
    if body.taskId is None:
        raise ApiError(422, "INVALID_REQUEST", "请选择探索任务。")
    task_id = body.taskId
    entry, profile, work, assignment, version, published = context(session, actor, task_id)
    already_claimed = assignment is not None
    if body.versionId is None or body.versionId != version.id:
        raise ApiError(409, "VERSION_CONFLICT", "任务版本已更新，请刷新后重试。")
    if assignment and body.command != "claim" and body.revision != assignment.revision:
        raise ApiError(409, "VERSION_CONFLICT", "任务状态已更新，请重新打开后操作。")
    mode = published.content.get("completionMode") or "assessment"
    if body.command in {"claim", "readMaterial", "completeLearning"}:
        work, assignment = claim(session, actor, task_id, body.versionId)
    if not assignment:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "请先领取探索任务。")
    session.refresh(assignment, with_for_update=True)
    if already_claimed and body.command != "claim" and body.revision != assignment.revision:
        raise ApiError(409, "VERSION_CONFLICT", "任务状态已更新，请重新打开后操作。")
    if body.command == "claim":
        if assignment.status == AssignmentStatus.CANCELLED:
            if profile.status != "published" or body.revision != assignment.revision:
                raise ApiError(409, "VERSION_CONFLICT", "任务已归档或状态已更新。")
            assignment.status, assignment.revision = AssignmentStatus.IN_PROGRESS, assignment.revision + 1
    elif body.command == "readMaterial":
        materials = published.content.get("materials", [])
        if body.index is None or body.index < 0 or body.index >= len(materials):
            raise ApiError(422, "INVALID_MATERIAL", "请选择有效学习材料。")
        if body.index not in work.opened_materials:
            work.opened_materials = [*work.opened_materials, body.index]
            assignment.revision += 1
    elif body.command == "completeLearning":
        if mode == "assessment":
            raise ApiError(409, "INVALID_STATE_TRANSITION", "测试任务需要提交结果并等待审核。")
        if assignment.status != AssignmentStatus.COMPLETED:
            if assignment.status != AssignmentStatus.IN_PROGRESS:
                raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能完成。")
            if mode == "learning" and set(range(len(published.content.get("materials", [])))) - set(work.opened_materials):
                raise ApiError(409, "MATERIALS_REQUIRED", "请逐项打开并学习全部学习材料。")
            if mode == "checkin" and not body.checkinConfirmed:
                raise ApiError(422, "CHECKIN_CONFIRMATION_REQUIRED", "请确认已经成功进入项目培训群后再完成签退。")
            work.completed_at, work.checkin_confirmed = datetime.now(UTC), mode == "checkin"
            assignment.status, assignment.revision = AssignmentStatus.COMPLETED, assignment.revision + 1
            enrollment = session.get(Enrollment, assignment.enrollment_id)
            enrollment.status, enrollment.revision = EnrollmentStatus.COMPLETED, enrollment.revision + 1
    elif body.command in {"draft", "submit"}:
        if mode != "assessment":
            raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务无需提交文字作业。")
        if body.command == "submit" and published.content.get("reviewMode") == "ai":
            raise ApiError(409, "AI_ASSESSMENT_REQUIRED", "本任务按 AI 评分标准自动评测，请完成 AI 自测，达到通过分数后直接完成任务。")
        from journey_api.schemas import SaveSubmissionDraftCommand, SubmissionCommand
        from journey_api.submission_routes import save_submission_draft, submit_assignment
        request.state.defer_exploration_commit = True
        if body.command == "draft":
            save_submission_draft(assignment.id, SaveSubmissionDraftCommand(expected_revision=assignment.revision, body=body.answer),
                request, idempotency_key=key, actor=actor, session=session)
        else:
            answer = body.answer.strip()
            if not answer:
                raise ApiError(422, "ANSWER_REQUIRED", "请填写测试结果、结果链接或简短说明。")
            # The dynamic assessment accepts a result link or a short note.
            # All state, ownership, reviewer and history checks stay in the
            # canonical submission handler. Its legacy 40-character entry
            # schema continues to protect existing task endpoints.
            command = SubmissionCommand.model_construct(expected_revision=assignment.revision, body=answer)
            submit_assignment(assignment.id, command, request, idempotency_key=key, actor=actor, session=session)
    elif body.command == "selfCheck":
        return run_self_check(session, actor, body, assignment, version, published.content, key, request)
    else:
        raise ApiError(422, "INVALID_REQUEST", "不支持的探索营操作。")
    session.flush()
    result = task_view(session, actor, task_id)
    if body.command == "completeLearning":
        treasure_view(session, actor)
    return result


def run_self_check(session, actor, body, assignment, version, content, key, request=None):
    from journey_api.exploration_ai_self_check import evaluate
    row = evaluate(session, actor, body, assignment, version, content, key)
    complete_scored_attempt(session, actor, body, request=request, row=row)
    return self_check_response(session, actor, body.taskId, row)


def complete_scored_attempt(session, actor, body, request, row):
    from journey_api.exploration_ai_completion import complete
    details = row.details or {}
    grading = details.get("grading") or {}
    if (row.status != "COMPLETED" or not details.get("analysisCompleted")
            or not grading.get("validated") or not grading.get("passed")
            or details.get("inputKind") == "document" and not details.get("gradingDocumentValidated")):
        return
    # An unchanged document can reuse its canonical prior attempt under a new
    # request key. Bind it to this user's requested task/version, then use the
    # canonical attempt's original input and revision for its persisted proof.
    task_id = session.scalar(select(ExplorationWork.task_id).where(
        ExplorationWork.assignment_id == row.assignment_id,
        ExplorationWork.organization_id == actor.organization_id,
        ExplorationWork.user_id == actor.id))
    if row.task_version_id != body.versionId or task_id != body.taskId:
        return
    # Grading is already durable. Release external workflow locks before
    # entering the completion service's consistent learner/assignment lock order.
    session.commit()
    complete(session, actor, attempt_id=row.id, expected_request_hash=details.get("requestHash"),
        expected_answer=row.answer, validated_result=grading,
        request_id=str(getattr(getattr(request, "state", None), "request_id", None) or row.id),
        expected_assignment_revision=details.get("assignmentRevision"))
    session.flush()
    session.refresh(row)


@router.post("/review-admin/exploration/materials")
async def upload_material(request: Request, name: str, type: str = "file",
    actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_super(session, actor)
    name = name.strip()
    if not name or len(name) > 240 or re.search(r"[\\/\x00-\x1f\x7f]", name) or type not in {"file", "image"}:
        raise ApiError(422, "INVALID_MATERIAL", "请提供有效文件名。")
    mime = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower().strip()
    if mime == "image/x-ms-bmp":
        mime = "image/bmp"
    if mime == "application/octet-stream":
        known_media = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
            "webp": "image/webp", "avif": "image/avif", "bmp": "image/bmp", "mp4": "video/mp4",
            "webm": "video/webm", "ogv": "video/ogg", "ogg": "video/ogg"}
        mime = known_media.get(name.rsplit(".", 1)[-1].lower(), mime)
    if not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", mime) or len(mime) > 100:
        raise ApiError(422, "INVALID_MATERIAL", "文件类型无效。")
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_MATERIAL_BYTES):
        raise ApiError(413, "MATERIAL_TOO_LARGE", "单个学习材料不能超过 100 MB。")
    digest, size = hashlib.sha256(), 0
    with SpooledTemporaryFile(max_size=2 * 1024 * 1024) as stream:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_MATERIAL_BYTES:
                raise ApiError(413, "MATERIAL_TOO_LARGE", "单个学习材料不能超过 100 MB。")
            digest.update(chunk)
            stream.write(chunk)
        if not size or length and size != int(length):
            raise ApiError(422, "INVALID_MATERIAL", "上传文件为空或长度不完整。")
        stream.seek(0)
        row = ExplorationMaterial(id=uuid.uuid4(), organization_id=actor.organization_id, uploaded_by=actor.id,
            name=name, kind=type, mime=mime, size=size, sha256=digest.hexdigest(), content=stream.read())
    session.add(row)
    audit(session, request, actor, "exploration.material_uploaded", row.id, {"size": size, "sha256": row.sha256})
    session.commit()
    return envelope(request, dict(id=str(row.id), name=name, type=type, url="exploration-material:" + str(row.id), mime=mime, size=size))


@router.get("/review-admin/exploration/materials/{material_id}")
@router.head("/review-admin/exploration/materials/{material_id}", include_in_schema=False)
@router.get("/me/exploration/materials/{material_id}")
@router.head("/me/exploration/materials/{material_id}", include_in_schema=False)
def download_material(material_id: uuid.UUID, request: Request, inline: str | None = None,
    actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    staff_roles = actor.roles.intersection({Role.REVIEWER, Role.OPERATOR, Role.CONTENT_EDITOR})
    if request.url.path.startswith("/api/v1/review-admin/") and (actor.entry_role == Role.LEARNER or not staff_roles):
        raise ApiError(403, "FORBIDDEN", "需要审核或管理权限。")
    row = session.get(ExplorationMaterial, material_id)
    if not row or row.organization_id != actor.organization_id:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的学习文件。")
    allowed = False
    if staff_roles and actor.entry_role != Role.LEARNER:
        # Reviewers need task evidence even when they cannot publish. The
        # authenticated staff role is organization-scoped by get_actor.
        allowed = True
    elif actor.has_role(Role.LEARNER):
        learner = get_learner_actor(actor)
        lock_catalog(session, learner)
        visible = {entry.task_id for entry in catalog(session, learner)}
        visible.update(session.scalars(select(ExplorationWork.task_id).where(ExplorationWork.organization_id == learner.organization_id,
            ExplorationWork.user_id == learner.id)))
        for task_id in visible:
            try:
                *_, snapshot = context(session, learner, task_id)
            except ApiError:
                continue
            resources = list(snapshot.content.get("materials", []))
            if (snapshot.content.get("completionMode") or "assessment") == "assessment":
                resources.extend(snapshot.content.get("taskFiles", []))
            if any(item.get("url") == "exploration-material:" + str(material_id) for item in resources):
                allowed = True
                break
    if not allowed:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的学习文件。")
    media = row.mime in {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp", "video/mp4", "video/webm", "video/ogg"}
    disposition = "inline" if inline and media and not re.search(r"\.(?:svgz?|html?|xhtml)$", row.name, re.I) else "attachment"
    headers = {"Content-Disposition": disposition + "; filename*=UTF-8''" + quote(row.name), "Accept-Ranges": "bytes",
        "ETag": '"' + row.sha256 + '"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    start, end, status = 0, row.size - 1, 200
    range_header = request.headers.get("range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or not any(match.groups()):
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{row.size}"})
        left, right = match.groups()
        start = int(left) if left else max(0, row.size - int(right))
        end = min(row.size - 1, int(right)) if left and right else row.size - 1
        if start >= row.size or end < start:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{row.size}"})
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{row.size}"
    headers["Content-Length"] = str(end - start + 1)
    data = b"" if request.method == "HEAD" else session.scalar(select(func.substr(ExplorationMaterial.content, start + 1, end - start + 1))
        .where(ExplorationMaterial.id == row.id))
    return Response(content=data, status_code=status,
        media_type=row.mime if disposition == "inline" else "application/octet-stream", headers=headers)
