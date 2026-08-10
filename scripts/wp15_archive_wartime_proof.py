#!/usr/bin/env python3
"""Validate one encrypted wartime restore proof without reading business rows."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from pathlib import Path


TARGET_DATABASE = "journey_next_cutover_20260810"
CANDIDATE = "ff53052847a268d025bceb93c3eab37986d50219"
MIGRATION = "0019_wp30_invitation_control"
RUN_ID = re.compile(r"^[1-9][0-9]{5,19}$")


class ArchiveError(RuntimeError):
    pass


def regular_file(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ArchiveError(f"required regular file is missing: {name}")
    return path


def validate(directory: Path, key: str, run_id: str) -> dict[str, object]:
    if len(key) < 32:
        raise ArchiveError("backup key is missing or short")
    if RUN_ID.fullmatch(run_id) is None:
        raise ArchiveError("backup run identifier is invalid")
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
        "schema_version": 1,
        "run_id": run_id,
        "candidate_sha": CANDIDATE,
        "source_database": "journey_next_staging",
        "isolated_restore_database": TARGET_DATABASE,
        "migration": MIGRATION,
        "backup": "PASS",
        "restore": "PASS",
        "encrypted_artifact_decrypt_verified": True,
        "active_notification_recipients": 0,
        "source_modified": False,
    }
    for name, value in expected.items():
        if manifest.get(name) != value:
            raise ArchiveError(f"unexpected manifest field: {name}")

    encrypted_sha = hashlib.sha256(encrypted.read_bytes()).hexdigest()
    if manifest.get("encrypted_backup_sha256") != encrypted_sha:
        raise ArchiveError("encrypted backup digest differs from manifest")
    source_bytes = source_facts.read_bytes()
    if source_bytes != target_facts.read_bytes():
        raise ArchiveError("source and target PII-free facts differ")
    if manifest.get("pii_free_facts_sha256") != hashlib.sha256(source_bytes).hexdigest():
        raise ArchiveError("PII-free facts digest differs from manifest")
    return {
        "run_id": run_id,
        "target_database": TARGET_DATABASE,
        "encrypted_backup_sha256": encrypted_sha,
        "source_target_facts_equal": True,
        "plaintext_present": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        result = validate(
            args.directory, os.environ.get("WP15_BACKUP_KEY", ""), args.run_id
        )
    except (ArchiveError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"WP15_ARCHIVE_WARTIME_PROOF_ERROR: {error}") from error
    print(json.dumps(result, sort_keys=True))
    print("WP15_ARCHIVE_WARTIME_PROOF=PASS backend=github-actions-artifact")


if __name__ == "__main__":
    main()
