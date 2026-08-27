from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from journey_api.domain import AssignmentActionState, resolve_current_action
from journey_api.models import AssignmentStatus, EnrollmentStatus
from journey_api.shared_domain import (
    AiUseDisclosure,
    DataClassification,
    EvidenceAuthority,
    EvidenceContract,
    EvidenceVisibility,
    HumanGateContract,
    HumanGateDecision,
    HumanGateKind,
    JourneyModuleKey,
    PersonContract,
    require_formal_result_basis,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "config/human_experience_machine_cases.v1.json"
NAMESPACE = UUID("d329f63a-a96a-4e64-bcc8-a99aed4fcf37")


def payload() -> dict[str, object]:
    return json.loads(CASES.read_text())


def stable_uuid(label: str) -> UUID:
    return uuid5(NAMESPACE, label)


def test_machine_case_denominators_are_exact_and_non_human() -> None:
    cases = payload()
    assert cases["semantics"] == (
        "LOCAL_SYNTHETIC_MACHINE_CASES_ONLY_NOT_HUMAN_UAT_NOT_OWNER_SIGNOFF_NOT_RELEASE"
    )
    modules = cases["modules"]
    projection = cases["authoritative_state_projection"]
    ctas = cases["enabled_primary_ctas"]
    escalation = cases["ai_incentive_escalation"]
    recovery = cases["failure_recovery"]
    assert len(projection["fixture_learner_refs"]) * len(projection["states"]) == projection["expected_case_count"] == 56
    assert len(ctas["viewports"]) * len(ctas["states"]) == ctas["expected_case_count"] == 21
    assert len(modules) * len(escalation["attempt_types"]) == escalation["expected_case_count"] == 28
    assert len(modules) * len(recovery["fault_modes"]) * len(recovery["operations"]) == recovery["expected_case_count"] == 64


@pytest.mark.parametrize("learner_number", range(1, 9))
@pytest.mark.parametrize(
    ("state", "expected_action"),
    [
        ("PENDING_IDENTITY", "CONFIRM_IDENTITY"),
        ("AVAILABLE", "START_OR_CONTINUE_TASK"),
        ("IN_PROGRESS", "START_OR_CONTINUE_TASK"),
        ("SUBMITTED", "WAIT_FOR_REVIEW"),
        ("IN_REVIEW", "WAIT_FOR_REVIEW"),
        ("NEEDS_REVISION", "REVISE_SUBMISSION"),
        ("COMPLETED", "VIEW_RESULT_OR_HANDOFF"),
    ],
)
def test_56_authoritative_state_projections_match_the_page_contract(
    learner_number: int,
    state: str,
    expected_action: str,
) -> None:
    resource_id = stable_uuid(f"machine-learner-{learner_number:02d}:{state}")
    if state == "PENDING_IDENTITY":
        action = resolve_current_action(
            fallback_resource_id=resource_id,
            fallback_revision=1,
            enrollment_status=EnrollmentStatus.PENDING_IDENTITY,
            assignments=(),
        )
    else:
        action = resolve_current_action(
            fallback_resource_id=resource_id,
            fallback_revision=1,
            enrollment_status=EnrollmentStatus.ACTIVE,
            assignments=(
                AssignmentActionState(
                    id=resource_id,
                    status=AssignmentStatus(state),
                    revision=learner_number,
                    position=1,
                ),
            ),
        )
    assert action.action_type == expected_action
    assert action.resource_id == resource_id
    page_source = (ROOT / "apps/web/src/app/app/page.tsx").read_text()
    assert expected_action in page_source or expected_action == "CONFIRM_IDENTITY"
    if expected_action == "CONFIRM_IDENTITY":
        assert "locked" in page_source


ATTEMPT_AUTHORITY = {
    "AI_ADVISORY": EvidenceAuthority.AI_ADVISORY,
    "POINTS": EvidenceAuthority.INCENTIVE_LEDGER,
    "BADGE": EvidenceAuthority.INCENTIVE_LEDGER,
    "STREAK": EvidenceAuthority.INCENTIVE_LEDGER,
    "RANK": EvidenceAuthority.INCENTIVE_LEDGER,
    "SELF_ATTESTATION": EvidenceAuthority.SELF_ATTESTATION,
    "LOW_RISK_COMPLETION": EvidenceAuthority.SELF_ATTESTATION,
}


@pytest.mark.parametrize(
    "module_key",
    [
        JourneyModuleKey.EXPLORATION_CAMP,
        JourneyModuleKey.NEWCOMER_VILLAGE,
        JourneyModuleKey.AI_ACADEMY,
        JourneyModuleKey.DELIVERY_GUILD,
    ],
)
@pytest.mark.parametrize("attempt_type", tuple(ATTEMPT_AUTHORITY))
def test_28_ai_and_incentive_attempts_cannot_create_a_formal_result(
    module_key: JourneyModuleKey,
    attempt_type: str,
) -> None:
    organization_id = stable_uuid(f"org:{module_key.value}")
    person_id = stable_uuid(f"person:{module_key.value}")
    evidence_id = stable_uuid(f"evidence:{module_key.value}:{attempt_type}")
    now = datetime(2026, 8, 27, tzinfo=UTC)
    authority = ATTEMPT_AUTHORITY[attempt_type]
    person = PersonContract(
        organization_id=organization_id,
        person_id=person_id,
    )
    evidence = EvidenceContract(
        evidence_id=evidence_id,
        organization_id=organization_id,
        person_id=person_id,
        module_key=module_key,
        authority=authority,
        authorized_source_ref=f"machine-negative/{attempt_type.lower()}",
        created_by=person_id,
        occurred_at=now,
        revision=1,
        ai_use=AiUseDisclosure(
            used=authority is EvidenceAuthority.AI_ADVISORY,
            purpose="machine negative advisory" if authority is EvidenceAuthority.AI_ADVISORY else None,
            model_version="fixture-v1" if authority is EvidenceAuthority.AI_ADVISORY else None,
            prompt_version="fixture-v1" if authority is EvidenceAuthority.AI_ADVISORY else None,
        ),
        visibility=(EvidenceVisibility.PERSON,),
        data_classification=DataClassification.INTERNAL,
        retention_policy="machine-test-only",
    )
    gate = HumanGateContract(
        gate_id=stable_uuid(f"gate:{module_key.value}:{attempt_type}"),
        organization_id=organization_id,
        person_id=person_id,
        module_key=module_key,
        gate_kind=HumanGateKind.TASK_PASS,
        evidence_ids=(evidence_id,),
        rubric_version="fixture-v1",
        decision=HumanGateDecision.PASS,
        reason="Machine negative case must remain non-formal.",
        signed_by_person_ids=(stable_uuid(f"reviewer:{module_key.value}"),),
        signed_at=now,
    )
    before = (person, evidence, gate)
    with pytest.raises(ValueError, match="practice evidence"):
        require_formal_result_basis(person=person, evidence=(evidence,), gate=gate)
    assert (person, evidence, gate) == before


def test_64_failure_recovery_cases_bind_to_executed_shared_runtime_proofs() -> None:
    cases = payload()
    recovery = cases["failure_recovery"]
    proof_paths = {
        proof.split("::", 1)[0]
        for value in recovery["proof_tests"].values()
        for proof in value.split(";")
    }
    assert all((ROOT / path).is_file() for path in proof_paths)
    assert recovery["minimum_safe_recovery_count"] == 61
    assert recovery["expected_formal_miswrite_count"] == 0
    # Execution of these proof files is required by the HX machine target; this
    # test only freezes the 4×4×4 denominator and prevents silent proof drift.
    makefile = (ROOT / "Makefile").read_text()
    for path in proof_paths:
        if path.startswith("apps/web/scripts/"):
            assert "$(MAKE) web-check" in makefile
        else:
            assert "$(MAKE) api-test" in makefile
