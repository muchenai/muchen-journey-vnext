"""Read retries never duplicate document writes or model generation."""
import io
import json
import ssl
from http.client import BadStatusLine, HTTPException, IncompleteRead, LineTooLong
from urllib.error import HTTPError, URLError

import pytest

from journey_api import ai_self_check_clients as clients
from journey_api.errors import ApiError


SUCCESS = {"code": 0, "data": {"items": []}}
READ_URL = "https://open.feishu.cn/open-apis/docx/v1/documents/documenttoken123"
META_URL = "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=open_id"
META_BODY = {"request_docs": [{"doc_token": "documenttoken123", "doc_type": "docx"}]}
COMMENT_QUERY_URL = "https://open.feishu.cn/open-apis/drive/v1/files/documenttoken123/comments/batch_query?file_type=docx"
COMMENT_QUERY_BODY = {"comment_ids": ["7709459938531151100"]}


def install_transport(monkeypatch, outcomes):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append((request.get_method(), timeout))
            outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, io.BytesIO):
                return outcome
            payload = outcome if isinstance(outcome, bytes) else json.dumps(outcome).encode()
            return io.BytesIO(payload)

    monkeypatch.setattr(clients, "build_opener", lambda *args: Opener())
    return calls


def http_error(status, payload=None):
    return HTTPError(READ_URL, status, "private upstream detail", {},
                     io.BytesIO(json.dumps(payload or {"message": "private response"}).encode()))


@pytest.mark.parametrize("failure", [
    TimeoutError("private timeout"),
    URLError("private interrupted connection"),
    ConnectionResetError("private reset"),
])
def test_feishu_get_recovers_once_with_sixty_second_timeout_without_logging_private_data(monkeypatch, caplog, failure):
    calls = install_transport(monkeypatch, [failure, SUCCESS])
    assert clients.request_json(READ_URL, token="private-token") == SUCCESS
    assert calls == [("GET", 60), ("GET", 60)]
    assert "private" not in caplog.text


def test_feishu_get_exhausts_after_two_attempts_with_clear_error(monkeypatch, caplog):
    calls = install_transport(monkeypatch, [URLError("private connection failure")])
    with pytest.raises(ApiError) as exc:
        clients.request_json(READ_URL, timeout=7)
    assert calls == [("GET", 7), ("GET", 7)]
    assert exc.value.code == "FEISHU_REQUEST_FAILED"
    assert exc.value.details == {"upstream_status": None}
    assert isinstance(exc.value.__cause__, URLError)
    assert "private" not in exc.value.message + caplog.text


class InterruptedResponse(io.BytesIO):
    def read(self, size=-1):
        raise IncompleteRead(b"private partial response", 1)


def test_feishu_get_retries_interrupted_response_read(monkeypatch):
    calls = install_transport(monkeypatch, [InterruptedResponse(), SUCCESS])
    assert clients.request_json(READ_URL) == SUCCESS
    assert calls == [("GET", 60), ("GET", 60)]


def test_feishu_get_exhausted_interruption_has_clear_transport_error(monkeypatch):
    calls = install_transport(monkeypatch, [IncompleteRead(b"private partial", 1)])
    with pytest.raises(ApiError) as exc:
        clients.request_json(READ_URL)
    assert len(calls) == 2
    assert exc.value.code == "FEISHU_REQUEST_FAILED"
    assert isinstance(exc.value.__cause__, IncompleteRead)


@pytest.mark.parametrize("failure", [
    HTTPException("private protocol error"),
    BadStatusLine("private malformed status"),
    LineTooLong("private header"),
])
def test_malformed_http_protocol_is_reported_without_retry(monkeypatch, failure):
    calls = install_transport(monkeypatch, [failure, SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json(READ_URL)
    assert calls == [("GET", 60)]
    assert exc.value.code == "FEISHU_REQUEST_FAILED"
    assert exc.value.__cause__ is failure
    assert "private" not in exc.value.message


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_feishu_get_retries_only_transient_http_statuses(monkeypatch, status):
    calls = install_transport(monkeypatch, [http_error(status, {"code": 99991400}), SUCCESS])
    assert clients.request_json(READ_URL) == SUCCESS
    assert len(calls) == 2


def test_exhausted_transient_http_status_has_clear_transport_error(monkeypatch):
    calls = install_transport(monkeypatch, [http_error(503), http_error(503), SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json(READ_URL)
    assert len(calls) == 2
    assert exc.value.code == "FEISHU_REQUEST_FAILED"
    assert exc.value.details == {"upstream_status": 503}


def test_exhausted_feishu_get_rate_limit_preserves_explicit_numeric_rejection(monkeypatch):
    calls = install_transport(monkeypatch, [
        http_error(429, {"code": 99991400}), http_error(429, {"code": 99991400}), SUCCESS])
    assert clients.request_json(READ_URL) == {"code": 99991400}
    assert len(calls) == 2


def test_comment_rate_limit_preserves_explicit_rejection_without_retry(monkeypatch):
    calls = install_transport(monkeypatch, [http_error(429, {"code": 99991400}), SUCCESS])
    assert clients.request_json("https://open.feishu.cn/open-apis/drive/v1/files/documenttoken123/new_comments",
                                body={"text": "private"}) == {"code": 99991400}
    assert calls == [("POST", 20)]


@pytest.mark.parametrize("failure", [
    ssl.SSLCertVerificationError("private certificate"),
    URLError(ssl.SSLCertVerificationError("private certificate")),
])
@pytest.mark.parametrize("url,body", [(READ_URL, None), (META_URL, META_BODY), (COMMENT_QUERY_URL, COMMENT_QUERY_BODY)])
def test_certificate_failure_never_retries(monkeypatch, failure, url, body):
    calls = install_transport(monkeypatch, [failure, SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json(url, body=body)
    assert len(calls) == 1
    assert exc.value.code == "FEISHU_REQUEST_FAILED"


@pytest.mark.parametrize("method,body", [
    (None, {"comment": "private comment"}),
    ("POST", {"comment": "private comment"}),
    ("PUT", {"comment": "private comment"}),
    ("PATCH", {"comment": "private comment"}),
    ("DELETE", None),
])
@pytest.mark.parametrize("failure", [TimeoutError(), IncompleteRead(b"private partial", 1), http_error(503)])
def test_comment_writes_are_never_retried(monkeypatch, method, body, failure):
    calls = install_transport(monkeypatch, [failure, SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json("https://open.feishu.cn/open-apis/drive/v1/files/documenttoken123/comments",
                             body=body, method=method)
    assert calls == [(method or "POST", 20)]
    assert exc.value.code == "FEISHU_REQUEST_FAILED"


def test_auth_post_is_never_retried(monkeypatch):
    calls = install_transport(monkeypatch, [URLError("private auth failure"), SUCCESS])
    with pytest.raises(ApiError):
        clients.request_json("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                             body={"app_id": "private-id", "app_secret": "private-secret"})
    assert calls == [("POST", 20)]


@pytest.mark.parametrize("method,body", [("GET", None), ("POST", {"prompt": "private prompt"})])
@pytest.mark.parametrize("failure", [TimeoutError(), IncompleteRead(b"private partial", 1)])
@pytest.mark.parametrize("timeout", [60, 180])
def test_ai_transport_never_adds_retries(monkeypatch, method, body, failure, timeout):
    calls = install_transport(monkeypatch, [failure, SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json("https://ai.example/chat/completions", service="AI", method=method, body=body,
                             timeout=timeout)
    assert calls == [(method, timeout)]
    assert exc.value.code == "AI_REQUEST_FAILED"
    assert exc.value.retryable


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_explicit_feishu_rejection_preserves_numeric_code_without_retry(monkeypatch, status):
    calls = install_transport(monkeypatch, [http_error(status, {"code": 99991672, "msg": "private"}), SUCCESS])
    assert clients.request_json(READ_URL) == {"code": 99991672}
    assert len(calls) == 1


def test_explicit_http_rejection_with_interrupted_error_body_does_not_retry(monkeypatch):
    rejection = HTTPError(READ_URL, 403, "private detail", {}, InterruptedResponse())
    calls = install_transport(monkeypatch, [rejection, SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json(READ_URL)
    assert len(calls) == 1
    assert exc.value.code == "FEISHU_REQUEST_FAILED"
    assert exc.value.details == {"upstream_status": 403}


@pytest.mark.parametrize("payload", [b"private invalid json", b"[]", b"x" * 2_000_001],
                         ids=["invalid-json", "non-object", "oversized"])
@pytest.mark.parametrize("url,body", [(READ_URL, None), (META_URL, META_BODY), (COMMENT_QUERY_URL, COMMENT_QUERY_BODY)])
def test_invalid_or_oversized_json_is_not_retried(monkeypatch, payload, url, body):
    calls = install_transport(monkeypatch, [payload, SUCCESS])
    with pytest.raises(ApiError) as exc:
        clients.request_json(url, body=body)
    assert len(calls) == 1
    assert exc.value.code == "FEISHU_REQUEST_FAILED"


@pytest.mark.parametrize("method", [None, "POST"])
def test_metadata_post_recovers_once_with_sixty_second_timeout(monkeypatch, method):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    assert clients.request_json(META_URL, body=META_BODY, method=method) == SUCCESS
    assert calls == [("POST", 60), ("POST", 60)]


def test_metadata_post_exhausts_after_two_sixty_second_attempts(monkeypatch):
    calls = install_transport(monkeypatch, [TimeoutError()])
    with pytest.raises(ApiError) as exc:
        clients.request_json(META_URL, body=META_BODY)
    assert calls == [("POST", 60), ("POST", 60)]
    assert exc.value.code == "FEISHU_REQUEST_FAILED"


def test_owner_metadata_query_uses_read_policy_through_documents_call(monkeypatch):
    owner = "ou_abcdefghij123"
    response = {"code": 0, "data": {"metas": [{
        "doc_token": "documenttoken123", "doc_type": "docx", "owner_id": owner}]}}
    calls = install_transport(monkeypatch, [TimeoutError(), response])
    documents = clients.FeishuDocuments(None)
    documents._token = "private-token"
    document = clients.Document("documenttoken123", "title", "title", "body", "1")
    assert documents.owner_open_id(document) == owner
    assert calls == [("POST", 60), ("POST", 60)]


@pytest.mark.parametrize("url", [
    "http://open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=open_id",
    "https://open.feishu.cn.evil.example/open-apis/drive/v1/metas/batch_query?user_id_type=open_id",
    "https://open.feishu.cn@evil.example/open-apis/drive/v1/metas/batch_query?user_id_type=open_id",
    "https://open.feishu.cn:444/open-apis/drive/v1/metas/batch_query?user_id_type=open_id",
    "https://private@open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=open_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query/comments?user_id_type=open_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas//batch_query?user_id_type=open_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas/../metas/batch_query?user_id_type=open_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas/%62atch_query?user_id_type=open_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query",
    "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=user_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=open_id&user_id_type=open_id",
    "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=open_id&operation=comment",
    META_URL + "#comment",
])
def test_spoofed_metadata_post_is_not_given_read_timeout_or_retries(monkeypatch, url):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    with pytest.raises(ApiError):
        clients.request_json(url, body=META_BODY)
    assert calls == [("POST", 20)]


@pytest.mark.parametrize("method,body", [
    ("PUT", META_BODY), ("PATCH", META_BODY), ("DELETE", META_BODY), ("GET", META_BODY),
    ("POST", {}), ("POST", {"request_docs": []}),
    ("POST", {"request_docs": [{"doc_token": "documenttoken123", "doc_type": "docx"}], "comment": "private"}),
])
def test_metadata_path_alone_never_enables_read_policy(monkeypatch, method, body):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    with pytest.raises(ApiError):
        clients.request_json(META_URL, method=method, body=body)
    assert calls == [(method, 20)]


def test_unofficial_get_is_not_given_feishu_read_policy(monkeypatch):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    with pytest.raises(ApiError):
        clients.request_json("https://feishu.example/documents")
    assert calls == [("GET", 20)]


def test_comment_visibility_query_recovers_once_with_sixty_second_timeout(monkeypatch):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    assert clients.request_json(COMMENT_QUERY_URL, body=COMMENT_QUERY_BODY) == SUCCESS
    assert calls == [("POST", 60), ("POST", 60)]


def test_comment_visibility_query_exhausts_after_two_attempts(monkeypatch):
    calls = install_transport(monkeypatch, [TimeoutError()])
    with pytest.raises(ApiError) as exc:
        clients.request_json(COMMENT_QUERY_URL, body=COMMENT_QUERY_BODY)
    assert calls == [("POST", 60), ("POST", 60)]
    assert exc.value.code == "FEISHU_REQUEST_FAILED"


@pytest.mark.parametrize("is_solved", [False, True])
def test_update_title_comment_retries_only_visibility_reads_and_never_replays_writes(monkeypatch, is_solved):
    comment_id = COMMENT_QUERY_BODY["comment_ids"][0]
    current = {"code": 0, "data": {"items": [{"comment_id": comment_id, "is_solved": is_solved}]}}
    opened = {"code": 0, "data": {"items": [{"comment_id": comment_id, "is_solved": False}]}}
    outcomes = [{"code": 0}, TimeoutError(), current]
    expected = [("PUT", 20), ("POST", 60), ("POST", 60)]
    if is_solved:
        outcomes.extend([{"code": 0}, TimeoutError(), opened])
        expected.extend([("PATCH", 20), ("POST", 60), ("POST", 60)])
    calls = install_transport(monkeypatch, outcomes)
    documents = clients.FeishuDocuments(None)
    documents._token = "private-token"
    document = clients.Document("documenttoken123", "title", "title", "body", "1")
    recipient = clients.HumanRecipient("ou_abcdefghij123")
    assert documents.update_title_comment(document, comment_id, "123", "private feedback", (recipient,)) == comment_id
    assert calls == expected


@pytest.mark.parametrize("url,body,method", [
    (COMMENT_QUERY_URL.replace("open.feishu.cn", "open.feishu.cn.evil.example"), COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL.replace("/batch_query", "/new_comments"), COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL.replace("/batch_query", "/batch_query/"), COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL.replace("/batch_query", "/%62atch_query"), COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL + "&is_solved=false", COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL + "&file_type=docx", COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL.replace("file_type=docx", "file_type=sheet"), COMMENT_QUERY_BODY, "POST"),
    (COMMENT_QUERY_URL, {"comment_ids": []}, "POST"),
    (COMMENT_QUERY_URL, {"comment_ids": ["bad/comment"]}, "POST"),
    (COMMENT_QUERY_URL, {"comment_ids": ["1", "2"]}, "POST"),
    (COMMENT_QUERY_URL, {**COMMENT_QUERY_BODY, "is_solved": False}, "POST"),
    (COMMENT_QUERY_URL, COMMENT_QUERY_BODY, "PUT"),
    (COMMENT_QUERY_URL, COMMENT_QUERY_BODY, "PATCH"),
])
def test_comment_query_policy_rejects_wrong_origin_path_query_body_and_methods(monkeypatch, url, body, method):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    with pytest.raises(ApiError):
        clients.request_json(url, body=body, method=method)
    assert calls == [(method, 20)]


@pytest.mark.parametrize("method,suffix,body", [
    ("POST", "new_comments", {"reply_elements": [{"type": "text", "text": "private"}]}),
    ("PUT", "comments/7709459938531151100/replies/123?file_type=docx&user_id_type=open_id",
     {"content": {"elements": []}}),
    ("PATCH", "comments/7709459938531151100?file_type=docx", {"is_solved": False}),
])
def test_real_comment_write_paths_keep_twenty_seconds_and_one_attempt(monkeypatch, method, suffix, body):
    calls = install_transport(monkeypatch, [TimeoutError(), SUCCESS])
    with pytest.raises(ApiError):
        clients.request_json("https://open.feishu.cn/open-apis/drive/v1/files/documenttoken123/" + suffix,
                             method=method, body=body)
    assert calls == [(method, 20)]
