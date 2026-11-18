"""Freeze a readable Feishu answer document as ordinary private rubric bytes.

Only the existing Feishu document reader performs external I/O. Importing never
uses AI, writes a document comment, or follows the supplied host as an HTTP URL.
The resulting source fields are provenance metadata, not a signature: publishers
may also provide their own scoring files.
"""
from __future__ import annotations

import base64
import re
from urllib.parse import urlsplit
import uuid

from journey_api.ai_rubric_materials import _readable_body
from journey_api.errors import ApiError

MAX_SOURCE_TITLE = 240
MAX_SOURCE_REVISION = 100


def validate_rubric_source_url(value: str) -> str:
    """Validate the same modern document references supported by the reader."""
    from journey_api.ai_self_check_clients import document_ref

    value = value.strip()
    try:
        document_ref(value)
        # ``document_ref`` also accepts a human-readable prefix for learner
        # input; persisted provenance must be an actual HTTPS URL.
        if urlsplit(value).scheme != "https":
            raise ValueError("not a URL")
    except (ApiError, ValueError) as exc:
        raise ApiError(422, "AI_RUBRIC_SOURCE_INVALID",
            "请输入有效的标准答案文档飞书链接，仅支持新版飞书文字文档或知识库中的文字文档。") from exc
    return value


def _import_error(error: ApiError) -> ApiError:
    """Translate shared learner/comment errors into the importing context."""
    if error.code == "UNSUPPORTED_WIKI_DOCUMENT":
        return ApiError(422, "AI_RUBRIC_SOURCE_UNSUPPORTED",
            "标准答案文档仅支持新版飞书文字文档，请选择文字文档或指向文字文档的知识库链接。")
    if error.code == "FEISHU_DOCUMENT_ACCESS":
        return ApiError(403, "AI_RUBRIC_SOURCE_ACCESS",
            "无法读取标准答案文档，请确认飞书应用具有文档读取权限，且该文档已授权给应用访问。")
    if error.code == "FEISHU_APP_NOT_CONFIGURED":
        return ApiError(503, "AI_RUBRIC_SOURCE_UNAVAILABLE",
            "标准答案文档读取服务暂不可用，请联系管理员检查飞书应用配置。")
    if error.code == "DOCUMENT_CHANGED":
        return ApiError(409, "AI_RUBRIC_SOURCE_CHANGED",
            "读取期间标准答案文档发生了修改，请重新导入以保存一致的文档版本。", retryable=True)
    if error.code == "DOCUMENT_TOO_LARGE":
        return ApiError(422, "AI_RUBRIC_SOURCE_TOO_LARGE",
            "标准答案文档内容过多，未能完整读取，请精简为 20,000 字以内后重试。")
    if error.code == "DOCUMENT_REQUIRES_TEXT":
        return ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            "标准答案文档包含图片、嵌入表格或附件等无法完整读取的内容，请将标准答案整理为可读取文字后重新导入。")
    if error.code == "DOCUMENT_SIZE_UNSUPPORTED":
        return ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            "标准答案文档正文为空或过长，请提供含可读取文字且不超过 20,000 字的文档。")
    if error.code == "DOCUMENT_INCOMPLETE":
        return ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            "标准答案文档的结构或内容未能完整读取，请检查文档及嵌入内容后重新导入。")
    if error.code in {"DOCUMENT_REVISION_MISSING", "DOCUMENT_TITLE_MISSING"}:
        return ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            "无法完整读取标准答案文档的标题、版本或正文，请检查文档后重新导入。")
    return ApiError(502, "AI_RUBRIC_SOURCE_UNAVAILABLE",
        "标准答案文档读取失败，请确认文档仍然存在并已授权给应用访问，稍后重新导入。",
        retryable=error.retryable)


def _source_title(value: str) -> str:
    # Titles can contain newlines and filename characters; metadata and download
    # names should remain single-line text on all supported operating systems.
    value = re.sub(r"[\x00-\x1f\x7f\ud800-\udfff]", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:MAX_SOURCE_TITLE] or "标准答案"


def _filename(title: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "_", title).strip(" .")
    value = re.sub(r"\.txt$", "", value, flags=re.IGNORECASE).rstrip(" .")
    value = value[:156].rstrip(" .") or "标准答案"
    # Avoid Windows device names while leaving ordinary titles unchanged.
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value, flags=re.IGNORECASE):
        value = "_" + value
    return value + ".txt"


def import_rubric_document(url: str, *, documents=None) -> dict:
    """Read once and return a TXT scoring attachment from authoritative bytes."""
    from journey_api.ai_self_check_clients import TOKEN, get_documents

    source = validate_rubric_source_url(url)
    try:
        client = documents if documents is not None else get_documents()
        token = client.resolve(source)
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise ApiError(422, "UNSUPPORTED_WIKI_DOCUMENT", "Unsupported document")
        document = client.read(token)
    except ApiError as exc:
        raise _import_error(exc) from exc
    except (TimeoutError, ConnectionError, OSError) as exc:
        raise ApiError(502, "AI_RUBRIC_SOURCE_UNAVAILABLE",
            "标准答案文档读取超时或连接失败，请稍后重新导入。", retryable=True) from exc

    if (document.token != token or not isinstance(document.title, str)
            or not isinstance(document.body, str) or not isinstance(document.revision, str)
            or len(document.revision) > MAX_SOURCE_REVISION or not re.fullmatch(r"[0-9]+", document.revision)):
        raise ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            "无法完整读取标准答案文档的标题、版本或正文，请检查文档后重新导入。")
    title = _source_title(document.title)
    try:
        body = _readable_body(document.body, title)
    except ApiError as exc:
        raise ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            exc.message.replace("评分文档", "标准答案文档")) from exc
    try:
        original = body.encode("utf-8")
    except UnicodeError as exc:
        raise ApiError(422, "AI_RUBRIC_SOURCE_UNREADABLE",
            "标准答案文档包含无法识别的文字，请检查文档正文后重新导入。") from exc
    return {
        "id": str(uuid.uuid4()),
        "name": _filename(title),
        "type": "file",
        "url": "data:text/plain;base64," + base64.b64encode(original).decode("ascii"),
        "mime": "text/plain",
        "size": len(original),
        "sourceUrl": f"https://{urlsplit(source).hostname}/docx/{token}",
        "sourceRevision": document.revision,
        "sourceTitle": title,
    }
