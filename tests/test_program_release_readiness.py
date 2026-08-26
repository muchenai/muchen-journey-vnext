from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from journey_api.program_release_readiness import (
    COMMON_CONTRACT_ROLES,
    HIGH_IMPACT_CONTRACT_ROLES,
    REQUIRED_BUILD_CONTRACTS,
    REQUIRED_COMPONENTS,
    REQUIRED_MODULES,
    REQUIRED_RELEASE_CHECKS,
    BuildContractGate,
    CandidateBinding,
    CandidateSignature,
    CandidateSignatureRole,
    CandidateState,
    ComponentGate,
    ContractRole,
    ContractSignature,
    GateEvidence,
    GateState,
    IndependenceRoster,
    ModuleUATGate,
    OwnerAcceptanceGate,
    ProgramReleaseReadinessInput,
    ReadinessDecision,
    ReleaseApprovalGate,
    ReleaseCheck,
    ReleaseReadinessError,
    ReviewDecision,
    SourceBinding,
    evaluate_release_readiness,
    main,
    verify_source_bindings,
)


NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)
HEAD = "a" * 40
OLD_HEAD = "b" * 40
DIGEST = "c" * 64


def source(label: str, ref: str = "evidence/source.json", digest: str = DIGEST) -> SourceBinding:
    return SourceBinding(label=label, ref=ref, sha256=digest)


def contract_signature(role: str, contract_source: SourceBinding, index: int) -> ContractSignature:
    return ContractSignature(
        signer_ref=f"CONTRACT-{index:03d}",
        role=ContractRole(role),
        decision=ReviewDecision.APPROVE,
        subject_sha256=contract_source.sha256,
        signed_at=NOW,
        evidence=source(f"contract-signature-{index:03d}"),
        attestation_kind="REAL_HUMAN_SIGNATURE",
    )


def candidate_signature(
    role: CandidateSignatureRole,
    actor: str,
    index: int,
) -> CandidateSignature:
    return CandidateSignature(
        signer_ref=actor,
        role=role,
        decision=ReviewDecision.APPROVE,
        candidate_sha=HEAD,
        signed_at=NOW,
        evidence=source(f"candidate-signature-{index:03d}"),
        attestation_kind="REAL_HUMAN_SIGNATURE",
    )


def passing_input() -> ProgramReleaseReadinessInput:
    components = tuple(
        ComponentGate(
            key=key,
            source=source(f"component-{index:02d}"),
            machine=GateState.PASS,
            pro_review=GateState.PASS,
            human_validation=GateState.PASS,
            operationalization=GateState.PASS,
        )
        for index, key in enumerate(REQUIRED_COMPONENTS, 1)
    )
    contracts: list[BuildContractGate] = []
    signature_index = 1
    for contract_id in REQUIRED_BUILD_CONTRACTS:
        contract_source = source(f"contract-{contract_id.lower()}")
        roles = set(COMMON_CONTRACT_ROLES)
        if contract_id == "BC-005":
            roles.update(HIGH_IMPACT_CONTRACT_ROLES)
        signatures = []
        for role in sorted(roles):
            signatures.append(contract_signature(role, contract_source, signature_index))
            signature_index += 1
        contracts.append(
            BuildContractGate(
                contract_id=contract_id,
                source=contract_source,
                state=GateState.PASS,
                signatures=tuple(signatures),
            )
        )
    module_uat = tuple(
        ModuleUATGate(
            module_key=module,
            state=GateState.PASS,
            participant_count=3,
            scenario_count=4,
            passed_scenario_count=4,
            evidence=(source(f"uat-{index:02d}"),),
            signatures=(
                candidate_signature(CandidateSignatureRole.QA_UAT, "QA-001", 100 + index),
            ),
            real_target_people=True,
            synthetic_or_ai_evidence=False,
        )
        for index, module in enumerate(REQUIRED_MODULES, 1)
    )
    return ProgramReleaseReadinessInput(
        schema_version=1,
        contract="muchen-journey-program-release-readiness.v1",
        branch="codex/full-module-development",
        product_source=source("product-contract"),
        candidate=CandidateBinding(
            state=CandidateState.FROZEN,
            branch="codex/full-module-development",
            current_head_sha=HEAD,
            worktree_clean=True,
            frozen_candidate_sha=HEAD,
            wp07_manifest=source("wp07-manifest"),
        ),
        owner_acceptance=OwnerAcceptanceGate(
            appointed_role_count=14,
            accepted_role_count=14,
            source=source("owner-acceptance"),
        ),
        current_golden_path_machine=GateEvidence(
            state=GateState.PASS,
            evidence=(source("golden-path-machine"),),
        ),
        current_golden_path_human=GateEvidence(
            state=GateState.PASS,
            evidence=(source("golden-path-human"),),
            real_human_evidence=True,
        ),
        components=components,
        build_contracts=tuple(contracts),
        module_uat=module_uat,
        historical_real_inventory_audit=GateEvidence(
            state=GateState.PASS,
            evidence=(source("historical-audit"),),
            real_human_evidence=True,
        ),
        historical_data_owner_approval=GateEvidence(
            state=GateState.PASS,
            evidence=(source("data-owner-approval"),),
            real_human_evidence=True,
        ),
        independence_roster=IndependenceRoster(
            candidate_builder_refs=("BUILDER-001",),
            product_owner_refs=("PRODUCT-001",),
            module_owner_refs=("MODULE-001",),
            formal_reviewer_refs=("REVIEWER-001",),
            panel_refs=("PANEL-001",),
            uat_actor_refs=("QA-001",),
            appeal_reviewer_refs=("APPEAL-001",),
            release_owner_refs=("RELEASE-001",),
            independent_release_reviewer_refs=("INDEPENDENT-001",),
        ),
        release_gate_source=source("release-gate"),
        release_checks=tuple(
            ReleaseCheck(key=key, state=GateState.PASS) for key in REQUIRED_RELEASE_CHECKS
        ),
        release_approval=ReleaseApprovalGate(
            state=GateState.PASS,
            signatures=(
                candidate_signature(
                    CandidateSignatureRole.RELEASE_OWNER,
                    "RELEASE-001",
                    201,
                ),
                candidate_signature(
                    CandidateSignatureRole.INDEPENDENT_RELEASE_REVIEWER,
                    "INDEPENDENT-001",
                    202,
                ),
            ),
        ),
        production_data_accessed=False,
        production_mutation_executed=False,
        migration_authorized=False,
        release_execution_authorized=False,
    )


def pending_input() -> ProgramReleaseReadinessInput:
    passing = passing_input().model_dump(mode="json")
    passing["candidate"] = {
        "state": "STALE_RELEASE_MANIFEST",
        "branch": "codex/full-module-development",
        "current_head_sha": HEAD,
        "worktree_clean": False,
        "frozen_candidate_sha": OLD_HEAD,
        "wp07_manifest": source("wp07-manifest").model_dump(),
    }
    passing["owner_acceptance"]["accepted_role_count"] = 6
    passing["current_golden_path_machine"] = {
        "state": "FAIL",
        "evidence": [source("golden-path-machine").model_dump()],
        "real_human_evidence": False,
        "synthetic_or_ai_evidence": False,
    }
    passing["current_golden_path_human"] = {
        "state": "NOT_RUN",
        "evidence": [],
        "real_human_evidence": False,
        "synthetic_or_ai_evidence": False,
    }
    for component in passing["components"]:
        component["pro_review"] = "NOT_RUN"
        component["human_validation"] = "NOT_RUN"
        component["operationalization"] = "NOT_RUN"
    for contract in passing["build_contracts"]:
        contract["state"] = "NOT_RUN"
        contract["signatures"] = []
    for uat in passing["module_uat"]:
        uat.update(
            {
                "state": "NOT_RUN",
                "participant_count": 0,
                "scenario_count": 0,
                "passed_scenario_count": 0,
                "evidence": [],
                "signatures": [],
                "real_target_people": False,
                "synthetic_or_ai_evidence": False,
            }
        )
    passing["historical_real_inventory_audit"] = {
        "state": "NOT_RUN",
        "evidence": [],
        "real_human_evidence": False,
        "synthetic_or_ai_evidence": False,
    }
    passing["historical_data_owner_approval"] = {
        "state": "NOT_RUN",
        "evidence": [],
        "real_human_evidence": False,
        "synthetic_or_ai_evidence": False,
    }
    passing["independence_roster"] = IndependenceRoster().model_dump()
    pending_release_checks = {
        "real_human_uat",
        "real_external_notification",
        "production_preflight",
        "off_host_backup_restore",
        "release_approvals",
        "real_observation_window",
    }
    for check in passing["release_checks"]:
        if check["key"] in pending_release_checks:
            check["state"] = "NOT_RUN"
    passing["release_approval"] = {"state": "NOT_RUN", "signatures": []}
    return ProgramReleaseReadinessInput.model_validate_json(json.dumps(passing))


def test_fully_bound_human_approved_input_still_does_not_authorize_execution():
    report = evaluate_release_readiness(
        passing_input(),
        evaluated_at=NOW,
        source_bindings_verified=True,
    )

    assert report.decision is ReadinessDecision.RELEASE_REVIEW_APPROVED_NO_EXECUTION
    assert report.blocker_codes == ()
    assert report.explicit_release_approval_verified is True
    assert report.release_execution_authorized is False
    assert report.candidate_package_created is False
    assert report.production_mutation_executed is False
    assert report.migration_authorized is False


def test_current_pending_shape_is_no_go_and_pii_free():
    document = pending_input()
    report = evaluate_release_readiness(
        document,
        evaluated_at=NOW,
        source_bindings_verified=True,
    )
    serialized = json.dumps(report.model_dump(mode="json"), sort_keys=True)

    assert report.decision is ReadinessDecision.NO_GO
    assert report.component_machine_pass_count == 5
    assert report.component_pro_review_pass_count == 0
    assert report.contracts_fully_signed_count == 0
    assert report.owner_roles_accepted == 6
    assert report.owner_roles_appointed == 14
    assert report.module_uat_pass_count == 0
    assert report.release_check_pass_count == 11
    assert "CANDIDATE_STALE_RELEASE_MANIFEST" in report.blocker_codes
    assert "WORKTREE_NOT_CLEAN" in report.blocker_codes
    assert "OWNER_ACCEPTANCE_PENDING" in report.blocker_codes
    assert "BC_005_SIGNOFF_NOT_RUN" in report.blocker_codes
    assert "INDEPENDENT_QA_UAT_NOT_APPOINTED" in report.blocker_codes
    assert "INDEPENDENT_APPEAL_REVIEWER_NOT_APPOINTED" in report.blocker_codes
    assert "INDEPENDENT_RELEASE_REVIEWER_NOT_APPOINTED" in report.blocker_codes
    assert report.contains_actor_identifiers is False
    assert "BUILDER-001" not in serialized
    assert "PRODUCT-001" not in serialized


def test_synthetic_or_ai_uat_cannot_be_pass():
    with pytest.raises(ValidationError, match="real target people"):
        ModuleUATGate(
            module_key="exploration-camp",
            state=GateState.PASS,
            participant_count=3,
            scenario_count=1,
            passed_scenario_count=1,
            evidence=(source("fake-uat"),),
            signatures=(candidate_signature(CandidateSignatureRole.QA_UAT, "QA-001", 1),),
            real_target_people=False,
            synthetic_or_ai_evidence=True,
        )


def test_not_run_gate_cannot_carry_completion_evidence():
    with pytest.raises(ValidationError, match="NOT_RUN cannot carry"):
        GateEvidence(state=GateState.NOT_RUN, evidence=(source("fake-pass"),))


def test_human_signature_kind_rejects_ai_or_self_attestation():
    values = candidate_signature(CandidateSignatureRole.QA_UAT, "QA-001", 1).model_dump()
    values["attestation_kind"] = "AI_ATTESTATION"
    with pytest.raises(ValidationError):
        CandidateSignature(**values)


def test_contract_pass_requires_all_roles_and_exact_contract_version():
    document = passing_input().model_dump(mode="json")
    contract = document["build_contracts"][0]
    contract["signatures"] = contract["signatures"][:-1]
    contract["signatures"][0]["subject_sha256"] = "d" * 64
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert "BC_001_SIGNER_ROLES_INCOMPLETE" in report.blocker_codes
    assert "BC_001_SIGNATURE_SUBJECT_MISMATCH" in report.blocker_codes


def test_candidate_signature_must_bind_frozen_revision():
    document = passing_input().model_dump(mode="json")
    document["module_uat"][0]["signatures"][0]["candidate_sha"] = OLD_HEAD
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert "EXPLORATION_CAMP_UAT_CANDIDATE_MISMATCH" in report.blocker_codes


def test_independent_qa_must_not_be_builder_owner_reviewer_or_panel():
    document = passing_input().model_dump(mode="json")
    document["independence_roster"]["uat_actor_refs"] = ["BUILDER-001"]
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert "INDEPENDENT_QA_UAT_NOT_APPOINTED" in report.blocker_codes
    assert "INDEPENDENT_QA_UAT_SIGNATURE_MISSING" in report.blocker_codes


def test_panel_member_cannot_be_independent_appeal_reviewer():
    document = passing_input().model_dump(mode="json")
    document["independence_roster"]["appeal_reviewer_refs"] = ["PANEL-001"]
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert "PANEL_APPEAL_ROLE_CONFLICT" in report.blocker_codes


def test_release_owner_cannot_self_sign_as_independent_reviewer():
    document = passing_input().model_dump(mode="json")
    document["independence_roster"]["independent_release_reviewer_refs"] = ["RELEASE-001"]
    document["release_approval"]["signatures"][1]["signer_ref"] = "RELEASE-001"
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert "INDEPENDENT_RELEASE_REVIEWER_NOT_APPOINTED" in report.blocker_codes
    assert "EXPLICIT_RELEASE_APPROVAL_DUPLICATE_SIGNER" in report.blocker_codes
    assert "INDEPENDENT_RELEASE_SIGNATURE_MISSING" in report.blocker_codes


def test_ready_for_independent_uat_is_distinct_from_no_go():
    document = passing_input().model_dump(mode="json")
    for uat in document["module_uat"]:
        uat.update(
            {
                "state": "NOT_RUN",
                "participant_count": 0,
                "scenario_count": 0,
                "passed_scenario_count": 0,
                "evidence": [],
                "signatures": [],
                "real_target_people": False,
                "synthetic_or_ai_evidence": False,
            }
        )
    for check in document["release_checks"]:
        if check["key"] == "real_human_uat":
            check["state"] = "NOT_RUN"
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert report.decision is ReadinessDecision.READY_FOR_INDEPENDENT_UAT


def test_ready_for_release_decision_is_not_release_approval():
    document = passing_input().model_dump(mode="json")
    document["release_approval"] = {"state": "NOT_RUN", "signatures": []}
    for check in document["release_checks"]:
        if check["key"] == "release_approvals":
            check["state"] = "NOT_RUN"
    parsed = ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))
    report = evaluate_release_readiness(parsed, evaluated_at=NOW, source_bindings_verified=True)

    assert report.decision is ReadinessDecision.READY_FOR_EXPLICIT_RELEASE_DECISION
    assert report.explicit_release_approval_verified is False
    assert report.release_execution_authorized is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("production_data_accessed", True),
        ("production_mutation_executed", True),
        ("migration_authorized", True),
        ("release_execution_authorized", True),
    ],
)
def test_local_readiness_input_cannot_authorize_or_claim_production(field, value):
    document = passing_input().model_dump(mode="json")
    document[field] = value
    with pytest.raises(ValidationError, match="cannot authorize or execute"):
        ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(
    ("field", "item_field"),
    [
        ("components", "key"),
        ("build_contracts", "contract_id"),
        ("module_uat", "module_key"),
        ("release_checks", "key"),
    ],
)
def test_program_scope_must_be_exact(field, item_field):
    document = passing_input().model_dump(mode="json")
    document[field] = document[field][:-1]
    with pytest.raises(ValidationError, match="exact first-release scope"):
        ProgramReleaseReadinessInput.model_validate_json(json.dumps(document))


def write_bound_sources(tmp_path: Path, document: ProgramReleaseReadinessInput) -> ProgramReleaseReadinessInput:
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"safe":true}\n')
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    binding = SourceBinding(label="bound-source", ref="evidence.json", sha256=digest).model_dump()
    values = document.model_dump(mode="json")

    def replace(value):
        if isinstance(value, dict):
            if set(value) == {"label", "ref", "sha256"}:
                return dict(binding)
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        return value

    return ProgramReleaseReadinessInput.model_validate_json(json.dumps(replace(values)))


def test_source_bindings_detect_tampering(tmp_path):
    document = write_bound_sources(tmp_path, passing_input())
    verify_source_bindings(document, repository=tmp_path)
    (tmp_path / "evidence.json").write_text('{"safe":false}\n')

    with pytest.raises(ReleaseReadinessError, match="checksum differs"):
        verify_source_bindings(document, repository=tmp_path)


def test_source_bindings_reject_symbolic_links(tmp_path):
    document = write_bound_sources(tmp_path, passing_input())
    evidence = tmp_path / "evidence.json"
    target = tmp_path / "actual.json"
    evidence.rename(target)
    evidence.symlink_to(target.name)

    with pytest.raises(ReleaseReadinessError, match="symbolic link"):
        verify_source_bindings(document, repository=tmp_path)


def test_source_binding_rejects_path_escape():
    with pytest.raises(ValidationError, match="bounded repository-relative"):
        SourceBinding(label="escape", ref="../secret", sha256=DIGEST)


def test_cli_writes_immutable_pii_free_no_go_report(tmp_path, monkeypatch, capsys):
    document = write_bound_sources(tmp_path, pending_input())
    input_path = tmp_path / "input.json"
    report_path = tmp_path / "report.json"
    input_path.write_text(json.dumps(document.model_dump(mode="json")))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "program_release_readiness",
            "--input",
            "input.json",
            "--repo",
            str(tmp_path),
            "--report",
            "report.json",
            "--evaluated-at",
            "2026-08-24T00:00:00Z",
        ],
    )

    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    report = json.loads(report_path.read_text())
    assert output["decision"] == "NO_GO"
    assert output["candidate_package_created"] is False
    assert output["release_execution_authorized"] is False
    assert report["contains_actor_identifiers"] is False
    assert report["human_validation_inferred"] is False
    assert report["production_mutation_executed"] is False
    assert report_path.stat().st_mode & 0o777 == 0o600

    assert main() == 2
    overwrite = json.loads(capsys.readouterr().out)
    assert overwrite["status"] == "INVALID"
    assert "immutable" in overwrite["error"]
