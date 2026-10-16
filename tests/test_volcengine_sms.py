import io
import json
from urllib.error import HTTPError

import pytest

from journey_api.sms import SmsDeliveryError, VolcengineSmsClient


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return json.dumps(self.payload).encode()


def _client() -> VolcengineSmsClient:
    return VolcengineSmsClient(
        access_key_id="test-ak",
        secret_access_key="test-sk",
        sms_account="account",
        sign="沐晨",
        template_id="SPT_test",
        template_code_param="xxxx",
    )


def test_send_code_signs_request_without_exposing_credentials(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({"ResponseMetadata": {}, "Result": {"MessageID": "msg-1"}})

    monkeypatch.setattr("journey_api.sms.urlopen", fake_urlopen)

    assert _client().send_code("13800138000", "654321") == "msg-1"
    request = captured["request"]
    assert request.full_url.endswith("Action=SendSms&Version=2020-01-01")
    assert request.headers["Authorization"].startswith("HMAC-SHA256 Credential=test-ak/")
    assert "test-sk" not in request.headers["Authorization"]
    body = json.loads(request.data)
    assert body["PhoneNumbers"] == "13800138000"
    assert json.loads(body["TemplateParam"]) == {"xxxx": "654321"}


def test_send_code_uses_correlation_tag(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return _Response({"ResponseMetadata": {}, "Result": {"MessageID": ["msg-2"]}})

    monkeypatch.setattr("journey_api.sms.urlopen", fake_urlopen)

    assert _client().send_code("13800138000", "654321", tag="req-safe") == "msg-2"
    assert captured["body"]["Tag"] == "req-safe"


def test_send_code_accepts_message_id_list(monkeypatch):
    monkeypatch.setattr(
        "journey_api.sms.urlopen",
        lambda *_args, **_kwargs: _Response(
            {"ResponseMetadata": {}, "Result": {"MessageID": ["msg-1"]}}
        ),
    )

    assert _client().send_code("13800138000", "654321") == "msg-1"


def test_send_code_maps_provider_error(monkeypatch):
    monkeypatch.setattr(
        "journey_api.sms.urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "ResponseMetadata": {
                    "Error": {"Code": "Throttling", "Message": "too many requests"}
                }
            }
        ),
    )

    with pytest.raises(SmsDeliveryError) as raised:
        _client().send_code("13800138000", "654321")

    assert raised.value.retryable is True
    assert "Throttling" in str(raised.value)


def test_send_code_maps_http_failure(monkeypatch):
    def fail(*_args, **_kwargs):
        raise HTTPError("https://sms.volcengineapi.com", 503, "down", {}, io.BytesIO())

    monkeypatch.setattr("journey_api.sms.urlopen", fail)

    with pytest.raises(SmsDeliveryError) as raised:
        _client().send_code("13800138000", "654321")

    assert raised.value.retryable is True
