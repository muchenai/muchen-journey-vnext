"""Switch/rollback failure injection. All containers and paths are synthetic."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import canary_app_upgrade as mod


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
    assert execute.call_args.args == (u.new, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "90", "api", "web")
    assert execute.call_args.kwargs["timeout"] == 120


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
