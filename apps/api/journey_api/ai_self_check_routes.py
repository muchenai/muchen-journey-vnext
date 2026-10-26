"""Local self-check integration, isolated from submissions and reviewer decisions."""
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from journey_api.ai_self_check_clients import (
    AI_UNAVAILABLE_MESSAGE, AIReviewer, FeishuDocuments, document_ref, get_documents, get_reviewer,
)
from journey_api.ai_self_check_rules import (
    RULE_VERSION, SYSTEM_PROMPT, evidence_for, protected_urls, references_for, render_feedback,
)
from journey_api.ai_task_alignment import TASK_NAMES, ensure_task_questions
from journey_api.auth import Actor, get_learner_actor
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.journey_service import lock_active_learner_assignment
from journey_api.learner_write_limits import enforce_learner_write_limit
from journey_api.models import AISelfCheck, Assignment, AuditEntry, Enrollment, TaskDefinition

router = APIRouter(prefix="/api/v1/me/assignments")


class SelfCheckCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_url: str = Field(min_length=10, max_length=2000)
    # A fresh user click has a fresh UUID; retransmitting that click must not
    # rerun the model or update the comment again.
    request_id: uuid.UUID | None = None


def public_record(row: AISelfCheck) -> dict:
    error_message = row.error_message
    if error_message == "AI 接口暂时不可用，请联系管理员检查模型、额度和网络。":
        error_message = AI_UNAVAILABLE_MESSAGE
    labels = {
        "RUNNING": "AI 正在读取文档并生成评价，请稍后查看历史记录。",
        "SENDING": "正在确认飞书标题评论结果，请勿重复提交。若长时间未更新，请联系管理员核对。",
        "UNCERTAIN": "飞书评论结果尚未确认，已暂停重发。请联系管理员核对文档标题评论。",
        "FAILED": error_message or "自查未完成，尚未发表评论，可重试。",
    }
    return {"id": str(row.id), "createdAt": row.created_at.isoformat(),
            "body": row.document_url, "status": row.status,
            "result": row.result if row.status == "COMPLETED" else labels.get(row.status, "自查未完成"),
            "commentId": row.comment_id, "documentRevision": row.document_revision}


def document_hash(document) -> str:
    content = json.dumps([document.title, document.body, document.body_character_count], ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def restart_changed_document(session: Session, row: AISelfCheck, document,
                             request_id: uuid.UUID | None = None) -> tuple[AISelfCheck, bool]:
    previous_attempt = row.attempt_id
    # The network read occurred without a lock; another caller may have claimed
    # or completed a newer evaluation meanwhile. Never overwrite that attempt.
    row = session.scalar(select(AISelfCheck).where(AISelfCheck.id == row.id)
                         .execution_options(populate_existing=True).with_for_update())
    if row.status != "COMPLETED" or row.attempt_id != previous_attempt:
        session.commit()
        return row, False
    if request_id and (row.attempt_id == request_id
                       or any(entry.get("id") == str(request_id) for entry in row.archived_results or [])):
        session.commit()
        return row, False
    unchanged = (row.document_hash == document_hash(document) if row.document_hash
                 else row.document_revision == document.revision)
    if request_id is None and unchanged and row.rule_version == RULE_VERSION:
        # Populate content fingerprints for pre-migration completed records.
        row.document_hash = document_hash(document)
        session.commit()
        return row, False
    snapshot = {**public_record(row), "id": str(row.attempt_id),
                "model": row.model, "generatedAt": row.updated_at.isoformat()}
    row.archived_results = [*(row.archived_results or []), snapshot]
    row.status, row.attempt_id = "RUNNING", request_id or uuid.uuid4()
    row.created_at = row.updated_at = datetime.now(UTC)
    row.result, row.error_message = "", ""
    row.model, row.rule_version = get_settings().ai_model, RULE_VERSION
    session.commit()
    return row, True


@router.get("/{assignment_id}/ai-self-checks")
def history(assignment_id: uuid.UUID, request: Request, actor: Actor = Depends(get_learner_actor),
            session: Session = Depends(get_db)):
    exists = session.scalar(select(Assignment.id).join(Enrollment).where(
        Assignment.id == assignment_id, Assignment.organization_id == actor.organization_id,
        Enrollment.learner_id == actor.id, Enrollment.organization_id == actor.organization_id))
    if exists is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    rows = session.scalars(select(AISelfCheck).where(
        AISelfCheck.assignment_id == assignment_id, AISelfCheck.organization_id == actor.organization_id,
        AISelfCheck.learner_id == actor.id).order_by(AISelfCheck.created_at.desc()).limit(50)).all()
    records = [entry for row in rows for entry in [public_record(row), *(row.archived_results or [])]]
    records.sort(key=lambda entry: entry["createdAt"], reverse=True)
    return {"data": records, "request_id": request.state.request_id}


def claim(session: Session, actor: Actor, assignment_id: uuid.UUID, token: str, url: str,
          request_id: uuid.UUID | None = None) -> tuple[AISelfCheck, bool]:
    now = datetime.now(UTC)
    new_id = uuid.uuid4()
    session.execute(insert(AISelfCheck).values(
        id=new_id, organization_id=actor.organization_id, learner_id=actor.id,
        assignment_id=assignment_id, document_token=token, document_url=url,
        status="RUNNING", attempt_id=request_id or uuid.uuid4(), model=get_settings().ai_model,
        rule_version=RULE_VERSION, created_at=now, updated_at=now,
    ).on_conflict_do_nothing(constraint="uq_ai_self_check_document"))
    row = session.scalar(select(AISelfCheck).where(
        AISelfCheck.organization_id == actor.organization_id, AISelfCheck.document_token == token
    ).with_for_update())
    assert row is not None
    if row.learner_id != actor.id or row.assignment_id != assignment_id:
        if reuse_authorized_local_test_document(session, row, actor, assignment_id):
            # Release only the unique claim, retaining the original record,
            # owner, URL and evaluations for learner/reviewer history reads.
            previous = row
            previous.document_token = f"local-archive:{previous.id}"
            session.flush()
            row = AISelfCheck(
                id=new_id, organization_id=actor.organization_id,
                learner_id=actor.id, assignment_id=assignment_id,
                document_token=token, document_url=url, status="RUNNING",
                attempt_id=request_id or uuid.uuid4(), archived_results=[],
                model=get_settings().ai_model, rule_version=RULE_VERSION,
                created_at=now, updated_at=now,
                comment_id=previous.comment_id, comment_reply_id=previous.comment_reply_id,
                # Needed only to resolve legacy comments lacking a reply ID.
                result=previous.result if previous.comment_id and not previous.comment_reply_id else "",
            )
            session.add(row)
            session.commit()
            return row, True
        session.rollback()
        raise ApiError(409, "DOCUMENT_ALREADY_CLAIMED", "该文档已用于其他任务或账号的自查，请使用自己的当前任务文档。")
    if row.id == new_id:
        session.commit()
        return row, True
    if request_id and (row.attempt_id == request_id
                       or any(entry.get("id") == str(request_id) for entry in row.archived_results or [])):
        session.commit()
        return row, False
    if row.status == "FAILED" or (row.status == "RUNNING" and row.updated_at < now - timedelta(minutes=10)):
        row.status, row.attempt_id, row.updated_at = "RUNNING", request_id or uuid.uuid4(), now
        row.created_at = now
        row.error_message = ""
        # A retry may still need the prior comment text to resolve its reply.
        # Never lose that anchor before the reply ID has been saved.
        if not row.comment_id or row.comment_reply_id:
            row.result = ""
        row.model, row.rule_version = get_settings().ai_model, RULE_VERSION
        session.commit()
        return row, True
    session.commit()
    return row, False


def reuse_authorized_local_test_document(
    session: Session, row: AISelfCheck, actor: Actor, assignment_id: uuid.UUID,
) -> bool:
    """Honor only an explicit administrator-created LOCAL test reset receipt."""
    if get_settings().app_env != "local" or row.status != "COMPLETED":
        return False
    authorization = session.scalar(select(AuditEntry).where(
        AuditEntry.organization_id == actor.organization_id,
        AuditEntry.resource_id == row.id,
        AuditEntry.action == "local_test.self_check_reuse_authorized",
        AuditEntry.result == "SUCCESS",
    ).order_by(AuditEntry.occurred_at.desc()).limit(1))
    if authorization is None:
        return False
    expected = {
        "previous_learner_id": str(row.learner_id),
        "previous_assignment_id": str(row.assignment_id),
        "new_learner_id": str(actor.id),
        "new_assignment_id": str(assignment_id),
    }
    if any(authorization.details.get(key) != value for key, value in expected.items()):
        return False
    source = session.get(Assignment, row.assignment_id)
    target = session.get(Assignment, assignment_id)
    return bool(source and target and source.organization_id == actor.organization_id
                and target.organization_id == actor.organization_id
                and source.task_version_id == target.task_version_id)


@router.post("/{assignment_id}/ai-self-checks")
def self_check(assignment_id: uuid.UUID, command: SelfCheckCommand, request: Request,
               actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db),
               documents: FeishuDocuments = Depends(get_documents), reviewer: AIReviewer = Depends(get_reviewer)):
    if not get_settings().ai_self_check_enabled:
        raise ApiError(503, "AI_SELF_CHECK_DISABLED", "AI 自查尚未启用，请联系管理员。")
    assignment, _ = lock_active_learner_assignment(session, actor, assignment_id, allow_completed_material_review=True)
    definition = session.get(TaskDefinition, assignment.task_definition_id)
    stage = definition.stable_key
    reference_links = references_for(stage)
    session.commit()  # No enrollment/assignment locks or connections during network I/O.
    document_ref(command.document_url)
    enforce_learner_write_limit(actor, "ai")
    # Never comment on the supplied answer keys, source materials or task templates.
    protected = {document_ref(url) for url in protected_urls()}
    if document_ref(command.document_url) in protected:
        raise ApiError(422, "REFERENCE_DOCUMENT_NOT_SUBMISSION", "这是题目或参考材料，请填写你自己的答题文档链接。")
    token = documents.resolve(command.document_url)
    protected_doc_tokens = {t for kind, t in protected if kind == "docx"}
    resolved_references = [(label, *documents.resolve_reference(url)) for label, url in reference_links]
    if token in protected_doc_tokens | {t for _, _, t in resolved_references}:
        raise ApiError(422, "REFERENCE_DOCUMENT_NOT_SUBMISSION", "这是题目或参考材料，请填写你自己的答题文档链接。")
    # Preserve the supplied tenant URL for the user's history; strip tracking query and fragment.
    source_url = command.document_url.strip().removeprefix("飞书文档：").strip().split("?", 1)[0].split("#", 1)[0]
    document = None
    references = None

    def read_references():
        entries = []
        for label, reference_kind, reference_token in resolved_references:
            reference = documents.read_reference(reference_kind, reference_token)
            entries.append({"label": label, "title": reference.title,
                            "revision": reference.revision, "body": reference.body})
        return entries

    if stage in TASK_NAMES:
        # Do not reserve a wrong document for this assignment: it must remain
        # available to its actual task after the learner corrects the link.
        document = documents.read(token)
        references = read_references()
        ensure_task_questions(stage, document.body, references)
    row, claimed = claim(session, actor, assignment_id, token, source_url, command.request_id)
    if not claimed and row.status == "COMPLETED":
        document = document or documents.read(token)
        references = references if references is not None else read_references()
        # Validate before cached-result reuse, including documents evaluated by
        # older versions that had no task-identity check.
        ensure_task_questions(stage, document.body, references)
        row, claimed = restart_changed_document(session, row, document, command.request_id)
    if not claimed:
        return {"data": public_record(row), "request_id": request.state.request_id}
    row_id, attempt_id = row.id, row.attempt_id
    sending = False
    try:
        document = document or documents.read(token)
        references = references if references is not None else read_references()
        ensure_task_questions(stage, document.body, references)
        owner = documents.human_owner(document) if get_settings().ai_comment_mention_owner else None
        # Resolve the original root reply before model work. Missing/deleted
        # comments or permissions must never fall back to creating a second one.
        if row.comment_id and not row.comment_reply_id:
            previous = row.archived_results[-1]["result"] if row.archived_results else row.result
            row.comment_reply_id = documents.original_reply(document, row.comment_id, previous)
            session.commit()
        evidence = evidence_for(stage, document, references)
        serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
        if len(serialized) > 100_000:
            raise ApiError(422, "AI_INPUT_TOO_LARGE", "文档和参考资料总量过大，尚未进行自查。")
        feedback = render_feedback(reviewer.review(SYSTEM_PROMPT, evidence), stage, document.body, document.body_character_count)
        if owner is not None:
            documents.ensure_owner(document, owner)
        documents.ensure_revision(document)
        row = session.scalar(select(AISelfCheck).where(AISelfCheck.id == row_id).with_for_update())
        if row.attempt_id != attempt_id or row.status != "RUNNING":
            session.rollback()
            raise ApiError(409, "AI_ATTEMPT_SUPERSEDED", "自查状态已更新，请查看历史记录。")
        row.status, row.result = "SENDING", feedback
        row.model = getattr(reviewer, "last_model", None) or get_settings().ai_model
        row.document_revision = document.revision
        row.document_hash = document_hash(document)
        row.input_hash = hashlib.sha256(serialized.encode()).hexdigest()
        row.updated_at = datetime.now(UTC)
        session.commit()  # Durable BEFORE the one and only external side effect.
        sending = True
        if row.comment_id:
            comment_id = documents.update_title_comment(document, row.comment_id, row.comment_reply_id,
                                                         feedback, (owner,) if owner else ())
        else:
            comment_id = (documents.comment_on_title(document, feedback, (owner,))
                          if owner is not None
                          else documents.comment_on_title(document, feedback))
        row = session.get(AISelfCheck, row_id)
        row.comment_id, row.status, row.updated_at = comment_id, "COMPLETED", datetime.now(UTC)
        session.commit()
        return {"data": public_record(row), "request_id": request.state.request_id}
    except Exception as exc:
        session.rollback()
        row = session.scalar(select(AISelfCheck).where(AISelfCheck.id == row_id).with_for_update())
        error = exc if isinstance(exc, ApiError) else ApiError(502, "AI_SELF_CHECK_FAILED", "自查未完成，请稍后重试或联系管理员。")
        if row.attempt_id == attempt_id and row.status != "COMPLETED":
            # Feishu's explicit nonzero error means rejection; transport errors
            # after dispatch are ambiguous and must NEVER cause an automatic resend.
            uncertain = sending and error.code != "FEISHU_DOCUMENT_ACCESS"
            row.status = "UNCERTAIN" if uncertain else "FAILED"
            row.error_message, row.updated_at = error.message, datetime.now(UTC)
            session.commit()
            if uncertain:
                raise ApiError(502, "AI_COMMENT_UNCERTAIN", public_record(row)["result"]) from exc
        else:
            session.rollback()
        raise error from exc
