"""Bind this release to the running application and preserve existing learning data."""
import hashlib
import json
from pathlib import Path
import os
import sys
from unittest.mock import Mock, patch

import pytest

from test_dynamic_exploration_release import API_IMAGE, WEB_IMAGE, baseline_files, load, release


with patch.dict(sys.modules):
    sys.modules["canary_schema_upgrade"] = load("canary_schema_upgrade", "scripts/canary_schema_upgrade.py")
    sys.modules["grant_runtime"] = load("grant_runtime", "deploy/course-workspace-release/grant_runtime.py")
    sys.modules["dynamic_release"] = release
    workspace = load("course_workspace_release", "deploy/course-workspace-release/activate.py")

ROOT = Path(__file__).resolve().parents[1]
Activation = workspace.CourseWorkspaceActivation


def inputs():
    candidate = json.loads((ROOT / "deploy/course-workspace-release/baseline.json").read_text())
    candidate.update(candidate="a" * 40, package_run_id="5555")
    previous = {"candidate": Activation.base_api, "package_run_id": "44357590475",
                "base_candidate": workspace.PRIOR_API, "base_web_candidate": workspace.PRIOR_WEB,
                "migrations": {"to": Activation.source_schema}, "database": candidate["database"],
                "images": {"api": API_IMAGE, "web": WEB_IMAGE, **candidate["images"]}}
    raw = baseline_files()
    raw.update({name: b"original" for name in (*workspace.PACKAGE_FILES, "secrets/migration.env")})
    raw["secrets/api.env"] = raw["secrets/web.env"] = ("APP_RELEASE=" + Activation.base_api + "\n").encode()
    prepared = {"manifest": previous, "hashes": {key: release.digest(data) for key, data in raw.items()}}
    receipt = {"release": Activation.base_api, "status": "PASS", "schema": Activation.source_schema,
               "package_run_id": "44357590475", "previous_api_release": workspace.PRIOR_API,
               "previous_web_release": workspace.PRIOR_WEB, "existing_business_rows_preserved": True,
               "curriculum_initialized": True, "other_containers_unchanged": True}
    return candidate, prepared, receipt, raw


def instantiate(candidate, prepared, receipt, raw):
    base_dir = release.ROOT / "releases" / (Activation.base_api + "-dynamic-exploration")
    def read(path):
        if path.name == "schema-upgrade-prepared.json":
            return json.dumps(prepared).encode()
        if path.name == "activation-receipt.json":
            return json.dumps(receipt).encode()
        return raw[path.relative_to(base_dir).as_posix()]
    with patch.object(workspace, "read_file", side_effect=read), patch.object(release, "read_file", side_effect=read):
        return Activation(candidate, Path("/offline-package"))


def test_course_activation_uses_previous_loaded_image_ids_and_hashes():
    app = instantiate(*inputs())
    assert app.old_images == {"api": API_IMAGE, "web": WEB_IMAGE}
    assert app.base.name == Activation.base_api + "-dynamic-exploration"
    assert app.new.name == "a" * 40 + "-course-workspace"
    assert not app.seeds_curriculum
    assert app.source_schema == "0060_migrated_ai_ownership" and app.target_schema == "0063_admin_video_storage"
    assert set(app.new_tables) == set(load("wp06", "scripts/wp06_ops.py").COURSE_WORKSPACE_TABLES)


@pytest.mark.parametrize("changed", ["receipt", "schema", "images", "configuration", "path", "role", "package", "database"])
def test_changed_or_unbound_previous_release_fails_before_staging(changed):
    candidate, prepared, receipt, raw = inputs()
    if changed == "receipt":
        receipt["other_containers_unchanged"] = False
    elif changed == "schema":
        candidate["migrations"]["from"] = "0056_guild_halls"
    elif changed == "images":
        prepared["manifest"]["images"]["api"] = "sha256:" + "d" * 64
    elif changed == "configuration":
        raw["compose.canary.yaml"] += b"edit"
    elif changed == "path":
        prepared["hashes"]["../escape"] = "a" * 64
    elif changed == "role":
        del prepared["hashes"]["secrets/migration.env"]
    elif changed == "package":
        receipt["package_run_id"] = "99999"
    else:
        candidate["database"] = "other"
    with pytest.raises(Exception, match="^BASE_|SCHEMA_PIN|DATABASE_PIN"):
        instantiate(candidate, prepared, receipt, raw)


def test_new_cutover_requires_proven_backup_and_overlay_does_not_run_prior_import():
    app = instantiate(*inputs())
    with pytest.raises(release.UpgradeError, match="PRODUCTION_WRITE_PROBE_FORBIDDEN"):
        app.docker_api("secrets/migration.env", "python", "scripts/upgrade_exploration_catalog.py", "--apply")
    extra = ("/api/review-native/course-workspace", "/api/review-native/experience/permissions")
    assert all(route in app.protected_endpoints for route in extra)
    assert "exploration_self_checks" in app.in_flight_sql
    flow = (ROOT / ".github/workflows/course-workspace-release.yml").read_text()
    assert "environment: production-canary-uat" in flow and "inputs.expected_commit == github.sha" in flow
    assert "run['head_sha']==p['candidate']" in flow and "run['conclusion']=='success'" in flow
    assert "wp08_security_group close" in flow and "if: always() && steps.runner.outputs.cidr != ''" in flow
    assert "RELEASE_PROFILE: course-workspace" in flow and "catalog_actor.py" not in flow


def restore_verifier():
    with patch.dict(sys.modules):
        sys.modules["diagnose_backup"] = load("diagnose_backup", "deploy/admin-reviewed/diagnose_backup.py")
        return load("restore_backup", "deploy/academy-release/restore_backup.py")


def test_backup_hash_reads_video_sized_dumps_in_bounded_chunks(tmp_path):
    restore = restore_verifier()
    dump = tmp_path.resolve() / "backup.dump"
    data = b"x" * (2 * 1024**2) + b"tail"
    dump.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    tracking = Mock(wraps=hashlib.sha256())
    with patch.object(restore.hashlib, "sha256", return_value=tracking):
        assert restore.stable_file_digest(dump, release.require) == expected
    assert [len(c.args[0]) for c in tracking.update.call_args_list] == [1024**2, 1024**2, 4]


def test_backup_hash_rejects_empty_directory_symlink_and_mid_read_truncation(tmp_path):
    restore = restore_verifier()
    root = tmp_path.resolve()
    dump = root / "dump"
    dump.touch()
    for unsafe in (root, dump):
        with pytest.raises(release.UpgradeError, match="UNSAFE_DIGEST_FILE"):
            restore.stable_file_digest(unsafe, release.require)
    dump.write_bytes(b"x" * (3 * 1024**2))
    tracking = Mock(wraps=hashlib.sha256())
    tracking.update.side_effect = lambda data: dump.write_bytes(b"short")
    with patch.object(restore.hashlib, "sha256", return_value=tracking), pytest.raises(release.UpgradeError, match="FILE_CHANGED_DURING_HASH"):
        restore.stable_file_digest(dump, release.require)
    if hasattr(os, "mkfifo"):
        fifo = root / "pipe"
        os.mkfifo(fifo)
        with pytest.raises(release.UpgradeError, match="UNSAFE_DIGEST_FILE"):
            restore.stable_file_digest(fifo, release.require)
    link = root / "link"
    try:
        link.symlink_to(dump)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(release.UpgradeError, match="UNSAFE_DIGEST_FILE"):
        restore.stable_file_digest(link, release.require)


@pytest.mark.parametrize("truncate_after_restore", [False, True])
def test_backup_receipt_binds_the_dump_that_was_restored(tmp_path, truncate_after_restore):
    restore = restore_verifier()
    root = tmp_path.resolve()
    dump, encrypted, verify = (root / name for name in ("canary.dump", "encrypted", "verify"))
    dump.write_bytes(b"original dump")
    before = {"migration": "0060_migrated_ai_ownership"}
    app = Mock(manifest={"candidate": "1" * 40}, backup=root, new=root, package=root,
               images={"dbrestore": "database", "api": "api"})
    module = Mock(require=release.require)
    module.changed_env.return_value = b"isolated"
    module.write_new.side_effect = lambda path, data: path.write_bytes(data)

    def run(command, **kwargs):
        if command[0] == "openssl":
            source = Path(command[command.index("-in") + 1])
            Path(command[command.index("-out") + 1]).write_bytes(source.read_bytes())
        elif command[-1] == "/tmp/db_facts.py":
            return json.dumps(before).encode()
        return b""

    module.run.side_effect = run
    if truncate_after_restore:
        app.validate_restored_database.side_effect = lambda *args: dump.write_bytes(b"truncated")
    with patch.object(restore.subprocess, "run", return_value=Mock(returncode=1)), \
            patch.object(restore, "cleanup_restore_resources", return_value=True), patch.object(restore, "wait_restore_ready"):
        if truncate_after_restore:
            with pytest.raises(release.UpgradeError, match="BACKUP_DECRYPT_VERIFY"):
                restore.restore_verified_backup(app, before, dump, encrypted, verify, "temporary", module)
            assert not (root / "backup-receipt.json").exists()
        else:
            restore.restore_verified_backup(app, before, dump, encrypted, verify, "temporary", module)
            receipt = json.loads((root / "backup-receipt.json").read_text())
            assert receipt["backup_sha256"] == hashlib.sha256(encrypted.read_bytes()).hexdigest()
