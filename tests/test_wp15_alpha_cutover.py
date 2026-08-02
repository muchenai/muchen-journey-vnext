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
    assert value["production_database"] == "journey_next_restore_20260803"
    assert value["preserved_failed_restore_database"] == "journey_next_production"
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


def test_schema_audit_is_read_only_and_stops_on_nonempty_target():
    if not cutover.SCHEMA_AUDIT.exists():
        pytest.skip("runtime image intentionally excludes production deployment files")
    source = cutover.SCHEMA_AUDIT.read_text()
    assert "default_transaction_read_only=on" in source
    assert "TARGET_DATABASE_NOT_EMPTY" in source
    assert "WP15_PRODUCTION_PUBLIC_SCHEMA_AUDIT=PASS mutation=false" in source
