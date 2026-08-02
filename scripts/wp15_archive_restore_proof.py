#!/usr/bin/env python3
"""Validate one exact encrypted restore proof without reading database content."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path


RUN_ID = "20260802T181906Z"
TARGET_DATABASE = "journey_next_restore_20260803"
CANDIDATE = "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a"


class ArchiveError(RuntimeError):
    pass


def regular_file(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ArchiveError(f"required regular file is missing: {name}")
    return path


def validate(directory: Path, key: str) -> dict[str, object]:
    if len(key) < 32:
        raise ArchiveError("backup key is missing or short")
    encrypted = regular_file(directory, "journey-next.dump.enc")
    manifest_path = regular_file(directory, "backup-manifest.json")
    source_facts = regular_file(directory, "source-facts.json")
    target_facts = regular_file(directory, "target-facts.json")
    if (directory / "journey-next.dump").exists() or (
        directory / "journey-next.verify.dump"
    ).exists():
        raise ArchiveError("plaintext dump is present")

    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ArchiveError("manifest must be an object")
    signature = manifest.pop("manifest_hmac_sha256", None)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    expected_signature = hmac.new(key.encode(), canonical, hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, expected_signature
    ):
        raise ArchiveError("manifest HMAC is invalid")
    expected = {
        "run_id": RUN_ID,
        "candidate_sha": CANDIDATE,
        "isolated_restore_database": TARGET_DATABASE,
        "backup": "PASS",
        "restore": "PASS",
        "encrypted_artifact_decrypt_verified": True,
        "active_notification_recipients": 0,
    }
    for name, value in expected.items():
        if manifest.get(name) != value:
            raise ArchiveError(f"unexpected manifest field: {name}")
    encrypted_sha = hashlib.sha256(encrypted.read_bytes()).hexdigest()
    if manifest.get("encrypted_backup_sha256") != encrypted_sha:
        raise ArchiveError("encrypted backup digest differs from manifest")
    if source_facts.read_bytes() != target_facts.read_bytes():
        raise ArchiveError("source and target PII-free facts differ")
    return {
        "run_id": RUN_ID,
        "target_database": TARGET_DATABASE,
        "encrypted_backup_sha256": encrypted_sha,
        "source_target_facts_equal": True,
        "plaintext_present": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(args.directory, os.environ.get("WP15_BACKUP_KEY", ""))
    except (ArchiveError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"WP15_ARCHIVE_RESTORE_PROOF_ERROR: {error}") from error
    print(json.dumps(result, sort_keys=True))
    print("WP15_ARCHIVE_RESTORE_PROOF=PASS backend=github-actions-artifact")


if __name__ == "__main__":
    main()
