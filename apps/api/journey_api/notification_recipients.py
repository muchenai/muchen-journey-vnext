from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


OPEN_ID_PATTERN = re.compile(r"^ou_[A-Za-z0-9_-]{8,120}$")
KEY_VERSION = 1


def decode_recipient_key(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        key = base64.b64decode(
            (value + padding).encode("ascii"), altchars=b"-_", validate=True
        )
    except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError(
            "NOTIFICATION_RECIPIENT_KEY must be URL-safe base64"
        ) from exc
    if len(key) != 32:
        raise ValueError("NOTIFICATION_RECIPIENT_KEY must decode to exactly 32 bytes")
    return key


def validate_open_id(value: str) -> str:
    normalized = value.strip()
    if not OPEN_ID_PATTERN.fullmatch(normalized):
        raise ValueError("Feishu recipient must be one valid open_id")
    return normalized


def endpoint_aad(organization_id: uuid.UUID, user_id: uuid.UUID) -> bytes:
    return (
        "journey-next:notification-endpoint:v1:"
        f"{organization_id}:{user_id}:FEISHU:open_id"
    ).encode("ascii")


def encrypt_open_id(
    value: str,
    *,
    key_value: str,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[str, str]:
    recipient = validate_open_id(value)
    key = decode_recipient_key(key_value)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        recipient.encode("utf-8"),
        endpoint_aad(organization_id, user_id),
    )
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
    fingerprint = hmac.new(
        key,
        b"notification-recipient-fingerprint:v1:" + recipient.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"v{KEY_VERSION}.{encoded}", fingerprint


def decrypt_open_id(
    value: str,
    *,
    key_value: str,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    prefix, separator, encoded = value.partition(".")
    if prefix != f"v{KEY_VERSION}" or not separator or not encoded:
        raise ValueError("notification endpoint ciphertext version is invalid")
    key = decode_recipient_key(key_value)
    try:
        padding = "=" * (-len(encoded) % 4)
        blob = base64.b64decode(
            (encoded + padding).encode("ascii"), altchars=b"-_", validate=True
        )
        if len(blob) < 29:
            raise ValueError("notification endpoint ciphertext is truncated")
        plaintext = AESGCM(key).decrypt(
            blob[:12],
            blob[12:],
            endpoint_aad(organization_id, user_id),
        )
        recipient = plaintext.decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("notification endpoint ciphertext is invalid") from exc
    return validate_open_id(recipient)
