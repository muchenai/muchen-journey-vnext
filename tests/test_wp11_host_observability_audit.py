from __future__ import annotations

import json

import pytest

from scripts import wp11_host_observability_audit as audit
from scripts import wp11_staging_observability_contract as contract


CANDIDATE = "1" * 40


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
