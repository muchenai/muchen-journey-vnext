import subprocess
from unittest.mock import Mock

from scripts import canary_registry_diagnostic as mod


def test_manifest_reports_layers_without_pull(monkeypatch):
    payload = {"layers": [{"size": 10}, {"size": 20}]}
    monkeypatch.setattr(mod.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, '{"layers":[{"size":10},{"size":20}]}', "")))
    result = mod.run(["docker", "manifest", "inspect", mod.API])
    assert result["layer_count"] == 2
    assert result["compressed_bytes"] == 30
    assert result["status"] == "PASS"


def test_timeout_is_explicit(monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("docker", 1)))
    result = mod.run(["docker", "manifest", "inspect", mod.API])
    assert result["status"] == "TIMEOUT"


def test_no_pull_or_mutating_commands_in_source():
    source = open("scripts/canary_registry_diagnostic.py", encoding="utf-8").read()
    assert '"docker", "pull"' not in source
    assert '"docker", "run"' not in source
    assert '"docker", "restart"' not in source
