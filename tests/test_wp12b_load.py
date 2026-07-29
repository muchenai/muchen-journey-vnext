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
    execute,
    load_bundle,
    load_contract,
    summarize,
    validate_origin,
    validate_public_origin,
    validate_workflow_source,
    verify_evidence,
    write_owner_only,
)


def write_private(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def valid_workflow_source():
    return """
workflow_dispatch:
environment: staging
inputs.confirmation == format('RUN_WP12B_{0}', inputs.candidate)
git merge-base --is-ancestor
cat /srv/journey-next-staging/DEPLOYED_CANDIDATE
python3 scripts/wp12b_load.py contract-check
- name: Verify deployed candidate and prepare synthetic identities
test -f .deployment.env && test ! -L .deployment.env
. ./.deployment.env
docker compose exec -T api python -m journey_api.wp12b_synthetic prepare < /dev/null
- name: Execute bounded internal API load
docker inspect api
ssh -o ExitOnForwardFailure=yes -N -L 127.0.0.1:38000:10.0.0.2:8000 host
python3 scripts/wp12b_load.py run --origin http://127.0.0.1:38000 --public-origin https://staging-vnext.muchenai.com --output "$load_report"
- name: Audit immutable facts and tenant scope
test -f .deployment.env && test ! -L .deployment.env
. ./.deployment.env
docker compose exec -T api python -m journey_api.wp12b_synthetic audit < /dev/null
- name: Retire all synthetic identities
if: always() && steps.prepare.outputs.run_id != ''
cleanup_remote_files
trap cleanup_remote_files EXIT
--filter label=com.docker.compose.project=journey-next-staging
--filter label=com.docker.compose.service=api
test "${#api_containers[@]}" -eq 1
docker exec "$api_container" python -m journey_api.wp12b_synthetic retire
docker cp "$api_container:$container_retired" output
docker exec "$api_container" python -c cleanup
- name: Close WP-12B evidence gate
python3 scripts/wp12b_load.py verify
- name: Assemble PII-free evidence
if: always() && steps.prepare.outputs.run_id != '' && steps.retire.outcome == 'success'
cp "$RUNNER_TEMP/wp12b-load.json" wp12b-evidence/load.json
- name: Upload PII-free evidence
if: always() && steps.assemble.outcome == 'success'
  path: wp12b-evidence
- name: Close SSH ingress
if: always() && steps.frozen.outputs.security_group_id != ''
python3 -m scripts.wp08_security_group close
"""


def test_wp12b_contract_is_bounded_and_zero_tolerance():
    contract = load_contract()
    assert contract["organization_count"] == 20
    assert contract["learners_per_organization"] == 25
    assert contract["peak_concurrency"] == 50
    assert contract["p95_budget_seconds"] == 1.0
    assert contract["max_cross_org_leaks"] == 0
    assert contract["max_duplicate_facts"] == 0
    assert validate_origin("http://127.0.0.1:38000") == "http://127.0.0.1:38000"
    assert validate_public_origin("https://staging-vnext.muchenai.com") == (
        "https://staging-vnext.muchenai.com"
    )
    for unsafe in (
        "https://staging-vnext.muchenai.com",
        "https://muchenai.com",
        "https://journey.muchenai.com",
        "https://staging-vnext.muchenai.com/path",
        "http://staging-vnext.muchenai.com",
    ):
        with pytest.raises(LoadError):
            validate_origin(unsafe)
    for unsafe_public in (
        "http://127.0.0.1:38000",
        "https://staging-vnext.muchenai.com/path",
        "https://journey.muchenai.com",
    ):
        with pytest.raises(LoadError):
            validate_public_origin(unsafe_public)


def test_wp12b_workflow_contract_rejects_mutation_and_bundle_upload():
    valid = valid_workflow_source()
    validate_workflow_source(valid)
    with pytest.raises(LoadError, match="forbidden operations"):
        validate_workflow_source(valid + "\nterraform apply")
    with pytest.raises(LoadError, match="private session bundle"):
        validate_workflow_source(valid + "\nwp12b-bundle")


def test_wp12b_failure_evidence_is_owner_only_and_contains_no_session_material(tmp_path):
    report = {
        "schema_version": 1,
        "failure_code": "REVIEW_QUEUE_COUNT_MISMATCH",
        "diagnostics": {
            "expected_review_queue_count": 500,
            "actual_review_queue_count": 0,
        },
        "status": "FAIL",
        "session_material_recorded": False,
    }
    output = tmp_path / "load.json"
    write_owner_only(output, report)
    persisted = output.read_text(encoding="utf-8")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert "session_token" not in persisted
    assert json.loads(persisted) == report


def test_wp12b_runner_persists_pii_free_report_before_known_flow_failure(
    tmp_path, monkeypatch
):
    now = datetime.now(timezone.utc)
    candidate = "local-test-candidate"
    actor_token = "s" * 40
    csrf_token = "c" * 40
    organizations = []
    for index in range(2):
        ref = f"org-{index:03d}"
        organizations.append(
            {
                "ref": ref,
                "learners": [
                    {
                        "organization_ref": ref,
                        "role": "LEARNER",
                        "session_token": actor_token + str(index),
                        "csrf_token": csrf_token + str(index),
                        "assignment_id": f"assignment-{index}",
                    }
                ],
                "reviewers": [
                    {
                        "organization_ref": ref,
                        "role": "REVIEWER",
                        "session_token": "r" * 40 + str(index),
                        "csrf_token": "x" * 40 + str(index),
                        "assignment_id": None,
                    }
                ],
                "operator": {
                    "organization_ref": ref,
                    "role": "OPERATOR",
                    "session_token": "o" * 40 + str(index),
                    "csrf_token": "y" * 40 + str(index),
                    "assignment_id": None,
                },
            }
        )
    bundle = tmp_path / "bundle.json"
    write_private(
        bundle,
        {
            "schema_version": 1,
            "classification": "SYNTHETIC_NO_REAL_PII",
            "scope": "LOCAL_SMOKE",
            "candidate_sha": candidate,
            "run_id": "wp12b-report-test",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "organizations": organizations,
        },
    )

    class FakeRunner:
        def __init__(self, _origin, _timeout_seconds):
            self._observations = []

        @property
        def observations(self):
            return tuple(self._observations)

        def request(self, operation, _path, *, expected_status=200, **_kwargs):
            self._observations.append(
                Observation(operation, expected_status, expected_status, 0.01)
            )
            if operation == "readiness.api":
                return 200, {"release": candidate}
            return expected_status, {}

    monkeypatch.setattr("scripts.wp12b_load.Runner", FakeRunner)
    output = tmp_path / "failure.json"
    with pytest.raises(LoadError, match="REVIEW_QUEUE_COUNT_MISMATCH"):
        execute(
            "http://127.0.0.1:38000",
            bundle,
            smoke=True,
            output=output,
        )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["failure_code"] == "REVIEW_QUEUE_COUNT_MISMATCH"
    assert report["diagnostics"] == {
        "expected_review_queue_count": 2,
        "actual_review_queue_count": 0,
    }
    assert report["status"] == "FAIL"
    assert report["session_material_recorded"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_wp12b_workflow_loads_compose_env_and_retirement_bypasses_compose():
    valid = valid_workflow_source()
    with pytest.raises(LoadError, match="prepare must load"):
        validate_workflow_source(valid.replace(". ./.deployment.env", ":", 1))

    audit_marker = "- name: Audit immutable facts and tenant scope"
    prefix, audit_and_after = valid.split(audit_marker, 1)
    with pytest.raises(LoadError, match="audit must load"):
        validate_workflow_source(
            prefix + audit_marker + audit_and_after.replace(". ./.deployment.env", ":", 1)
        )

    retire_marker = "- name: Retire all synthetic identities"
    prefix, retire_and_after = valid.split(retire_marker, 1)
    invalid_retire = retire_and_after.replace(
        'docker exec "$api_container" python -m journey_api.wp12b_synthetic retire',
        'docker compose exec -T api python -m journey_api.wp12b_synthetic retire',
        1,
    )
    with pytest.raises(LoadError, match="retirement must not depend"):
        validate_workflow_source(prefix + retire_marker + invalid_retire)


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
