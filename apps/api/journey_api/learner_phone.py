"""Verified phone display data; authentication continues to use hashed subjects."""
import base64
import hashlib
import hmac
import re
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from journey_api.config import get_settings
from journey_api.identity import credential_hash
from journey_api.models import ExternalIdentity


def _key() -> bytes:
    return hashlib.sha256(("learner-phone-display:v1:" + get_settings().identity_subject_secret).encode()).digest()


def _context(identity: ExternalIdentity) -> bytes:
    return f"{identity.organization_id}:{identity.id}:{identity.user_id}".encode()


def remember_verified_phone(identity: ExternalIdentity, phone: str) -> None:
    expected = credential_hash(get_settings().identity_subject_secret, "phone-subject", phone)
    if (identity.provider not in {"PHONE", "PHONE_PASSWORD"} or identity.revoked_at is not None
            or not re.fullmatch(r"1[3-9]\d{9}", phone) or not hmac.compare_digest(identity.subject, expected)):
        raise ValueError("Phone does not match verified identity")
    if read_verified_phone(identity) == phone:
        return
    nonce = secrets.token_bytes(12)
    identity.phone_ciphertext = base64.urlsafe_b64encode(
        nonce + AESGCM(_key()).encrypt(nonce, phone.encode(), _context(identity))).decode()


def read_verified_phone(identity: ExternalIdentity) -> str:
    if identity.provider not in {"PHONE", "PHONE_PASSWORD"} or identity.revoked_at is not None or not identity.phone_ciphertext:
        return ""
    try:
        payload = base64.urlsafe_b64decode(identity.phone_ciphertext)
        phone = AESGCM(_key()).decrypt(payload[:12], payload[12:], _context(identity)).decode()
        expected = credential_hash(get_settings().identity_subject_secret, "phone-subject", phone)
        return phone if re.fullmatch(r"1[3-9]\d{9}", phone) and hmac.compare_digest(identity.subject, expected) else ""
    except (ValueError, InvalidTag, UnicodeError):
        return ""
