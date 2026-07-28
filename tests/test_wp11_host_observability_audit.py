from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import wp11_host_observability_audit as audit
from scripts import wp11_staging_observability_contract as contract


CANDIDATE = "1" * 40


def test_logcollector_uses_the_official_host_service_name(monkeypatch):
    commands: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="active\n")

    monkeypatch.setattr(audit.subprocess, "run", fake_run)

    assert audit._logcollector_is_active() is True
    assert commands == [("systemctl", "is-active", "logcollectord.service")]


def test_bounded_logcollector_diagnostic_never_returns_secret_values(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "logcollector"
    (root / "etc").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "data" / "ops").mkdir()
    (root / "logcollector").write_text("binary-placeholder")
    (root / "etc" / "logcollector.yml").write_text(
        "\n".join(
            [
                'endpoint: "https://tls-cn-beijing.ivolces.com"',
                "region: 'cn-beijing'",
                "secret_id: must-not-be-returned",
                "secret_key: must-not-be-returned-either",
            ]
        )
    )
    (root / "agent_info.json").write_text(
        json.dumps({"ip": "192.0.2.1", "version": "2.4.2"})
    )
    (root / "data" / "delivered-rule.json").write_text(
        '{"name":"journey-next-staging-json-stdout"}'
    )
    (root / "data" / "ops" / "1.yml.fail").write_text("private failure")

    monkeypatch.setattr(audit, "LOGCOLLECTOR_ROOT", root)
    monkeypatch.setattr(audit, "LOGCOLLECTOR_CONFIG", root / "etc/logcollector.yml")
    monkeypatch.setattr(audit, "LOGCOLLECTOR_AGENT_INFO", root / "agent_info.json")
    monkeypatch.setattr(audit, "_run", lambda *_args: "LogCollector 2.4.2")

    result = audit._logcollector_diagnostic()

    assert result == audit.LogCollectorDiagnostic(
        version="2.4.2",
        agent_info_valid=True,
        endpoint_region_valid=True,
        credentials_present=True,
        staging_rule_marker_observed=True,
        ops_failure_files=1,
    )
    assert "must-not-be-returned" not in repr(result)


def test_structured_log_summary_requires_expected_release_and_rejects_sensitive_keys():
    raw = "\n".join(
        [
            json.dumps(
                {
                    "service": "worker",
                    "event": "runtime.snapshot",
                    "release": CANDIDATE,
                    "outbox_backlog": 0,
                }
            ),
            "not-json",
            json.dumps(
                {
                    "service": "worker",
                    "event": "runtime.snapshot",
                    "release": "2" * 40,
                    "nested": {"token": "must-never-ship"},
                }
            ),
        ]
    )

    summary = audit.summarize_json_lines(
        raw, expected_event="runtime.snapshot", candidate=CANDIDATE
    )

    assert summary.parsed == 2
    assert summary.expected_event_count == 2
    assert summary.release_match_count == 1
    assert summary.forbidden_fields == frozenset({"token"})


def test_notification_summary_is_zero_recipient_and_preserves_pending_history():
    audit.validate_notification_summary(
        {
            "active_recipients": 0,
            "unsafe_without_recipient": 0,
            "external_receipts": 0,
            "notification_attempts": 0,
            "worker_release": CANDIDATE,
            "worker_fresh": True,
        },
        CANDIDATE,
    )

    with pytest.raises(audit.AuditError, match="notification_attempts"):
        audit.validate_notification_summary(
            {
                "active_recipients": 0,
                "unsafe_without_recipient": 0,
                "external_receipts": 0,
                "notification_attempts": 1,
                "worker_release": CANDIDATE,
                "worker_fresh": True,
            },
            CANDIDATE,
        )


def test_workflow_is_read_only_and_always_closes_temporary_ssh_ingress():
    workflow = "\n".join(contract.REQUIRED_MARKERS.values())
    contract.validate_workflow(workflow)

    with pytest.raises(contract.ContractError, match="terraform apply"):
        contract.validate_workflow(workflow + "\nterraform apply")

    with pytest.raises(contract.ContractError, match="candidate artifact apply gate"):
        contract.validate_workflow(workflow + "\nmake wp08-staging-apply-check")

    mask = contract.REQUIRED_MARKERS["runner address masking"]
    export = contract.REQUIRED_MARKERS["runner environment export"]
    misordered = workflow.replace(mask, "").replace(export, "") + f"\n{export}\n{mask}"
    with pytest.raises(contract.ContractError, match="masked before environment export"):
        contract.validate_workflow(misordered)
