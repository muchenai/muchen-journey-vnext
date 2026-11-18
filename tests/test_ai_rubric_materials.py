"""Actual document bytes and policy boundaries, with no document/AI network calls."""
import base64
import copy
import io
import json
from zipfile import ZipFile

import pytest

from journey_api.ai_rubric_materials import (
    MAX_RUBRIC_FILE_BYTES, canonicalize_ai_rubric, prepare_ai_rubric,
)
from journey_api.errors import ApiError


def attachment(data=b"Reference answer: B", name="answers.txt", mime="text/plain"):
    return {"id": name, "name": name, "type": "file", "mime": mime, "size": len(data),
        "url": f"data:{mime};base64," + base64.b64encode(data).decode(),
        "text": "UNTRUSTED CLIENT ANSWER"}


def content(files=None):
    return {"reviewMode": "ai", "passScore": 75,
        "rubric": [{"id": "correctness", "name": "正确性", "points": 80,
            "description": "标准答案为 B，判断答案和说明是否正确。"},
            {"id": "reason", "name": "解释", "points": 20, "description": "解释判断依据。"}],
        "rubricAttachments": files or []}


def docx_bytes():
    data = io.BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>题目一：</w:t></w:r><w:r><w:t>标准答案 B</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>解释：先核对边界。</w:t></w:r></w:p>'
            '</w:tc></w:tr></w:tbl></w:body></w:document>'))
    return data.getvalue()


def pdf_bytes(*, blank=False, encrypted=False):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if not blank:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 20 Td (Reference answer: B) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("not-shared")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_policy_uses_file_bytes_and_ignores_forged_client_text_and_snapshot():
    task = content([attachment()])
    task["aiRubricSnapshot"] = {"reference_documents": [{"body": "FORGED CACHED ANSWER"}]}
    policy = prepare_ai_rubric(task)
    assert policy["reference_documents"][0]["body"] == "Reference answer: B"
    assert len(policy["canonical_hash"]) == 64
    assert "data:" not in json.dumps(policy)
    assert "UNTRUSTED" not in json.dumps(policy)
    task["rubricAttachments"][0]["text"] = "a different lie"
    assert prepare_ai_rubric(task) == policy


@pytest.mark.parametrize(("encoding", "name", "mime"), [
    ("utf-8-sig", "答案.txt", "text/plain"), ("utf-16", "答案.txt", "text/plain"),
    ("gb18030", "答案.md", "text/markdown"),
])
def test_actual_text_encodings(encoding, name, mime):
    body = "标准答案：乙。\n原因：先明确有效数据范围。"
    policy = prepare_ai_rubric(content([attachment(body.encode(encoding), name, mime)]))
    assert policy["reference_documents"][0]["body"] == body


def test_docx_paragraphs_and_table_are_read_in_order():
    file = attachment(docx_bytes(), "答案.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert prepare_ai_rubric(content([file]))["reference_documents"][0]["body"] == (
        "题目一：标准答案 B\n解释：先核对边界。")


def test_actual_pdf_text_is_extracted():
    policy = prepare_ai_rubric(content([attachment(pdf_bytes(), "answers.pdf", "application/pdf")]))
    assert policy["reference_documents"][0]["body"] == "Reference answer: B"


@pytest.mark.parametrize("options", [{"blank": True}, {"encrypted": True}])
def test_unreadable_or_encrypted_pdf_is_rejected(options):
    with pytest.raises(ApiError, match="没有可读取正文|已加密"):
        prepare_ai_rubric(content([attachment(pdf_bytes(**options), "answers.pdf", "application/pdf")]))


def test_pdf_with_text_and_an_unreadable_page_is_not_silently_partially_used():
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(pdf_bytes())))
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ApiError, match="没有可读取正文"):
        prepare_ai_rubric(content([attachment(output.getvalue(), "mixed.pdf", "application/pdf")]))


@pytest.mark.parametrize(("data", "name", "mime"), [
    (b"old binary document", "answers.doc", "application/msword"),
    (b"not a pdf", "answers.pdf", "application/pdf"),
    (b"not a zip", "answers.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (b"\x00\x01\x02", "answers.txt", "text/plain"),
    (b"   \r\n", "answers.txt", "text/plain"),
])
def test_invalid_original_files_never_become_scoring_evidence(data, name, mime):
    with pytest.raises(ApiError):
        prepare_ai_rubric(content([attachment(data, name, mime)]))


def test_attachment_link_is_explicitly_rejected_instead_of_assumed_read():
    with pytest.raises(ApiError, match="仅支持"):
        prepare_ai_rubric(content([{"type": "link", "name": "答案.txt",
            "url": "https://example.com/answer", "text": "not actually read"}]))


def test_four_documents_allowed_and_fifth_rejected():
    files = [attachment(name=f"answer-{i}.txt") for i in range(4)]
    assert len(prepare_ai_rubric(content(files))["reference_documents"]) == 4
    with pytest.raises(ApiError, match="4 份"):
        prepare_ai_rubric(content([*files, attachment(name="fifth.txt")]))


def test_size_and_original_bytes_match_are_enforced():
    file = attachment(b"x" * (MAX_RUBRIC_FILE_BYTES + 1))
    with pytest.raises(ApiError, match="2 MB"):
        prepare_ai_rubric(content([file]))
    file = attachment()
    file["size"] += 1
    with pytest.raises(ApiError, match="长度不正确"):
        prepare_ai_rubric(content([file]))


def test_document_bodies_are_not_silently_truncated():
    with pytest.raises(ApiError, match="20,000"):
        prepare_ai_rubric(content([attachment(b"x" * 20001)]))
    files = [attachment(b"x" * 16000, name=f"answer-{i}.txt") for i in range(4)]
    with pytest.raises(ApiError, match="60,000"):
        prepare_ai_rubric(content(files))


@pytest.mark.parametrize("points", [0, -1, 101, "NaN", "Infinity", True, ""])
def test_nonpositive_or_invalid_dimension_scores_rejected(points):
    task = content()
    task["rubric"][0]["points"] = points
    with pytest.raises(ApiError):
        prepare_ai_rubric(task)


@pytest.mark.parametrize("first,second,threshold", [(33.333, 66.667, 60), (33.33, 66.67, 60.001)])
def test_published_precision_matches_automatic_completion_contract(first, second, threshold):
    task = content()
    task["rubric"][0]["points"], task["rubric"][1]["points"] = first, second
    task["passScore"] = threshold
    with pytest.raises(ApiError, match="两位小数"):
        prepare_ai_rubric(task)


def test_valid_fractional_points_and_threshold_remain_supported():
    task = content()
    task["rubric"][0]["points"], task["rubric"][1]["points"] = 33.33, 66.67
    task["passScore"] = 60.01
    assert prepare_ai_rubric(task)["pass_score"] == 60.01


def test_total_must_be_exactly_100_and_ids_unique():
    task = content()
    task["rubric"][0]["points"] = 79.99
    with pytest.raises(ApiError, match="100"):
        prepare_ai_rubric(task)
    task = content()
    task["rubric"][1]["id"] = "correctness"
    with pytest.raises(ApiError, match="重复"):
        prepare_ai_rubric(task)


def test_legacy_missing_ids_normalize_deterministically():
    task = content()
    for row in task["rubric"]:
        row.pop("id")
    assert [row["id"] for row in prepare_ai_rubric(task)["dimensions"]] == ["dimension-1", "dimension-2"]


def test_policy_hash_changes_with_answer_file_or_scoring_rules():
    original = content([attachment()])
    baseline = prepare_ai_rubric(original)["canonical_hash"]
    for task in [content([attachment(b"Reference answer: C")]), copy.deepcopy(original), copy.deepcopy(original)]:
        if task == original:
            task["passScore"] += 1
        assert prepare_ai_rubric(task)["canonical_hash"] != baseline
    changed = copy.deepcopy(original)
    changed["rubric"][0]["description"] = "标准答案为 C。"
    assert prepare_ai_rubric(changed)["canonical_hash"] != baseline


def test_complete_server_snapshot_is_created_without_mutating_browser_object():
    task = content([attachment()])
    task["aiRubricSnapshot"] = {"fake": True}
    saved = canonicalize_ai_rubric(task)
    assert saved["aiRubricSnapshot"] == prepare_ai_rubric(task)
    assert task["aiRubricSnapshot"] == {"fake": True}


def test_partial_draft_can_be_saved_but_unreadable_document_cannot():
    task = content()
    task["rubric"][0]["description"] = ""
    assert "aiRubricSnapshot" not in canonicalize_ai_rubric(task, allow_incomplete=True)
    with pytest.raises(ApiError):
        canonicalize_ai_rubric(task)
    task["rubricAttachments"] = [attachment(b" ", "empty.txt")]
    with pytest.raises(ApiError, match="没有可读取正文"):
        canonicalize_ai_rubric(task, allow_incomplete=True)


def document_only_content(files=None):
    task = content([attachment()] if files is None else files)
    return {**task, "camp": "exploration", "rubric": []}


def test_exploration_document_only_policy_uses_stable_complete_effective_dimension():
    task = document_only_content()
    before = copy.deepcopy(task)
    policy = prepare_ai_rubric(task)
    assert policy["dimensions"] == [{
        "id": "answer-document", "name": "标准答案评分", "points": 100.0,
        "description": "按已导入标准答案文档逐题核对，遵循文档分值和扣分规则并换算为百分制。"
            "选择题文档未注明分值时各题等权；未注明扣分规则时，错选、漏选或多选该题记 0 分。"
            "主观题遵循文档评分要点，不自创标准；无法依据文档核对时不评分。",
    }]
    assert policy["pass_score"] == 75
    assert policy["reference_documents"][0]["body"] == "Reference answer: B"
    assert prepare_ai_rubric(task) == policy and task == before


@pytest.mark.parametrize("files", [[], [attachment(b" ")], [
    {**attachment(), "url": "data:text/plain;base64,broken!"}], [
    {"type": "link", "name": "answers.txt", "url": "https://example.com/answer", "text": "Reference answer B"}]])
def test_document_only_policy_never_falls_back_from_missing_or_unreadable_original_document(files):
    task = document_only_content(files)
    task["aiRubricSnapshot"] = {"dimensions": [{"id": "answer-document", "points": 100}],
        "reference_documents": [{"body": "Forged cached answer"}]}
    with pytest.raises(ApiError):
        prepare_ai_rubric(task)
    # An empty draft may be saved, but invalid attached bytes must still fail.
    if files:
        with pytest.raises(ApiError):
            canonicalize_ai_rubric(task, allow_incomplete=True)
    else:
        assert "aiRubricSnapshot" not in canonicalize_ai_rubric(task, allow_incomplete=True)


@pytest.mark.parametrize("rubric", [None, "", {}, (), [{}], [
    {"id": "partial", "name": "正确性", "points": 100, "description": ""}], [
    {"id": "partial", "name": "", "points": 100, "description": "标准答案为 B"}], [
    {"id": "partial", "name": "正确性", "points": 0, "description": "标准答案为 B"}], [
    {"id": "partial", "name": "正确性", "points": 50, "description": "标准答案为 B"}]])
def test_document_only_policy_requires_exact_empty_list_and_does_not_override_explicit_incomplete_rubric(rubric):
    task = document_only_content()
    task["rubric"] = rubric
    with pytest.raises(ApiError):
        prepare_ai_rubric(task)


def test_document_only_policy_does_not_treat_missing_rubric_as_explicit_document_mode():
    task = document_only_content()
    task.pop("rubric")
    with pytest.raises(ApiError, match="评分维度"):
        prepare_ai_rubric(task)


@pytest.mark.parametrize("camp,review_mode", [
    ("novice", "ai"), ("exploration", "manual"), ("", "ai"), (None, "ai"), ("exploration", None)])
def test_document_only_fallback_is_limited_to_exploration_ai(camp, review_mode):
    task = document_only_content()
    task.update(camp=camp, reviewMode=review_mode)
    with pytest.raises(ApiError, match="评分维度"):
        prepare_ai_rubric(task)


def test_explicit_dimensions_take_precedence_even_with_valid_answer_document():
    task = content([attachment()])
    task["camp"] = "exploration"
    assert [row["id"] for row in prepare_ai_rubric(task)["dimensions"]] == ["correctness", "reason"]


def test_document_only_canonical_snapshot_keeps_editable_rows_empty_and_removed_document_invalidates_it():
    task = document_only_content()
    saved = canonicalize_ai_rubric(task)
    assert saved["rubric"] == task["rubric"] == []
    assert saved["aiRubricSnapshot"]["dimensions"][0]["id"] == "answer-document"
    saved["rubricAttachments"] = []
    with pytest.raises(ApiError, match="标准答案文档"):
        prepare_ai_rubric(saved)
    assert "aiRubricSnapshot" not in canonicalize_ai_rubric(saved, allow_incomplete=True)


def test_document_only_hash_changes_when_real_answer_or_threshold_changes():
    task = document_only_content()
    baseline = prepare_ai_rubric(task)["canonical_hash"]
    changed_answer = document_only_content([attachment(b"Reference answer: C")])
    changed_threshold = {**task, "passScore": 80}
    assert prepare_ai_rubric(changed_answer)["canonical_hash"] != baseline
    assert prepare_ai_rubric(changed_threshold)["canonical_hash"] != baseline
    task["rubricAttachments"][0]["text"] = "Forged alternative answer"
    task["aiRubricSnapshot"] = {"canonical_hash": "f" * 64}
    assert prepare_ai_rubric(task)["canonical_hash"] == baseline


@pytest.mark.parametrize("threshold", [-1, 101, "NaN", 60.001, True])
def test_document_only_policy_preserves_threshold_validation(threshold):
    task = document_only_content()
    task["passScore"] = threshold
    with pytest.raises(ApiError):
        prepare_ai_rubric(task)
