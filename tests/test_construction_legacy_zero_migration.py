from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.muchen_legacy_zero_migration_gate import (
    LegacyZeroMigrationError,
    validate_archive_tar,
    validate_reference_archive,
    validate_release_config,
    validate_runtime_surfaces,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads(
    (ROOT / "config/muchen_journey_2026_09_01_controlled_release.json").read_text(
        encoding="utf-8"
    )
)


def test_owner_disposition_is_exact_zero_migration() -> None:
    validate_release_config(CONFIG)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("legacy_data_usage", "IMPORT"),
        ("legacy_formal_migration", "REQUIRED"),
        ("legacy_completeness_gate", "PASS"),
        ("historical_completeness_gate", "SUPERSEDED_FOR_RELEASE"),
        ("complete_legacy_snapshot", "ESTABLISHED"),
        ("migrate_record_count", 1),
        ("migrate_record_count", False),
    ],
)
def test_any_legacy_disposition_expansion_fails_closed(field: str, value: object) -> None:
    changed = copy.deepcopy(CONFIG)
    changed["legacy_disposition"][field] = value
    with pytest.raises(LegacyZeroMigrationError):
        validate_release_config(changed)


def test_release_or_production_authorization_cannot_be_smuggled_into_disposition() -> None:
    for field in ("release_authorized", "production_mutation_executed"):
        changed = copy.deepcopy(CONFIG)
        changed[field] = True
        with pytest.raises(LegacyZeroMigrationError):
            validate_release_config(changed)


def test_sealed_reference_archive_is_incomplete_non_authoritative_and_non_formal() -> None:
    root = ROOT / "outputs/audits/minimum-runtime-phase0/LEGACY_REFERENCE_ARCHIVE_V0.1"
    manifest = validate_reference_archive(root)
    assert manifest["legacy_source_state"]["complete_legacy_snapshot_inferred"] is False
    assert manifest["disposition"]["historical_completeness_gate"] == "FAIL"
    assert all(value is False for value in manifest["formal_state_effects"].values())


def test_sealed_archive_tar_is_hash_bound_without_extraction() -> None:
    tar_path = ROOT / "outputs/audits/minimum-runtime-phase0/LEGACY_REFERENCE_ARCHIVE_V0.1.tar.gz"
    checksum_path = tar_path.with_suffix(tar_path.suffix + ".sha256")
    assert validate_archive_tar(tar_path, checksum_path) == hashlib.sha256(
        tar_path.read_bytes()
    ).hexdigest()


def test_runtime_has_no_legacy_import_entrypoint_or_migration() -> None:
    validate_runtime_surfaces(ROOT)


def test_archive_formal_effect_or_checksum_tampering_fails_closed(tmp_path: Path) -> None:
    source = ROOT / "outputs/audits/minimum-runtime-phase0/LEGACY_REFERENCE_ARCHIVE_V0.1"
    archive = tmp_path / "archive"
    archive.mkdir()
    for name in ("README.md", "archive-manifest.v0.1.json"):
        (archive / name).write_bytes((source / name).read_bytes())
    manifest_path = archive / "archive-manifest.v0.1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["formal_state_effects"]["users"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (archive / "SHA256SUMS").write_text(
        "\n".join(
            f"{hashlib.sha256((archive / name).read_bytes()).hexdigest()}  {name}"
            for name in ("README.md", "archive-manifest.v0.1.json")
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(LegacyZeroMigrationError, match="no formal state"):
        validate_reference_archive(archive)


def test_runtime_anchor_tampering_fails_closed(tmp_path: Path) -> None:
    for relative in (
        "apps/api/journey_api/main.py",
        "apps/api/journey_api/routes.py",
        "apps/api/journey_api/models.py",
        "contracts/openapi.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("safe\n", encoding="utf-8")
    migrations = tmp_path / "migrations/versions"
    migrations.mkdir(parents=True)
    (migrations / "9999_legacy_migration_shadow.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(LegacyZeroMigrationError, match="Legacy import migration"):
        validate_runtime_surfaces(tmp_path)
