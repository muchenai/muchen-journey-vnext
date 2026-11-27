"""Offline standard-answer document imports; no database, AI, or Feishu writes."""
import base64
from copy import deepcopy
from types import SimpleNamespace
import uuid

from pydantic import ValidationError
import pytest

from journey_api.ai_rubric_link_import import import_rubric_document
from journey_api.ai_rubric_materials import prepare_ai_rubric
from journey_api.ai_self_check_clients import Document
from journey_api.errors import ApiError

DOC_TOKEN = "StandardAnswerDoc123"
WIKI_TOKEN = "StandardAnswerWiki123"
DOC_URL = f"https://sample.feishu.cn/docx/{DOC_TOKEN}"
WIKI_URL = f"https://sample.feishu.cn/wiki/{WIKI_TOKEN}?from=copy#heading"


class Documents:
    def __init__(self, *, title="标准答案", body="参考答案为 B。\n解释必须包含判断依据。", revision="7", error=None):
        self.document = Document(DOC_TOKEN, DOC_TOKEN, title, body, revision)
        self.error = error
        self.calls = []

    def resolve(self, url):
        self.calls.append(("resolve", url))
        if self.error:
            raise self.error
        return DOC_TOKEN

    def read(self, token):
        self.calls.append(("read", token))
        return self.document

    def __getattr__(self, name):
        raise AssertionError(f"Import must not call document write/AI operation: {name}")


def decoded(material):
    return base64.b64decode(material["url"].split(",", 1)[1], validate=True).decode("utf-8")


@pytest.mark.parametrize("url", [DOC_URL, WIKI_URL, f"https://sample.larksuite.com/wiki/{WIKI_TOKEN}"])
def test_import_freezes_real_body_as_private_txt_with_canonical_docx_provenance(url):
    documents = Documents(body=" \r\n参考答案为 B。\r\n解释必须包含判断依据。\r\n ")
    material = import_rubric_document(url, documents=documents)
    assert documents.calls == [("resolve", url), ("read", DOC_TOKEN)]
    assert str(uuid.UUID(material["id"])) == material["id"]
    assert material["name"] == "标准答案.txt"
    assert material["type"] == "file" and material["mime"] == "text/plain"
    assert material["size"] == len(decoded(material).encode("utf-8"))
    assert decoded(material) == "参考答案为 B。\n解释必须包含判断依据。"
    assert material["sourceUrl"] == (
        f"https://sample.larksuite.com/docx/{DOC_TOKEN}" if "larksuite" in url else DOC_URL)
    assert material["sourceRevision"] == "7" and material["sourceTitle"] == "标准答案"
    assert "text" not in material and "aiRubricSnapshot" not in material


def test_import_acquires_existing_document_client_only_after_url_validation(monkeypatch):
    import journey_api.ai_self_check_clients as clients
    documents = Documents()
    acquired = []
    monkeypatch.setattr(clients, "get_documents", lambda: acquired.append(True) or documents)
    material = import_rubric_document(DOC_URL)
    assert acquired == [True] and decoded(material).startswith("参考答案")
    with pytest.raises(ApiError, match="标准答案文档"):
        import_rubric_document("https://example.com/docx/BadToken123")
    assert acquired == [True]


@pytest.mark.parametrize("url", [
    "http://sample.feishu.cn/docx/StandardAnswerDoc123",
    "https://example.com/docx/StandardAnswerDoc123",
    "https://sample.feishu.cn.evil.test/docx/StandardAnswerDoc123",
    "https://user:password@sample.feishu.cn/docx/StandardAnswerDoc123",
    "https://sample.feishu.cn:8443/docx/StandardAnswerDoc123",
    "https://sample.feishu.cn/slides/StandardAnswerDoc123",
    "https://sample.feishu.cn/docx/short",
    "https://sample.feishu.cn/docx/Standard AnswerDoc123",
    "飞书文档：" + DOC_URL,
    "",
])
def test_import_rejects_invalid_document_references_without_external_calls(url):
    documents = Documents()
    with pytest.raises(ApiError, match="标准答案文档") as exc:
        import_rubric_document(url, documents=documents)
    assert exc.value.status_code == 422
    assert documents.calls == []


@pytest.mark.parametrize("title,expected", [
    ('  参考/答案\\版本:*?"<>|\n  一  ', "参考_答案_版本_______ 一.txt"),
    ("标准答案.TXT", "标准答案.txt"),
    ("", "标准答案.txt"),
    ("CON", "_CON.txt"),
    ("NUL.old", "_NUL.old.txt"),
])
def test_import_sanitizes_single_line_download_filename(title, expected):
    material = import_rubric_document(DOC_URL, documents=Documents(title=title))
    assert material["name"] == expected
    assert len(material["name"]) <= 160
    assert "\n" not in material["sourceTitle"]


def test_import_bounds_filename_and_source_title_without_truncating_document_body():
    material = import_rubric_document(DOC_URL, documents=Documents(title="字" * 1000))
    assert material["name"] == "字" * 156 + ".txt"
    assert len(material["sourceTitle"]) == 240
    assert decoded(material) == "参考答案为 B。\n解释必须包含判断依据。"


@pytest.mark.parametrize("body", ["", " \n\t ", "!@#$", "答案\x00B", "答案\ufffdB", "字" * 20001, "答案\ud800"])
def test_import_rejects_unreadable_or_overlong_body_without_creating_an_attachment(body):
    documents = Documents(body=body)
    with pytest.raises(ApiError, match="标准答案文档") as exc:
        import_rubric_document(DOC_URL, documents=documents)
    assert exc.value.status_code == 422
    assert documents.calls == [("resolve", DOC_URL), ("read", DOC_TOKEN)]


def test_import_accepts_exact_body_character_limit():
    material = import_rubric_document(DOC_URL, documents=Documents(body="字" * 20000))
    assert material["size"] == 60000 and len(decoded(material)) == 20000


@pytest.mark.parametrize("revision", ["", "?", "1" * 101])
def test_import_rejects_unconfirmed_document_version(revision):
    with pytest.raises(ApiError, match="标准答案文档"):
        import_rubric_document(DOC_URL, documents=Documents(revision=revision))


@pytest.mark.parametrize("error,status,phrase", [
    (ApiError(422, "UNSUPPORTED_WIKI_DOCUMENT", "slides"), 422, "文字文档"),
    (ApiError(502, "FEISHU_DOCUMENT_ACCESS", "private upstream", details={"upstream_code": 99991672}), 403, "读取权限"),
    (ApiError(503, "FEISHU_APP_NOT_CONFIGURED", "private upstream"), 503, "应用配置"),
    (ApiError(409, "DOCUMENT_CHANGED", "private upstream"), 409, "发生了修改"),
    (ApiError(422, "DOCUMENT_TOO_LARGE", "private upstream"), 422, "20,000"),
    (ApiError(422, "DOCUMENT_REQUIRES_TEXT", "private upstream"), 422, "可读取文字"),
    (ApiError(422, "DOCUMENT_SIZE_UNSUPPORTED", "private upstream"), 422, "正文为空或过长"),
    (ApiError(422, "DOCUMENT_INCOMPLETE", "private upstream"), 422, "嵌入内容"),
    (ApiError(502, "DOCUMENT_REVISION_MISSING", "private upstream"), 422, "版本"),
    (ApiError(422, "DOCUMENT_TITLE_MISSING", "private upstream"), 422, "标题"),
    (ApiError(502, "FEISHU_REQUEST_FAILED", "private upstream",
        details={"upstream_status": 404}, retryable=True), 502, "仍然存在"),
    (TimeoutError("private upstream"), 502, "超时"),
])
def test_import_errors_use_answer_document_context_and_do_not_return_fake_material(error, status, phrase):
    documents = Documents(error=error)
    with pytest.raises(ApiError) as exc:
        import_rubric_document(WIKI_URL, documents=documents)
    assert exc.value.status_code == status
    assert "标准答案文档" in exc.value.message and phrase in exc.value.message
    assert "private upstream" not in exc.value.message
    assert "评论" not in exc.value.message and "自查" not in exc.value.message
    assert documents.calls == [("resolve", WIKI_URL)]


def test_imported_original_bytes_remain_the_scoring_authority():
    documents = Documents()
    material = import_rubric_document(WIKI_URL, documents=documents)
    original = deepcopy(material)
    material["text"] = "Untrusted client supplied replacement"
    material["sourceRevision"] = "99"
    policy = prepare_ai_rubric({"rubric": [
        {"id": "correct", "name": "正确性", "points": 100, "description": "依据标准答案判断"}],
        "passScore": 60, "rubricAttachments": [material],
        "aiRubricSnapshot": {"reference_documents": [{"body": "Untrusted cached answer"}]}})
    assert policy["reference_documents"][0]["body"] == decoded(original)
    assert documents.calls == [("resolve", WIKI_URL), ("read", DOC_TOKEN)]
    assert "base64" not in repr(policy) and "Untrusted" not in repr(policy)


def test_source_metadata_is_supported_only_for_private_rubric_materials():
    from journey_api.review_admin_routes import Material, RubricMaterial, TaskContent
    material = import_rubric_document(WIKI_URL, documents=Documents())
    assert RubricMaterial.model_validate(material).model_dump(mode="json") == {
        **material, "text": ""}
    task = TaskContent(camp="exploration", rubricAttachments=[material]).model_dump(mode="json")
    assert task["rubricAttachments"][0]["sourceUrl"] == DOC_URL
    with pytest.raises(ValidationError):
        Material.model_validate(material)
    for field in ("materials", "taskFiles"):
        with pytest.raises(ValidationError):
            TaskContent.model_validate({"camp": "exploration", field: [material]})


@pytest.mark.parametrize("field,value", [
    ("sourceUrl", "https://example.com/docx/StandardAnswerDoc123"),
    ("sourceUrl", "https://sample.feishu.cn/slides/StandardAnswerDoc123"),
    ("sourceRevision", "x" * 101),
    ("sourceTitle", "字" * 241),
])
def test_rubric_source_metadata_is_bounded_and_rejects_non_document_links(field, value):
    from journey_api.review_admin_routes import RubricMaterial
    material = import_rubric_document(DOC_URL, documents=Documents())
    with pytest.raises(ValidationError):
        RubricMaterial.model_validate({**material, field: value})


class ImportSession:
    def __init__(self, events):
        self.events = events

    def commit(self):
        self.events.append("commit")


def route_fixture(monkeypatch):
    import journey_api.review_admin_routes as routes
    events = []
    request = SimpleNamespace(state=SimpleNamespace(request_id="rubric-import-test"))
    actor = object()
    session = ImportSession(events)
    command = routes.ImportRubricDocument(url=WIKI_URL, camp="exploration", difficulty="")
    monkeypatch.setattr(routes, "import_rubric_document", lambda url: events.append(("read", url)) or {"id": "frozen"})
    return routes, command, request, actor, session, events


def test_import_route_releases_permission_lock_then_rechecks_after_external_io(monkeypatch):
    routes, command, request, actor, session, events = route_fixture(monkeypatch)
    monkeypatch.setattr(routes, "require_publisher",
        lambda db, user, difficulty: events.append(("authorize", db is session, user is actor, difficulty)))
    result = routes.import_rubric_document_route(command, request, actor, session)
    assert events == [("authorize", True, True, None), "commit",
        ("read", WIKI_URL), ("authorize", True, True, None)]
    assert result == {"data": {"material": {"id": "frozen"}}, "request_id": "rubric-import-test"}


@pytest.mark.parametrize("camp,difficulty", [("exploration", ""), ("novice", "挑战")])
def test_import_route_denies_unauthorized_publisher_before_client_or_database_mutation(monkeypatch, camp, difficulty):
    routes, command, request, actor, session, events = route_fixture(monkeypatch)
    command = routes.ImportRubricDocument(url=WIKI_URL, camp=camp, difficulty=difficulty)
    def deny(db, user, actual_difficulty):
        events.append(("authorize", actual_difficulty))
        raise ApiError(403, "FORBIDDEN", "当前账号没有任务发布权限。")
    monkeypatch.setattr(routes, "require_publisher", deny)
    with pytest.raises(ApiError, match="没有任务发布权限"):
        routes.import_rubric_document_route(command, request, actor, session)
    assert events == [("authorize", difficulty or None)]


def test_import_route_does_not_return_attachment_when_access_is_revoked_during_read(monkeypatch):
    routes, command, request, actor, session, events = route_fixture(monkeypatch)
    def check(*args):
        if events:
            raise ApiError(403, "FORBIDDEN", "当前账号没有任务发布权限。")
        events.append("authorized")
    monkeypatch.setattr(routes, "require_publisher", check)
    with pytest.raises(ApiError, match="没有任务发布权限"):
        routes.import_rubric_document_route(command, request, actor, session)
    assert events == ["authorized", "commit", ("read", WIKI_URL)]


def test_import_route_does_not_accept_client_body_or_snapshot():
    from journey_api.review_admin_routes import ImportRubricDocument
    with pytest.raises(ValidationError):
        ImportRubricDocument(url=DOC_URL, camp="exploration",
            text="Forged answer", aiRubricSnapshot={"body": "Forged answer"})
