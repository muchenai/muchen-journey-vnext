from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "outputs/controller-integration/human-experience-v1.0/requirement-gap-matrix.v1.json"
ORDER = ROOT / "outputs/controller-integration/human-experience-v1.0/p0-implementation-order.v1.json"
REGRESSION = ROOT / "outputs/controller-integration/human-experience-v1.0/regression-matrix.v1.json"
MACHINE_CASES = ROOT / "config/human_experience_machine_cases.v1.json"
UAT_PLAN = ROOT / "docs/uat/HX_V1.0_REAL_HUMAN_UAT_PLAN.md"
OWNER_PACKAGE = ROOT / "docs/uat/HX_V1.0_OWNER_REVIEW_PACKAGE.md"
CONTRACT = ROOT / "docs/baselines/build-contracts/01A_Shared_Human_Experience_Layer_Contract_V1.0.md"
EXPECTED_SHA = "ff5190c472556440730d489cda707d1c6b4e23c1ce1fa29ceb14795e7c3b4f08"


def expected_ids() -> list[str]:
    groups = [
        ("HX-PAGE", 22),
        ("HX-LEARN", 13),
        ("HX-BAN", 15),
        ("HX-GATE", 4),
        ("HX-METRIC", 10),
        ("HX-IMPL", 6),
        ("HX-RESIGN", 9),
    ]
    return [f"{prefix}-{number:03d}" for prefix, total in groups for number in range(1, total + 1)]


def test_hx_contract_copy_is_exactly_pinned() -> None:
    assert hashlib.sha256(CONTRACT.read_bytes()).hexdigest() == EXPECTED_SHA


def test_all_hx_requirements_are_unique_continuous_and_classified() -> None:
    payload = json.loads(MATRIX.read_text())
    rows = payload["requirements"]
    ids = [row["id"] for row in rows]
    assert len(rows) == payload["requirement_count"] == 79
    assert len(ids) == len(set(ids))
    assert set(ids) == set(expected_ids())
    assert set(payload["status_counts"]) <= set(payload["allowed_statuses"])
    assert sum(payload["status_counts"].values()) == 79
    for row in rows:
        assert row["status"] in payload["allowed_statuses"]
        assert row["audit_finding"].strip()
        assert row["trace_paths"]
        for relative in row["trace_paths"]:
            assert (ROOT / relative).exists(), f"{row['id']} missing audit path: {relative}"


def test_machine_matrix_does_not_claim_human_or_release_facts() -> None:
    payload = json.loads(MATRIX.read_text())
    semantics = payload["audit_semantics"].lower()
    assert "not owner signoff" in semantics
    assert "human uat" in semantics
    assert "release" in semantics
    human_ids = {"HX-GATE-002", "HX-METRIC-001", "HX-METRIC-002", "HX-METRIC-003", "HX-METRIC-007", "HX-METRIC-009", "HX-METRIC-010"}
    by_id = {row["id"]: row for row in payload["requirements"]}
    assert all(by_id[item]["status"] == "GATED" for item in human_ids)


def test_p0_order_and_regression_matrix_are_complete_before_runtime_changes() -> None:
    order = json.loads(ORDER.read_text())
    assert [item["phase"] for item in order["phases"]] == [
        f"HX-IMPL-{number:03d}" for number in range(1, 7)
    ]
    assert [item["order"] for item in order["phases"]] == list(range(1, 7))
    assert all(item["depends_on"] and item["stop_if"] for item in order["phases"])

    regression = json.loads(REGRESSION.read_text())
    suites = regression["suites"]
    assert [item["id"] for item in suites] == [
        f"HX-REG-{number:03d}" for number in range(1, 11)
    ]
    assert all(item["command"] and item["expected"] for item in suites)


def test_human_plans_remain_not_run_and_machine_cases_deny_release_inference() -> None:
    cases = json.loads(MACHINE_CASES.read_text())
    assert "NOT_HUMAN_UAT" in cases["semantics"]
    assert "NOT_OWNER_SIGNOFF" in cases["semantics"]
    assert "NOT_RELEASE" in cases["semantics"]
    uat = UAT_PLAN.read_text()
    owner = OWNER_PACKAGE.read_text()
    assert uat.count("`NOT_RUN`") >= 20
    for fact in ("真人 UAT：`NOT_RUN`", "Owner 签署：`NOT_RUN`", "Canary：`NOT_RUN`", "Release：`NOT_AUTHORIZED`"):
        assert fact in owner
