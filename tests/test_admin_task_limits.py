from copy import deepcopy
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import pytest

from journey_api import publication_routes as publications
from journey_api import review_admin_routes as admin
from journey_api.admin_task_limits import validate_admin_task_text
from journey_api.auth import get_actor
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.main import api_error_handler, validation_error_handler
from journey_api.models import Role, TaskDefinitionStatus, User, UserStatus
from journey_api.review_admin_models import ReviewAdminTask
from journey_api.schemas import PublishTaskVersionCommand


FIELDS = [("title", 60, "任务标题不能超过 60 字"), ("summary", 400, "任务简述不能超过 400 字")]


def valid_content():
    return {
        "title": "管理任务长度验证", "summary": "阅读任务材料后提交完整的分析与执行方案。",
        "publishingDepartment": "开发部", "badges": [{"id": "product", "weight": 100}],
        "materials": [{"id": "source", "name": "参考材料", "type": "link", "url": "https://example.com/material"}],
    }


@pytest.mark.parametrize("field,limit,message", FIELDS)
@pytest.mark.parametrize("value_for", [
    lambda limit: "字" * limit,
    lambda limit: " " + "x" * (limit - 2) + " ",
    lambda limit: "😀" * (limit // 2),
    lambda limit: "😀" * (limit // 2 - 1) + "ab",
])
def test_exact_utf16_limits_preserve_raw_text(field, limit, message, value_for):
    value = value_for(limit)
    content = admin.TaskContent.model_validate({**valid_content(), field: value})
    assert getattr(content, field) == value
    assert admin.task_content_for_publish(content.model_dump())["title" if field == "title" else "purpose"] == value


@pytest.mark.parametrize("field,limit,message", FIELDS)
@pytest.mark.parametrize("value_for", [
    lambda limit: "字" * (limit + 1),
    lambda limit: " " + "x" * limit,
    lambda limit: "😀" * (limit // 2) + "a",
    lambda limit: "😀" * (limit // 2 + 1),
])
def test_limits_reject_raw_whitespace_and_supplementary_characters(field, limit, message, value_for):
    with pytest.raises(ApiError) as error:
        admin.TaskContent.model_validate({**valid_content(), field: value_for(limit)})
    assert (error.value.status_code, error.value.code, error.value.message) == (422, "VALIDATION_FAILED", message)


def test_empty_drafts_and_publish_minimums_are_unchanged():
    assert admin.TaskContent().title == admin.TaskContent().summary == ""
    content = admin.TaskContent(title="  ", summary=" ")
    assert content.title == "  " and content.summary == " "
    for field, value, message in [("title", " 两字 ", "任务标题至少需要 3 个字"),
                                  ("summary", " " + "字" * 9 + " ", "任务简述至少需要 10 个字")]:
        with pytest.raises(ApiError, match=message):
            admin.task_content_for_publish({**valid_content(), field: value})
    assert admin.task_content_for_publish({**valid_content(), "title": "字" * 3, "summary": "字" * 10})


def test_utf16_counter_handles_unpaired_surrogates_without_encoding_errors():
    assert validate_admin_task_text("title", "\ud800" * 60) == "\ud800" * 60
    with pytest.raises(ApiError, match="任务标题不能超过 60 字"):
        validate_admin_task_text("title", "\ud800" * 61)


def test_generic_publication_contract_keeps_its_existing_limits():
    body = admin.task_content_for_publish(valid_content())
    command = PublishTaskVersionCommand(**{
        **body, "title": "字" * 180, "purpose": "字" * 2000, "learner_outcome": "字" * 2000,
        "expected_revision": 1, "reviewed_by": uuid.uuid4(),
    })
    assert len(command.title) == 180 and len(command.purpose) == 2000
    schema = admin.TaskContent.model_json_schema()["properties"]
    assert schema["title"]["maxLength"] == 60 and schema["summary"]["maxLength"] == 400


class ReadOnlySession:
    def __init__(self, rows, scalar_results):
        self.rows = rows
        self.scalar_results = iter(scalar_results)

    def get(self, model, key):
        return self.rows.get(model)

    def scalar(self, query):
        return next(self.scalar_results)

    def scalars(self, query):
        return [Role.OPERATOR]

    def refresh(self, row, **kwargs):
        pass

    def execute(self, query):
        return SimpleNamespace(one=lambda: (0, 0))

    def commit(self):
        raise AssertionError("Invalid content must not commit")


def request_fixture(monkeypatch, action, content):
    actor = SimpleNamespace(id=uuid.uuid4(), organization_id=uuid.uuid4())
    definition = SimpleNamespace(id=uuid.uuid4(), organization_id=actor.organization_id, created_by=actor.id,
                                 revision=1, stable_key="ADMIN-limits", status=TaskDefinitionStatus.DRAFT)
    profile = SimpleNamespace(content=content, revision=1, status="draft")
    owner = SimpleNamespace(status=UserStatus.ACTIVE, display_name="测试发布者")
    approval = SimpleNamespace(id=uuid.uuid4(), task_id=definition.id, content=deepcopy(content),
                               revision=1, task_revision=1, status="pending", submitted_by=actor.id)
    results = {"save": [], "publish": [definition, actor.id], "submit": [definition, None],
               "approve": [approval, definition], "read": [None]}
    session = ReadOnlySession({ReviewAdminTask: profile, User: owner}, results[action])
    for module in [admin, publications]:
        monkeypatch.setattr(module, "require_publisher", lambda *args: None)
        monkeypatch.setattr(module, "require_super", lambda *args: None)
        monkeypatch.setattr(module, "audit", lambda *args: None)
    monkeypatch.setattr(admin, "find_replay", lambda *args, **kwargs: None)
    monkeypatch.setattr(publications, "ensure_editable", lambda *args: None)
    monkeypatch.setattr(publications, "access_for", lambda *args: None)
    return actor, definition, profile, approval, session


@pytest.mark.parametrize("action", ["save", "publish", "submit", "approve"])
@pytest.mark.parametrize("field,limit,message", FIELDS)
def test_admin_http_paths_return_chinese_422_for_legacy_overlong_content(monkeypatch, action, field, limit, message):
    content = {**valid_content(), field: "😀" * (limit // 2) + "字"}
    before = deepcopy(content)
    actor, definition, profile, approval, session = request_fixture(monkeypatch, action, content)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(admin.router)
    app.include_router(publications.router)
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_db] = lambda: session
    client = TestClient(app)
    path = f"/api/v1/review-admin/tasks/{definition.id}"
    if action == "save":
        response = client.put(path, json={"id": str(definition.id), "expected_revision": 1, "content": content})
    elif action == "publish":
        response = client.post(path + "/publish", headers={"Idempotency-Key": str(uuid.uuid4())},
                               json={"expected_revision": 1, "reviewed_by": str(actor.id)})
    elif action == "submit":
        response = client.post(path + "/submit-publication", json={"expected_revision": 1})
    else:
        response = client.post(f"/api/v1/review-admin/publications/{approval.id}/decision",
                               json={"expected_revision": 1, "decision": "approved"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["message"] == message
    assert profile.content == before


def test_legacy_task_read_preserves_overlong_content(monkeypatch):
    content = {**valid_content(), "title": "字" * 180, "summary": "字" * 2000}
    _, definition, _, _, session = request_fixture(monkeypatch, "read", content)
    monkeypatch.setattr(admin, "latest_version", lambda *args: None)
    result = admin.task_data(session, definition)
    assert result["title"] == content["title"] and result["summary"] == content["summary"]


@pytest.mark.parametrize("archived", [True, False])
def test_legacy_archive_and_restore_keep_content_without_a_management_profile(monkeypatch, archived):
    content = {**valid_content(), "title": "字" * 180, "summary": "字" * 2000}
    actor, definition, _, _, session = request_fixture(monkeypatch, "read", content)
    session.rows[ReviewAdminTask] = None
    session.scalar_results = iter([definition])
    saved, commits = [], []
    session.add = saved.append
    session.commit = lambda: commits.append(True)
    monkeypatch.setattr(admin, "task_data", lambda *args: {**content, "revision": 0, "version": 1})
    request = SimpleNamespace(state=SimpleNamespace(request_id="limits-unit-test"))
    admin.archive_task(definition.id, admin.ArchiveTask(expected_revision=0, archived=archived), request,
                       actor=actor, session=session)
    assert saved[0].content["title"] == content["title"] and saved[0].content["summary"] == content["summary"]
    assert saved[0].status == ("archived" if archived else "published")
    assert commits == [True]


def test_other_invalid_legacy_content_returns_validation_error_instead_of_500():
    content = valid_content()
    content["materials"][0]["name"] = ""
    with pytest.raises(ApiError) as error:
        admin.task_content_for_publish(content)
    assert error.value.status_code == 422 and error.value.code == "VALIDATION_FAILED"
    assert error.value.message == "任务内容不符合要求，请检查基础信息和学习材料后重试。"
