from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


VOLCENGINE_SMS_HOST = "sms.volcengineapi.com"
VOLCENGINE_SMS_REGION = "cn-north-1"
VOLCENGINE_SMS_SERVICE = "volcSMS"
VOLCENGINE_SMS_VERSION = "2020-01-01"
VOLCENGINE_SMS_CONTENT_TYPE = "application/json;charset=utf-8"


class SmsDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def _canonical_query(parameters: dict[str, str]) -> str:
    return "&".join(
        f"{quote(key, safe='-_.~')}={quote(str(parameters[key]), safe='-_.~')}"
        for key in sorted(parameters)
    )


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def _signed_headers(
    parameters: dict[str, str],
    access_key_id: str,
    secret_access_key: str,
    body: bytes,
    *,
    method: str = "POST",
    now: datetime | None = None,
) -> dict[str, str]:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    date = timestamp[:8]
    body_sha256 = hashlib.sha256(body).hexdigest()
    headers = {
        "Host": VOLCENGINE_SMS_HOST,
        "X-Content-Sha256": body_sha256,
        "X-Date": timestamp,
        "Content-Type": VOLCENGINE_SMS_CONTENT_TYPE,
    }
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    names = sorted(normalized_headers)
    canonical_headers = "".join(
        f"{name}:{normalized_headers[name]}\n" for name in names
    )
    signed_names = ";".join(names)
    canonical_request = "\n".join(
        (
            method,
            "/",
            _canonical_query(parameters),
            canonical_headers,
            signed_names,
            body_sha256,
        )
    )
    scope = f"{date}/{VOLCENGINE_SMS_REGION}/{VOLCENGINE_SMS_SERVICE}/request"
    string_to_sign = "\n".join(
        (
            "HMAC-SHA256",
            timestamp,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        )
    )
    signing_key = _hmac(
        _hmac(
            _hmac(_hmac(secret_access_key.encode(), date), VOLCENGINE_SMS_REGION),
            VOLCENGINE_SMS_SERVICE,
        ),
        "request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"HMAC-SHA256 Credential={access_key_id}/{scope}, "
        f"SignedHeaders={signed_names}, Signature={signature}"
    )
    return headers


@dataclass(frozen=True)
class VolcengineSmsClient:
    access_key_id: str
    secret_access_key: str
    sms_account: str
    sign: str
    template_id: str
    template_code_param: str = "code"
    timeout_seconds: int = 10

    def send_code(self, phone: str, code: str, *, tag: str = "muchen-journey-login") -> str:
        body = json.dumps(
            {
                "SmsAccount": self.sms_account,
                "Sign": self.sign,
                "TemplateID": self.template_id,
                "TemplateParam": json.dumps(
                    {self.template_code_param: code},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "PhoneNumbers": phone,
                "Tag": tag,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        result = self._request("SendSms", body)
        message_id = self._message_id(result)
        if not message_id:
            raise SmsDeliveryError("短信服务未返回发送凭证。")
        return message_id

    def _request(
        self,
        action: str,
        body: bytes = b"{}",
        *,
        method: str = "POST",
        version: str = VOLCENGINE_SMS_VERSION,
        query: dict[str, str] | None = None,
    ) -> dict[str, object]:
        parameters = {"Action": action, "Version": version, **(query or {})}
        request_body = body if method != "GET" else b""
        request = Request(
            f"https://{VOLCENGINE_SMS_HOST}/?{_canonical_query(parameters)}",
            data=request_body if method != "GET" else None,
            headers=_signed_headers(
                parameters,
                self.access_key_id,
                self.secret_access_key,
                request_body,
                method=method,
            ),
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw = response.read(1_000_001)
        except HTTPError as error:
            retryable = error.code == 429 or error.code >= 500
            raise SmsDeliveryError(
                f"短信服务请求失败（HTTP {error.code}）。", retryable=retryable
            ) from error
        except (URLError, TimeoutError) as error:
            raise SmsDeliveryError("短信服务暂时无法连接。", retryable=True) from error
        if len(raw) > 1_000_000:
            raise SmsDeliveryError("短信服务响应异常。")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SmsDeliveryError("短信服务返回了无法识别的响应。") from error
        if not isinstance(payload, dict):
            raise SmsDeliveryError("短信服务返回了无法识别的响应。")
        metadata = payload.get("ResponseMetadata")
        provider_error = metadata.get("Error") if isinstance(metadata, dict) else None
        if isinstance(provider_error, dict):
            provider_code = str(provider_error.get("Code", "UNKNOWN"))
            retryable = provider_code in {"Throttling", "ServiceUnavailable", "InternalError"}
            raise SmsDeliveryError(
                f"短信服务拒绝了发送请求（{provider_code}）。", retryable=retryable
            )
        return payload

    @staticmethod
    def _message_id(payload: dict[str, object]) -> str:
        result = payload.get("Result")
        if not isinstance(result, dict):
            return ""
        for key in ("MessageID", "MessageId", "message_id"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list) and value and isinstance(value[0], str):
                return value[0]
        return ""
