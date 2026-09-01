"""Fail-closed program release-readiness contract for Muchen Journey.

This module can validate a local, PII-free release review package.  It cannot
create a WP-07 candidate, record a human action, approve a release, connect to
an environment, or execute any production mutation.
"""

from __future__ import annotations

import argparse
import enum
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SHA256 = re.compile(r"^[0-9a-f]{64}$")
FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
OPAQUE_ACTOR_REF = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")
BOUNDED_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")

REQUIRED_COMPONENTS = (
    "g1-shared-people-domain",
    "g2-exploration-newcomer-loop",
    "g3-ai-guild-certification-loop",
    "g4-career-map-growth-plan-loop",
    "g5-historical-data-rehearsal",
)
REQUIRED_BUILD_CONTRACTS = (
    "BC-001",
    "BC-002",
    "BC-003",
    "BC-004",
    "BC-005",
    "BC-006",
)
REQUIRED_MODULES = (
    "exploration-camp",
    "newcomer-village",
    "ai-academy",
    "delivery-guild",
    "certification-arena",
    "career-map",
)
REQUIRED_RELEASE_CHECKS = (
    "local_automated_suite",
    "empty_database_migration",
    "persistent_database_migration_rollback",
    "compose_health",
    "http_permission_negative",
    "browser_three_viewports",
    "dependency_security_audits",
    "local_backup_isolated_restore",
    "local_alert_and_rollback_drills",
    "real_human_uat",
    "real_external_notification",
    "staging_validation",
    "production_preflight",
    "physical_acl_validation",
    "off_host_backup_restore",
    "release_approvals",
    "real_observation_window",
)
COMMON_CONTRACT_ROLES = {
    "PRODUCT_OWNER",
    "MODULE_OWNER",
    "TECH_LEAD",
    "DATA_OWNER",
    "SECURITY_PRIVACY",
    "QA_UAT",
}
HIGH_IMPACT_CONTRACT_ROLES = {
    "REVIEWER_PANEL_OWNER",
    "INDEPENDENT_APPEAL_OWNER",
}


class ReleaseReadinessError(RuntimeError):
    """A readiness package is unsafe, malformed, or not source-bound."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GateState(str, enum.Enum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class CandidateState(str, enum.Enum):
    DEVELOPMENT_WORKTREE = "DEVELOPMENT_WORKTREE"
    STALE_RELEASE_MANIFEST = "STALE_RELEASE_MANIFEST"
    FROZEN = "FROZEN"


class ReviewDecision(str, enum.Enum):
    APPROVE = "APPROVE"
    REVISE = "REVISE"
    REJECT = "REJECT"


class ContractRole(str, enum.Enum):
    PRODUCT_OWNER = "PRODUCT_OWNER"
    MODULE_OWNER = "MODULE_OWNER"
    TECH_LEAD = "TECH_LEAD"
    DATA_OWNER = "DATA_OWNER"
    SECURITY_PRIVACY = "SECURITY_PRIVACY"
    QA_UAT = "QA_UAT"
    REVIEWER_PANEL_OWNER = "REVIEWER_PANEL_OWNER"
    INDEPENDENT_APPEAL_OWNER = "INDEPENDENT_APPEAL_OWNER"


class CandidateSignatureRole(str, enum.Enum):
    QA_UAT = "QA_UAT"
    PRODUCT_OWNER = "PRODUCT_OWNER"
    RELEASE_OWNER = "RELEASE_OWNER"
    INDEPENDENT_RELEASE_REVIEWER = "INDEPENDENT_RELEASE_REVIEWER"


class ReadinessDecision(str, enum.Enum):
    NO_GO = "NO_GO"
    READY_FOR_INDEPENDENT_UAT = "READY_FOR_INDEPENDENT_UAT"
    READY_FOR_EXPLICIT_RELEASE_DECISION = "READY_FOR_EXPLICIT_RELEASE_DECISION"
    RELEASE_REVIEW_APPROVED_NO_EXECUTION = "RELEASE_REVIEW_APPROVED_NO_EXECUTION"


class SourceBinding(StrictModel):
    label: str = Field(min_length=2, max_length=96, pattern=BOUNDED_KEY.pattern)
    ref: str = Field(min_length=3, max_length=240)
    sha256: str = Field(pattern=SHA256.pattern)

    @field_validator("ref")
    @classmethod
    def bounded_repository_ref(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or value.startswith("./"):
            raise ValueError("source ref must be a bounded repository-relative path")
        return value


class CandidateBinding(StrictModel):
    state: CandidateState
    branch: str = Field(min_length=3, max_length=120)
    current_head_sha: str = Field(pattern=FULL_GIT_SHA.pattern)
    worktree_clean: bool
    frozen_candidate_sha: str | None = None
    wp07_manifest: SourceBinding | None = None

    @field_validator("frozen_candidate_sha")
    @classmethod
    def full_candidate_sha(cls, value: str | None) -> str | None:
        if value is not None and FULL_GIT_SHA.fullmatch(value) is None:
            raise ValueError("frozen candidate must use a full 40-character SHA")
        return value

    @model_validator(mode="after")
    def state_is_truthful(self) -> Self:
        if self.state is CandidateState.FROZEN:
            if not self.worktree_clean:
                raise ValueError("a frozen candidate requires a clean worktree")
            if self.frozen_candidate_sha != self.current_head_sha:
                raise ValueError("a frozen candidate must bind the current HEAD")
            if self.wp07_manifest is None:
                raise ValueError("a frozen candidate requires the WP-07 manifest")
        if self.state is CandidateState.DEVELOPMENT_WORKTREE and self.worktree_clean:
            raise ValueError("a development-worktree candidate must remain dirty")
        if self.state is CandidateState.STALE_RELEASE_MANIFEST:
            if self.wp07_manifest is None or self.frozen_candidate_sha is None:
                raise ValueError("a stale candidate must identify its old WP-07 manifest")
            if self.worktree_clean and self.frozen_candidate_sha == self.current_head_sha:
                raise ValueError("a current clean candidate is not stale")
        return self


class GateEvidence(StrictModel):
    state: GateState
    evidence: tuple[SourceBinding, ...] = ()
    real_human_evidence: bool = False
    synthetic_or_ai_evidence: bool = False

    @model_validator(mode="after")
    def evidence_matches_state(self) -> Self:
        if self.state is GateState.NOT_RUN and self.evidence:
            raise ValueError("NOT_RUN cannot carry completion evidence")
        if self.state is GateState.PASS and not self.evidence:
            raise ValueError("PASS requires source-bound evidence")
        if self.real_human_evidence and self.synthetic_or_ai_evidence:
            raise ValueError("real human evidence cannot also be synthetic or AI evidence")
        return self


class ComponentGate(StrictModel):
    key: str = Field(pattern=BOUNDED_KEY.pattern)
    source: SourceBinding
    machine: GateState
    pro_review: GateState
    human_validation: GateState
    operationalization: GateState


class ContractSignature(StrictModel):
    signer_ref: str = Field(pattern=OPAQUE_ACTOR_REF.pattern)
    role: ContractRole
    decision: ReviewDecision
    subject_sha256: str = Field(pattern=SHA256.pattern)
    signed_at: datetime
    evidence: SourceBinding
    attestation_kind: str = Field(pattern=r"^REAL_HUMAN_SIGNATURE$")

    @field_validator("signed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("signature time must include a timezone")
        return value.astimezone(timezone.utc)


class BuildContractGate(StrictModel):
    contract_id: str = Field(pattern=r"^BC-00[1-6]$")
    source: SourceBinding
    state: GateState
    signatures: tuple[ContractSignature, ...] = ()

    @model_validator(mode="after")
    def pending_has_no_signatures(self) -> Self:
        if self.state is GateState.NOT_RUN and self.signatures:
            raise ValueError("an unsigned contract cannot contain signatures")
        return self


class CandidateSignature(StrictModel):
    signer_ref: str = Field(pattern=OPAQUE_ACTOR_REF.pattern)
    role: CandidateSignatureRole
    decision: ReviewDecision
    candidate_sha: str = Field(pattern=FULL_GIT_SHA.pattern)
    signed_at: datetime
    evidence: SourceBinding
    attestation_kind: str = Field(pattern=r"^REAL_HUMAN_SIGNATURE$")

    @field_validator("signed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("signature time must include a timezone")
        return value.astimezone(timezone.utc)


class ModuleUATGate(StrictModel):
    module_key: str = Field(pattern=BOUNDED_KEY.pattern)
    state: GateState
    participant_count: int = Field(ge=0, le=1000)
    scenario_count: int = Field(ge=0, le=1000)
    passed_scenario_count: int = Field(ge=0, le=1000)
    evidence: tuple[SourceBinding, ...] = ()
    signatures: tuple[CandidateSignature, ...] = ()
    real_target_people: bool = False
    synthetic_or_ai_evidence: bool = False

    @model_validator(mode="after")
    def state_is_truthful(self) -> Self:
        if self.passed_scenario_count > self.scenario_count:
            raise ValueError("passed scenarios cannot exceed total scenarios")
        if self.state is GateState.NOT_RUN:
            if any(
                (
                    self.participant_count,
                    self.scenario_count,
                    self.passed_scenario_count,
                    len(self.evidence),
                    len(self.signatures),
                )
            ):
                raise ValueError("NOT_RUN UAT cannot contain completion facts")
            if self.real_target_people or self.synthetic_or_ai_evidence:
                raise ValueError("NOT_RUN UAT cannot claim an evidence kind")
        if self.state is GateState.PASS:
            if self.participant_count == 0 or self.scenario_count == 0:
                raise ValueError("PASS UAT requires participants and scenarios")
            if self.passed_scenario_count != self.scenario_count:
                raise ValueError("PASS UAT requires every declared scenario to pass")
            if not self.evidence or not self.signatures:
                raise ValueError("PASS UAT requires evidence and human signatures")
            if not self.real_target_people or self.synthetic_or_ai_evidence:
                raise ValueError("PASS UAT requires real target people, never synthetic or AI evidence")
        return self


class OwnerAcceptanceGate(StrictModel):
    appointed_role_count: int = Field(ge=1, le=100)
    accepted_role_count: int = Field(ge=0, le=100)
    source: SourceBinding

    @model_validator(mode="after")
    def accepted_does_not_exceed_appointed(self) -> Self:
        if self.accepted_role_count > self.appointed_role_count:
            raise ValueError("accepted roles cannot exceed appointed roles")
        return self


class IndependenceRoster(StrictModel):
    candidate_builder_refs: tuple[str, ...] = ()
    product_owner_refs: tuple[str, ...] = ()
    module_owner_refs: tuple[str, ...] = ()
    formal_reviewer_refs: tuple[str, ...] = ()
    panel_refs: tuple[str, ...] = ()
    uat_actor_refs: tuple[str, ...] = ()
    appeal_reviewer_refs: tuple[str, ...] = ()
    release_owner_refs: tuple[str, ...] = ()
    independent_release_reviewer_refs: tuple[str, ...] = ()

    @field_validator("*")
    @classmethod
    def opaque_unique_actor_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("actor refs must be unique within each duty set")
        if any(OPAQUE_ACTOR_REF.fullmatch(item) is None for item in value):
            raise ValueError("actor refs must be bounded pseudonymous identifiers")
        return value


class ReleaseCheck(StrictModel):
    key: str = Field(pattern=BOUNDED_KEY.pattern)
    state: GateState


class ReleaseApprovalGate(StrictModel):
    state: GateState
    signatures: tuple[CandidateSignature, ...] = ()

    @model_validator(mode="after")
    def state_is_truthful(self) -> Self:
        if self.state is GateState.NOT_RUN and self.signatures:
            raise ValueError("NOT_RUN release approval cannot contain signatures")
        if self.state is GateState.PASS and len(self.signatures) < 2:
            raise ValueError("PASS release approval requires at least two signatures")
        return self


class ProgramReleaseReadinessInput(StrictModel):
    schema_version: int = Field(ge=1, le=1)
    contract: str = Field(pattern=r"^muchen-journey-program-release-readiness\.v1$")
    branch: str = Field(pattern=r"^codex/full-module-development$")
    product_source: SourceBinding
    candidate: CandidateBinding
    owner_acceptance: OwnerAcceptanceGate
    current_golden_path_machine: GateEvidence
    current_golden_path_human: GateEvidence
    components: tuple[ComponentGate, ...]
    build_contracts: tuple[BuildContractGate, ...]
    module_uat: tuple[ModuleUATGate, ...]
    historical_real_inventory_audit: GateEvidence
    historical_data_owner_approval: GateEvidence
    independence_roster: IndependenceRoster
    release_gate_source: SourceBinding
    release_checks: tuple[ReleaseCheck, ...]
    release_approval: ReleaseApprovalGate
    production_data_accessed: bool
    production_mutation_executed: bool
    migration_authorized: bool
    release_execution_authorized: bool

    @model_validator(mode="after")
    def exact_program_scope_and_no_execution(self) -> Self:
        def exact(values: tuple[str, ...], expected: tuple[str, ...], label: str) -> None:
            if len(values) != len(set(values)) or set(values) != set(expected):
                raise ValueError(f"{label} must contain the exact first-release scope")

        exact(tuple(item.key for item in self.components), REQUIRED_COMPONENTS, "components")
        exact(
            tuple(item.contract_id for item in self.build_contracts),
            REQUIRED_BUILD_CONTRACTS,
            "build contracts",
        )
        exact(tuple(item.module_key for item in self.module_uat), REQUIRED_MODULES, "module UAT")
        exact(tuple(item.key for item in self.release_checks), REQUIRED_RELEASE_CHECKS, "release checks")
        if any(
            (
                self.production_data_accessed,
                self.production_mutation_executed,
                self.migration_authorized,
                self.release_execution_authorized,
            )
        ):
            raise ValueError("a local readiness input cannot authorize or execute production work")
        return self


class ProgramReleaseReadinessReport(StrictModel):
    contract: str
    evaluated_at: datetime
    decision: ReadinessDecision
    blocker_codes: tuple[str, ...]
    blocker_count: int
    component_machine_pass_count: int
    component_pro_review_pass_count: int
    component_operationalization_pass_count: int
    contracts_fully_signed_count: int
    owner_roles_accepted: int
    owner_roles_appointed: int
    module_uat_pass_count: int
    release_check_pass_count: int
    release_check_total: int
    source_bindings_verified: bool
    contains_actor_identifiers: bool
    candidate_package_created: bool
    human_validation_inferred: bool
    explicit_release_approval_verified: bool
    release_execution_authorized: bool
    production_data_accessed: bool
    production_mutation_executed: bool
    migration_authorized: bool


def _source_bindings(document: ProgramReleaseReadinessInput) -> tuple[SourceBinding, ...]:
    sources: list[SourceBinding] = [
        document.product_source,
        document.owner_acceptance.source,
        document.release_gate_source,
    ]
    if document.candidate.wp07_manifest is not None:
        sources.append(document.candidate.wp07_manifest)
    sources.extend(item.source for item in document.components)
    sources.extend(item.source for item in document.build_contracts)
    sources.extend(document.current_golden_path_machine.evidence)
    sources.extend(document.current_golden_path_human.evidence)
    sources.extend(document.historical_real_inventory_audit.evidence)
    sources.extend(document.historical_data_owner_approval.evidence)
    for contract in document.build_contracts:
        sources.extend(signature.evidence for signature in contract.signatures)
    for uat in document.module_uat:
        sources.extend(uat.evidence)
        sources.extend(signature.evidence for signature in uat.signatures)
    sources.extend(signature.evidence for signature in document.release_approval.signatures)
    return tuple(sources)


def verify_source_bindings(
    document: ProgramReleaseReadinessInput,
    *,
    repository: Path,
) -> None:
    root = repository.resolve()
    for source in _source_bindings(document):
        unresolved = root / source.ref
        component = root
        for part in Path(source.ref).parts:
            component = component / part
            if component.is_symlink():
                raise ReleaseReadinessError(
                    f"source path contains a symbolic link: {source.label}"
                )
        path = unresolved.resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ReleaseReadinessError(f"source escapes repository: {source.label}") from error
        if not path.is_file() or path.is_symlink():
            raise ReleaseReadinessError(f"source is not a regular repository file: {source.label}")
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ReleaseReadinessError(f"source exceeds the 10 MiB review limit: {source.label}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != source.sha256:
            raise ReleaseReadinessError(f"source checksum differs: {source.label}")


def _required_contract_roles(contract_id: str) -> set[str]:
    roles = set(COMMON_CONTRACT_ROLES)
    if contract_id == "BC-005":
        roles.update(HIGH_IMPACT_CONTRACT_ROLES)
    return roles


def _contract_blockers(contract: BuildContractGate) -> list[str]:
    prefix = contract.contract_id.replace("-", "_")
    if contract.state is not GateState.PASS:
        return [f"{prefix}_SIGNOFF_{contract.state.value}"]
    blockers: list[str] = []
    roles = [signature.role.value for signature in contract.signatures]
    if len(roles) != len(set(roles)):
        blockers.append(f"{prefix}_DUPLICATE_SIGNER_ROLE")
    if set(roles) != _required_contract_roles(contract.contract_id):
        blockers.append(f"{prefix}_SIGNER_ROLES_INCOMPLETE")
    if any(signature.decision is not ReviewDecision.APPROVE for signature in contract.signatures):
        blockers.append(f"{prefix}_NOT_ALL_APPROVED")
    if any(signature.subject_sha256 != contract.source.sha256 for signature in contract.signatures):
        blockers.append(f"{prefix}_SIGNATURE_SUBJECT_MISMATCH")
    return blockers


def _candidate_signature_blockers(
    signatures: tuple[CandidateSignature, ...],
    *,
    candidate_sha: str | None,
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    actors = [item.signer_ref for item in signatures]
    if len(actors) != len(set(actors)):
        blockers.append(f"{prefix}_DUPLICATE_SIGNER")
    if candidate_sha is None or any(item.candidate_sha != candidate_sha for item in signatures):
        blockers.append(f"{prefix}_CANDIDATE_MISMATCH")
    if any(item.decision is not ReviewDecision.APPROVE for item in signatures):
        blockers.append(f"{prefix}_NOT_ALL_APPROVED")
    return blockers


def evaluate_release_readiness(
    document: ProgramReleaseReadinessInput,
    *,
    evaluated_at: datetime,
    source_bindings_verified: bool,
) -> ProgramReleaseReadinessReport:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ReleaseReadinessError("evaluated_at must include a timezone")
    blockers: list[str] = []
    candidate_sha = document.candidate.frozen_candidate_sha

    if document.candidate.state is not CandidateState.FROZEN:
        blockers.append(f"CANDIDATE_{document.candidate.state.value}")
    if not document.candidate.worktree_clean:
        blockers.append("WORKTREE_NOT_CLEAN")
    if candidate_sha != document.candidate.current_head_sha:
        blockers.append("CANDIDATE_REVISION_MISMATCH")

    for label, gate in (
        ("CURRENT_GOLDEN_PATH_MACHINE", document.current_golden_path_machine),
        ("CURRENT_GOLDEN_PATH_HUMAN", document.current_golden_path_human),
        ("HISTORICAL_REAL_INVENTORY_AUDIT", document.historical_real_inventory_audit),
        ("HISTORICAL_DATA_OWNER_APPROVAL", document.historical_data_owner_approval),
    ):
        if gate.state is not GateState.PASS:
            blockers.append(f"{label}_{gate.state.value}")
    if document.current_golden_path_human.state is GateState.PASS and not document.current_golden_path_human.real_human_evidence:
        blockers.append("CURRENT_GOLDEN_PATH_HUMAN_NOT_REAL")

    if document.owner_acceptance.accepted_role_count != document.owner_acceptance.appointed_role_count:
        blockers.append("OWNER_ACCEPTANCE_PENDING")

    for component in document.components:
        prefix = component.key.upper().replace("-", "_")
        for label, state in (
            ("MACHINE", component.machine),
            ("PRO_REVIEW", component.pro_review),
            ("HUMAN_VALIDATION", component.human_validation),
            ("OPERATIONALIZATION", component.operationalization),
        ):
            if state is not GateState.PASS:
                blockers.append(f"{prefix}_{label}_{state.value}")

    for contract in document.build_contracts:
        blockers.extend(_contract_blockers(contract))

    uat_signature_roles: set[str] = set()
    for uat in document.module_uat:
        prefix = uat.module_key.upper().replace("-", "_")
        if uat.state is not GateState.PASS:
            blockers.append(f"{prefix}_UAT_{uat.state.value}")
            continue
        roles = {signature.role.value for signature in uat.signatures}
        if CandidateSignatureRole.QA_UAT.value not in roles:
            blockers.append(f"{prefix}_UAT_QA_SIGNATURE_MISSING")
        blockers.extend(
            _candidate_signature_blockers(
                uat.signatures,
                candidate_sha=candidate_sha,
                prefix=f"{prefix}_UAT",
            )
        )
        uat_signature_roles.update(signature.signer_ref for signature in uat.signatures)

    roster = document.independence_roster
    uat_conflicts = (
        set(roster.candidate_builder_refs)
        | set(roster.module_owner_refs)
        | set(roster.formal_reviewer_refs)
        | set(roster.panel_refs)
    )
    independent_uat = set(roster.uat_actor_refs) - uat_conflicts
    if not independent_uat:
        blockers.append("INDEPENDENT_QA_UAT_NOT_APPOINTED")
    if uat_signature_roles and not independent_uat.intersection(uat_signature_roles):
        blockers.append("INDEPENDENT_QA_UAT_SIGNATURE_MISSING")

    if not roster.appeal_reviewer_refs:
        blockers.append("INDEPENDENT_APPEAL_REVIEWER_NOT_APPOINTED")
    elif set(roster.appeal_reviewer_refs) & set(roster.panel_refs):
        blockers.append("PANEL_APPEAL_ROLE_CONFLICT")

    for check in document.release_checks:
        if check.state is not GateState.PASS:
            blockers.append(f"RELEASE_CHECK_{check.key.upper()}_{check.state.value}")

    if document.release_approval.state is not GateState.PASS:
        blockers.append(f"EXPLICIT_RELEASE_APPROVAL_{document.release_approval.state.value}")
    else:
        roles = {item.role.value for item in document.release_approval.signatures}
        required = {
            CandidateSignatureRole.RELEASE_OWNER.value,
            CandidateSignatureRole.INDEPENDENT_RELEASE_REVIEWER.value,
        }
        if roles != required:
            blockers.append("EXPLICIT_RELEASE_APPROVAL_ROLES_INCOMPLETE")
        blockers.extend(
            _candidate_signature_blockers(
                document.release_approval.signatures,
                candidate_sha=candidate_sha,
                prefix="EXPLICIT_RELEASE_APPROVAL",
            )
        )

    independent_release = set(roster.independent_release_reviewer_refs)
    release_conflicts = (
        set(roster.candidate_builder_refs)
        | set(roster.product_owner_refs)
        | set(roster.module_owner_refs)
        | set(roster.release_owner_refs)
    )
    valid_independent_release = independent_release - release_conflicts
    if not valid_independent_release:
        blockers.append("INDEPENDENT_RELEASE_REVIEWER_NOT_APPOINTED")
    if document.release_approval.state is GateState.PASS:
        signed_independent = {
            item.signer_ref
            for item in document.release_approval.signatures
            if item.role is CandidateSignatureRole.INDEPENDENT_RELEASE_REVIEWER
        }
        if not signed_independent.intersection(valid_independent_release):
            blockers.append("INDEPENDENT_RELEASE_SIGNATURE_MISSING")

    blockers = sorted(set(blockers))
    human_blocker_markers = ("_UAT_", "_HUMAN_", "INDEPENDENT_QA_UAT")
    approval_blocker_markers = (
        "EXPLICIT_RELEASE_APPROVAL",
        "INDEPENDENT_RELEASE",
        "RELEASE_CHECK_RELEASE_APPROVALS",
    )
    prehuman = [
        item
        for item in blockers
        if not any(marker in item for marker in (*human_blocker_markers, *approval_blocker_markers))
    ]
    human = [item for item in blockers if any(marker in item for marker in human_blocker_markers)]
    approvals = [item for item in blockers if any(marker in item for marker in approval_blocker_markers)]
    if prehuman:
        decision = ReadinessDecision.NO_GO
    elif human:
        decision = ReadinessDecision.READY_FOR_INDEPENDENT_UAT
    elif approvals:
        decision = ReadinessDecision.READY_FOR_EXPLICIT_RELEASE_DECISION
    else:
        decision = ReadinessDecision.RELEASE_REVIEW_APPROVED_NO_EXECUTION

    return ProgramReleaseReadinessReport(
        contract="muchen-journey-program-release-readiness-report.v1",
        evaluated_at=evaluated_at.astimezone(timezone.utc),
        decision=decision,
        blocker_codes=tuple(blockers),
        blocker_count=len(blockers),
        component_machine_pass_count=sum(item.machine is GateState.PASS for item in document.components),
        component_pro_review_pass_count=sum(item.pro_review is GateState.PASS for item in document.components),
        component_operationalization_pass_count=sum(
            item.operationalization is GateState.PASS for item in document.components
        ),
        contracts_fully_signed_count=sum(item.state is GateState.PASS for item in document.build_contracts),
        owner_roles_accepted=document.owner_acceptance.accepted_role_count,
        owner_roles_appointed=document.owner_acceptance.appointed_role_count,
        module_uat_pass_count=sum(item.state is GateState.PASS for item in document.module_uat),
        release_check_pass_count=sum(item.state is GateState.PASS for item in document.release_checks),
        release_check_total=len(document.release_checks),
        source_bindings_verified=source_bindings_verified,
        contains_actor_identifiers=False,
        candidate_package_created=False,
        human_validation_inferred=False,
        explicit_release_approval_verified=document.release_approval.state is GateState.PASS,
        release_execution_authorized=False,
        production_data_accessed=False,
        production_mutation_executed=False,
        migration_authorized=False,
    )


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _load_input(path: Path) -> ProgramReleaseReadinessInput:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ReleaseReadinessError(f"cannot read readiness input: {error}") from error
    if len(raw) > 2 * 1024 * 1024:
        raise ReleaseReadinessError("readiness input exceeds 2 MiB")
    try:
        return ProgramReleaseReadinessInput.model_validate_json(raw)
    except ValidationError as error:
        raise ReleaseReadinessError(f"readiness input is invalid: {error}") from error


def _write_private(path: Path, report: ProgramReleaseReadinessReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ReleaseReadinessError("report path already exists; evidence is immutable") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(payload + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", required=True)
    parser.add_argument("--evaluated-at", required=True, type=parse_time)
    args = parser.parse_args()
    repository = Path(args.repo).resolve()
    input_path = Path(args.input)
    report_path = Path(args.report)
    if not input_path.is_absolute():
        input_path = repository / input_path
    if not report_path.is_absolute():
        report_path = repository / report_path
    try:
        input_path.resolve().relative_to(repository)
        report_path.resolve().relative_to(repository)
        document = _load_input(input_path)
        verify_source_bindings(document, repository=repository)
        report = evaluate_release_readiness(
            document,
            evaluated_at=args.evaluated_at,
            source_bindings_verified=True,
        )
        _write_private(report_path, report)
    except (ValueError, ReleaseReadinessError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": report.decision.value,
                "blocker_count": report.blocker_count,
                "candidate_package_created": False,
                "release_execution_authorized": False,
                "production_mutation_executed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
