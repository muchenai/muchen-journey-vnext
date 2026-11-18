"""Private, server-parsed scoring policy for administrator-authored AI tasks.

Only the original uploaded bytes are used as reference evidence. Client supplied
``text`` and earlier ``aiRubricSnapshot`` values never replace document parsing.
No external URL is fetched and no base64 is included in the prepared policy.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from journey_api.errors import ApiError

MAX_RUBRIC_FILES = 4
MAX_RUBRIC_FILE_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_CHARACTERS = 20000
MAX_REFERENCE_CHARACTERS = 60000
MAX_DOCX_EXPANDED_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 100
_MIMES = {
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pdf": {"application/pdf"},
}
_ANSWER_DOCUMENT_DESCRIPTION = (
    "按已导入标准答案文档逐题核对，遵循文档分值和扣分规则并换算为百分制。"
    "选择题文档未注明分值时各题等权；未注明扣分规则时，错选、漏选或多选该题记 0 分。"
    "主观题遵循文档评分要点，不自创标准；无法依据文档核对时不评分。"
)


def _invalid(message: str) -> None:
    raise ApiError(422, "AI_RUBRIC_INVALID", message)


def _readable_body(text: str, name: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or not re.search(r"[\w\u3400-\u9fff]", text, re.UNICODE):
        _invalid(f"评分文档“{name}”没有可读取正文，请上传含文字的 TXT、MD、DOCX 或 PDF。")
    if "\x00" in text or "\ufffd" in text or any(ord(c) < 32 and c not in "\n\t" for c in text):
        _invalid(f"评分文档“{name}”包含无法识别的文字，请转换为 UTF-8 TXT 或 DOCX 后重试。")
    if len(text) > MAX_DOCUMENT_CHARACTERS:
        _invalid(f"评分文档“{name}”正文超过 20,000 字，请精简评分依据后重试。")
    return text


def _plain_text(data: bytes, name: str) -> str:
    encodings = ("utf-16",) if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            return _readable_body(data.decode(encoding, errors="strict"), name)
        except UnicodeDecodeError:
            continue
    _invalid(f"无法识别评分文档“{name}”的编码，请另存为 UTF-8 TXT 后重试。")


def _docx_text(data: bytes, name: str) -> str:
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(item.file_size for item in entries) > MAX_DOCX_EXPANDED_BYTES:
                _invalid(f"评分文档“{name}”解压后过大，请精简内容后重试。")
            if len({item.filename for item in entries}) != len(entries):
                _invalid(f"评分文档“{name}”结构异常，请重新另存为 DOCX。")
            if "word/document.xml" not in archive.namelist():
                _invalid(f"评分文档“{name}”不是有效 DOCX，请检查文件格式。")
            names = ["word/document.xml", *sorted(item.filename for item in entries if re.fullmatch(
                r"word/(?:footnotes|endnotes|header\d+|footer\d+)\.xml", item.filename))]
            paragraphs: list[str] = []
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for part in names:
                raw = archive.read(part)
                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    _invalid(f"评分文档“{name}”含不支持的 XML 定义，请重新另存为 DOCX。")
                root = ElementTree.fromstring(raw)
                for paragraph in root.iter(namespace + "p"):
                    fragments = []
                    for node in paragraph.iter():
                        if node.tag == namespace + "t":
                            fragments.append(node.text or "")
                        elif node.tag == namespace + "tab":
                            fragments.append("\t")
                        elif node.tag in {namespace + "br", namespace + "cr"}:
                            fragments.append("\n")
                    paragraphs.append("".join(fragments))
            return _readable_body("\n".join(paragraphs), name)
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError, OSError) as exc:
        raise ApiError(422, "AI_RUBRIC_INVALID", f"无法读取评分文档“{name}”，请重新另存为 DOCX 后上传。") from exc


def _pdf_text(data: bytes, name: str) -> str:
    try:
        from pypdf import PdfReader, apply_configuration

        # Context-local limits also apply to font maps and indirect PDF streams.
        # Never relax the application's other concurrent PDF readers.
        with apply_configuration(
            maximum_declared_stream_length=MAX_DOCX_EXPANDED_BYTES,
            array_based_stream_maximum_output_length=MAX_DOCX_EXPANDED_BYTES,
            zlib_maximum_output_length=MAX_DOCX_EXPANDED_BYTES,
            lzw_maximum_output_length=MAX_DOCX_EXPANDED_BYTES,
            stream_decoding_work_maximum_length=4 * MAX_DOCX_EXPANDED_BYTES,
            array_maximum_element_count=20000,
            dictionary_maximum_element_count=20000,
        ):
            reader = PdfReader(io.BytesIO(data), strict=True, xref_stream_maximum_entries=20000)
            if reader.is_encrypted:
                _invalid(f"评分文档“{name}”已加密，请解除密码保护后上传。")
            if len(reader.pages) > MAX_PDF_PAGES:
                _invalid(f"评分文档“{name}”超过 100 页，请精简评分依据后重试。")
            parts: list[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if not text.strip():
                    _invalid(f"评分文档“{name}”含没有可读取正文的页面，扫描件请先识别文字，空白页请移除后重试。")
                parts.append(text)
                if sum(len(part) for part in parts) > MAX_DOCUMENT_CHARACTERS:
                    _invalid(f"评分文档“{name}”正文超过 20,000 字，请精简评分依据后重试。")
            return _readable_body("\n".join(parts), name)
    except ApiError:
        raise
    except Exception as exc:
        # Reader errors must not expose document contents or dependency details.
        raise ApiError(422, "AI_RUBRIC_INVALID", f"无法读取评分文档“{name}”，请转成含文字的 PDF、DOCX 或 TXT 后上传。") from exc


def parse_rubric_documents(content: dict) -> list[dict]:
    attachments = content.get("rubricAttachments") or []
    if not isinstance(attachments, list) or len(attachments) > MAX_RUBRIC_FILES:
        _invalid("最多附加 4 份评分文档。")
    documents = []
    for item in attachments:
        if not isinstance(item, dict):
            _invalid("评分文档格式无效，请移除后重新上传。")
        name = str(item.get("name") or "").strip()
        extension = PurePosixPath(name.replace("\\", "/")).suffix.lower()
        if extension == ".doc":
            _invalid(f"评分文档“{name}”是旧版 DOC，请转换为 DOCX、PDF 或 TXT 后上传。")
        if not name or extension not in _MIMES or item.get("type") != "file":
            _invalid("评分文档仅支持 TXT、MD、DOCX 和含文字的 PDF，请重新上传。")
        mime = item.get("mime")
        url = item.get("url", "")
        if mime not in _MIMES[extension] or not isinstance(url, str) or not url.startswith(f"data:{mime};base64,"):
            _invalid(f"评分文档“{name}”格式与文件内容不匹配，请重新上传。")
        encoded = url.split(",", 1)[1]
        if len(encoded) > 4 * math.ceil(MAX_RUBRIC_FILE_BYTES / 3):
            _invalid(f"评分文档“{name}”超过 2 MB，请精简后上传。")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ApiError(422, "AI_RUBRIC_INVALID", f"评分文档“{name}”内容损坏，请重新上传。") from exc
        if not data or len(data) > MAX_RUBRIC_FILE_BYTES or item.get("size") != len(data):
            _invalid(f"评分文档“{name}”为空、超过 2 MB 或长度不正确，请重新上传。")
        body = (_plain_text(data, name) if extension in {".txt", ".md"} else
                _docx_text(data, name) if extension == ".docx" else _pdf_text(data, name))
        documents.append({"name": name, "body": body, "sha256": hashlib.sha256(data).hexdigest()})
    if sum(len(item["body"]) for item in documents) > MAX_REFERENCE_CHARACTERS:
        _invalid("评分文档正文合计超过 60,000 字，请精简评分依据后重试。")
    return documents


def _decimal(value, message: str) -> Decimal:
    try:
        if isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError
        return result
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ApiError(422, "AI_RUBRIC_INVALID", message) from exc


def prepare_ai_rubric(content: dict) -> dict:
    """Return private scoring evidence from a current or historic task snapshot."""
    raw_rows = content.get("rubric")
    rows = raw_rows or []
    documents = None
    if (content.get("camp") == "exploration" and content.get("reviewMode") == "ai"
            and isinstance(raw_rows, list) and len(raw_rows) == 0):
        # A document-only policy is derived rather than persisted as an editable
        # row. Removing the document must not leave behind an invented standard.
        documents = parse_rubric_documents(content)
        if not documents:
            _invalid("请至少添加一份可读取的标准答案文档，或配置完整的评分维度。")
        rows = [{"id": "answer-document", "name": "标准答案评分", "points": 100,
            "description": _ANSWER_DOCUMENT_DESCRIPTION}]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
        _invalid("AI 评分需配置 1～12 个评分维度。")
    dimensions, seen = [], set()
    total = Decimal(0)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            _invalid("AI 评分维度格式无效，请重新配置。")
        name, description = str(row.get("name") or "").strip(), str(row.get("description") or "").strip()
        key = str(row.get("id") or f"dimension-{index + 1}")
        if not name or len(name) > 120 or not description or len(description) > 2000:
            _invalid(f"请完善评分维度 {index + 1} 的名称和评分描述，可在描述中填写标准答案。")
        if key in seen or len(key) > 100:
            _invalid("评分维度标识重复或无效，请删除重复维度后重新添加。")
        seen.add(key)
        points = _decimal(row.get("points"), "评分维度分值必须为有效数字。")
        if not 0 < points <= 100:
            _invalid(f"评分维度 {index + 1} 的分值需大于 0 且不超过 100。")
        if points.as_tuple().exponent < -2:
            _invalid(f"评分维度 {index + 1} 的分值最多保留两位小数。")
        total += points
        dimensions.append({"id": key, "name": name, "points": float(points), "description": description})
    if total != Decimal(100):
        _invalid("评分维度总分需为 100 分。")
    pass_score = _decimal(content.get("passScore", 60), "请设置 0～100 分的有效通过分数。")
    if not 0 <= pass_score <= 100:
        _invalid("通过分数需在 0～100 分之间。")
    if pass_score.as_tuple().exponent < -2:
        _invalid("通过分数最多保留两位小数。")
    if documents is None:
        documents = parse_rubric_documents(content)
    policy = {"dimensions": dimensions, "pass_score": float(pass_score), "reference_documents": documents}
    policy["canonical_hash"] = hashlib.sha256(json.dumps(policy, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return policy


def canonicalize_ai_rubric(content: dict, *, allow_incomplete: bool = False) -> dict:
    """Attach a server-only canonical snapshot; browser payloads cannot supply it."""
    result = dict(content)
    result.pop("aiRubricSnapshot", None)
    if result.get("reviewMode") != "ai":
        return result
    # Validate uploaded documents even while the rubric is an unfinished draft.
    parse_rubric_documents(result)
    try:
        policy = prepare_ai_rubric(result)
    except ApiError:
        if not allow_incomplete:
            raise
        return result
    result["aiRubricSnapshot"] = policy
    return result
