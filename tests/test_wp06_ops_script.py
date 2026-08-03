import copy
import json

import pytest

import scripts.wp06_ops as ops
from scripts.wp06_ops import (
    EXTERNAL_BLOCKERS,
    OpsError,
    alert_decisions,
    evaluate_release_gate,
    release_gate,
)


def evidence(status: str = "PASS") -> dict[str, object]:
    from scripts.wp06_ops import REQUIRED_RELEASE_CHECKS

    return {
        "schema_version": 1,
        "candidate": "test-candidate",
        "checks": {name: status for name in REQUIRED_RELEASE_CHECKS},
    }


def test_release_gate_is_fail_closed_for_missing_not_run_and_failed_checks():
    document = evidence()
    document["checks"]["real_human_uat"] = "NOT_RUN"  # type: ignore[index]
    decision = evaluate_release_gate(document)
    assert decision["decision"] == "NO_GO"
    assert decision["blockers"] == ["real_human_uat"]

    missing = evidence()
    del missing["checks"]["physical_acl_validation"]  # type: ignore[index]
    missing_decision = evaluate_release_gate(missing)
    assert "physical_acl_validation" in missing_decision["blockers"]

    failed = evidence()
    failed["checks"]["local_backup_isolated_restore"] = "FAIL"  # type: ignore[index]
    assert evaluate_release_gate(failed)["decision"] == "NO_GO"


def test_release_gate_requires_strict_known_schema_and_preserves_external_blockers():
    document = evidence("NOT_RUN")
    result = evaluate_release_gate(document)
    assert EXTERNAL_BLOCKERS.issubset(set(result["blockers"]))
    unknown = copy.deepcopy(document)
    unknown["checks"]["invented_approval"] = "PASS"  # type: ignore[index]
    with pytest.raises(OpsError):
        evaluate_release_gate(unknown)


def test_expect_no_go_allows_completed_external_checks_while_other_blockers_remain(tmp_path):
    document = evidence("PASS")
    document["checks"]["real_human_uat"] = "NOT_RUN"  # type: ignore[index]
    document["checks"]["physical_acl_validation"] = "FAIL"  # type: ignore[index]
    path = tmp_path / "release-gate.json"
    path.write_text(json.dumps(document))

    assert release_gate(path, expect_no_go=True) == 0


def test_alert_policy_detects_worker_queue_and_revision_failures():
    assert alert_decisions(
        {
            "worker_stale": True,
            "outbox_backlog": 10,
            "notification_dead": 1,
            "api_release": "candidate",
            "worker_release": "previous",
            "migration_revision": "0009_notification_scope",
        }
    ) == [
        "WORKER_STALE",
        "OUTBOX_BACKLOG_HIGH",
        "NOTIFICATION_DEAD",
        "RELEASE_REVISION_MISMATCH",
        "MIGRATION_REVISION_MISMATCH",
    ]


def test_http_request_uses_explicit_local_api_port(monkeypatch):
    captured = {}

    class Response:
        status = 200
        headers = {}

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("MJ_API_PORT", "38000")
    monkeypatch.setattr(ops.urllib.request, "urlopen", urlopen)

    assert ops.http_request("/health/ready")[0] == 200
    assert captured == {"url": "http://127.0.0.1:38000/health/ready", "timeout": 5}


def test_http_request_rejects_invalid_local_api_port(monkeypatch):
    monkeypatch.setenv("MJ_API_PORT", "70000")

    with pytest.raises(OpsError, match="valid TCP port"):
        ops.http_request("/health/ready")


def test_migration_check_seeds_at_head_before_preparing_historical_fixture(
    monkeypatch, tmp_path
):
    calls: list[tuple[str, ...]] = []
    legacy_facts = {"counts": {"enrollments": 1}, "task_version_fingerprint": "fixed"}
    current_facts = {
        "migration_revision": ops.EXPECTED_MIGRATION_HEAD,
        "counts": {"enrollments": 1},
        "task_version_fingerprint": "fixed",
        "invalid_constraints": 0,
        "critical_invariant_violations": 0,
    }

    monkeypatch.setattr(ops, "ensure_local_services", lambda: None)
    monkeypatch.setattr(ops, "psql", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(ops, "compose", lambda *args: calls.append(args))
    monkeypatch.setattr(ops, "legacy_database_facts", lambda *_args: legacy_facts)
    monkeypatch.setattr(ops, "database_facts", lambda *_args: current_facts)
    monkeypatch.setattr(ops, "make_run_directory", lambda: tmp_path)
    monkeypatch.setattr(
        ops,
        "write_private_json",
        lambda path, value: path.write_text(json.dumps(value)),
    )

    report_path = ops.migration_check()
    report = json.loads(report_path.read_text())
    api_steps = [
        call[6:]
        for call in calls
        if len(call) > 6 and call[5] == "api"
    ]

    assert api_steps == [
        ("alembic", "upgrade", "head"),
        ("python", "-m", "journey_api.seed"),
        ("alembic", "downgrade", "0009_notification_scope"),
        ("alembic", "upgrade", "head"),
        ("alembic", "downgrade", "0009_notification_scope"),
        ("alembic", "upgrade", "head"),
    ]
    assert report["legacy_fixture_prepared_by_current_seed_then_downgrade"] is True
    assert report["business_facts_preserved"] is True
