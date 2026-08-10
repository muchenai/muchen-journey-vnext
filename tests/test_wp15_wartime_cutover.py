import json
from pathlib import Path

import pytest

from scripts import wp15_wartime_cutover as cutover


def test_wartime_contract_locks_fresh_restore_and_exact_rollback() -> None:
    value = cutover.load_contract()
    assert value["candidate_sha"] == "ff53052847a268d025bceb93c3eab37986d50219"
    assert value["production_database"] == "journey_next_cutover_20260810"
    assert value["rollback_database"] == "journey_next_restore_20260803"
    assert value["production_database"] != value["staging_database"]
    assert value["rollback"]["dns_mutation_required"] is False


def test_wartime_contract_rejects_unpinned_image(tmp_path: Path) -> None:
    value = cutover.load_contract()
    value["images"]["web"] = "web:latest"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value))
    with pytest.raises(cutover.WartimeCutoverError, match="digest pinned"):
        cutover.load_contract(path)


def test_reviewed_wartime_files_are_fail_closed_and_non_mutating_at_check_time() -> None:
    if not cutover.WORKFLOW.exists():
        pytest.skip("runtime image intentionally excludes GitHub workflow files")
    result = cutover.check()
    assert result == {
        "status": "PASS",
        "candidate": "ff53052847a268d025bceb93c3eab37986d50219",
        "production_host": "journey.muchenai.com",
        "production_go": False,
        "production_mutation_executed": False,
    }
