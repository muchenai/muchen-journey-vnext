#!/usr/bin/env python3
"""Create and verify chained, expiring, HMAC-bound WP-31 phase evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


SHA256 = re.compile(r"[0-9a-f]{64}")
RUN_ID = re.compile(r"[1-9][0-9]{5,19}")
PHASES = ("preflight", "backup-restore", "deploy", "inspect", "rollback")


class PhaseEvidenceError(RuntimeError):
    pass


def canonical(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def key() -> bytes:
    value = os.getenv("WP15_BACKUP_KEY", "")
    if len(value) < 32 or "\n" in value or "\r" in value:
        raise PhaseEvidenceError("phase evidence key is unavailable")
    return value.encode()


def parse_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PhaseEvidenceError("evidence time is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise PhaseEvidenceError("evidence time is invalid") from error
    if parsed.tzinfo != timezone.utc:
        raise PhaseEvidenceError("evidence time is not UTC")
    return parsed


def load(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise PhaseEvidenceError("evidence is not a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PhaseEvidenceError("evidence is not an object")
    return value


def create(
    output: Path,
    phase: str,
    run_id: str,
    candidate: str,
    ops_manifest_sha256: str,
    rollback_candidate: str,
    previous_run_id: str | None,
    payloads: list[Path],
    lifetime_minutes: int,
) -> dict[str, object]:
    if output.exists() or output.is_symlink():
        raise PhaseEvidenceError("evidence output already exists")
    if phase not in PHASES or not RUN_ID.fullmatch(run_id):
        raise PhaseEvidenceError("phase or run ID is invalid")
    if previous_run_id is not None and not RUN_ID.fullmatch(previous_run_id):
        raise PhaseEvidenceError("previous run ID is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate) or not re.fullmatch(
        r"[0-9a-f]{40}", rollback_candidate
    ):
        raise PhaseEvidenceError("candidate binding is invalid")
    if not SHA256.fullmatch(ops_manifest_sha256):
        raise PhaseEvidenceError("ops manifest binding is invalid")
    if not 1 <= lifetime_minutes <= 60:
        raise PhaseEvidenceError("evidence lifetime is invalid")
    payload_hashes: dict[str, str] = {}
    for path in payloads:
        resolved = path.resolve()
        if path.is_symlink() or not path.is_file() or path.name in payload_hashes:
            raise PhaseEvidenceError("payload is invalid")
        payload_hashes[path.name] = file_sha256(resolved)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    body: dict[str, object] = {
        "schema_version": 1,
        "phase": phase,
        "run_id": run_id,
        "candidate_sha": candidate,
        "ops_manifest_sha256": ops_manifest_sha256,
        "rollback_candidate_sha": rollback_candidate,
        "previous_run_id": previous_run_id,
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (now + timedelta(minutes=lifetime_minutes))
        .isoformat()
        .replace("+00:00", "Z"),
        "payload_sha256": payload_hashes,
    }
    body["evidence_hmac_sha256"] = hmac.new(key(), canonical(body), hashlib.sha256).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2, sort_keys=True)
        handle.write("\n")
    output.chmod(0o600)
    return body


def verify(
    path: Path,
    phase: str,
    run_id: str,
    candidate: str,
    ops_manifest_sha256: str,
    rollback_candidate: str,
    previous_run_id: str | None,
    payload_dir: Path,
) -> dict[str, object]:
    value = load(path)
    signature = value.pop("evidence_hmac_sha256", None)
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, hmac.new(key(), canonical(value), hashlib.sha256).hexdigest()
    ):
        raise PhaseEvidenceError("evidence HMAC differs")
    expected = {
        "schema_version": 1,
        "phase": phase,
        "run_id": run_id,
        "candidate_sha": candidate,
        "ops_manifest_sha256": ops_manifest_sha256,
        "rollback_candidate_sha": rollback_candidate,
        "previous_run_id": previous_run_id,
    }
    if any(value.get(name) != expected_value for name, expected_value in expected.items()):
        raise PhaseEvidenceError("evidence chain binding differs")
    created = parse_time(value.get("created_at_utc"))
    expires = parse_time(value.get("expires_at_utc"))
    now = datetime.now(timezone.utc)
    if not created <= now < expires or expires - created > timedelta(minutes=60):
        raise PhaseEvidenceError("evidence is expired or not yet valid")
    payloads = value.get("payload_sha256")
    if not isinstance(payloads, dict):
        raise PhaseEvidenceError("payload hash map is missing")
    for name, expected_hash in payloads.items():
        if not isinstance(name, str) or Path(name).name != name or not isinstance(expected_hash, str):
            raise PhaseEvidenceError("payload hash entry is invalid")
        candidate_path = payload_dir / name
        if candidate_path.is_symlink() or not candidate_path.is_file():
            raise PhaseEvidenceError("bound payload is missing")
        if file_sha256(candidate_path) != expected_hash:
            raise PhaseEvidenceError("bound payload bytes differ")
    value["evidence_hmac_sha256"] = signature
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "verify"):
        item = sub.add_parser(name)
        item.add_argument("--evidence", type=Path, required=True)
        item.add_argument("--phase", choices=PHASES, required=True)
        item.add_argument("--run-id", required=True)
        item.add_argument("--candidate", required=True)
        item.add_argument("--ops-manifest-sha256", required=True)
        item.add_argument("--rollback-candidate", required=True)
        item.add_argument("--previous-run-id")
        item.add_argument("--payload-dir", type=Path, required=True)
    create_parser = sub.choices["create"]
    create_parser.add_argument("--payload", action="append", type=Path, default=[])
    create_parser.add_argument("--lifetime-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create(
                args.evidence,
                args.phase,
                args.run_id,
                args.candidate,
                args.ops_manifest_sha256,
                args.rollback_candidate,
                args.previous_run_id,
                args.payload,
                args.lifetime_minutes,
            )
        else:
            result = verify(
                args.evidence,
                args.phase,
                args.run_id,
                args.candidate,
                args.ops_manifest_sha256,
                args.rollback_candidate,
                args.previous_run_id,
                args.payload_dir,
            )
    except (OSError, UnicodeError, json.JSONDecodeError, PhaseEvidenceError) as error:
        print(f"WP31_PHASE_EVIDENCE=FAIL reason={error}")
        return 2
    print(
        "WP31_PHASE_EVIDENCE=PASS "
        f"phase={result['phase']} run_id={result['run_id']} "
        f"evidence_sha256={file_sha256(args.evidence)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
