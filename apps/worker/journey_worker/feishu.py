from __future__ import annotations

import http.client
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


FEISHU_HOST = "open.feishu.cn"
TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_PATH = "/open-apis/im/v1/messages"
RETRYABLE_CODES = {230020, 99991400, 99991403}


class FeishuDeliveryError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class FeishuReceipt:
    message_id: str


def _json_object(response: http.client.HTTPResponse) -> dict[str, Any]:
    try:
        payload = json.loads(response.read(65_537))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuDeliveryError("FEISHU_INVALID_RESPONSE", retryable=True) from exc
    if not isinstance(payload, dict):
        raise FeishuDeliveryError("FEISHU_INVALID_RESPONSE", retryable=True)
    return payload


def _connection(
    timeout_seconds: int,
) -> http.client.HTTPSConnection:
    return http.client.HTTPSConnection(FEISHU_HOST, timeout=timeout_seconds)


def _provider_error(status: int, payload: dict[str, Any]) -> FeishuDeliveryError:
    raw_code = payload.get("code")
    provider_code = raw_code if isinstance(raw_code, int) else 0
    if status in {408, 429} or status >= 500 or provider_code in RETRYABLE_CODES:
        return FeishuDeliveryError("FEISHU_RETRYABLE", retryable=True)
    if status in {401, 403} or provider_code in {99991663, 99991668}:
        return FeishuDeliveryError("FEISHU_CREDENTIAL_REJECTED", retryable=True)
    if status == 400:
        return FeishuDeliveryError("FEISHU_RECIPIENT_REJECTED", retryable=False)
    return FeishuDeliveryError("FEISHU_PROVIDER_REJECTED", retryable=False)


def deliver(
    *,
    app_id: str,
    app_secret: str,
    receive_id: str,
    dedupe_key: str,
    app_result_url: str,
    timeout_seconds: int,
    connection_factory: Callable[[int], http.client.HTTPSConnection] = _connection,
) -> FeishuReceipt:
    token_connection = connection_factory(timeout_seconds)
    try:
        token_connection.request(
            "POST",
            TOKEN_PATH,
            body=json.dumps(
                {"app_id": app_id, "app_secret": app_secret}, separators=(",", ":")
            ),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        token_response = token_connection.getresponse()
        token_payload = _json_object(token_response)
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise FeishuDeliveryError("FEISHU_NETWORK_ERROR", retryable=True) from exc
    finally:
        token_connection.close()
    if token_response.status != 200 or token_payload.get("code") != 0:
        raise _provider_error(token_response.status, token_payload)
    token = token_payload.get("tenant_access_token")
    if not isinstance(token, str) or not token:
        raise FeishuDeliveryError("FEISHU_INVALID_RESPONSE", retryable=True)

    request_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"journey-next:{dedupe_key}")
    content = json.dumps(
        {
            "text": (
                "Muchen Journey 的结果已更新，请登录应用结果页查看。\n"
                f"{app_result_url}"
            )
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    message_connection = connection_factory(timeout_seconds)
    try:
        message_connection.request(
            "POST",
            f"{MESSAGE_PATH}?receive_id_type=open_id&uuid={request_uuid}",
            body=json.dumps(
                {"receive_id": receive_id, "msg_type": "text", "content": content},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        message_response = message_connection.getresponse()
        message_payload = _json_object(message_response)
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise FeishuDeliveryError("FEISHU_NETWORK_ERROR", retryable=True) from exc
    finally:
        message_connection.close()
    if message_response.status != 200 or message_payload.get("code") != 0:
        raise _provider_error(message_response.status, message_payload)
    data = message_payload.get("data")
    message_id = data.get("message_id") if isinstance(data, dict) else None
    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 200:
        raise FeishuDeliveryError("FEISHU_INVALID_RESPONSE", retryable=True)
    return FeishuReceipt(message_id=message_id)
