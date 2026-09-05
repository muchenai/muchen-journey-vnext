import json

import pytest

from scripts import wp31_canary_database_guard as guard


def facts(**overrides):
    value = {
        "database_name": guard.CANARY_DATABASE,
        "database_exists": True,
        "canary_service_active": False,
        "current_release_reference": False,
        "workflow_runs_in_progress": 0,
    }
    value.update(overrides)
    return value


def test_rebuild_requires_existing_unused_database():
    assert guard.safe_to_rebuild(facts()) is True
    assert guard.safe_to_rebuild(facts(database_exists=False)) is False
    assert guard.safe_to_rebuild(facts(canary_service_active=True)) is False
    assert guard.safe_to_rebuild(facts(current_release_reference=True)) is False
    assert guard.safe_to_rebuild(facts(workflow_runs_in_progress=1)) is False


def test_create_allows_absent_database_but_still_blocks_references():
    assert guard.safe_to_create(facts(database_exists=False)) is True
    assert guard.safe_to_create(facts(canary_service_active=True)) is False
    assert guard.safe_to_create(facts(current_release_reference=True)) is False


def test_check_fails_closed_and_reports_safe_result(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text(json.dumps(facts()), encoding="utf-8")
    assert guard.check(path, "rebuild")["safe"] is True
    path.write_text(json.dumps(facts(workflow_runs_in_progress=2)), encoding="utf-8")
    with pytest.raises(guard.DatabaseGuardError):
        guard.check(path, "rebuild")
