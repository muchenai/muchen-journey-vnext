"""Offline safety tests for the migration-aware Canary release path."""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import canary_schema_upgrade as mod
from scripts.canary_schema_migration_head import migration_heads


def manifest():
    return {
        "schema_version": 2,
        "base_candidate": "b8a5dd580eaec72945cbe4f0e37c1152ee4645a1",
        "candidate": "a" * 40,
        "database": mod.DATABASE,
        "migrations": {
            "from": "0028_canary_main_merge",
            "to": "0029_treasure_coaching_reviews",
        },
        "images": {
            "api": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:" + "1" * 64,
            "web": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:" + "2" * 64,
            "dbrestore": "ghcr.io/muchenai/muchen-journey-vnext-dbrestore@sha256:" + "3" * 64,
        },
        "old_images": {
            "api": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:" + "4" * 64,
            "web": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:" + "5" * 64,
        },
        "compatibility": "ADDITIVE_SCHEMA_THEN_IMMUTABLE_BACKFILL",
    }


def write_manifest(tmp_path, value=None):
    raw = (json.dumps(value or manifest(), sort_keys=True) + "\n").encode()
    path = tmp_path / "manifest.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_manifest_pins_database_migrations_and_old_images(tmp_path):
    path, sha = write_manifest(tmp_path)
    assert mod.load_manifest(path, sha) == manifest()
    for field, value in [
        ("database", "another"),
        ("migrations", {"from": "0028_canary_main_merge", "to": "head"}),
        ("base_candidate", "0" * 40),
    ]:
        changed = manifest()
        changed[field] = value
        path, sha = write_manifest(tmp_path, changed)
        with pytest.raises(mod.UpgradeError):
            mod.load_manifest(path, sha)


def test_manifest_hash_is_byte_exact(tmp_path):
    path, sha = write_manifest(tmp_path)
    mod.load_manifest(path, sha)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(mod.UpgradeError, match="MANIFEST_HASH"):
        mod.load_manifest(path, sha)


def test_rollback_refuses_once_coaching_facts_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    upgrade = mod.Upgrade(manifest(), tmp_path)
    monkeypatch.setattr(upgrade, "verify_prepared", Mock())
    monkeypatch.setattr(upgrade, "coaching_fact_count", Mock(return_value=1))
    monkeypatch.setattr(upgrade, "up", Mock())
    with pytest.raises(mod.UpgradeError, match="COACHING_FACTS_EXIST_FORWARD_FIX_ONLY"):
        upgrade.rollback_pre_backfill()
    upgrade.up.assert_not_called()


def test_switch_failure_rolls_back_only_before_backfill(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    upgrade = mod.Upgrade(manifest(), tmp_path)
    upgrade.backup.mkdir(parents=True)
    (upgrade.backup / "migration-receipt.json").write_text("{}")
    monkeypatch.setattr(upgrade, "verify_prepared", Mock())
    monkeypatch.setattr(upgrade, "current", Mock(return_value=upgrade.base))
    monkeypatch.setattr(upgrade, "coaching_fact_count", Mock(return_value=0))
    monkeypatch.setattr(upgrade, "healthy", Mock())
    monkeypatch.setattr(upgrade, "up", Mock(side_effect=RuntimeError("synthetic")))
    rollback = Mock()
    monkeypatch.setattr(upgrade, "rollback_pre_backfill", rollback)
    monkeypatch.setattr(mod, "write_new", Mock())
    with pytest.raises(mod.UpgradeError, match="SWITCH_FAILED_OLD_VERSION_HEALTHY"):
        upgrade.switch()
    rollback.assert_called_once_with()


def test_release_workflow_separates_irreversible_backfill():
    source = Path(".github/workflows/canary-schema-release.yml").read_text()
    assert "BACKFILL_FORWARD_ONLY_$short" in source
    assert "rollback-pre-backfill" in source
    assert "environment: production-canary-uat" in source
    assert 'refs/tags/canary-schema-release-$GITHUB_SHA' in source
    assert "WP08_MIGRATION_DB_PASSWORD" in source
    assert "WP15_BACKUP_KEY" in source
    assert "canary.dump.enc" in source
    assert "terraform apply" not in source


def test_package_workflow_pins_restore_image_and_migration_range():
    source = Path(".github/workflows/canary-schema-package.yml").read_text()
    assert "postgres:17.6-alpine3.22@sha256:747d5ed1fdeeb124b880fbe3d7c6557d2c4064ae41d6b6297d417882effce4be" in source
    assert "0028_canary_main_merge" in source
    assert "0029_treasure_coaching_reviews" in source
    assert "ADDITIVE_SCHEMA_THEN_IMMUTABLE_BACKFILL" in source
    assert "make ci-main" in source
    assert "merge-base --is-ancestor" not in source


def test_migration_head_parser_handles_merge_revision():
    assert migration_heads(Path("migrations/versions")) == [
        "0029_treasure_coaching_reviews"
    ]


def test_fact_probe_never_exports_raw_rows():
    source = Path("deploy/production/db_facts.py").read_text()
    assert "content_fingerprints" in source
    assert "to_jsonb" in source
    assert "print(" in source
    assert "SELECT *" not in source.upper()
