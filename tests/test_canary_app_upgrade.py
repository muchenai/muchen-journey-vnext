"""Switch/rollback failure injection. All containers and paths are synthetic."""
import json
import os
from pathlib import Path
import stat
from unittest.mock import Mock

import pytest

from scripts import canary_app_upgrade as mod


@pytest.mark.skipif(os.name != "posix", reason="Deployment uses Linux file modes")
@pytest.mark.parametrize("mask", [0o077, 0o777])
@pytest.mark.parametrize("mode", [0o600, 0o644, 0o755])
def test_new_file_preserves_required_mode_under_restrictive_umask(tmp_path, mask, mode):
    path = tmp_path / "new-file"
    previous = os.umask(mask)
    try:
        mod.write_new(path, b"synthetic", mode)
        assert os.umask(mask) == mask
    finally:
        os.umask(previous)
    assert path.read_bytes() == b"synthetic"
    assert stat.S_IMODE(path.stat().st_mode) == mode
    with pytest.raises(FileExistsError):
        mod.write_new(path, b"replacement", 0o600)
    assert path.read_bytes() == b"synthetic"
    assert stat.S_IMODE(path.stat().st_mode) == mode


@pytest.mark.skipif(os.name != "posix", reason="Deployment uses Linux file modes")
@pytest.mark.parametrize("changed_file,mode,category", [
    ("secrets/volcengine-rds-ca.pem", 0o600, "CA_PERMISSIONS"),
    ("secrets/api.env", 0o644, "ENV_PERMISSIONS"),
])
def test_prepared_permission_drift_fails_before_switch(tmp_path, monkeypatch, changed_file, mode, category):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "OLD", tmp_path / "old")
    u = mod.Upgrade(manifest())
    hashes = {}
    for release in (mod.OLD, u.new):
        (release / "secrets").mkdir(parents=True)
        for name in mod.COPY_FILES + mod.ENV_FILES:
            required_mode = 0o644 if name == "secrets/volcengine-rds-ca.pem" else 0o600
            mod.write_new(release / name, b"synthetic", required_mode)
            hashes[name] = mod.digest(b"synthetic")
    mod.write_new(u.new / "upgrade-prepared.json", json.dumps({
        "manifest": u.m, "old_hashes": hashes, "new_hashes": hashes,
    }).encode())
    u.verify_prepared()
    (u.new / changed_file).chmod(mode)
    up = Mock()
    monkeypatch.setattr(u, "up", up)
    with pytest.raises(mod.UpgradeError, match=category):
        u.switch()
    up.assert_not_called()
    assert not (u.new / "upgrade-attempt.json").exists()


def manifest():
    return {"schema_version": 1, "base_candidate": mod.BASE, "candidate": "a" * 40,
            "images": {s: f"ghcr.io/muchenai/muchen-journey-vnext-{s}@sha256:" + "b" * 64 for s in ("api", "web")},
            "compatibility": "NO_SCHEMA_OR_IDENTITY_CHANGE"}


@pytest.fixture
def upgrade(monkeypatch):
    u = mod.Upgrade(manifest())
    for name in ("verify_prepared", "healthy", "image_check", "up", "pointer", "containers"):
        monkeypatch.setattr(u, name, Mock())
    monkeypatch.setattr(u, "current", Mock(return_value=mod.OLD))
    monkeypatch.setattr(mod, "write_new", Mock())
    return u


def test_success_updates_pointer_only_after_new_health(upgrade):
    events = []
    upgrade.up.side_effect = lambda path: events.append(("up", path))
    upgrade.healthy.side_effect = lambda path, *_, **__: events.append(("healthy", path))
    upgrade.pointer.side_effect = lambda path: events.append(("pointer", path))
    upgrade.switch()
    assert events == [("healthy", mod.OLD), ("up", upgrade.new), ("healthy", upgrade.new), ("pointer", upgrade.new), ("healthy", upgrade.new)]


@pytest.mark.parametrize("failed_step", ["up", "healthy", "pointer"])
def test_any_switch_failure_recreates_old_application_once(upgrade, failed_step):
    if failed_step == "up":
        upgrade.up.side_effect = [RuntimeError("synthetic"), None]
    elif failed_step == "healthy":
        upgrade.healthy.side_effect = [None, RuntimeError("synthetic"), None]
    else:
        upgrade.pointer.side_effect = RuntimeError("synthetic")
    with pytest.raises(mod.UpgradeError, match="^SWITCH_FAILED_OLD_VERSION_HEALTHY:"):
        upgrade.switch()
    assert [c.args[0] for c in upgrade.up.call_args_list] == [upgrade.new, mod.OLD]


def test_rollback_failure_does_not_claim_recovery_or_loop(upgrade):
    upgrade.up.side_effect = RuntimeError("secret must not be printed")
    with pytest.raises(mod.UpgradeError, match="^SWITCH_FAILED_ROLLBACK_NOT_CONFIRMED$"):
        upgrade.switch()
    assert upgrade.up.call_count == 2


def test_existing_attempt_blocks_second_switch_before_container_change(upgrade, monkeypatch):
    monkeypatch.setattr(mod, "write_new", Mock(side_effect=FileExistsError()))
    with pytest.raises(FileExistsError):
        upgrade.switch()
    upgrade.up.assert_not_called()


def test_missing_old_image_prevents_switch(upgrade):
    upgrade.image_check.side_effect = mod.UpgradeError("IMAGE_MISSING")
    with pytest.raises(mod.UpgradeError):
        upgrade.switch()
    upgrade.up.assert_not_called()


def test_current_release_drift_prevents_switch(upgrade):
    upgrade.current.return_value = Path("/unrelated")
    with pytest.raises(mod.UpgradeError, match="CURRENT_CHANGED"):
        upgrade.switch()
    upgrade.up.assert_not_called()


def test_rollback_switches_pointer_only_after_old_health(upgrade):
    upgrade.current.return_value = upgrade.new
    upgrade.rollback()
    upgrade.up.assert_called_once_with(mod.OLD)
    upgrade.healthy.assert_called_once_with(mod.OLD, mod.BASE, mod.OLD_IMAGES)
    upgrade.pointer.assert_called_once_with(mod.OLD)
    assert upgrade.containers.call_args.kwargs == {"allow_missing": True}


def test_only_up_api_web_no_pull_build_migration_or_down(monkeypatch):
    execute = Mock()
    monkeypatch.setattr(mod, "compose", execute)
    u = mod.Upgrade(manifest())
    u.up(u.new)
    assert execute.call_args.args == (u.new, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "240", "api", "web")
    assert execute.call_args.kwargs["timeout"] == 300


def test_env_rewrite_preserves_all_secrets_database_and_allowlist():
    raw = b"APP_RELEASE=old\nFEISHU_APP_SECRET=synthetic==\nDATABASE_URL=unchanged\nCANARY_LEARNER_USER_IDS=unchanged\nIDENTITY_SUBJECT_SECRET=synthetic\n"
    assert mod.changed_env(raw, {"APP_RELEASE": "new"}) == raw.replace(b"APP_RELEASE=old", b"APP_RELEASE=new")


@pytest.mark.parametrize("raw", [b"X=1\nX=2\n", b"X=1\r\n", b"X=\0\n"])
def test_ambiguous_env_rejected(raw):
    with pytest.raises(mod.UpgradeError):
        mod.changed_env(raw, {"X": "3"})


def test_manifest_hash_and_digest_are_mandatory(tmp_path):
    p = tmp_path / "manifest.json"
    raw = json.dumps(manifest()).encode()
    p.write_bytes(raw)
    assert mod.load_manifest(p, mod.digest(raw)) == manifest()
    with pytest.raises(mod.UpgradeError, match="MANIFEST_HASH"):
        mod.load_manifest(p, "0" * 64)
    m = manifest(); m["images"]["api"] = "ghcr.io/muchenai/muchen-journey-vnext-api:latest"
    raw = json.dumps(m).encode(); p.write_bytes(raw)
    with pytest.raises(mod.UpgradeError, match="IMAGE_REFERENCE"):
        mod.load_manifest(p, mod.digest(raw))


def test_package_and_rollback_use_the_same_deployed_base():
    from scripts.canary_app_compatibility import BASE, SOURCE_BASE
    assert BASE == mod.BASE == "29c0473c488dd9f2d35ca40aec32e505169d4a72"
    assert SOURCE_BASE == BASE
    assert mod.OLD == mod.ROOT / "releases" / (BASE + "-app-upgrade")
    assert mod.OLD_IMAGES == {
        "api": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:bb8d3d127821286a78b3d30458340aec95b6f654c8d63872df9ca46cf747e7d5",
        "web": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:5dbea3966c7ac2ce033002cf71313b6c40076080b081736ab1207800f952a77c",
    }


def test_manifest_for_previous_upgrade_is_rejected(tmp_path):
    m = manifest()
    m["base_candidate"] = "a00b18dc077c128597bb50cd4a1e20699aedb6fa"
    m["candidate"] = mod.BASE
    raw = json.dumps(m).encode()
    p = tmp_path / "manifest.json"
    p.write_bytes(raw)
    with pytest.raises(mod.UpgradeError, match="BASE_CANDIDATE"):
        mod.load_manifest(p, mod.digest(raw))


def test_switch_validates_baseline_before_host_access_and_keeps_attempt_guard():
    source = Path(".github/workflows/canary-app-switch.yml").read_text()
    assert source.index("manifest=load_manifest(") < source.index("terraform init")
    assert source.index("verify_package(directory)") < source.index("terraform init")
    assert '"$RUNNER_TEMP/package/canary_app_upgrade.py"' in source
    assert "upgrade-attempt.json" not in source
    assert "chmod 0644" not in source


def test_no_containers_after_failed_recreate_still_allows_recovery(monkeypatch):
    monkeypatch.setattr(mod, "run", Mock(return_value=b""))
    u = mod.Upgrade(manifest())
    assert u.containers({s: {v} for s,v in mod.OLD_IMAGES.items()}, allow_missing=True) == []
    with pytest.raises(mod.UpgradeError):
        u.containers({s: {v} for s,v in mod.OLD_IMAGES.items()})


def test_extra_worker_blocks_recovery_instead_of_touching_it(monkeypatch):
    monkeypatch.setattr(mod, "run", Mock(return_value=(mod.PROJECT + "-worker-1\n").encode()))
    with pytest.raises(mod.UpgradeError, match="EXTRA_OR_MISSING_CONTAINER"):
        mod.Upgrade(manifest()).containers({}, allow_missing=True)
