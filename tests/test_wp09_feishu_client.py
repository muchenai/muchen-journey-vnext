import json
from urllib import parse

import pytest

from journey_api.config import Settings
from journey_api.feishu_oauth import (
    AUTHORIZE_URL,
    TOKEN_URL,
    USER_INFO_URL,
    FeishuOAuthClient,
    OAuthProviderError,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        return self.payload[:size]


def settings() -> Settings:
    return Settings(
        app_env="test",
        session_secret="test-session-secret-independent-00000001",
        invite_secret="test-invite-secret-independent-000000002",
        import_signing_key="test-import-secret-independent-000000003",
        identity_subject_secret="test-subject-secret-independent-0000004",
        feishu_oauth_enabled=True,
        feishu_app_id="cli_test",
        feishu_app_secret="test-feishu-app-secret-00005",
        feishu_oauth_redirect_uri="http://localhost/auth/feishu/callback",
    )


def test_feishu_client_uses_approved_hosts_and_server_side_code_exchange(monkeypatch):
    calls: list[tuple[object, float]] = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if request.full_url == TOKEN_URL:
            return FakeResponse({"access_token": "u-test-token"})
        if request.full_url == USER_INFO_URL:
            return FakeResponse({"data": {"open_id": "ou_stable_subject"}})
        raise AssertionError(request.full_url)

    monkeypatch.setattr("journey_api.feishu_oauth.request.urlopen", fake_urlopen)
    client = FeishuOAuthClient(settings())
    authorization = parse.urlsplit(client.authorization_url("state-value"))
    assert f"{authorization.scheme}://{authorization.netloc}{authorization.path}" == AUTHORIZE_URL
    assert parse.parse_qs(authorization.query) == {
        "app_id": ["cli_test"],
        "redirect_uri": ["http://localhost/auth/feishu/callback"],
        "state": ["state-value"],
    }

    assert client.exchange_code("one-time-code").open_id == "ou_stable_subject"
    token_request, token_timeout = calls[0]
    assert token_timeout == 5
    assert token_request.full_url == TOKEN_URL
    assert token_request.method == "POST"
    assert json.loads(token_request.data) == {
        "grant_type": "authorization_code",
        "client_id": "cli_test",
        "client_secret": "test-feishu-app-secret-00005",
        "code": "one-time-code",
        "redirect_uri": "http://localhost/auth/feishu/callback",
    }
    profile_request, profile_timeout = calls[1]
    assert profile_timeout == 5
    assert profile_request.full_url == USER_INFO_URL
    assert profile_request.headers["Authorization"] == "Bearer u-test-token"


@pytest.mark.parametrize(
    "payload",
    [
        {"code": 10003, "msg": "invalid code"},
        {"access_token": ""},
        ["not", "an", "object"],
    ],
)
def test_feishu_client_rejects_invalid_token_responses(monkeypatch, payload):
    monkeypatch.setattr(
        "journey_api.feishu_oauth.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )
    with pytest.raises(OAuthProviderError):
        FeishuOAuthClient(settings()).exchange_code("invalid-code")
