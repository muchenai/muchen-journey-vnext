"""Offline tests: no real credentials, registry requests, SSH, or production DB."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import canary_prepare_remote as mod


@pytest.mark.parametrize("args,label", [
    (["docker", "ps", "-a"], "container_list"),
    (["docker", "inspect", "synthetic"], "container_inspect"),
    (["docker", "image", "inspect", "synthetic"], "image_inspect"),
    (["docker", "pull", "ghcr.io/example/example-api@sha256:synthetic"], "pull_api"),
    (["docker", "pull", "ghcr.io/example/example-web@sha256:synthetic"], "pull_web"),
    (["curl", "-fsS", "https://synthetic.invalid"], "public_readiness"),
    (["/synthetic/compose.sh", "-f", "compose.canary.yaml", "config", "--format", "json"], "compose_config"),
])
def test_known_prepare_operations(args, label):
    assert mod.command_label(args) == label


@pytest.mark.parametrize("args", [
    ["docker", "restart", "api"], ["docker", "rm", "api"],
    ["docker", "compose", "up"], ["docker", "exec", "api", "python", "seed.py"],
    ["/synthetic/compose.sh", "-f", "compose.canary.yaml", "up", "-d", "api", "web"],
    ["/synthetic/compose.sh", "-f", "compose.canary.yaml", "down"],
    ["/synthetic/compose.sh", "-f", "compose.canary.yaml", "config", "--environment"],
])
def test_mutating_container_commands_never_execute(args, monkeypatch):
    execute = Mock()
    monkeypatch.setattr(mod.subprocess, "run", execute)
    with pytest.raises(mod.PreparationError, match="COMMAND_NOT_ALLOWED"):
        mod.safe_run(args)
    execute.assert_not_called()


def test_failure_reports_operation_without_secret(monkeypatch, capsys):
    monkeypatch.setattr(mod.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 1, b"SECRET_FROM_STDOUT", b"unauthorized SECRET_FROM_STDERR")))
    with pytest.raises(mod.PreparationError, match="pull_api:UNAUTHORIZED") as error:
        mod.safe_run(["docker", "pull", "synthetic-api@sha256:synthetic"])
    assert "SECRET" not in str(error.value) + capsys.readouterr().out


def test_success_does_not_log_inspected_env(monkeypatch, capsys):
    monkeypatch.setattr(mod.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, b"SECRET_ENV", b"")))
    assert mod.safe_run(["docker", "inspect", "synthetic"]) == b"SECRET_ENV"
    assert "SECRET_ENV" not in capsys.readouterr().out


def test_timeout_is_categorized_without_command_output(monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("SECRET", 1)))
    with pytest.raises(mod.PreparationError, match="image_inspect:TIMEOUT"):
        mod.safe_run(["docker", "image", "inspect", "synthetic"])


def test_package_is_byte_pinned_not_merely_json_equal(tmp_path, monkeypatch):
    raw = json.dumps({"candidate": mod.CANDIDATE}).encode()
    monkeypatch.setattr(mod, "HASHES", {"manifest.json": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "manifest.json").write_bytes(raw)
    assert mod.verify_package(tmp_path)["candidate"] == mod.CANDIDATE
    (tmp_path / "manifest.json").write_bytes(raw + b"\n")
    with pytest.raises(mod.PreparationError, match="PACKAGE_HASH_MISMATCH"):
        mod.verify_package(tmp_path)


def test_missing_package_stops(tmp_path):
    with pytest.raises(mod.PreparationError, match="UNSAFE_PACKAGE_FILE"):
        mod.verify_package(tmp_path)


def test_workflow_keeps_environment_and_exact_tag_boundary():
    source = Path(".github/workflows/canary-app-prepare.yml").read_text()
    assert "environment: production-canary-uat" in source
    assert 'refs/tags/canary-app-prepare-$GITHUB_SHA' in source
    assert 'packages: read' in source and 'packages: write' not in source
    assert 'run_attempt' in source
    assert 'WP08_DEPLOY_SSH_PRIVATE_KEY' in source
    for forbidden in ("terraform apply", "WP08_RUNTIME_DB_PASSWORD", "WP08_MIGRATION_DB_PASSWORD", "WP09_FEISHU_APP_SECRET", "WP15_BACKUP_KEY", "greenfield_canary_deploy.sh", "--acknowledge-interruption"):
        assert forbidden not in source


def test_remote_wrapper_has_no_switch_entrypoint():
    source = Path("scripts/canary_prepare_remote.py").read_text()
    assert "upgrade.prepare()" in source
    assert "upgrade.switch(" not in source and "upgrade.rollback(" not in source
    assert 'sys.stdin.read(4097)' in source
    assert 'os.environ["DOCKER_CONFIG"] = str(config)' in source
    assert 'config.resolve().parent != directory' in source


def test_pull_timeout_is_bounded_but_longer_than_old_default(monkeypatch):
    calls = []
    monkeypatch.setattr(mod.subprocess, "run", Mock(side_effect=lambda *args, **kwargs: calls.append(kwargs) or subprocess.CompletedProcess([], 0, b"", b"")))
    mod.safe_run(["docker", "pull", "synthetic-api@sha256:synthetic"], timeout=600)
    assert calls[0]["timeout"] == 1800


@pytest.mark.parametrize("failure", [None, "login", "prepare"])
def test_temporary_login_cleanup_and_existing_config_preserved(tmp_path, monkeypatch, capsys, failure):
    root = tmp_path / "canary"
    (root / "releases").mkdir(parents=True)
    old = root / "releases" / "old"
    old.mkdir()
    runner = Mock()
    runner.new = root / "releases" / "new"
    runner.current.return_value = old
    if failure == "prepare":
        runner.prepare.side_effect = mod.PreparationError("SYNTHETIC_PREPARE_FAILURE")
    module = SimpleNamespace(ROOT=root, OLD=old, BASE="old", OLD_IMAGES={},
                             Upgrade=Mock(return_value=runner), load_manifest=Mock())
    monkeypatch.setattr(mod, "verify_package", Mock(return_value={}))
    monkeypatch.setattr(mod.importlib.util, "spec_from_file_location", Mock(return_value=SimpleNamespace(loader=Mock())))
    monkeypatch.setattr(mod.importlib.util, "module_from_spec", Mock(return_value=module))
    monkeypatch.setattr(mod.sys, "platform", "linux")
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(mod.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(flock=Mock(), LOCK_EX=1, LOCK_NB=2))
    monkeypatch.setenv("DOCKER_CONFIG", "existing-private-config")
    execute = Mock(return_value=subprocess.CompletedProcess([], 1 if failure == "login" else 0, b"HIDDEN", b"HIDDEN"))
    monkeypatch.setattr(mod.subprocess, "run", execute)
    if failure:
        with pytest.raises(mod.PreparationError):
            mod.prepare(tmp_path, "synthetic-user", "synthetic-token")
    else:
        mod.prepare(tmp_path, "synthetic-user", "synthetic-token")
        assert json.loads((tmp_path / "result.json").read_text())["switch_performed"] is False
    assert mod.os.environ["DOCKER_CONFIG"] == "existing-private-config"
    assert not list(tmp_path.glob(".registry-*"))
    assert execute.call_args.kwargs["input"] == b"synthetic-token"
    output = capsys.readouterr().out
    assert "synthetic-token" not in output and "HIDDEN" not in output
    runner.switch.assert_not_called()
    runner.rollback.assert_not_called()
    if failure == "login":
        runner.prepare.assert_not_called()
