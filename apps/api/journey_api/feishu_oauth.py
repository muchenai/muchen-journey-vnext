import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib import error, parse, request

from journey_api.config import Settings, get_settings

AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
MAX_RESPONSE_BYTES = 65_536


class OAuthProviderError(RuntimeError):
    """A deliberately detail-free provider error safe for API translation."""


@dataclass(frozen=True)
class FeishuProfile:
    open_id: str


def _read_json(response: Any) -> dict[str, Any]:
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OAuthProviderError("provider response exceeded the approved size")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthProviderError("provider returned an invalid response") from exc
    if not isinstance(payload, dict):
        raise OAuthProviderError("provider returned an invalid response")
    return payload


class FeishuOAuthClient:
    def __init__(self, settings: Settings) -> None:
        self._app_id = settings.feishu_app_id
        self._app_secret = settings.feishu_app_secret
        self._redirect_uri = settings.feishu_oauth_redirect_uri

    def authorization_url(self, state: str) -> str:
        query = parse.urlencode(
            {
                "app_id": self._app_id,
                "redirect_uri": self._redirect_uri,
                "state": state,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    def exchange_code(self, code: str) -> FeishuProfile:
        token_payload = self._request_json(
            TOKEN_URL,
            method="POST",
            body={
                "grant_type": "authorization_code",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "code": code,
                "redirect_uri": self._redirect_uri,
            },
        )
        token_data = token_payload.get("data", token_payload)
        access_token = token_data.get("access_token") if isinstance(token_data, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise OAuthProviderError("provider did not return an access token")
        profile_payload = self._request_json(
            USER_INFO_URL,
            method="GET",
            authorization=access_token,
        )
        profile_data = profile_payload.get("data", profile_payload)
        open_id = profile_data.get("open_id") if isinstance(profile_data, dict) else None
        if not isinstance(open_id, str) or not 1 <= len(open_id) <= 180:
            raise OAuthProviderError("provider did not return a stable subject")
        return FeishuProfile(open_id=open_id)

    @staticmethod
    def _request_json(
        url: str,
        *,
        method: str,
        body: dict[str, str] | None = None,
        authorization: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        encoded = None
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            encoded = json.dumps(body, separators=(",", ":")).encode()
        if authorization is not None:
            headers["Authorization"] = f"Bearer {authorization}"
        provider_request = request.Request(url, data=encoded, headers=headers, method=method)
        try:
            with request.urlopen(provider_request, timeout=5) as response:
                return _read_json(response)
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise OAuthProviderError("provider request failed") from exc


@lru_cache
def get_feishu_oauth_client() -> FeishuOAuthClient:
    return FeishuOAuthClient(get_settings())
