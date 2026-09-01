#!/usr/bin/env python3
"""Verify the release-only zero-Legacy-migration disposition without reading Legacy data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


RELEASE_CONFIG = Path("config/muchen_journey_2026_09_01_controlled_release.json")
ARCHIVE_ROOT = Path("outputs/audits/minimum-runtime-phase0/LEGACY_REFERENCE_ARCHIVE_V0.1")
ARCHIVE_TAR = Path("outputs/audits/minimum-runtime-phase0/LEGACY_REFERENCE_ARCHIVE_V0.1.tar.gz")
ARCHIVE_TAR_SUM = Path(
    "outputs/audits/minimum-runtime-phase0/LEGACY_REFERENCE_ARCHIVE_V0.1.tar.gz.sha256"
)
RUNTIME_SURFACES = (
    Path("apps/api/journey_api/main.py"),
    Path("apps/api/journey_api/routes.py"),
    Path("apps/api/journey_api/models.py"),
    Path("contracts/openapi.json"),
)
FORBIDDEN_RUNTIME_ANCHORS = (
    "legacy_migration_shadow",
    "historical_data_audit",
    "phase0_feishu",
    "LEGACY_REFERENCE_ARCHIVE",
)


class LegacyZeroMigrationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_regular_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LegacyZeroMigrationError("required JSON evidence is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyZeroMigrationError("required JSON evidence is unreadable") from exc
    if not isinstance(value, dict):
        raise LegacyZeroMigrationError("required JSON evidence must be an object")
    return value


def validate_release_config(value: dict[str, Any]) -> None:
    disposition = value.get("legacy_disposition")
    expected = {
        "legacy_data_usage": "REFERENCE_ONLY",
        "legacy_formal_migration": "NOT_REQUIRED",
        "legacy_completeness_gate": "SUPERSEDED_FOR_RELEASE",
        "historical_completeness_gate": "FAIL",
        "complete_legacy_snapshot": "NOT_ESTABLISHED",
        "migrate_record_count": 0,
    }
    if not isinstance(disposition, dict) or disposition != expected:
        raise LegacyZeroMigrationError("release Legacy disposition is not the exact Owner decision")
    if isinstance(disposition["migrate_record_count"], bool):
        raise LegacyZeroMigrationError("migrate_record_count must be integer zero")
    if value.get("release_authorized") is not False:
        raise LegacyZeroMigrationError("release must remain unauthorized")
    if value.get("production_mutation_executed") is not False:
        raise LegacyZeroMigrationError("production mutation must remain false")


def validate_reference_archive(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise LegacyZeroMigrationError("reference archive must be a regular directory")
    readme = root / "README.md"
    sums = root / "SHA256SUMS"
    manifest_path = root / "archive-manifest.v0.1.json"
    if any(path.is_symlink() or not path.is_file() for path in (readme, sums, manifest_path)):
        raise LegacyZeroMigrationError("reference archive is incomplete")

    manifest = read_regular_json(manifest_path)
    disposition = manifest.get("disposition")
    if not isinstance(disposition, dict):
        raise LegacyZeroMigrationError("archive disposition is missing")
    validate_release_config(
        {
            "legacy_disposition": {
                "legacy_data_usage": disposition.get("legacy_data_usage"),
                "legacy_formal_migration": disposition.get("legacy_formal_migration"),
                "legacy_completeness_gate": disposition.get("release_completeness_gate"),
                "historical_completeness_gate": disposition.get("historical_completeness_gate"),
                "complete_legacy_snapshot": disposition.get("complete_legacy_snapshot"),
                "migrate_record_count": disposition.get("migrate_record_count"),
            },
            "release_authorized": False,
            "production_mutation_executed": False,
        }
    )
    if manifest.get("classification") != ["INCOMPLETE", "NON_AUTHORITATIVE", "REFERENCE_ONLY"]:
        raise LegacyZeroMigrationError("archive classification is not exact")
    formal_effects = manifest.get("formal_state_effects")
    if not isinstance(formal_effects, dict) or not formal_effects or any(
        value is not False for value in formal_effects.values()
    ):
        raise LegacyZeroMigrationError("archive must produce no formal state")
    safety = manifest.get("safety")
    if not isinstance(safety, dict) or not safety or any(value is not False for value in safety.values()):
        raise LegacyZeroMigrationError("archive safety evidence is not fail-closed")

    expected_sums: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        pieces = line.split(maxsplit=1)
        if len(pieces) != 2 or len(pieces[0]) != 64:
            raise LegacyZeroMigrationError("archive checksum manifest is invalid")
        expected_sums[pieces[1]] = pieces[0]
    for name in ("README.md", "archive-manifest.v0.1.json"):
        if expected_sums.get(name) != sha256_file(root / name):
            raise LegacyZeroMigrationError("reference archive checksum mismatch")
    return manifest


def validate_archive_tar(tar_path: Path, checksum_path: Path) -> str:
    if any(path.is_symlink() or not path.is_file() for path in (tar_path, checksum_path)):
        raise LegacyZeroMigrationError("sealed archive tar evidence is missing")
    pieces = checksum_path.read_text(encoding="utf-8").strip().split(maxsplit=1)
    if len(pieces) != 2 or pieces[1] != tar_path.name or len(pieces[0]) != 64:
        raise LegacyZeroMigrationError("sealed archive tar checksum is invalid")
    actual = sha256_file(tar_path)
    if actual != pieces[0]:
        raise LegacyZeroMigrationError("sealed archive tar checksum mismatch")
    return actual


def validate_runtime_surfaces(repo: Path) -> None:
    for relative in RUNTIME_SURFACES:
        path = repo / relative
        if path.is_symlink() or not path.is_file():
            raise LegacyZeroMigrationError("required Runtime surface is missing")
        content = path.read_text(encoding="utf-8")
        if any(anchor in content for anchor in FORBIDDEN_RUNTIME_ANCHORS):
            raise LegacyZeroMigrationError("Legacy import surface is reachable from Runtime")
    migrations = repo / "migrations" / "versions"
    if migrations.is_symlink() or not migrations.is_dir():
        raise LegacyZeroMigrationError("migration directory is missing")
    if any(any(anchor in path.name for anchor in FORBIDDEN_RUNTIME_ANCHORS) for path in migrations.iterdir()):
        raise LegacyZeroMigrationError("Legacy import migration is present")


def verify(repo: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    config = read_regular_json(repo / RELEASE_CONFIG)
    validate_release_config(config)
    archive = validate_reference_archive(repo / ARCHIVE_ROOT)
    archive_tar_sha256 = validate_archive_tar(repo / ARCHIVE_TAR, repo / ARCHIVE_TAR_SUM)
    validate_runtime_surfaces(repo)
    return {
        "archive_id": archive.get("archive_id"),
        "archive_tar_sha256": archive_tar_sha256,
        "migrate_record_count": 0,
    }


def main() -> int:
    try:
        result = verify(Path.cwd())
    except (LegacyZeroMigrationError, OSError, UnicodeDecodeError, ValueError) as error:
        print("LEGACY_ZERO_MIGRATION_GATE=FAIL_CLOSED")
        print(f"ERROR={type(error).__name__}")
        return 2
    print("LEGACY_ZERO_MIGRATION_GATE=PASS")
    print(f"ARCHIVE_ID={result['archive_id']}")
    print("LEGACY_DATA_USAGE=REFERENCE_ONLY")
    print("LEGACY_FORMAL_MIGRATION=NOT_REQUIRED")
    print("MIGRATE_RECORD_COUNT=0")
    print("LEGACY_SOURCE_READ_EXECUTED=false")
    print("JOURNEY20_DATABASE_WRITE_EXECUTED=false")
    print("MIGRATION_EXECUTED=false")
    print("PRODUCTION_MUTATION_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
