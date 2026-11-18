"""Dynamic task evidence backed by the original durable document comment state machine.

Exploration rows retain each exact input/result; AISelfCheck owns the unique
document claim and the externally visible comment. No request is allowed to
retry an ambiguous comment dispatch, including a request with a fresh key.
"""
import hashlib
import json
import logging
import re
import traceback
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from journey_api import ai_self_check_clients as clients
from journey_api.ai_self_check_routes import claim, document_hash, restart_changed_document
from journey_api.ai_self_check_rules import protected_urls
from journey_api.exploration_ai_grading import SYSTEM_PROMPT_SCORED, grade_feedback
from journey_api.config import get_settings
from journey_api.errors import ApiError
from journey_api.exploration_ai_authorization import authorize_exploration_learner
from journey_api.exploration_models import ExplorationSelfCheck, ExplorationWork
from journey_api.idempotency import canonical_hash
from journey_api.learner_write_limits import enforce_learner_write_limit
from journey_api.models import (AISelfCheck, Assignment, AssignmentStatus, Enrollment,
    EnrollmentStatus)
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask

RULE_VERSION = "dynamic-exploration-publisher-scoring-v2"
ACTIVE = {AssignmentStatus.IN_PROGRESS, AssignmentStatus.NEEDS_REVISION}
logger = logging.getLogger(__name__)


def input_document(answer):
    """Accept one Feishu answer URL embedded in optional learner explanation."""
    found = []
    for match in re.finditer(r"https?://[^\s<>\"'，。；、！？（）【】)\]}]+", answer):
        url = match.group().rstrip("。，；、！？）)]}，：:;")
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            continue
        if host.endswith((".feishu.cn", ".larksuite.com")):
            clients.document_ref(url)
            clean = url.split("?", 1)[0].split("#", 1)[0]
            if clean not in found:
                found.append(clean)
    if len(found) > 1:
        raise ApiError(422, "MULTIPLE_SELF_CHECK_DOCUMENTS", "每次自测请只提供一份答题文档，可同时填写补充说明。")
    return found[0] if found else None


def attempt_id(actor, task_id, key):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"exploration-ai:{actor.organization_id}:{actor.id}:{task_id}:{key}")


def request_hash(body):
    return canonical_hash(body.model_dump(mode="json", exclude={"key", "idempotencyKey"}))


def replay(session, actor, body, key):
    row = session.get(ExplorationSelfCheck, attempt_id(actor, body.taskId, key))
    if row is None:
        return None
    if row.organization_id != actor.organization_id or row.user_id != actor.id:
        raise ApiError(404, "NOT_FOUND", "没有找到本次自测。")
    if (row.details or {}).get("requestHash") != request_hash(body):
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一幂等键不能用于不同请求。")
    target = (row.details or {}).get("canonicalRecordId")
    if target:
        canonical = session.get(ExplorationSelfCheck, uuid.UUID(target))
        if canonical and canonical.organization_id == actor.organization_id and canonical.user_id == actor.id:
            row = canonical
    refresh_document_record(session, row)
    return row


def record(row):
    details = row.details or {}
    grading = details.get("grading") or {}
    return dict(id=str(row.id), createdAt=row.created_at.isoformat(), body=row.answer,
        result=row.result, status=row.status, commentId=details.get("commentId"), mode="AI",
        taskVersionId=str(row.task_version_id), assignmentId=str(row.assignment_id),
        inputKind=details.get("inputKind", "text"), documentUrl=details.get("documentUrl"),
        commentStatus=details.get("commentStatus", "NOT_REQUIRED"),
        commentMessage=details.get("commentMessage", ""), errorMessage=details.get("errorMessage", ""),
        score=grading.get("score"), maxScore=grading.get("maxScore", 100),
        passed=grading.get("passed"), dimensions=grading.get("dimensions", []),
        taskCompleted=bool(details.get("completion")))


def _details(row, **values):
    row.details = {**(row.details or {}), **values}


def refresh_document_record(session, row):
    source_id = (row.details or {}).get("aiSelfCheckId")
    if not source_id:
        if row.status == "RUNNING" and row.created_at < datetime.now(UTC) - timedelta(minutes=10):
            row = session.scalar(select(ExplorationSelfCheck).where(ExplorationSelfCheck.id == row.id)
                .execution_options(populate_existing=True).with_for_update())
            if row.status != "RUNNING" or (row.details or {}).get("aiSelfCheckId"):
                return
            row.status, row.result = "FAILED", "本次自测等待超时，请重新进行自测。"
            _details(row, errorMessage=row.result,
                commentStatus="FAILED" if (row.details or {}).get("inputKind") == "document" else "NOT_REQUIRED",
                commentMessage="尚未发表评论。" if (row.details or {}).get("inputKind") == "document" else "")
        return
    # Source -> projection is the same lock order used by writers. A history
    # poll must not overwrite a just-completed attempt with its stale RUNNING
    # snapshot, or lose the analysisCompleted marker after a comment failure.
    source = session.scalar(select(AISelfCheck).where(AISelfCheck.id == uuid.UUID(source_id))
        .execution_options(populate_existing=True).with_for_update())
    if not source or source.attempt_id != row.id:
        return  # Prior attempts are immutable history, not the latest evaluation.
    row = session.scalar(select(ExplorationSelfCheck).where(ExplorationSelfCheck.id == row.id)
        .execution_options(populate_existing=True).with_for_update())
    if source.status == "RUNNING" and source.updated_at < datetime.now(UTC) - timedelta(minutes=10):
        # RUNNING has not dispatched a comment. Expire the abandoned lease so
        # the learner can deliberately retry with a fresh request. Never expire
        # SENDING/UNCERTAIN, whose external effect must be confirmed manually.
        source = session.scalar(select(AISelfCheck).where(AISelfCheck.id == source.id)
            .execution_options(populate_existing=True).with_for_update())
        if source.attempt_id != row.id:
            return
        if source.status == "RUNNING" and source.updated_at < datetime.now(UTC) - timedelta(minutes=10):
            source.status, source.error_message, source.updated_at = (
                "FAILED", "本次自测等待超时，未发表评论，请重新进行自测。", datetime.now(UTC))
    has_feedback = bool((row.details or {}).get("analysisCompleted") or
        source.result and source.status in {"SENDING", "COMPLETED", "UNCERTAIN"})
    row.status = "COMPLETED" if has_feedback else (
        "FAILED" if source.status == "FAILED" else "RUNNING")
    row.result = ((row.result or source.result) if has_feedback
        else source.error_message if source.status == "FAILED" else "")
    state = {"RUNNING": "PENDING", "SENDING": "PENDING", "COMPLETED": "SENT",
        "UNCERTAIN": "UNCERTAIN", "FAILED": "FAILED"}[source.status]
    messages = {"PENDING": "正在读取文档或确认标题评论，请勿重复发送。",
        "SENT": "评价已写入文档标题评论，并 @ 当前文档所有者。",
        "UNCERTAIN": "飞书评论结果尚未确认，已暂停重发，请联系管理员核对标题评论。",
        "FAILED": source.error_message or "标题评论未发送。"}
    _details(row, commentStatus=state, commentMessage=messages[state], commentId=source.comment_id,
        errorMessage=source.error_message)


def _new_record(session, actor, body, assignment_id, version_id, key, url):
    check_id = attempt_id(actor, body.taskId, key)
    details = dict(requestHash=request_hash(body), inputKind="document" if url else "text",
        documentUrl=url, commentStatus="PENDING" if url else "NOT_REQUIRED", assignmentRevision=body.revision)
    inserted = session.execute(insert(ExplorationSelfCheck).values(id=check_id,
        organization_id=actor.organization_id, user_id=actor.id, assignment_id=assignment_id,
        task_version_id=version_id, answer=body.answer, result="", status="RUNNING", details=details,
        created_at=datetime.now(UTC)).on_conflict_do_nothing(index_elements=["id"]).returning(ExplorationSelfCheck.id)).scalar()
    session.commit()  # Release task/enrollment locks BEFORE all external I/O.
    row = session.get(ExplorationSelfCheck, check_id, populate_existing=True)
    if (row.details or {}).get("requestHash") != request_hash(body):
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一幂等键不能用于不同请求。")
    session.commit()  # session.get above must not retain a connection during I/O.
    return row, inserted is not None


def _evidence(content, answer, document=None, references=None):
    from journey_api.ai_rubric_materials import prepare_ai_rubric
    def material(item):
        return {"title": item.get("name", ""), "text": item.get("text", ""),
            "url": item.get("url") if item.get("type") == "link" else None}
    evidence = {"task": {"title": content["title"], "description": content["summary"],
        "requirements": content.get("requirements", [])}, "answer": document.body if document else answer,
        "materials": [material(item) for item in content.get("materials", [])],
        "task_files": [material(item) for item in content.get("taskFiles", [])],
        "grading_policy": prepare_ai_rubric(content),
        "reference_documents": references or [],
        "read_scope": "已读取的答题正文、补充说明、任务说明及列出的飞书参考文档正文；其他外链、附件、图片和视频未读取。"}
    if document:
        evidence["learner_document"] = {"title": document.title, "body": document.body, "revision": document.revision}
        evidence["supplemental_text"] = answer
        evidence["body_character_count_excluding_whitespace"] = (document.body_character_count
            if document.body_character_count is not None else len(re.sub(r"\s", "", document.body)))
    else:
        evidence["read_scope"] = ("已提供的文字、任务说明及列出的飞书参考文档正文；其他外部链接、附件、图片和视频正文未读取。"
            if references else "已提供的文字和任务说明；外部链接、附件、图片和视频正文未读取。")
    evidence["read_scope"] += " grading_policy.reference_documents 中的评分文档已由服务端读取正文，可作为发布人员的评分依据。"
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    if len(serialized) > 100_000:
        raise ApiError(422, "AI_INPUT_TOO_LARGE", "文档和参考资料总量过大，尚未进行自测。")
    return evidence, serialized


def _reference_links(content):
    links = [(item.get("name", "参考资料"), item.get("url", "")) for item in
        [*content.get("materials", []), *content.get("taskFiles", []),
         *content.get("rubricAttachments", [])] if item.get("type") == "link"]
    if content.get("assessmentUrl"):
        links.append(("任务要求", content["assessmentUrl"]))
    seen = set()
    for label, url in links:
        try:
            ref = clients.document_ref(url)
        except ApiError:
            continue
        if ref not in seen:
            seen.add(ref)
            yield label, url, ref


def _rubric_source_refs(content):
    """Imported answer keys are private frozen evidence, never live references."""
    for item in content.get("rubricAttachments", []):
        if not item.get("sourceUrl"):
            continue
        try:
            yield clients.document_ref(item["sourceUrl"])
        except ApiError:
            continue


def _validate_current_assignment(session, actor, row):
    """Recheck the durable permission boundary immediately before saving SENDING."""
    permitted = authorize_exploration_learner(session, actor)
    current = session.scalar(select(Assignment).join(Enrollment)
        .where(Assignment.id == row.assignment_id, Assignment.organization_id == actor.organization_id,
            Enrollment.organization_id == actor.organization_id, Enrollment.learner_id == actor.id,
            Enrollment.status == EnrollmentStatus.ACTIVE)
        .execution_options(populate_existing=True).with_for_update(of=Assignment))
    work = session.scalar(select(ExplorationWork).where(ExplorationWork.assignment_id == row.assignment_id,
        ExplorationWork.organization_id == actor.organization_id, ExplorationWork.user_id == actor.id))
    if not current or not permitted or not work or current.task_version_id != row.task_version_id or current.status not in ACTIVE:
        raise ApiError(409, "AI_TASK_STATE_CHANGED", "任务版本、权限或状态已变化，未发表评论，请刷新后重试。")
    published = session.get(PublishedTaskContent, current.task_version_id)
    profile = session.get(ReviewAdminTask, current.task_definition_id, populate_existing=True)
    if (not published or published.content.get("completionMode") != "assessment"
            or published.content.get("reviewMode") != "ai" or not profile or profile.status == "deleted"):
        raise ApiError(409, "AI_TASK_STATE_CHANGED", "任务已不可自测，未发表评论，请刷新后重试。")


def _read_references(documents, resolved):
    references = []
    for label, kind, token in resolved:
        reference = documents.read_reference(kind, token)
        references.append(dict(label=label, title=reference.title, revision=reference.revision, body=reference.body))
    return references


def _failed(session, row_id, error, source_id=None, sending=False):
    session.rollback()
    row = session.get(ExplorationSelfCheck, row_id, populate_existing=True)
    if source_id:
        source = session.scalar(select(AISelfCheck).where(AISelfCheck.id == source_id).with_for_update())
        if source.attempt_id != row.id:
            _details(row, errorMessage="本次自测已被较新的请求替代，请查看最新记录。", commentStatus="FAILED",
                commentMessage="本次请求未发表评论。")
            row.status = "COMPLETED" if (row.details or {}).get("analysisCompleted") else "FAILED"
            session.commit()
            return row
        if source.status == "COMPLETED":
            refresh_document_record(session, row)
            session.commit()
            return row
        source.status = "UNCERTAIN" if sending and error.code != "FEISHU_DOCUMENT_ACCESS" else "FAILED"
        source.error_message, source.updated_at = error.message, datetime.now(UTC)
        refresh_document_record(session, row)
    else:
        if not (row.details or {}).get("analysisCompleted"):
            row.status, row.result = "FAILED", error.message
        _details(row, errorMessage=error.message,
            commentStatus="FAILED" if (row.details or {}).get("inputKind") == "document" else "NOT_REQUIRED",
            commentMessage="尚未发表评论。" if (row.details or {}).get("inputKind") == "document" else "")
    session.commit()
    return row


def _mark_superseded(session, source, current_id):
    rows = session.scalars(select(ExplorationSelfCheck).where(
        ExplorationSelfCheck.assignment_id == source.assignment_id,
        ExplorationSelfCheck.id != current_id,
        ExplorationSelfCheck.details["aiSelfCheckId"].as_string() == str(source.id),
        ExplorationSelfCheck.details["commentStatus"].as_string() == "PENDING").with_for_update())
    for old in rows:
        old.status = "COMPLETED" if (old.details or {}).get("analysisCompleted") else "FAILED"
        message = "本次自测已被较新的请求替代，请查看最新记录。"
        if not old.result:
            old.result = message
        _details(old, errorMessage=message, commentStatus="FAILED", commentMessage="本次请求未发表评论。")


def evaluate(session, actor, body, assignment, version, content, key):
    if content.get("completionMode") != "assessment" or assignment.status not in ACTIVE:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能进行 AI 自测。")
    if content.get("reviewMode") != "ai":
        raise ApiError(409, "AI_NOT_CONFIGURED", "本任务采用人工审核，未开启 AI 自测。")
    from journey_api.ai_rubric_materials import prepare_ai_rubric
    prepare_ai_rubric(content)  # Reject missing/unreadable publisher standards before model I/O.
    if not body.answer.strip():
        raise ApiError(422, "ANSWER_REQUIRED", "请填写测试结果或飞书答题文档链接后再进行自测。")
    url = input_document(body.answer)
    row, fresh = _new_record(session, actor, body, assignment.id, version.id, key, url)
    if not fresh:
        return replay(session, actor, body, key)
    row_id, source_id, sending = row.id, None, False
    stage = "prepare"
    try:
        enforce_learner_write_limit(actor, "ai")
        if not get_settings().ai_self_check_enabled:
            raise ApiError(503, "AI_UNAVAILABLE", "AI 自测当前未启用，请联系管理员检查模型配置。")
        reference_links = list(_reference_links(content))
        documents = clients.get_documents() if url or reference_links else None
        stage = "resolve_references"
        resolved = [(label, *documents.resolve_reference(link)) for label, link, _ in reference_links]
        if not url:
            stage = "read_references"
            references = _read_references(documents, resolved)
            stage = "prepare_evidence"
            evidence, serialized = _evidence(content, body.answer, references=references)
            stage = "score"
            reviewer = clients.get_reviewer()
            grading = grade_feedback(reviewer.review(SYSTEM_PROMPT_SCORED, evidence), content)
            grading.update(evidenceHash=hashlib.sha256(serialized.encode()).hexdigest(),
                model=getattr(reviewer, "last_model", None) or get_settings().ai_model)
            feedback = grading["feedback"]
            stage = "save_analysis"
            row = session.scalar(select(ExplorationSelfCheck).where(ExplorationSelfCheck.id == row_id)
                .execution_options(populate_existing=True).with_for_update())
            if row.status != "RUNNING":
                session.commit()
                return row
            row.status, row.result = "COMPLETED", feedback
            _details(row, analysisCompleted=True, grading=grading, gradingAnswer=body.answer)
            session.commit()
            stage = "validate_task"
            _validate_current_assignment(session, actor, row)
            session.commit()
            return row
        protected = {clients.document_ref(link) for link in protected_urls()} | set(_rubric_source_refs(content))
        if clients.document_ref(url) in protected:
            raise ApiError(422, "REFERENCE_DOCUMENT_NOT_SUBMISSION", "这是题目或参考材料，请填写你自己的答题文档链接。")
        stage = "resolve_document"
        token = documents.resolve(url)
        if clients.document_ref(url) in {ref for _, _, ref in reference_links}:
            raise ApiError(422, "REFERENCE_DOCUMENT_NOT_SUBMISSION", "这是题目或参考材料，请填写你自己的答题文档链接。")
        if token in {value for kind, value in protected if kind == "docx"} | {value for _, _, value in resolved}:
            raise ApiError(422, "REFERENCE_DOCUMENT_NOT_SUBMISSION", "这是题目或参考材料，请填写你自己的答题文档链接。")
        stage = "claim_document"
        source, claimed = claim(session, actor, row.assignment_id, token, url, row.id)
        document = None
        if not claimed and source.status == "COMPLETED":
            stage = "read_document"
            document = documents.read(token)
            stage = "claim_document"
            source, claimed = restart_changed_document(session, source, document, row.id)
        if not claimed:
            canonical = session.get(ExplorationSelfCheck, source.attempt_id)
            if canonical is None:
                # Legacy records retain a safe document-only input rather than
                # substituting another request's supplemental text.
                canonical = ExplorationSelfCheck(id=source.attempt_id, organization_id=actor.organization_id,
                    user_id=actor.id, assignment_id=source.assignment_id, task_version_id=row.task_version_id,
                    answer=source.document_url, result=source.result, status="RUNNING", created_at=source.created_at,
                    details=dict(inputKind="document", documentUrl=source.document_url, aiSelfCheckId=str(source.id)))
                session.add(canonical)
            _details(row, canonicalRecordId=str(canonical.id))
            refresh_document_record(session, canonical)
            session.commit()
            return canonical
        source_id = source.id
        _details(row, aiSelfCheckId=str(source.id))
        source.rule_version = RULE_VERSION
        _mark_superseded(session, source, row.id)
        session.commit()
        stage = "read_document"
        document = document or documents.read(token)
        if not document.body.strip():
            raise ApiError(422, "ANSWER_REQUIRED", "答题文档正文为空，请填写答案后再进行自测。")
        stage = "read_references"
        references = _read_references(documents, resolved)
        # Always mention a verified human owner for dynamic exploration. The
        # optional legacy switch must not turn this user requirement off.
        stage = "verify_owner"
        owner = documents.human_owner(document)
        if source.comment_id and not source.comment_reply_id:
            stage = "resolve_original_comment"
            previous = source.archived_results[-1]["result"] if source.archived_results else source.result
            source.comment_reply_id = documents.original_reply(document, source.comment_id, previous)
            session.commit()
        stage = "prepare_evidence"
        evidence, serialized = _evidence(content, body.answer, document, references)
        stage = "score"
        reviewer = clients.get_reviewer()
        grading = grade_feedback(reviewer.review(SYSTEM_PROMPT_SCORED, evidence), content)
        grading.update(evidenceHash=hashlib.sha256(serialized.encode()).hexdigest(),
            model=getattr(reviewer, "last_model", None) or get_settings().ai_model)
        feedback = grading["feedback"]
        stage = "save_analysis"
        source = session.scalar(select(AISelfCheck).where(AISelfCheck.id == source_id)
            .execution_options(populate_existing=True).with_for_update())
        if source.attempt_id != row.id or source.status != "RUNNING":
            raise ApiError(409, "AI_ATTEMPT_SUPERSEDED", "自测状态已更新，请查看历史记录。")
        source.result, row.result, row.status = feedback, feedback, "COMPLETED"
        _details(row, analysisCompleted=True, grading=grading, gradingAnswer=document.body,
            gradingDocument=dict(url=url, revision=document.revision, sha256=document_hash(document)))
        session.commit()  # Feedback survives even if later comment validation fails.
        stage = "validate_document"
        documents.ensure_owner(document, owner)
        documents.ensure_revision(document)
        stage = "validate_task"
        _validate_current_assignment(session, actor, row)
        stage = "save_comment_intent"
        _details(row, gradingDocumentValidated=True)
        source = session.scalar(select(AISelfCheck).where(AISelfCheck.id == source_id)
            .execution_options(populate_existing=True).with_for_update())
        if source.attempt_id != row.id or source.status != "RUNNING":
            raise ApiError(409, "AI_ATTEMPT_SUPERSEDED", "自测状态已更新，请查看历史记录。")
        source.status, source.result = "SENDING", feedback
        source.model = getattr(reviewer, "last_model", None) or get_settings().ai_model
        source.document_revision, source.document_hash = document.revision, document_hash(document)
        source.input_hash, source.updated_at = hashlib.sha256(serialized.encode()).hexdigest(), datetime.now(UTC)
        refresh_document_record(session, row)
        session.commit()  # Result and SENDING are durable before the side effect.
        sending = True
        stage = "send_comment"
        if source.comment_id:
            comment_id = documents.update_title_comment(document, source.comment_id, source.comment_reply_id, feedback, (owner,))
        else:
            comment_id = documents.comment_on_title(document, feedback, (owner,))
        stage = "save_comment_receipt"
        source = session.get(AISelfCheck, source_id, populate_existing=True)
        source.status, source.comment_id, source.updated_at = "COMPLETED", comment_id, datetime.now(UTC)
        refresh_document_record(session, row)
        session.commit()
        return row
    except Exception as exc:
        # Exception messages and repr/locals may contain document bodies,
        # provider payloads or credentials. Retain only diagnostic metadata.
        logger.error(json.dumps({
            "event": "exploration.self_check_failed", "record_id": str(row_id),
            "stage": stage, "error_type": type(exc).__name__,
            "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None,
            "error_code": exc.code if isinstance(exc, ApiError) else "AI_SELF_CHECK_FAILED",
            "frames": [{"file": frame.filename.replace("\\", "/").rsplit("/", 1)[-1],
                        "function": frame.name, "line": frame.lineno}
                       for frame in traceback.extract_tb(exc.__traceback__)[-6:]],
        }))
        error = exc if isinstance(exc, ApiError) else ApiError(502, "AI_SELF_CHECK_FAILED", "自测未完成，请稍后重试或联系管理员。")
        read_failures = {
            "read_document": "飞书答题文档暂时读取失败，尚未进行 AI 评分，请稍后重试。",
            "read_references": "飞书参考材料暂时读取失败，尚未进行 AI 评分，请稍后重试。",
            "verify_owner": "飞书文档所有者暂时无法核实，尚未进行 AI 评分，请稍后重试。",
            "resolve_original_comment": "原有标题评论暂时读取失败，尚未进行 AI 评分，请稍后重试。",
        }
        if error.code == "FEISHU_REQUEST_FAILED" and stage in read_failures:
            error = ApiError(error.status_code, error.code, read_failures[stage],
                details=error.details, retryable=error.retryable)
        return _failed(session, row_id, error, source_id, sending)
