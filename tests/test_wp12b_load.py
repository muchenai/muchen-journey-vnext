import json
import stat
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from journey_api.config import get_settings
from journey_api.wp12b_synthetic import SyntheticError, audit, prepare, retire
from scripts.wp12b_load import (
    LoadError,
    Observation,
    load_bundle,
    load_contract,
    summarize,
    validate_origin,
    validate_workflow_source,
    verify_evidence,
)


def write_private(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def test_wp12b_contract_is_bounded_and_zero_tolerance():
    contract = load_contract()
    assert contract["organization_count"] == 20
    assert contract["learners_per_organization"] == 25
    assert contract["peak_concurrency"] == 50
    assert contract["p95_budget_seconds"] == 1.0
    assert contract["max_cross_org_leaks"] == 0
    assert contract["max_duplicate_facts"] == 0
    assert validate_origin("https://staging-vnext.muchenai.com") == (
        "https://staging-vnext.muchenai.com",
        "staging",
    )
    assert validate_origin("http://127.0.0.1:38000") == (
        "http://127.0.0.1:38000",
        "local",
    )
    for unsafe in (
        "https://muchenai.com",
        "https://journey.muchenai.com",
        "https://staging-vnext.muchenai.com/path",
        "http://staging-vnext.muchenai.com",
    ):
        with pytest.raises(LoadError):
            validate_origin(unsafe)


def test_wp12b_workflow_contract_rejects_mutation_and_bundle_upload():
    required = (
        "workflow_dispatch:",
        "environment: staging",
        "inputs.confirmation == format('RUN_WP12B_{0}', inputs.candidate)",
        "git merge-base --is-ancestor",
        "cat /srv/journey-next-staging/DEPLOYED_CANDIDATE",
        "python3 scripts/wp12b_load.py contract-check",
        "python3 scripts/wp12b_load.py run",
        "python3 scripts/wp12b_load.py verify",
        "if: always() && steps.prepare.outputs.run_id != ''",
        "python -m journey_api.wp12b_synthetic retire",
        "if: always() && steps.frozen.outputs.security_group_id != ''",
        "scripts.wp08_security_group close",
        "shred -u /tmp/wp12b-bundle-",
        "- name: Upload PII-free evidence\n  path: wp12b-evidence",
    )
    valid = "\n".join(required)
    validate_workflow_source(valid)
    with pytest.raises(LoadError, match="forbidden operations"):
        validate_workflow_source(valid + "\nterraform apply")
    with pytest.raises(LoadError, match="private session bundle"):
        validate_workflow_source(valid + "\nwp12b-bundle")


def test_wp12b_summary_fails_latency_status_and_cross_org_leak():
    config = load_contract()
    passing = (
        Observation("read", 200, 200, 0.1),
        Observation("isolation.foreign", 404, 404, 0.2),
    )
    assert summarize(passing, config)[0] == "PASS"
    slow = passing + (Observation("read", 200, 200, 1.1),)
    assert summarize(slow, config)[0] == "FAIL"
    leaked = (Observation("isolation.foreign", 404, 200, 0.1),)
    status, metrics = summarize(leaked, config)
    assert status == "FAIL"
    assert metrics["cross_org_leaks"] == 1
    conflicted = (Observation("write", 200, 409, 0.1),)
    status, metrics = summarize(conflicted, config)
    assert status == "FAIL"
    assert metrics["state_conflicts"] == 1


def test_wp12b_bundle_rejects_expired_session_material(tmp_path):
    now = datetime.now(timezone.utc)
    bundle = tmp_path / "bundle.json"
    write_private(
        bundle,
        {
            "schema_version": 1,
            "classification": "SYNTHETIC_NO_REAL_PII",
            "scope": "LOCAL_SMOKE",
            "candidate_sha": "local",
            "run_id": "wp12b-expired",
            "created_at": (now - timedelta(hours=3)).isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
            "organizations": [],
        },
    )
    with pytest.raises(LoadError, match="expired"):
        load_bundle(bundle, load_contract(), smoke=True)


def test_wp12b_evidence_requires_load_audit_and_retirement(tmp_path):
    candidate = "a" * 40
    run_id = "wp12b-test-evidence"
    load = {
        "scope": "STAGING_SYNTHETIC_MULTI_TENANT",
        "candidate_sha": candidate,
        "run_id": run_id,
        "status": "PASS",
        "staging_benchmark": "PASS",
        "metrics": {
            "http_5xx": 0,
            "state_conflicts": 0,
            "cross_org_leaks": 0,
            "unexpected_responses": 0,
        },
    }
    audit_report = {
        "candidate_sha": candidate,
        "run_id": run_id,
        "status": "PASS",
        "metrics": {
            "cross_org_mismatches": 0,
            "duplicate_facts": 0,
            "incomplete_flows": 0,
        },
    }
    retired = {
        "candidate_sha": candidate,
        "run_id": run_id,
        "status": "PASS",
        "metrics": {"active_sessions": 0, "active_users": 0},
    }
    paths = [tmp_path / name for name in ("load.json", "audit.json", "retired.json")]
    for path, payload in zip(paths, (load, audit_report, retired), strict=True):
        write_private(path, payload)
    assert verify_evidence(*paths)["decision"] == "WP12B_CLOSED"
    retired["metrics"]["active_sessions"] = 1
    write_private(tmp_path / "retired-fail.json", retired)
    with pytest.raises(LoadError, match="not fully retired"):
        verify_evidence(paths[0], paths[1], tmp_path / "retired-fail.json")


def test_wp12b_local_synthetic_identities_are_private_unique_and_retired(tmp_path):
    run_id = f"wp12b-{uuid.uuid4().hex[:12]}"
    candidate = get_settings().app_release
    bundle = tmp_path / "bundle.json"
    prepare(
        candidate=candidate,
        confirmation="PREPARE_WP12B_LOCAL",
        run_id=run_id,
        organizations=2,
        learners_per_organization=2,
        reviewers_per_organization=1,
        output=bundle,
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["classification"] == "SYNTHETIC_NO_REAL_PII"
    assert payload["scope"] == "LOCAL_SMOKE"
    assert len(payload["organizations"]) == 2
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    with pytest.raises(SyntheticError, match="already exists"):
        prepare(
            candidate=candidate,
            confirmation="PREPARE_WP12B_LOCAL",
            run_id=run_id,
            organizations=2,
            learners_per_organization=2,
            reviewers_per_organization=1,
            output=tmp_path / "duplicate.json",
        )
    incomplete = tmp_path / "incomplete.json"
    with pytest.raises(SyntheticError, match="audit failed"):
        audit(candidate=candidate, run_id=run_id, output=incomplete)
    assert json.loads(incomplete.read_text(encoding="utf-8"))["status"] == "FAIL"
    retired = tmp_path / "retired.json"
    retire(candidate=candidate, run_id=run_id, output=retired)
    retirement = json.loads(retired.read_text(encoding="utf-8"))
    assert retirement["status"] == "PASS"
    assert retirement["metrics"]["active_sessions"] == 0
    assert retirement["metrics"]["active_users"] == 0
