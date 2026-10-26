import io
import json
import ssl
from urllib.error import HTTPError, URLError

import pytest

from journey_api import ai_self_check_clients as clients
from journey_api.config import Settings
from journey_api.errors import ApiError


def reviewer():
    return clients.AIReviewer(Settings(ai_self_check_enabled=False,
        ai_base_url="https://provider.example/v1", ai_api_key="private-key"))


def install_transport(monkeypatch, outcomes):
    calls, sleeps = [], []
    clock = [0.0]

    class Opener:
        def open(self, request, timeout):
            calls.append(timeout)
            outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            clock[0] += 30
            if isinstance(outcome, Exception):
                raise outcome
            return io.BytesIO(json.dumps(outcome).encode())

    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(clients, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(clients.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(clients.time, "sleep", sleep)
    return calls, sleeps, clock


SUCCESS = {"choices": [{"finish_reason": "stop", "message": {"content": "valid feedback"}}]}


def http_error(status):
    return HTTPError("https://provider.example", status, "private provider detail", {}, io.BytesIO(b"private body"))


@pytest.mark.parametrize("failure", [URLError("private connection detail"), TimeoutError(),
    *[http_error(code) for code in (408, 429, 500, 502, 503, 504)]])
def test_temporary_failure_recovers_and_logs_no_private_input(monkeypatch, caplog, failure):
    calls, sleeps, _ = install_transport(monkeypatch, [failure, SUCCESS])
    assert reviewer().review("private prompt", {"body": "private evidence"}) == "valid feedback"
    assert calls == [180, 149]
    assert sleeps == [1]
    assert '"will_retry": true' in caplog.text
    assert "private" not in caplog.text


def test_failures_stop_after_three_requests(monkeypatch):
    calls, sleeps, _ = install_transport(monkeypatch, [URLError("offline")])
    with pytest.raises(ApiError) as exc:
        reviewer().review("prompt", {})
    assert len(calls) == 3
    assert sleeps == [1, 2]
    assert exc.value.message == "AI 接口暂时不可用，请联系管理员进行检查"


@pytest.mark.parametrize("failure", [*[http_error(code) for code in (400, 401, 403, 404, 422)],
    URLError(ssl.SSLCertVerificationError("invalid certificate")), ValueError("invalid response")])
def test_permanent_failure_is_not_retried(monkeypatch, failure):
    calls, sleeps, _ = install_transport(monkeypatch, [failure])
    with pytest.raises(ApiError):
        reviewer().review("prompt", {})
    assert len(calls) == 1 and sleeps == []


def test_exhausted_time_budget_does_not_start_another_request(monkeypatch):
    calls, sleeps, clock = install_transport(monkeypatch, [URLError("offline")])
    original = clients.request_json

    def slow(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            clock[0] = 180

    monkeypatch.setattr(clients, "request_json", slow)
    with pytest.raises(ApiError):
        reviewer().review("prompt", {})
    assert len(calls) == 1 and sleeps == []


def test_incomplete_generation_is_not_automatically_repeated(monkeypatch):
    calls, sleeps, _ = install_transport(monkeypatch, [{"choices": [{"finish_reason": "length"}]}])
    with pytest.raises(ApiError, match="完整评价"):
        reviewer().review("prompt", {})
    assert len(calls) == 1 and sleeps == []


def test_feishu_transport_never_retries_a_comment(monkeypatch):
    calls, sleeps, _ = install_transport(monkeypatch, [URLError("offline")])
    with pytest.raises(ApiError) as exc:
        clients.request_json("https://feishu.example/comments", body={"text": "comment"})
    assert exc.value.code == "FEISHU_REQUEST_FAILED"
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("failures", [0, 1, 2, 3])
def test_configured_fallback_order_and_actual_model(monkeypatch, failures):
    install_transport(monkeypatch, [URLError("offline")] * failures + [SUCCESS])
    calls = []
    original = clients.request_json

    def capture(*args, **kwargs):
        calls.append((kwargs["body"]["model"], kwargs["body"]["messages"], kwargs["timeout"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(clients, "request_json", capture)
    ai = clients.AIReviewer(Settings(ai_self_check_enabled=False,
        ai_base_url="https://provider.example/v1", ai_api_key="private-key",
        ai_model="deepseek-v4.1-flash", ai_fallback_model="deepseek-v4-pro-0813"))
    if failures == 3:
        with pytest.raises(ApiError):
            ai.review("same rubric", {"body": "same evidence"})
        assert ai.last_model is None
    else:
        assert ai.review("same rubric", {"body": "same evidence"}) == "valid feedback"
        assert ai.last_model == calls[-1][0]
    assert [row[0] for row in calls] == ["deepseek-v4.1-flash", "deepseek-v4.1-flash", "deepseek-v4-pro-0813"][:min(failures + 1, 3)]
    assert all(row[1] == calls[0][1] and row[2] <= 60 for row in calls)


def test_primary_timeout_reserves_time_for_fallback(monkeypatch):
    _, sleeps, clock = install_transport(monkeypatch, [])
    models = []

    def request(*args, **kwargs):
        models.append(kwargs["body"]["model"])
        if len(models) < 3:
            clock[0] += kwargs["timeout"]
            raise ApiError(502, "AI_REQUEST_FAILED", clients.AI_UNAVAILABLE_MESSAGE, retryable=True)
        assert 0 < kwargs["timeout"] <= 57
        return SUCCESS

    monkeypatch.setattr(clients, "request_json", request)
    ai = clients.AIReviewer(Settings(ai_self_check_enabled=False, ai_model="primary", ai_fallback_model="backup"))
    assert ai.review("rubric", {}) == "valid feedback"
    assert models == ["primary", "primary", "backup"] and sleeps == [1, 2]
