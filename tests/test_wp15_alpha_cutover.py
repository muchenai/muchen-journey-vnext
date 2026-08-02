import json
from pathlib import Path

import pytest

import scripts.wp15_alpha_cutover as cutover


def test_contract_locks_candidate_hosts_databases_and_fault_domain():
    value = cutover.load_contract()
    assert value["candidate_sha"] == "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a"
    assert value["production_host"] == "journey.muchenai.com"
    assert value["staging_host"] == "staging-vnext.muchenai.com"
    assert value["production_database"] != value["staging_database"]
    assert value["fault_domain"]["physical_ecs_and_rds_shared_for_alpha"] is True


def test_contract_rejects_unpinned_database_tool(tmp_path: Path):
    value = cutover.load_contract()
    value["database_tool"]["source"] = "postgres:latest"
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value))
    with pytest.raises(cutover.CutoverError, match="digest pinned"):
        cutover.load_contract(path)


def test_contract_rejects_oversized_database_tool(tmp_path: Path):
    value = cutover.load_contract()
    value["database_tool"]["max_compressed_bytes"] = 6_000_001
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value))
    with pytest.raises(cutover.CutoverError, match="size ceiling"):
        cutover.load_contract(path)


def test_reviewed_files_are_fail_closed_and_execute_no_mutation():
    if not cutover.WORKFLOW.exists():
        pytest.skip("runtime image intentionally excludes GitHub workflow files")
    result = cutover.check()
    assert result["status"] == "PASS"
    assert result["staging_preserved"] is True
    assert result["production_mutation_executed"] is False
