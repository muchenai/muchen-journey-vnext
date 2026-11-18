"""Bounded server-side integrations. Never follow redirects with credentials."""
from __future__ import annotations

import json
import logging
import math
import re
import ssl
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from http.client import HTTPException, IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from journey_api.config import Settings, get_settings
from journey_api.errors import ApiError

AI_UNAVAILABLE_MESSAGE = "AI 接口暂时不可用，请联系管理员进行检查"
LOW_REASONING_MODELS = {"deepseek-v4.1-flash", "deepseek-v4-flash-0731", "deepseek-v4-pro-0813"}
logger = logging.getLogger(__name__)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_feishu_read(url: str, method: str, body: dict | None) -> bool:
    """Only official read requests may wait longer or repeat after interruption."""
    try:
        target = urlsplit(url)
        if (target.scheme != "https" or target.hostname != "open.feishu.cn"
                or target.port not in {None, 443} or target.username or target.password or target.fragment):
            return False
        if method == "GET" and body is None:
            return True
        if method != "POST" or not isinstance(body, dict):
            return False
        query = parse_qsl(target.query, keep_blank_values=True, strict_parsing=True)
        if (target.path == "/open-apis/drive/v1/metas/batch_query"
                and query == [("user_id_type", "open_id")] and set(body) == {"request_docs"}):
            requested = body["request_docs"]
            return (isinstance(requested, list) and 1 <= len(requested) <= 50
                    and all(isinstance(item, dict) and set(item) == {"doc_token", "doc_type"}
                            and item["doc_type"] == "docx" and isinstance(item["doc_token"], str)
                            and TOKEN.fullmatch(item["doc_token"]) for item in requested))
        if (re.fullmatch(r"/open-apis/drive/v1/files/[A-Za-z0-9]{10,100}/comments/batch_query", target.path)
                and query == [("file_type", "docx")] and set(body) == {"comment_ids"}):
            requested = body["comment_ids"]
            return (isinstance(requested, list) and len(requested) == 1
                    and isinstance(requested[0], str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,160}", requested[0])))
        return False
    except ValueError:
        return False


def request_json(url: str, *, token: str = "", body: dict | None = None,
                 timeout: float | None = None, service: str = "FEISHU", method: str | None = None) -> dict:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request_method = (method or ("POST" if body is not None else "GET")).upper()
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                      headers=headers, method=request_method)
    read_only = service == "FEISHU" and _is_feishu_read(url, request_method, body)
    request_timeout = timeout if timeout is not None else (60 if read_only else 20)
    # Retry reads only. A failed comment write may already have reached Feishu,
    # and model generation has its own bounded retry policy in AIReviewer.
    attempts = 2 if read_only else 1
    for attempt in range(attempts):
        try:
            with build_opener(NoRedirect()).open(request, timeout=request_timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("oversized response")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("unexpected response")
            return result
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, HTTPException) as exc:
            status = exc.code if isinstance(exc, HTTPError) else None
            reason = exc.reason if isinstance(exc, URLError) else exc
            transient = (status in {408, 429, 500, 502, 503, 504} if status is not None else
                         isinstance(exc, (URLError, TimeoutError, OSError, IncompleteRead))
                         and not isinstance(reason, ssl.SSLCertVerificationError))
            if transient and attempt + 1 < attempts:
                if isinstance(exc, HTTPError):
                    exc.close()
                continue
            if service == "FEISHU" and isinstance(exc, HTTPError) and 400 <= exc.code < 500:
                # Preserve explicit permission failures, never their private body.
                try:
                    rejected = json.loads(exc.read(65_536))
                    if isinstance(rejected, dict) and isinstance(rejected.get("code"), int) and rejected["code"] != 0:
                        return {"code": rejected["code"]}
                except (ValueError, OSError, HTTPException):
                    pass
                finally:
                    exc.close()
            elif isinstance(exc, HTTPError):
                exc.close()
            # Provider bodies may contain credentials or private input. Do not echo them.
            raise ApiError(502, f"{service}_REQUEST_FAILED",
                           (AI_UNAVAILABLE_MESSAGE if service == "AI"
                            else "飞书接口未返回可确认的结果，请稍后重试或联系管理员。"),
                           details={"upstream_status": status},
                           retryable=transient if service == "AI" else True) from exc


TOKEN = re.compile(r"^[A-Za-z0-9]{10,100}$")
OPEN_ID = re.compile(r"^ou_[A-Za-z0-9]{10,100}$")


@dataclass(frozen=True)
class HumanRecipient:
    """Identity verified through this document application's contact API."""
    open_id: str


def title_comment_elements(text: str, recipients: tuple[HumanRecipient, ...]) -> list[dict]:
    if not text or len(text) > 9_800:
        raise ApiError(422, "COMMENT_TOO_LARGE", "评价内容超出评论长度限制，尚未发表评论。")
    ids = list(dict.fromkeys(recipient.open_id for recipient in recipients))
    if len(ids) > 1 or any(not OPEN_ID.fullmatch(value) for value in ids):
        raise ApiError(422, "OWNER_IDENTITY_UNRESOLVED", "文档所有者身份尚未核实，尚未发表评论。")
    elements = [{"type": "text", "text": text[i:i + 900]} for i in range(0, len(text), 900)]
    if ids:
        elements.append({"type": "text", "text": "\n\nAI 自查已完成，请文档所有者查看评价："})
        for open_id in ids:
            elements.extend([{"type": "mention_user", "mention_user": open_id},
                             {"type": "text", "text": " "}])
    return elements


def document_ref(value: str) -> tuple[str, str]:
    value = value.strip().removeprefix("飞书文档：").strip()
    try:
        url = urlsplit(value)
        segments = url.path.strip("/").split("/")
        valid = (url.scheme == "https" and url.hostname
                 and (url.hostname.endswith(".feishu.cn") or url.hostname.endswith(".larksuite.com"))
                 and not url.username and not url.password and url.port in {None, 443}
                 and len(segments) == 2 and segments[0] in {"docx", "wiki"}
                 and TOKEN.fullmatch(segments[1]) and not any(c.isspace() for c in value))
        if valid:
            return segments[0], segments[1]
    except ValueError:
        pass
    raise ApiError(422, "INVALID_SELF_CHECK_DOCUMENT", "请输入一个有效飞书文档或知识库链接。")


@dataclass(frozen=True)
class Document:
    token: str
    title_block_id: str
    title: str
    body: str
    revision: str
    body_character_count: int | None = None


def blocks_to_document(token: str, blocks: list[dict], revision: str) -> Document:
    by_id = {block["block_id"]: block for block in blocks}
    roots = [block for block in blocks if block.get("block_type") == 1]
    if len(roots) != 1:
        raise ApiError(422, "DOCUMENT_TITLE_MISSING", "无法定位文档标题，未发表评论。")
    root = roots[0]

    def text_of(block: dict) -> str:
        values = []
        for value in block.values():
            if not isinstance(value, dict):
                continue
            for element in value.get("elements", []):
                if "text_run" in element:
                    values.append(element["text_run"].get("content", ""))
                elif "equation" in element:
                    values.append(element["equation"].get("content", ""))
                elif "mention_doc" in element:
                    values.append(element["mention_doc"].get("title", "[文档引用]"))
                elif "mention_user" in element:
                    values.append("[人员引用]")
        return "".join(values)

    seen: set[str] = set()
    lines: list[str] = []
    # Structural containers are traversed; images, sheets and attachments cannot
    # silently disappear from an assessment that claims to read the whole answer.
    supported = {"page", "text", "bullet", "ordered", "code", "quote", "todo", "callout",
                 "divider", "grid", "grid_column", "table", "table_cell", "quote_container"}
    supported.update(f"heading{i}" for i in range(1, 10))

    def walk(block_id: str, ordered_number: int | None = None) -> None:
        if block_id in seen or block_id not in by_id:
            raise ApiError(422, "DOCUMENT_INCOMPLETE", "文档结构不完整，请稍后重试。")
        seen.add(block_id)
        block = by_id[block_id]
        if not supported.intersection(block):
            raise ApiError(422, "DOCUMENT_REQUIRES_TEXT",
                           "文档包含图片、嵌入表格或附件等当前无法完整读取的内容。请将待自查答案整理为文字后再试，尚未发表评论。")
        if block_id != root["block_id"]:
            text = text_of(block)
            if text:
                if ordered_number is not None:
                    text = f"{ordered_number}. {text}"
                lines.append(text)
        ordered_number = 0
        for child in block.get("children", []):
            child_block = by_id.get(child, {})
            if "ordered" in child_block:
                sequence = str(child_block["ordered"].get("style", {}).get("sequence", "auto"))
                ordered_number = int(sequence) if sequence.isdigit() else ordered_number + 1
                walk(child, ordered_number)
            else:
                ordered_number = 0
                walk(child)
            if "table_cell" in child_block:
                lines.append("\t")

    walk(root["block_id"])
    if len(seen) != len(by_id):
        raise ApiError(422, "DOCUMENT_INCOMPLETE", "文档部分内容未能读取，尚未发表评论。")
    body = "\n".join(lines).strip()
    if not body or len(body) > 60_000:
        raise ApiError(422, "DOCUMENT_SIZE_UNSUPPORTED", "文档正文为空或超过本地自查的 60000 字限制。")
    actual_count = sum(len(re.sub(r"\s", "", text_of(block))) for block in blocks
                       if block["block_id"] != root["block_id"])
    return Document(token, root["block_id"], text_of(root), body, revision, actual_count)


def slides_to_reference(token: str, presentation: dict) -> Document:
    xml = presentation.get("content", "")
    if not isinstance(xml, str) or len(xml) > 1_000_000 or re.search(r"<!DOCTYPE|<!ENTITY", xml, re.I):
        raise ApiError(422, "SLIDES_UNREADABLE", "公司介绍幻灯片内容无法安全读取，尚未自查。")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ApiError(422, "SLIDES_UNREADABLE", "公司介绍幻灯片读取不完整，尚未自查。") from exc
    slides = [node for node in root.iter() if node.tag.split("}")[-1] == "slide"]
    lines = ["读取范围：以下是幻灯片各页的可提取文字和讲者备注。图片、二维码和图片中的文字未识别；不要据此断言图片内容，也不要因无法核对图片内容认定学员答错。"]
    if not slides or len(slides) > 120:
        raise ApiError(422, "SLIDES_UNREADABLE", "公司介绍幻灯片页数不符合本地读取范围。")
    for index, slide in enumerate(slides, 1):
        texts = ["".join(node.itertext()).strip() for node in slide.iter()
                 if node.tag.split("}")[-1] == "content"]
        texts = [text for text in texts if text]
        if not texts:
            raise ApiError(422, "SLIDES_REQUIRES_TEXT", "公司介绍幻灯片有页面无法提取文字，请管理员提供可读取的文字材料。")
        lines.append(f"[第 {index} 页]\n" + "\n".join(texts))
    body = "\n\n".join(lines)
    if len(body) > 60_000:
        raise ApiError(422, "SLIDES_TOO_LARGE", "幻灯片文字超过本地自查读取范围。")
    return Document(token, "", "公司基础介绍材料（幻灯片文字及备注）", body, str(presentation.get("revision_id", "")))


class FeishuDocuments:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._token = ""

    def call(self, path: str, body: dict | None = None, *, method: str | None = None) -> dict:
        if not self._token:
            # Documents may use a separately authorized app. Never change the
            # OAuth application or mix credentials from the two applications.
            separate_app = bool(self.settings.ai_feishu_app_id)
            result = request_json("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                                  body={"app_id": (self.settings.ai_feishu_app_id if separate_app
                                                   else self.settings.feishu_app_id),
                                        "app_secret": (self.settings.ai_feishu_app_secret if separate_app
                                                       else self.settings.feishu_app_secret)})
            self._token = result.get("tenant_access_token", "")
            if result.get("code") != 0 or not self._token:
                raise ApiError(503, "FEISHU_APP_NOT_CONFIGURED", "飞书应用配置不可用，请联系管理员。")
        result = request_json("https://open.feishu.cn/open-apis" + path, token=self._token, body=body,
                              **({"method": method} if method else {}))
        if result.get("code") != 0:
            code = result.get("code")
            message = ("飞书应用缺少文档读取或评论权限，请联系管理员开通并发布应用权限。"
                       if code in {99991672, 99991663} else
                       "飞书无法访问此文档或执行评论，请确认应用已获授权且文档允许该应用访问。")
            raise ApiError(502, "FEISHU_DOCUMENT_ACCESS", message, details={"upstream_code": code})
        return result.get("data", {})

    def resolve(self, url: str) -> str:
        kind, token = self.resolve_reference(url)
        if kind != "docx":
            raise ApiError(422, "UNSUPPORTED_WIKI_DOCUMENT", "答题链接需要是新版飞书文字文档，才能在标题发表评论。")
        return token

    def resolve_reference(self, url: str) -> tuple[str, str]:
        kind, token = document_ref(url)
        if kind == "wiki":
            node = self.call("/wiki/v2/spaces/get_node?" + urlencode({"token": token})).get("node", {})
            if node.get("obj_type") not in {"docx", "slides"} or not TOKEN.fullmatch(node.get("obj_token", "")):
                raise ApiError(422, "UNSUPPORTED_WIKI_DOCUMENT", "参考材料需要是飞书文档或幻灯片。")
            kind, token = node["obj_type"], node["obj_token"]
        return kind, token

    def read_reference(self, kind: str, token: str) -> Document:
        if kind == "slides":
            data = self.call(f"/slides_ai/v1/xml_presentations/{token}?revision_id=-1")
            return slides_to_reference(token, data.get("xml_presentation", {}))
        return self.read(token)

    def read(self, token: str) -> Document:
        metadata = self.call(f"/docx/v1/documents/{token}").get("document", {})
        revision = str(metadata.get("revision_id", ""))
        if not revision.isdigit():
            raise ApiError(502, "DOCUMENT_REVISION_MISSING", "无法确定文档版本，尚未发表评论。")
        blocks: list[dict] = []
        cursor = ""
        for _ in range(30):
            # Tenant applications can read the latest document but may be
            # forbidden from reading a numbered historical snapshot. Detect
            # concurrent edits across all pages instead of requesting history.
            query = {"page_size": 500, "document_revision_id": -1}
            if cursor:
                query["page_token"] = cursor
            data = self.call(f"/docx/v1/documents/{token}/blocks?" + urlencode(query))
            blocks.extend(data.get("items", []))
            if not data.get("has_more"):
                current = self.call(f"/docx/v1/documents/{token}").get("document", {})
                if str(current.get("revision_id")) != revision:
                    raise ApiError(409, "DOCUMENT_CHANGED", "读取期间文档发生了修改，请重新自查，尚未发表评论。")
                return blocks_to_document(token, blocks, revision)
            cursor = data.get("page_token", "")
            if not cursor:
                break
        raise ApiError(422, "DOCUMENT_TOO_LARGE", "文档内容过多，未能完整读取，尚未发表评论。")

    def ensure_revision(self, document: Document) -> None:
        current = self.call(f"/docx/v1/documents/{document.token}").get("document", {})
        if str(current.get("revision_id")) != document.revision:
            raise ApiError(409, "DOCUMENT_CHANGED", "自查期间文档发生了修改，请重新自查，尚未发表评论。")

    def owner_open_id(self, document: Document) -> str:
        data = self.call("/drive/v1/metas/batch_query?user_id_type=open_id", {
            "request_docs": [{"doc_token": document.token, "doc_type": "docx"}],
        })
        metas = data.get("metas")
        if (data.get("failed_list") or not isinstance(metas, list) or len(metas) != 1
                or not isinstance(metas[0], dict) or metas[0].get("doc_token") != document.token
                or str(metas[0].get("doc_type", "")).lower() != "docx"):
            raise ApiError(502, "OWNER_IDENTITY_UNRESOLVED", "无法读取此文档的所有者，尚未发表评论。")
        owner_id = metas[0].get("owner_id")
        if not isinstance(owner_id, str) or not OPEN_ID.fullmatch(owner_id):
            raise ApiError(422, "OWNER_IDENTITY_UNRESOLVED", "文档所有者不是可核验的个人账号，请将文档归属到本人后重试。尚未发表评论。")
        return owner_id

    def human_owner(self, document: Document) -> HumanRecipient:
        """Use the current owner, never the creator, last editor or learner name.

        IDs and contact records come from the same document app. Contact lookup
        failure is unresolved identity, not evidence that somebody is a robot.
        """
        owner_id = self.owner_open_id(document)
        try:
            user = self.call(f"/contact/v3/users/{owner_id}?user_id_type=open_id").get("user", {})
        except ApiError as exc:
            raise ApiError(502, "OWNER_IDENTITY_UNRESOLVED",
                           "无法核实文档所有者的真人身份，请确认文档归属到本人，且本人在应用的通讯录可见范围内。尚未发表评论。",
                           details=exc.details) from exc
        if (not isinstance(user, dict) or user.get("open_id") != owner_id
                or not isinstance(user.get("user_id"), str) or not user["user_id"]):
            raise ApiError(502, "OWNER_IDENTITY_UNRESOLVED", "文档所有者尚未对应到有效的个人账号，尚未发表评论。")
        return HumanRecipient(owner_id)

    def ensure_owner(self, document: Document, owner: HumanRecipient) -> None:
        if self.owner_open_id(document) != owner.open_id:
            raise ApiError(409, "DOCUMENT_OWNER_CHANGED", "自查期间文档所有者发生了变更，请重新自查，尚未发表评论。")

    def comment_on_title(self, document: Document, text: str, recipients: tuple[HumanRecipient, ...] = ()) -> str:
        data = self.call(f"/drive/v1/files/{document.token}/new_comments", {
            "file_type": "docx", "anchor": {"block_id": document.title_block_id},
            "reply_elements": title_comment_elements(text, recipients),
        })
        comment_id = data.get("comment_id")
        if not isinstance(comment_id, str) or not comment_id:
            raise ApiError(502, "COMMENT_RESULT_UNKNOWN", "飞书评论结果尚未确认，请联系管理员核对，避免重复评论。")
        return comment_id

    def original_reply(self, document: Document, comment_id: str, previous_text: str) -> str:
        """Find our saved evaluation, never select an arbitrary human reply."""
        matches, cursor = [], ""
        for _ in range(10):
            query = {"file_type": "docx", "user_id_type": "open_id", "page_size": 100}
            if cursor:
                query["page_token"] = cursor
            data = self.call(f"/drive/v1/files/{document.token}/comments/{comment_id}/replies?" + urlencode(query))
            for reply in data.get("items", []):
                elements = (reply.get("content") or {}).get("elements", [])
                text = "".join((e.get("text_run") or {}).get("text", "") for e in elements)
                if previous_text and (text == previous_text or text.startswith(previous_text + "\n\nAI 自查已完成，请文档所有者查看评价：")):
                    reply_id = reply.get("reply_id")
                    if isinstance(reply_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,160}", reply_id):
                        matches.append(reply_id)
            if not data.get("has_more"):
                if len(matches) == 1:
                    return matches[0]
                break
            cursor = data.get("page_token", "")
            if not cursor:
                break
        raise ApiError(409, "AI_COMMENT_NOT_FOUND", "无法确认原 AI 评论，可能已被删除或修改。请联系管理员核对，不会新增重复评论。")

    def update_title_comment(self, document: Document, comment_id: str, reply_id: str,
                             text: str, recipients: tuple[HumanRecipient, ...] = ()) -> str:
        elements = []
        for item in title_comment_elements(text, recipients):
            if item["type"] == "text":
                elements.append({"type": "text_run", "text_run": {"text": item["text"]}})
            else:
                elements.append({"type": "person", "person": {"user_id": item["mention_user"]}})
        self.call(f"/drive/v1/files/{document.token}/comments/{comment_id}/replies/{reply_id}?file_type=docx&user_id_type=open_id",
                  {"content": {"elements": elements}}, method="PUT")
        # Editing a reply does not reopen a solved thread. Only reopen after
        # the new evaluation has been written, then verify its visibility.
        try:
            self.ensure_comment_open(document, comment_id)
        except ApiError as exc:
            # The evaluation PUT already succeeded. Do not treat a later
            # permission/transport error as an unwritten, safely retryable result.
            raise ApiError(502, "COMMENT_VISIBILITY_UNCONFIRMED",
                           "AI 评价已更新，但尚未确认原评论已恢复为未解决。请联系管理员核对，请勿重复发表评论。",
                           details=exc.details) from exc
        return comment_id

    def ensure_comment_open(self, document: Document, comment_id: str) -> None:
        path = f"/drive/v1/files/{document.token}/comments/"

        def solved_state() -> bool:
            data = self.call(path + "batch_query?file_type=docx", {"comment_ids": [comment_id]})
            items = [item for item in data.get("items", []) if item.get("comment_id") == comment_id]
            if (len(items) != 1 or items[0].get("is_deleted") is True
                    or not isinstance(items[0].get("is_solved"), bool)):
                raise ApiError(502, "COMMENT_VISIBILITY_UNCONFIRMED", "无法核实原 AI 评论的显示状态。")
            return items[0]["is_solved"]

        if solved_state():
            self.call(path + comment_id + "?file_type=docx", {"is_solved": False}, method="PATCH")
            if solved_state():
                raise ApiError(502, "COMMENT_VISIBILITY_UNCONFIRMED", "原 AI 评论仍是已解决状态，尚未确认恢复。")


def _ai_response_metadata(response: dict) -> dict:
    """Describe the response envelope without exposing provider or learner text."""
    choices = response.get("choices") if isinstance(response, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else None
    choice = choice if isinstance(choice, dict) else {}
    message = choice.get("message")
    message = message if isinstance(message, dict) else {}
    content = message.get("content")
    reasoning = message.get("reasoning_content")
    reason = choice.get("finish_reason")
    allowed_reasons = {"stop", "length", "content_filter", "tool_calls", "function_call"}
    metadata = {
        "finish_reason": (reason if isinstance(reason, str) and reason in allowed_reasons
                          else "missing" if reason is None else "other"),
        "choices_count": len(choices) if isinstance(choices, list) else None,
        "content_type": next((name for kind, name in (
            (str, "str"), (list, "list"), (dict, "dict"), (int, "int"),
            (float, "float"), (bool, "bool"), (type(None), "NoneType"))
            if type(content) is kind), "other"),
        "content_length": len(content) if isinstance(content, str) else 0,
        "reasoning_length": len(reasoning) if isinstance(reasoning, str) else 0,
    }
    usage = response.get("usage") if isinstance(response, dict) else None
    if isinstance(usage, dict):
        numeric_usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) in (int, float) and value >= 0 and (type(value) is int or math.isfinite(value)):
                numeric_usage[key] = value
        details = usage.get("completion_tokens_details")
        value = details.get("reasoning_tokens") if isinstance(details, dict) else None
        if type(value) in (int, float) and value >= 0 and (type(value) is int or math.isfinite(value)):
            numeric_usage["reasoning_tokens"] = value
        metadata["usage"] = numeric_usage
    return metadata


class AIReviewer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def review(self, system: str, evidence: dict) -> str:
        self.last_model = None
        body = {
            "model": self.settings.ai_model, "stream": False, "max_tokens": 3500,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)}],
        }
        # Retry generation only; document/comment operations remain outside this loop.
        # Share the existing 180-second request budget rather than tripling it.
        deadline = time.monotonic() + 180
        fallback = self.settings.ai_fallback_model.strip()
        models = [self.settings.ai_model, self.settings.ai_model, fallback or self.settings.ai_model]
        length_retried = False
        for attempt, model in enumerate(models, 1):
            body = {**body, "model": model}
            body.pop("reasoning_effort", None)
            if length_retried and model in LOW_REASONING_MODELS:
                body["reasoning_effort"] = "low"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ApiError(502, "AI_REQUEST_FAILED", AI_UNAVAILABLE_MESSAGE)
            try:
                response = request_json(self.settings.ai_base_url.rstrip("/") + "/chat/completions",
                                        token=self.settings.ai_api_key,
                                        timeout=max(0.001, min(60 if fallback else 180, remaining)),
                                        service="AI", body=body)
            except ApiError as exc:
                delay = float(attempt)
                retry = (exc.code == "AI_REQUEST_FAILED" and exc.retryable
                         and attempt < 3 and deadline - time.monotonic() > delay + 1)
                # Never log provider bodies, credentials, prompts or learner evidence.
                status = exc.details.get("upstream_status")
                logger.warning(json.dumps({"event": "ai.request_failed", "attempt": attempt,
                                           "model": model,
                                           "upstream_status": status if type(status) is int else None,
                                           "error_type": type(exc.__cause__).__name__,
                                           "will_retry": retry}))
                if not retry:
                    raise
                time.sleep(delay)
                continue

            metadata = {"event": "ai.generation_result", "attempt": attempt, "model": model,
                        **_ai_response_metadata(response), "will_retry": False}
            choices = response.get("choices") if isinstance(response, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices else None
            message = choice.get("message") if isinstance(choice, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            if not isinstance(choices, list) or (choices and not isinstance(choice, dict)):
                error = ApiError(502, "AI_INVALID_RESPONSE", "AI 返回的数据结构异常，尚未发表评论，请稍后重试。")
            elif not choices:
                error = ApiError(502, "AI_EMPTY_RESULT", "AI 未返回评价结果，尚未发表评论，请稍后重试。")
            elif reason == "content_filter":
                error = ApiError(502, "AI_CONTENT_FILTERED", "AI 评价被内容安全规则拦截，请检查提交内容后重试。")
            elif reason == "length":
                retry = (not length_retried and attempt < len(models)
                         and deadline - time.monotonic() > 1)
                metadata["will_retry"] = retry
                logger.warning(json.dumps(metadata))
                if not retry:
                    raise ApiError(502, "AI_INCOMPLETE_RESULT", "AI 评价生成达到长度上限，尚未生成完整评价，请稍后重试。")
                length_retried = True
                body = {**body, "max_tokens": 8000, "messages": [
                    {"role": "system", "content": system + "\n本次输出请保持精炼并完整闭合严格JSON。"
                    "保留原规定的所有字段、任务匹配判断和全部评价规则，不输出推理过程或Markdown。"
                     "summary不超过200字；如采用findings数组则最多8项，每个字段不超过100字；"
                     "如采用dimensions数组则必须完整覆盖所有配置维度，证据及建议分别不超过100字，不得遗漏维度。"
                     "next_steps最多3项，每项不超过100字；task_match.reason不超过150字。"
                     "任务不匹配或无法确认时，仍按原规则返回空summary、对应的空评价数组和空next_steps。"},
                    body["messages"][1],
                ]}
                continue
            elif reason != "stop":
                error = ApiError(502, "AI_INCOMPLETE_RESULT", "AI 未返回完整评价，尚未发表评论，请稍后重试。")
            elif not isinstance(message, dict) or (content is not None and not isinstance(content, str)):
                error = ApiError(502, "AI_INVALID_RESPONSE", "AI 返回的数据结构异常，尚未发表评论，请稍后重试。")
            elif content is None or not content.strip():
                error = ApiError(502, "AI_EMPTY_CONTENT", "AI 返回的评价正文为空，尚未发表评论，请稍后重试。")
            else:
                logger.info(json.dumps(metadata))
                self.last_model = model
                return content
            logger.warning(json.dumps(metadata))
            raise error


def get_documents() -> FeishuDocuments:
    return FeishuDocuments(get_settings())


def get_reviewer() -> AIReviewer:
    return AIReviewer(get_settings())
