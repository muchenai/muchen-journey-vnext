import subprocess
import json
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


def test_prepare_process_inventory_never_emits_arbitrary_arguments(tmp_path):
    for pid, argv in [("1", ["docker", "pull", mod.API, "synthetic-secret"]),
                      ("2", ["python3", "/private/canary_schema_upgrade.py", "prepare", "synthetic-secret"]),
                      ("3", ["unrelated", "synthetic-secret"])]:
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "cmdline").write_bytes("\0".join(argv).encode())
    rows = mod.prepare_processes(tmp_path)
    assert {row["operation"] for row in rows} == {"docker_image_download", "schema_upgrade"}
    assert "synthetic-secret" not in json.dumps(rows)
    assert "/private" not in json.dumps(rows)


def test_content_progress_drops_sensitive_urls(monkeypatch):
    digest = "sha256:" + "a" * 64
    output = f"REF SIZE AGE\nlayer-{digest} 32MiB 10m https://example.invalid/?token=synthetic-secret\n"
    monkeypatch.setattr(mod.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, output, "")))
    result = mod.active_content()
    assert result["downloads"] == [{"digest": digest, "size": "32MiB", "age": "10m"}]
    assert "synthetic-secret" not in json.dumps(result)
