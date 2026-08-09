import copy
import hashlib
import json
from pathlib import Path

import pytest

import scripts.wp08_web_only as web_only


def accepted_runtime(contract: dict[str, object]) -> dict[str, object]:
    baseline = contract["runtime_baseline"]
    assert isinstance(baseline, dict)
    return {
        "web_release": contract["candidate_commit"],
        "api_release": baseline["candidate_commit"],
        "worker_release": baseline["candidate_commit"],
        "migration_revision": baseline["migration_revision"],
        "config_schema_version": baseline["config_schema_version"],
        "api_status": "READY",
        "database_status": "READY",
        "worker_stale": False,
        "root_http_status": 200,
        "anonymous_ops_http_status": 401,
        "anonymous_review_http_status": 401,
    }


def test_checked_in_contract_is_static_web_only_and_baseline_compatible(monkeypatch):
    contract = copy.deepcopy(web_only.load_contract())
    assert contract["status"] == "RETIRED"
    assert (
        contract["superseded_by_candidate"]
        == "3445b5784d735fad2af4cd9a3568221b4aef7e19"
    )
    candidate_openapi = b'{"openapi":"historical-candidate"}\n'
    baseline = contract["runtime_baseline"]
    assert isinstance(baseline, dict)
    baseline["openapi_sha256"] = hashlib.sha256(candidate_openapi).hexdigest()

    def fake_git(*args: str, text: bool = True):
        if args[:2] == ("rev-parse", f"{contract['candidate_commit']}^"):
            return f"{contract['candidate_parent']}\n"
        if args[:2] == ("merge-base", "--is-ancestor"):
            return ""
        if args[:2] == ("diff", "--name-only") and "--" not in args:
            return "apps/web/src/app/ops/page.tsx\nMakefile\n"
        if args[:2] == ("diff", "--name-only") and "--" in args:
            return ""
        if args[:1] == ("show",):
            return candidate_openapi if not text else candidate_openapi.decode()
        raise AssertionError(args)

    monkeypatch.setattr(web_only, "_git", fake_git)
    web_only.check_repository(contract)


def test_runtime_accepts_candidate_web_on_exact_healthy_baseline():
    contract = web_only.load_contract()
    web_only.verify_runtime(contract, accepted_runtime(contract))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("api_release", "172c9f62ffdcd4fce31fb4900fdca46b3405ab89"),
        ("worker_release", "172c9f62ffdcd4fce31fb4900fdca46b3405ab89"),
        ("migration_revision", "0013_wp11_notify_observability"),
        ("worker_stale", True),
        ("anonymous_ops_http_status", 200),
    ),
)
def test_runtime_rejects_mixed_or_unsafe_component_state(field: str, value: object):
    contract = web_only.load_contract()
    evidence = accepted_runtime(contract)
    evidence[field] = value
    with pytest.raises(web_only.WebOnlyError, match="not UAT-compatible"):
        web_only.verify_runtime(contract, evidence)


def test_contract_rejects_widened_allowed_paths(tmp_path: Path):
    payload = json.loads(web_only.CONTRACT.read_text())
    payload["candidate_commit_allowed_paths"].append("apps/api/")
    contract = tmp_path / "wp08_web_only.json"
    contract.write_text(json.dumps(payload))
    with pytest.raises(web_only.WebOnlyError, match="allowed paths"):
        web_only.load_contract(contract)


def test_contract_cannot_be_reactivated(tmp_path: Path):
    payload = json.loads(web_only.CONTRACT.read_text())
    payload["status"] = "ACTIVE"
    contract = tmp_path / "wp08_web_only.json"
    contract.write_text(json.dumps(payload))
    with pytest.raises(web_only.WebOnlyError, match="remain retired"):
        web_only.load_contract(contract)


def test_runtime_rejects_unreviewed_evidence_fields():
    contract = web_only.load_contract()
    evidence = accepted_runtime(contract)
    evidence["raw_log"] = "forbidden"
    with pytest.raises(web_only.WebOnlyError, match="evidence keys"):
        web_only.verify_runtime(contract, evidence)


def repair_prestate(contract: dict[str, object]) -> dict[str, object]:
    return {
        "web_release": contract["candidate_commit"],
        "api_release": contract["candidate_commit"],
        "worker_release": contract["candidate_commit"],
        "worker_heartbeat_release": contract["candidate_commit"],
        "migration_revision": "0014_wp12_data_lifecycle",
        "config_schema_version": 3,
        "api_status": "READY",
        "worker_stale": False,
    }


def test_runtime_repair_accepts_the_read_only_inventory_prestate():
    contract = web_only.load_contract()
    web_only.verify_repair_prestate(contract, repair_prestate(contract))


def test_runtime_repair_retains_the_previous_reviewed_transitional_prestate():
    contract = web_only.load_contract()
    evidence = repair_prestate(contract)
    evidence.update(
        {
            "api_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
            "worker_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
            "worker_heartbeat_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
            "migration_revision": "0013_wp11_notify_observability",
            "worker_stale": True,
        }
    )
    web_only.verify_repair_prestate(contract, evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("web_release", "02863d0b670ee9b00b9def3e75bc6699827f555a"),
        ("api_release", "unknown-release"),
        ("worker_release", "unknown-release"),
        ("worker_heartbeat_release", "unknown-release"),
        ("migration_revision", "0012_wp10_file_security"),
        ("config_schema_version", 2),
        ("api_status", "DEGRADED"),
        ("worker_stale", "true"),
    ),
)
def test_runtime_repair_rejects_unreviewed_prestate(field: str, value: object):
    contract = web_only.load_contract()
    evidence = repair_prestate(contract)
    evidence[field] = value
    with pytest.raises(web_only.WebOnlyError, match="prestate is not allowed"):
        web_only.verify_repair_prestate(contract, evidence)
