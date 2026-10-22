"""The Ops repair must retain schema, facts and rollback protections."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
original_paths = list(sys.path)
try:
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "deploy/exploration-release"))
    spec = importlib.util.spec_from_file_location("ops_resilience_activation", ROOT / "deploy/ops-resilience/activate.py")
    activate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(activate)
finally:
    sys.path[:] = original_paths


@pytest.fixture
def release(tmp_path):
    manifest = json.loads((ROOT / "deploy/ops-resilience/baseline.json").read_text())
    manifest["candidate"] = "a" * 40
    manifest["images"].update(api="sha256:" + "a" * 64, web="sha256:" + "b" * 64)
    item = activate.Activation(manifest, tmp_path)
    item.new = tmp_path / "new"
    item.backup = tmp_path / "backup"
    item.new.mkdir()
    item.backup.mkdir()
    (item.backup / "canary.dump.enc").write_bytes(b"verified-backup")
    (item.backup / "backup-receipt.json").write_text(json.dumps({
        "candidate": manifest["candidate"], "restore": "PASS",
        "backup_sha256": activate.digest(b"verified-backup")}))
    (item.backup / "read-rehearsal.json").write_text(json.dumps({"schema": activate.TARGET_SCHEMA, "ops_read": "PASS"}))
    return item


@pytest.mark.parametrize("failure,writes", [(False, False), (True, False), (True, True)])
def test_switch_preserves_schema_and_guards_rollback(release, failure, writes):
    calls = []
    def up(path):
        calls.append(path)
        if failure and path == release.new:
            raise activate.UpgradeError("SIMULATED_SWITCH_FAILURE")
    def api(*args, **kwargs):
        assert args == ("secrets/migration.env", "alembic", "current")
        return activate.TARGET_SCHEMA.encode()
    facts = {"users": [42, "same"], "review_admin_tasks": [5, "same"]}
    with patch.object(release, "verify_base"), patch.object(release, "verify_prepared"), \
         patch.object(release, "guard", side_effect=[facts, facts, {"users": [43, "changed"]} if writes else facts]), \
         patch.object(release, "docker_api", side_effect=api), patch.object(release, "verify_ops_reads") as probe, \
         patch.object(release, "up", side_effect=up), patch.object(release, "healthy"), \
         patch.object(release, "pointer"), patch.object(release, "current", return_value=release.base), \
         patch.object(activate, "compose"), patch.object(activate, "run"):
        if failure:
            expected = "BUSINESS_WRITES_DETECTED_FORWARD_FIX_REQUIRED" if writes else "SIMULATED_SWITCH_FAILURE"
            with pytest.raises(activate.UpgradeError, match=expected):
                release.activate()
        else:
            release.activate()
        probe.assert_called_once()
    assert calls == ([release.new, release.base] if failure and not writes else [release.new])
    assert activate.SOURCE_SCHEMA == activate.TARGET_SCHEMA


def test_tampered_backup_stops_before_downtime(release):
    (release.backup / "canary.dump.enc").write_bytes(b"changed")
    with patch.object(release, "verify_base"), patch.object(release, "verify_prepared"), patch.object(activate, "compose") as compose:
        with pytest.raises(activate.UpgradeError, match="BACKUP_CHANGED"):
            release.activate()
        compose.assert_not_called()


def test_failed_ops_probe_blocks_activation(release):
    with patch.object(release, "docker_api", return_value=b'{"ops_enrollment_read":"FAIL"}'), \
         patch.object(activate, "read_file", return_value=b"read-only probe"):
        with pytest.raises(activate.UpgradeError, match="OPS_READ_CHECK"):
            release.verify_ops_reads()


def test_business_fingerprints_include_existing_review_workspace_data():
    source = (ROOT / "deploy/ops-resilience/facts_guard.py").read_text()
    # The older initial rollout required these tables to be empty. Existing
    # reviewer activity must now be fingerprinted just like other business facts.
    assert "NEW_REVIEW_BUSINESS_WRITES" not in source
    assert 'if table in {"alembic_version", "worker_heartbeats"}' in source
