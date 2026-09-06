import json

import pytest

from scripts import wp31_canary_lifecycle_diagnostic as diagnostic


EXPECTED_KEYS = {
    "schema_version",
    "status",
    "failure_category",
    "exit_code",
    "database_exists",
    "canary_service_active",
    "current_release_reference",
    "workflow_runs_in_progress",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_initial_record_is_safe_and_complete(tmp_path):
    path = tmp_path / "lifecycle-diagnostic.json"

    result = diagnostic.write_initial(path)

    assert set(result) == EXPECTED_KEYS
    assert result == read(path)
    assert result["schema_version"] == 1
    assert result["status"] == "NOT_STARTED"
    assert result["failure_category"] == "NOT_STARTED"
    assert result["exit_code"] is None
    assert result["database_exists"] is None
    assert result["canary_service_active"] is None
    assert result["current_release_reference"] is None
    assert result["workflow_runs_in_progress"] is None
    assert "message" not in result


def test_probe_failure_record_contains_only_allowlisted_facts(tmp_path):
    path = tmp_path / "lifecycle-diagnostic.json"

    result = diagnostic.write_failure(
        path,
        category="RDS_DATABASE_EXISTS_PROBE",
        exit_code=17,
    )

    assert result == read(path)
    assert result["status"] == "FAILED"
    assert result["failure_category"] == "RDS_DATABASE_EXISTS_PROBE"
    assert result["exit_code"] == 17
    assert set(result) == EXPECTED_KEYS


def test_guard_rejection_records_observed_lifecycle_facts(tmp_path):
    path = tmp_path / "lifecycle-diagnostic.json"

    result = diagnostic.write_observations(
        path,
        status="FAILED",
        failure_category="GUARD_REJECTED",
        database_exists=True,
        canary_service_active=False,
        current_release_reference=False,
        workflow_runs_in_progress=2,
        exit_code=2,
    )

    assert result == read(path)
    assert result["database_exists"] is True
    assert result["canary_service_active"] is False
    assert result["current_release_reference"] is False
    assert result["workflow_runs_in_progress"] == 2


def test_invalid_category_and_observation_fail_closed(tmp_path):
    path = tmp_path / "lifecycle-diagnostic.json"

    with pytest.raises(diagnostic.LifecycleDiagnosticError):
        diagnostic.write_failure(path, category="arbitrary-error", exit_code=1)

    with pytest.raises(diagnostic.LifecycleDiagnosticError):
        diagnostic.write_observations(
            path,
            status="FAILED",
            failure_category="GUARD_REJECTED",
            database_exists="unknown",
            canary_service_active=False,
            current_release_reference=False,
            workflow_runs_in_progress=0,
            exit_code=2,
        )


def test_passed_record_requires_no_failure_category(tmp_path):
    path = tmp_path / "lifecycle-diagnostic.json"

    result = diagnostic.write_observations(
        path,
        status="PASSED",
        failure_category="NONE",
        database_exists=False,
        canary_service_active=False,
        current_release_reference=False,
        workflow_runs_in_progress=0,
        exit_code=0,
    )

    assert result["status"] == "PASSED"
    assert result["failure_category"] == "NONE"
