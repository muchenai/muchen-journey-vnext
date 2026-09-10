#!/usr/bin/env python3
"""Bounded WP-31 identity delivery using compact JWE (RFC 7516/7518).

Only RSA-OAEP-256 + A256GCM is supported. RSA wraps a fresh 32-byte key,
never the complete identity JSON. No real private key is needed by CI.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAX_RESULT_BYTES = 8192
MAX_ENVELOPE_BYTES = 16384
RESULT_FIELDS = {
    "operator_user_id", "learner_user_id", "owner_user_id", "operator_roles",
    "owner_roles", "operator_link_id", "operator_link_start_path",
    "operator_link_expires_at", "expires_in_minutes",
}
LINK_PREFIX = "/auth/feishu?return_to=%2Fops&link_token="
SAFE_CATEGORIES = {
    "RESULT_CONTRACT_REJECTED", "RECIPIENT_KEY_REJECTED", "RESULT_CONTEXT_REJECTED",
    "ENVELOPE_REJECTED", "RESULT_FILE_REJECTED",
}


class IdentityResultError(ValueError):
    """A stable category, never a value from the identity payload."""


def _json(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise IdentityResultError("RESULT_CONTRACT_REJECTED")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def validate_result(raw: bytes) -> None:
    if not 0 < len(raw) <= MAX_RESULT_BYTES:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    value = _json(raw)
    if not isinstance(value, dict) or set(value) != RESULT_FIELDS:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    if value["operator_roles"] != ["OPERATOR", "REVIEWER"] or value["owner_roles"] != ["LEARNER", "REVIEWER"]:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    for field in ("operator_user_id", "learner_user_id", "owner_user_id", "operator_link_id"):
        identifier = value[field]
        if not isinstance(identifier, str) or str(UUID(identifier)) != identifier:
            raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    if len({value[field] for field in ("operator_user_id", "learner_user_id", "owner_user_id")}) != 3:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    path = value["operator_link_start_path"]
    if not isinstance(path, str) or re.fullmatch(re.escape(LINK_PREFIX) + r"[A-Za-z0-9_-]{43}", path) is None:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    expires = value["operator_link_expires_at"]
    if not isinstance(expires, str) or datetime.fromisoformat(expires).utcoffset() is None:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")
    minutes = value["expires_in_minutes"]
    if type(minutes) is not int or not 5 <= minutes <= 30:
        raise IdentityResultError("RESULT_CONTRACT_REJECTED")


def public_key(pem: bytes) -> rsa.RSAPublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 4096:
        raise IdentityResultError("RECIPIENT_KEY_REJECTED")
    return key


def _header(key: rsa.RSAPublicKey, run_id: str, candidate: str) -> dict[str, str]:
    if re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is None or re.fullmatch(r"[0-9a-f]{40}", candidate) is None:
        raise IdentityResultError("RESULT_CONTEXT_REJECTED")
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return {
        "alg": "RSA-OAEP-256", "enc": "A256GCM", "typ": "wp31-identity-result+jwe",
        "kid": hashlib.sha256(der).hexdigest(), "wp31_run_id": run_id,
        "wp31_candidate": candidate,
    }


def _b64(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _unb64(raw: bytes) -> bytes:
    if re.fullmatch(rb"[A-Za-z0-9_-]+", raw) is None:
        raise IdentityResultError("ENVELOPE_REJECTED")
    value = base64.b64decode(raw + b"=" * (-len(raw) % 4), altchars=b"-_", validate=True)
    if _b64(value) != raw:
        raise IdentityResultError("ENVELOPE_REJECTED")
    return value


def _oaep() -> padding.OAEP:
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def encrypt(raw: bytes, pem: bytes, run_id: str, candidate: str) -> bytes:
    validate_result(raw)
    key = public_key(pem)
    protected = _b64(json.dumps(_header(key, run_id, candidate), sort_keys=True, separators=(",", ":")).encode())
    cek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext_and_tag = AESGCM(cek).encrypt(nonce, raw, protected)
    # JWE AAD is the ASCII protected-header segment, not decoded header JSON.
    return b".".join((protected, _b64(key.encrypt(cek, _oaep())), _b64(nonce),
                      _b64(ciphertext_and_tag[:-16]), _b64(ciphertext_and_tag[-16:])))


def decrypt(envelope: bytes, pem: bytes, run_id: str, candidate: str) -> bytes:
    if not 0 < len(envelope) <= MAX_ENVELOPE_BYTES:
        raise IdentityResultError("ENVELOPE_REJECTED")
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size != 4096:
        raise IdentityResultError("RECIPIENT_KEY_REJECTED")
    parts = envelope.split(b".")
    if len(parts) != 5:
        raise IdentityResultError("ENVELOPE_REJECTED")
    protected, wrapped, nonce, ciphertext, tag = map(_unb64, parts)
    if _json(protected) != _header(key.public_key(), run_id, candidate):
        raise IdentityResultError("RESULT_CONTEXT_REJECTED")
    if len(wrapped) != 512 or len(nonce) != 12 or len(tag) != 16 or len(ciphertext) > MAX_RESULT_BYTES:
        raise IdentityResultError("ENVELOPE_REJECTED")
    cek = key.decrypt(wrapped, _oaep())
    if len(cek) != 32:
        raise IdentityResultError("ENVELOPE_REJECTED")
    raw = AESGCM(cek).decrypt(nonce, ciphertext + tag, parts[0])
    validate_result(raw)
    return raw


def _read(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise IdentityResultError("RESULT_FILE_REJECTED")
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise IdentityResultError("RESULT_FILE_REJECTED")
    return value


def _write_new(path: Path, value: bytes) -> None:
    # Never overwrite an existing result (including symlinks); no partial output on failure.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-key")
    check.add_argument("--public-key", type=Path, required=True)
    for name, key_flag in (("encrypt", "--public-key"), ("decrypt", "--private-key")):
        operation = sub.add_parser(name)
        operation.add_argument(key_flag, type=Path, required=True)
        operation.add_argument("--input", type=Path, required=True)
        operation.add_argument("--output", type=Path, required=True)
        operation.add_argument("--run-id", required=True)
        operation.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check-key":
            public_key(_read(args.public_key, MAX_ENVELOPE_BYTES))
        elif args.command == "encrypt":
            value = encrypt(_read(args.input, MAX_RESULT_BYTES), _read(args.public_key, MAX_ENVELOPE_BYTES), args.run_id, args.candidate)
            _write_new(args.output, value)
        else:
            value = decrypt(_read(args.input, MAX_ENVELOPE_BYTES), _read(args.private_key, MAX_ENVELOPE_BYTES), args.run_id, args.candidate)
            _write_new(args.output, value)
    except Exception as error:
        # Parsing, crypto, and I/O errors can embed credentials or private paths.
        category = str(error) if isinstance(error, IdentityResultError) and str(error) in SAFE_CATEGORIES else "RESULT_DELIVERY_REJECTED"
        print("WP31_IDENTITY_RESULT=FAIL category=" + category, file=sys.stderr)
        return 2
    print("WP31_IDENTITY_RESULT=PASS operation=" + args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
