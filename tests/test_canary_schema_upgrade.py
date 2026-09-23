"""Offline safety tests for the migration-aware Canary release path."""

import hashlib
import json
import importlib.util
import os
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
    assert 'PYTHONDONTWRITEBYTECODE: "1"' in source
    assert '"$RUNNER_TEMP/schema-package/"*' not in source
    for name in (
        "manifest.json",
        "canary_schema_upgrade.py",
        "canary_schema_facts_entry.py",
        "db_facts.py",
        "grant_runtime.py",
        "SHA256SUMS",
    ):
        assert f'"$package/{name}"' in source
    assert 'scripts/canary_schema_upgrade.py root@"$PUBLIC_IP":"$remote/canary_schema_upgrade_control.py"' in source
    assert 'scripts/wp31_database_snapshot.py root@"$PUBLIC_IP":"$remote/wp31_database_snapshot.py"' in source
    assert 'if [[ "$PHASE" == backup-migrate || "$PHASE" == backup-diagnose ]]' in source
    assert 'backup-diagnose) expected="BACKUP_DIAGNOSE_$short"' in source


def test_package_workflow_pins_restore_image_and_migration_range():
    source = Path(".github/workflows/canary-schema-package.yml").read_text()
    assert "postgres:17.6-alpine3.22@sha256:747d5ed1fdeeb124b880fbe3d7c6557d2c4064ae41d6b6297d417882effce4be" in source
    assert "0028_canary_main_merge" in source
    assert "0029_treasure_coaching_reviews" in source
    assert "ADDITIVE_SCHEMA_THEN_IMMUTABLE_BACKFILL" in source
    assert "make ci-main" in source
    assert "merge-base --is-ancestor" not in source
    assert 'cp deploy/production/greenfield_canary_grant_runtime.py "$out/grant_runtime.py"' in source


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


def test_incomplete_pre_migration_backup_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    upgrade = mod.Upgrade(manifest(), tmp_path)
    upgrade.backup.mkdir(parents=True)
    for name in ("before.json", "restored.json", "canary.dump"):
        (upgrade.backup / name).write_bytes(b"synthetic")
    upgrade.recover_incomplete_backup()
    assert not upgrade.backup.exists()


@pytest.mark.parametrize("name", ["canary.dump.enc", "migration-receipt.json", "unexpected"])
def test_incomplete_backup_recovery_refuses_ambiguous_state(tmp_path, monkeypatch, name):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    upgrade = mod.Upgrade(manifest(), tmp_path)
    upgrade.backup.mkdir(parents=True)
    (upgrade.backup / name).write_bytes(b"synthetic")
    with pytest.raises(mod.UpgradeError, match="INCOMPLETE_BACKUP_REQUIRES_MANUAL_RECOVERY"):
        upgrade.recover_incomplete_backup()
    assert (upgrade.backup / name).exists()


def test_backup_uses_one_exported_snapshot_for_dump_and_facts():
    source = Path("scripts/canary_schema_upgrade.py").read_text()
    assert '"--snapshot=" + snapshot_id' in source
    assert '"WP31_DATABASE_SNAPSHOT=" + snapshot_id' in source
    assert "RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT" in source
    assert '"docker", "rm", "-f", holder' in source


def test_backup_diagnostic_reports_only_safe_differences():
    source = Path("scripts/canary_schema_upgrade.py").read_text()
    assert '"count_differences": count_differences' in source
    assert '"fingerprint_difference_tables": fingerprint_differences' in source
    assert '"current_source_facts_equal": current == before' in source
    assert '"source_fingerprints"' not in source
    assert '"restored_fingerprints"' not in source


def test_old_api_probe_mounts_ca_and_cleans_only_its_container(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    upgrade = mod.Upgrade(manifest(), tmp_path)
    calls = []

    def subprocess_run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "container", "inspect"]:
            return Mock(returncode=1)
        return Mock(returncode=0, stdout=json.dumps({"release": manifest()["base_candidate"]}).encode())

    monkeypatch.setattr(mod.subprocess, "run", subprocess_run)
    launch = Mock(return_value=b"container-id")
    monkeypatch.setattr(mod, "run", launch)
    upgrade.probe_old_api()
    command = launch.call_args.args[0]
    assert f"{upgrade.base / 'secrets/volcengine-rds-ca.pem'}:/run/secrets/volcengine-rds-ca.pem:ro" in command
    assert calls[-1][:3] == ["docker", "rm", "-f"]

    calls.clear()
    launch.reset_mock()
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: Mock(returncode=0))
    with pytest.raises(mod.UpgradeError, match="OLD_PROBE_CONTAINER_EXISTS"):
        upgrade.probe_old_api()
    launch.assert_not_called()


@pytest.mark.skipif(os.name != "posix", reason="production file modes require POSIX")
def test_prepare_keeps_secrets_private_and_mounted_scripts_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    package = tmp_path / "package"
    package.mkdir()
    upgrade = mod.Upgrade(manifest(), package)
    (upgrade.base / "secrets").mkdir(parents=True)
    for name in mod.COPY_FILES:
        (upgrade.base / name).write_bytes(b"synthetic")
    for name in mod.PACKAGE_FILES:
        (package / name).write_bytes(b"synthetic")
    (upgrade.base / ".deployment.env").write_text("CANDIDATE_COMMIT=old\nAPI_IMAGE=old\nWEB_IMAGE=old\n")
    (upgrade.base / "secrets/api.env").write_text(
        f"APP_RELEASE=old\nDATABASE_URL=postgresql+psycopg://journey_next_runtime:synthetic@db:5432/{mod.DATABASE}\n"
    )
    (upgrade.base / "secrets/web.env").write_text("APP_RELEASE=old\n")
    monkeypatch.setattr(upgrade, "verify_base", Mock())
    monkeypatch.setattr(upgrade, "image_check", Mock())
    monkeypatch.setattr(mod, "run", Mock(return_value=b""))
    monkeypatch.setattr(mod.subprocess, "run", Mock(return_value=Mock(returncode=0)))
    config = {"services": {name: {"image": upgrade.old_images[name], "environment": {"APP_RELEASE": manifest()["base_candidate"]}} for name in ("api", "web")}}
    monkeypatch.setattr(mod, "compose", Mock(return_value=json.dumps(config).encode()))
    upgrade.prepare("synthetic", "synthetic-token", "synthetic-migration-password")
    assert (upgrade.new / "db_facts.py").stat().st_mode & 0o777 == 0o644
    assert (upgrade.new / "grant_runtime.py").stat().st_mode & 0o777 == 0o644
    for name in mod.ENV_FILES + ("secrets/migration.env",):
        assert (upgrade.new / name).stat().st_mode & 0o777 == 0o600


def test_canary_grants_reject_wrong_database_before_any_grant(monkeypatch):
    spec = importlib.util.spec_from_file_location("canary_grants", "deploy/production/greenfield_canary_grant_runtime.py")
    grants = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grants)
    monkeypatch.setenv("DATABASE_URL", "synthetic")
    from unittest.mock import MagicMock
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = "journey_next_staging"
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    monkeypatch.setattr(grants, "create_engine", Mock(return_value=engine))
    with pytest.raises(RuntimeError, match="unexpected database"):
        grants.main()
    assert connection.execute.call_count == 1
    engine.dispose.assert_called_once()
    connection.reset_mock()
    connection.execute.return_value.scalar_one.return_value = mod.DATABASE
    grants.main()
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert f"GRANT CONNECT ON DATABASE {mod.DATABASE} TO journey_next_runtime" in statements
    assert all("staging" not in statement for statement in statements)
