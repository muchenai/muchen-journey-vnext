import subprocess
from pathlib import Path

import pytest

from scripts import wp31_canary_service_probe as probe


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value", [
    "journey-next-greenfield-canary-api-1|journey-next-greenfield-canary\n",
    "custom-name|journey-next-greenfield-canary\n",
    "journey-next-greenfield-canary-web-1|\n",
    "journey-next-production-canary-api-1|\n",
    "custom-name|journey-next-production-canary\n",
])
def test_both_project_labels_and_fallback_names_detected(value):
    assert probe.service_present(value)


@pytest.mark.parametrize("value", ["", "production-api|journey-next-production\n", "staging-api|journey-next-staging\n"])
def test_no_canary(value):
    assert not probe.service_present(value)


@pytest.mark.parametrize("value", ["docker failed", "|", "a|b|c", "invalid name|project", "custom|journey-next-greenfield-canary\ninvalid"])
def test_invalid_metadata_is_not_absence(value):
    with pytest.raises(ValueError):
        probe.service_present(value)


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.CalledProcessError(1, "docker", stderr="SYNTHETIC_SECRET"), subprocess.TimeoutExpired("docker", 15)])
def test_failed_docker_probe_returns_unknown(monkeypatch, capsys, error):
    def failed(*args, **kwargs):
        raise error
    monkeypatch.setattr(probe.subprocess, "run", failed)
    assert probe.main() == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "WP31_CANARY_SERVICE_PROBE=UNKNOWN\n"


@pytest.mark.parametrize("value,code", [("", 1), ("x|journey-next-greenfield-canary\n", 0)])
def test_command_is_readonly_and_exit_status_is_exact(monkeypatch, value, code):
    def run(command, **kwargs):
        assert command == ["docker", "ps", "--format", probe.FORMAT]
        assert kwargs == {"check": True, "capture_output": True, "text": True, "timeout": 15}
        return subprocess.CompletedProcess(command, 0, value, "")
    monkeypatch.setattr(probe.subprocess, "run", run)
    assert probe.main() == code


def test_workflow_does_not_swallow_docker_errors_or_use_old_prefix_only():
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    start = workflow.index("      - name: Read-only Canary database lifecycle guard")
    end = workflow.index("      - name: Upload Canary lifecycle diagnostic", start)
    guard = workflow[start:end]
    assert '"python3 -" <scripts/wp31_canary_service_probe.py' in guard
    assert "grep -Eq '^journey-next-production-canary'" not in guard
    assert '*) fail_probe "$probe_status" SSH_CANARY_SERVICE_PROBE ;;' in guard
    compose = (ROOT / "deploy/production/compose.greenfield-canary.yaml").read_text()
    assert compose.splitlines()[0] == "name: " + probe.PROJECTS[0]
