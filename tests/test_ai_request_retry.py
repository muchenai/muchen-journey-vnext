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


def capture_requests(monkeypatch):
    requests = []
    original = clients.request_json

    def capture(*args, **kwargs):
        requests.append({"body": json.loads(json.dumps(kwargs["body"])), "timeout": kwargs["timeout"]})
        return original(*args, **kwargs)

    monkeypatch.setattr(clients, "request_json", capture)
    return requests


LENGTH = {"choices": [{"finish_reason": "length", "message": {"content": '{"partial":'}}]}


@pytest.mark.parametrize("truncated", [LENGTH, {"choices": [{"finish_reason": "length"}]}])
def test_length_recovers_once_with_larger_bounded_output_and_compact_json_prompt(monkeypatch, truncated):
    calls, sleeps, _ = install_transport(monkeypatch, [truncated, SUCCESS])
    requests = capture_requests(monkeypatch)
    ai = reviewer()
    assert ai.review("Original rubric, strict JSON and no scores.", {"body": "same evidence"}) == "valid feedback"
    assert len(calls) == 2 and sleeps == []
    assert [request["body"]["max_tokens"] for request in requests] == [3500, 8000]
    original, retry = [request["body"] for request in requests]
    assert retry["messages"][1] == original["messages"][1]
    assert retry["messages"][0]["content"].startswith(original["messages"][0]["content"])
    assert "严格JSON" in retry["messages"][0]["content"]
    assert "全部评价规则" in retry["messages"][0]["content"]
    assert "findings数组则最多8项" in retry["messages"][0]["content"]
    assert "必须完整覆盖所有配置维度" in retry["messages"][0]["content"]
    assert set(retry) == {"model", "stream", "max_tokens", "messages"}
    assert ai.last_model == retry["model"]


@pytest.mark.parametrize("model", sorted(clients.LOW_REASONING_MODELS))
def test_truncated_allowlisted_model_uses_low_reasoning_only_on_recovery(monkeypatch, model):
    install_transport(monkeypatch, [LENGTH, SUCCESS])
    requests = capture_requests(monkeypatch)
    ai = clients.AIReviewer(Settings(ai_self_check_enabled=False, ai_model=model,
        ai_base_url="https://provider.example/v1", ai_api_key="private-key"))
    assert ai.review("publisher standards", {}) == "valid feedback"
    assert "reasoning_effort" not in requests[0]["body"]
    assert requests[1]["body"]["reasoning_effort"] == "low"
    assert requests[1]["body"]["max_tokens"] == 8000


def test_recovery_does_not_forward_unsupported_reasoning_control_to_fallback(monkeypatch):
    install_transport(monkeypatch, [LENGTH, URLError("offline"), SUCCESS])
    requests = capture_requests(monkeypatch)
    ai = clients.AIReviewer(Settings(ai_self_check_enabled=False, ai_model="deepseek-v4.1-flash",
        ai_fallback_model="unrelated-provider-model", ai_base_url="https://provider.example/v1",
        ai_api_key="private-key"))
    assert ai.review("publisher standards", {}) == "valid feedback"
    assert requests[1]["body"]["reasoning_effort"] == "low"
    assert requests[2]["body"]["model"] == "unrelated-provider-model"
    assert "reasoning_effort" not in requests[2]["body"]


def test_second_length_stops_without_accepting_partial_content(monkeypatch, caplog):
    calls, sleeps, _ = install_transport(monkeypatch, [LENGTH])
    ai = reviewer()
    with pytest.raises(ApiError, match="长度上限") as exc:
        ai.review("prompt", {})
    assert exc.value.code == "AI_INCOMPLETE_RESULT"
    assert len(calls) == 2 and sleeps == [] and ai.last_model is None
    logs = [json.loads(record.message) for record in caplog.records]
    assert [record["will_retry"] for record in logs] == [True, False]
    assert all(record["finish_reason"] == "length" for record in logs)


@pytest.mark.parametrize("outcomes", [
    [URLError("offline"), LENGTH, SUCCESS],
    [LENGTH, URLError("offline"), SUCCESS],
])
def test_length_and_network_retries_share_three_attempt_limit_and_model_order(monkeypatch, outcomes):
    calls, _, _ = install_transport(monkeypatch, outcomes)
    requests = capture_requests(monkeypatch)
    ai = clients.AIReviewer(Settings(ai_self_check_enabled=False, ai_model="primary", ai_fallback_model="backup",
        ai_base_url="https://provider.example/v1", ai_api_key="private-key"))
    assert ai.review("rubric", {}) == "valid feedback"
    assert len(calls) == 3 and ai.last_model == "backup"
    assert [request["body"]["model"] for request in requests] == ["primary", "primary", "backup"]
    assert all(request["timeout"] <= 60 for request in requests)
    assert requests[-1]["body"]["max_tokens"] == 8000


def test_length_on_last_attempt_does_not_start_fourth_request(monkeypatch):
    calls, sleeps, _ = install_transport(monkeypatch, [URLError("offline"), URLError("offline"), LENGTH, SUCCESS])
    ai = reviewer()
    with pytest.raises(ApiError, match="长度上限"):
        ai.review("prompt", {})
    assert len(calls) == 3 and sleeps == [1, 2] and ai.last_model is None


def test_content_filter_is_not_retried_or_accepted(monkeypatch):
    filtered = {"choices": [{"finish_reason": "content_filter", "message": {"content": "partial feedback"}}]}
    calls, sleeps, _ = install_transport(monkeypatch, [filtered, SUCCESS])
    ai = reviewer()
    with pytest.raises(ApiError, match="内容安全规则拦截") as exc:
        ai.review("prompt", {})
    assert exc.value.code == "AI_CONTENT_FILTERED"
    assert len(calls) == 1 and sleeps == [] and ai.last_model is None


@pytest.mark.parametrize("response,code,message", [
    ({}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"error": {"message": "private upstream detail"}}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": None}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": {}}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": "private malformed choice"}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": []}, "AI_EMPTY_RESULT", "未返回评价结果"),
    ({"choices": [None]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop"}]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop", "message": []}]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": []}}]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": {}}}]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": False}}]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": 123}}]}, "AI_INVALID_RESPONSE", "数据结构异常"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": None}}]}, "AI_EMPTY_CONTENT", "评价正文为空"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}, "AI_EMPTY_CONTENT", "评价正文为空"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": " \n\t "}}]}, "AI_EMPTY_CONTENT", "评价正文为空"),
    ({"choices": [{"finish_reason": "stop", "message": {"reasoning_content": "private reasoning"}}]}, "AI_EMPTY_CONTENT", "评价正文为空"),
    ({"choices": [{"message": {"content": "answer without finish marker"}}]}, "AI_INCOMPLETE_RESULT", "未返回完整评价"),
    ({"choices": [{"finish_reason": "tool_calls", "message": {"content": "partial feedback"}}]}, "AI_INCOMPLETE_RESULT", "未返回完整评价"),
    ({"choices": [{"finish_reason": {"private": "detail"}, "message": {"content": "partial feedback"}}]}, "AI_INCOMPLETE_RESULT", "未返回完整评价"),
])
def test_empty_or_malformed_generation_has_specific_error_and_never_retries(monkeypatch, response, code, message):
    calls, sleeps, _ = install_transport(monkeypatch, [response, SUCCESS])
    ai = reviewer()
    with pytest.raises(ApiError, match=message) as exc:
        ai.review("prompt", {})
    assert exc.value.code == code
    assert len(calls) == 1 and sleeps == [] and ai.last_model is None


def test_generation_logs_only_allowlisted_metadata(monkeypatch, caplog):
    secret = "private-provider-and-learner-data"
    partial = {"choices": [{"finish_reason": "length", "message": {
        "content": secret, "reasoning_content": secret + secret}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 3500, "total_tokens": 3600,
                  "completion_tokens_details": {"reasoning_tokens": 3000, "private": secret}, "private": secret},
        "error": {"message": secret}}
    unknown_reason = {"choices": [{"finish_reason": secret, "message": {
        "content": secret, "reasoning_content": secret}}],
        "usage": {"prompt_tokens": secret, "completion_tokens": True, "total_tokens": -1,
                  "completion_tokens_details": {"reasoning_tokens": secret}, "private": secret}}
    install_transport(monkeypatch, [partial, unknown_reason])
    with pytest.raises(ApiError):
        reviewer().review("private prompt", {"body": "private evidence"})
    assert "private" not in caplog.text and secret not in caplog.text
    logs = [json.loads(record.message) for record in caplog.records]
    assert logs[0]["usage"] == {"prompt_tokens": 100, "completion_tokens": 3500,
                                "total_tokens": 3600, "reasoning_tokens": 3000}
    assert logs[0]["choices_count"] == 1 and logs[0]["content_type"] == "str"
    assert logs[0]["content_length"] == len(secret) and logs[0]["reasoning_length"] == 2 * len(secret)
    assert logs[1]["finish_reason"] == "other" and logs[1]["usage"] == {}


def test_length_does_not_retry_when_time_budget_is_exhausted(monkeypatch):
    calls, sleeps, clock = install_transport(monkeypatch, [LENGTH, SUCCESS])
    original = clients.request_json

    def slow(*args, **kwargs):
        response = original(*args, **kwargs)
        clock[0] = 180
        return response

    monkeypatch.setattr(clients, "request_json", slow)
    with pytest.raises(ApiError, match="长度上限"):
        reviewer().review("prompt", {})
    assert len(calls) == 1 and sleeps == []


def test_length_retry_uses_remaining_total_time_budget(monkeypatch):
    calls, sleeps, clock = install_transport(monkeypatch, [LENGTH, SUCCESS])
    original = clients.request_json

    def slow_first(*args, **kwargs):
        response = original(*args, **kwargs)
        if len(calls) == 1:
            clock[0] = 170
        return response

    monkeypatch.setattr(clients, "request_json", slow_first)
    assert reviewer().review("prompt", {}) == "valid feedback"
    assert calls == [180, 10] and sleeps == []


def test_scheduler_delay_after_network_retry_cannot_exceed_total_budget(monkeypatch):
    calls, sleeps, clock = install_transport(monkeypatch, [URLError("offline"), SUCCESS])

    def oversleep(delay):
        sleeps.append(delay)
        clock[0] = 180

    monkeypatch.setattr(clients.time, "sleep", oversleep)
    with pytest.raises(ApiError):
        reviewer().review("prompt", {})
    assert len(calls) == 1 and sleeps == [1]


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
