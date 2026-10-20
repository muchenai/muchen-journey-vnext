"""Owner notification tests; no real comments or notifications are sent."""
import pytest

from journey_api.ai_self_check_clients import Document, FeishuDocuments, HumanRecipient, title_comment_elements
from journey_api.config import get_settings
from journey_api.errors import ApiError
from test_ai_self_check import integration, run
from test_wp09_feishu_identity import assert_ok, oauth_provider


PERSON = "ou_" + "a" * 32
OTHER = "ou_" + "b" * 32
APP = "cli_" + "c" * 16
DOC = Document("documenttoken123", "title-block", "title", "answer", "3")


def meta(owner=PERSON):
    return {"metas": [{"doc_token": DOC.token, "doc_type": "docx", "owner_id": owner,
                       "latest_modify_user": OTHER}]}


def test_one_title_comment_mentions_owner_once(monkeypatch):
    client = FeishuDocuments(get_settings())
    calls = []
    monkeypatch.setattr(client, "call", lambda path, body=None: calls.append((path, body)) or {"comment_id": "one"})
    assert client.comment_on_title(DOC, "feedback", (HumanRecipient(PERSON), HumanRecipient(PERSON))) == "one"
    assert len(calls) == 1
    assert calls[0][1]["anchor"] == {"block_id": "title-block"}
    elements = calls[0][1]["reply_elements"]
    assert [e["mention_user"] for e in elements if e["type"] == "mention_user"] == [PERSON]
    assert "所有者" in "".join(e.get("text", "") for e in elements)


@pytest.mark.parametrize("value", ["all", "李鑫波", APP, "1234567890123456789", "ou_../../user"])
def test_names_apps_and_internal_ids_are_not_sent_as_mentions(value):
    with pytest.raises(ApiError):
        title_comment_elements("feedback", (HumanRecipient(value),))


def test_cannot_notify_additional_people():
    with pytest.raises(ApiError):
        title_comment_elements("feedback", (HumanRecipient(PERSON), HumanRecipient(OTHER)))


def test_current_owner_is_used_even_when_last_editor_is_different(monkeypatch):
    client = FeishuDocuments(get_settings())
    calls = []

    def call(path, body=None):
        calls.append(path)
        if "/metas/" in path:
            assert body == {"request_docs": [{"doc_token": DOC.token, "doc_type": "docx"}]}
            return meta()
        assert path == f"/contact/v3/users/{PERSON}?user_id_type=open_id"
        return {"user": {"open_id": PERSON, "user_id": "employee1", "name": "文档创建小助手"}}

    monkeypatch.setattr(client, "call", call)
    assert client.human_owner(DOC) == HumanRecipient(PERSON)
    assert len(calls) == 2


@pytest.mark.parametrize("response", [
    {}, {"metas": []}, {"metas": [{"doc_token": "different", "owner_id": PERSON}]},
    {"metas": [{"doc_token": DOC.token, "doc_type": "docx"}]},
    {**meta(), "failed_list": [{"code": 970003, "token": DOC.token}]},
    meta(APP), meta("7685704028373650648"),
])
def test_unresolved_metadata_does_not_guess_a_recipient(monkeypatch, response):
    client = FeishuDocuments(get_settings())
    monkeypatch.setattr(client, "call", lambda *args: response)
    with pytest.raises(ApiError) as exc:
        client.human_owner(DOC)
    assert exc.value.code == "OWNER_IDENTITY_UNRESOLVED"


@pytest.mark.parametrize("error_code", [99991672, 41050, 41003])
def test_contact_failure_is_not_mistaken_for_a_robot(monkeypatch, error_code):
    client = FeishuDocuments(get_settings())

    def call(path, body=None):
        if "/metas/" in path:
            return meta()
        raise ApiError(502, "FEISHU_DOCUMENT_ACCESS", "unavailable", details={"upstream_code": error_code})

    monkeypatch.setattr(client, "call", call)
    with pytest.raises(ApiError) as exc:
        client.human_owner(DOC)
    assert exc.value.code == "OWNER_IDENTITY_UNRESOLVED"


@pytest.mark.parametrize("user", [{}, {"open_id": OTHER, "user_id": "employee"}, {"open_id": PERSON}])
def test_mismatched_or_incomplete_contact_is_rejected(monkeypatch, user):
    client = FeishuDocuments(get_settings())
    monkeypatch.setattr(client, "call", lambda path, body=None: meta() if "/metas/" in path else {"user": user})
    with pytest.raises(ApiError):
        client.human_owner(DOC)


def test_owner_transfer_is_detected(monkeypatch):
    client = FeishuDocuments(get_settings())
    monkeypatch.setattr(client, "call", lambda *args: meta(OTHER))
    with pytest.raises(ApiError) as exc:
        client.ensure_owner(DOC, HumanRecipient(PERSON))
    assert exc.value.code == "DOCUMENT_OWNER_CHANGED"


def enable_owner(monkeypatch, docs):
    monkeypatch.setenv("AI_COMMENT_MENTION_OWNER", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(docs, "human_owner", lambda document: HumanRecipient(PERSON), raising=False)
    monkeypatch.setattr(docs, "ensure_owner", lambda document, owner: None, raising=False)


def test_enabled_owner_mention_keeps_one_shot_behavior(integration, monkeypatch):
    client, assignment_id, url, docs, ai = integration
    enable_owner(monkeypatch, docs)
    events = []
    monkeypatch.setattr(docs, "comment_on_title", lambda doc, feedback, recipients: events.append(recipients) or "comment-one")
    first = assert_ok(run(client, assignment_id, url))
    assert assert_ok(run(client, assignment_id, url)) == first
    assert events == [(HumanRecipient(PERSON),)]
    assert len(ai.calls) == 1
    assert PERSON not in str(ai.calls)


def test_unverified_owner_fails_before_model_and_comment_and_can_retry(integration, monkeypatch):
    client, assignment_id, url, docs, ai = integration
    enable_owner(monkeypatch, docs)

    def unavailable(document):
        raise ApiError(502, "OWNER_IDENTITY_UNRESOLVED", "未核实所有者")

    monkeypatch.setattr(docs, "human_owner", unavailable)
    assert run(client, assignment_id, url).status_code == 502
    assert not ai.calls and not docs.comments
    history = assert_ok(client.get(f"/api/v1/me/assignments/{assignment_id}/ai-self-checks"))
    assert history[0]["status"] == "FAILED"
    monkeypatch.setattr(docs, "human_owner", lambda document: HumanRecipient(PERSON))
    monkeypatch.setattr(docs, "comment_on_title", lambda document, feedback, recipients: "comment-one")
    assert assert_ok(run(client, assignment_id, url))["status"] == "COMPLETED"


def test_transfer_during_ai_run_does_not_send_to_old_owner(integration, monkeypatch):
    client, assignment_id, url, docs, ai = integration
    enable_owner(monkeypatch, docs)

    def transferred(document, owner):
        raise ApiError(409, "DOCUMENT_OWNER_CHANGED", "所有者发生变更")

    monkeypatch.setattr(docs, "ensure_owner", transferred)
    assert run(client, assignment_id, url).status_code == 409
    assert len(ai.calls) == 1 and not docs.comments
