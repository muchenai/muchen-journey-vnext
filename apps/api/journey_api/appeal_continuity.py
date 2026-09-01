from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Self

from pydantic import Field, model_validator

from journey_api.controlled_task_authorization import (
    ControlledTaskAuthorizationContract,
    MODULE_BUILD_CONTRACTS,
    TaskAuthorizationStatus,
)
from journey_api.module_execution_package import (
    ModuleExecutionPackageContract,
    ModulePackageStatus,
)
from journey_api.shared_domain import (
    AiUseDisclosure,
    AppealContract,
    AppealStatus,
    DataClassification,
    EvidenceAuthority,
    EvidenceContract,
    EvidenceVisibility,
    GrowthPlanContract,
    HumanGateContract,
    HumanGateDecision,
    HumanGateKind,
    JourneyModuleKey,
    PersonContract,
    SharedContractModel,
    SharedDomainAction,
    SharedDomainRole,
    require_formal_result_basis,
    require_shared_domain_permission,
)


APPEAL_NAMESPACE = uuid.UUID("90650f74-dfd5-423c-9479-c9fa41bb87b3")


class AppealPolicyStatus(str, enum.Enum):
    PENDING_OWNER_APPROVAL = "PENDING_OWNER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AppealPolicyRole(str, enum.Enum):
    MODULE_BUSINESS_OWNER = "MODULE_BUSINESS_OWNER"
    DATA_SECURITY_OWNER = "DATA_SECURITY_OWNER"
    APPEAL_REVIEWER_OWNER = "APPEAL_REVIEWER_OWNER"


class AppealPolicyDecision(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class GrowthPlanAppealImpactStatus(str, enum.Enum):
    CURRENT = "CURRENT"
    RECONFIRMATION_REQUIRED = "RECONFIRMATION_REQUIRED"


def _json_value(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        _json_value(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _expected_gate_kind(module_key: JourneyModuleKey) -> HumanGateKind:
    if module_key is JourneyModuleKey.NEWCOMER_VILLAGE:
        return HumanGateKind.TASK_PASS
    if module_key in {
        JourneyModuleKey.EXPLORATION_CAMP,
        JourneyModuleKey.AI_ACADEMY,
        JourneyModuleKey.DELIVERY_GUILD,
    }:
        return HumanGateKind.CAPABILITY
    raise ValueError("module does not use the shared single-reviewer appeal policy")


class HumanGateAppealPolicyScopeContract(SharedContractModel):
    contract_version: str = Field(
        default="human-gate-appeal-policy-scope.v1",
        pattern=r"^human-gate-appeal-policy-scope\.v1$",
    )
    organization_id: uuid.UUID
    module_key: JourneyModuleKey
    build_contract_ref: str = Field(min_length=3, max_length=300)
    policy_ref: str = Field(min_length=3, max_length=220)
    policy_version: str = Field(min_length=1, max_length=80)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    applicable_gate_kind: HumanGateKind
    task_authorization_id: uuid.UUID
    task_authorization_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    module_package_id: uuid.UUID | None = None
    module_package_scope_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    appeal_window_days: int = Field(ge=1, le=365)
    resolution_sla_business_days: int = Field(ge=1, le=90)
    reviewer_assignment_rule_ref: str = Field(min_length=3, max_length=300)
    correction_evidence_rule_ref: str = Field(min_length=3, max_length=300)
    visibility: tuple[EvidenceVisibility, ...] = Field(min_length=1)
    data_classification: DataClassification
    retention_policy: str = Field(min_length=3, max_length=120)
    human_reviewer_required: bool = True
    original_signer_review_allowed: bool = False
    automatic_talent_status_change_allowed: bool = False
    production_action_executed: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_policy_scope(self) -> Self:
        expected_contract = MODULE_BUILD_CONTRACTS.get(self.module_key)
        if expected_contract is None:
            raise ValueError("module does not use the shared appeal policy")
        if self.build_contract_ref != expected_contract:
            raise ValueError("appeal policy and Build Contract binding do not match")
        if self.applicable_gate_kind is not _expected_gate_kind(self.module_key):
            raise ValueError("appeal policy and Human Gate kind do not match")
        package_values = (
            self.module_package_id,
            self.module_package_scope_sha256,
        )
        package_required = self.module_key in {
            JourneyModuleKey.AI_ACADEMY,
            JourneyModuleKey.DELIVERY_GUILD,
        }
        if package_required and any(value is None for value in package_values):
            raise ValueError("AI Academy and Guild appeal policy requires module package binding")
        if not package_required and any(value is not None for value in package_values):
            raise ValueError("module package binding is not applicable to this appeal policy")
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("appeal policy visibility entries must be unique")
        if not {
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        }.issubset(self.visibility):
            raise ValueError("appeal evidence must remain visible to Person and Reviewers")
        if (
            not self.human_reviewer_required
            or self.original_signer_review_allowed
            or self.automatic_talent_status_change_allowed
        ):
            raise ValueError("appeal policy must preserve independent human accountability")
        if self.production_action_executed:
            raise ValueError("appeal policy cannot execute production work")
        if self.created_at.tzinfo is None:
            raise ValueError("appeal policy scope requires a timezone-aware timestamp")
        return self

    def subject_sha256(self) -> str:
        return _sha256(self.model_dump(mode="python"))


class AppealPolicySignatureContract(SharedContractModel):
    signer_person_id: uuid.UUID
    role: AppealPolicyRole
    decision: AppealPolicyDecision
    subject_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_at: datetime
    evidence_ref: str = Field(min_length=3, max_length=300)
    attestation_kind: str = Field(
        default="REAL_HUMAN_SIGNATURE",
        pattern=r"^REAL_HUMAN_SIGNATURE$",
    )

    @model_validator(mode="after")
    def require_human_timestamp(self) -> Self:
        if self.signed_at.tzinfo is None:
            raise ValueError("appeal policy signature requires a timezone-aware timestamp")
        return self


class HumanGateAppealPolicyContract(SharedContractModel):
    contract_version: str = Field(
        default="human-gate-appeal-policy.v1",
        pattern=r"^human-gate-appeal-policy\.v1$",
    )
    policy_id: uuid.UUID
    scope: HumanGateAppealPolicyScopeContract
    status: AppealPolicyStatus
    signatures: tuple[AppealPolicySignatureContract, ...] = ()
    decided_at: datetime | None = None
    production_action_executed: bool = False

    @model_validator(mode="after")
    def validate_policy_decision(self) -> Self:
        if self.production_action_executed:
            raise ValueError("appeal policy cannot execute production work")
        subject_sha256 = self.scope.subject_sha256()
        roles = [signature.role for signature in self.signatures]
        if len(set(roles)) != len(roles):
            raise ValueError("appeal policy roles must be signed at most once")
        if any(signature.subject_sha256 != subject_sha256 for signature in self.signatures):
            raise ValueError("appeal policy signatures must bind the exact scope digest")
        if any(signature.signed_at < self.scope.created_at for signature in self.signatures):
            raise ValueError("appeal policy cannot be signed before its scope exists")

        if self.status is AppealPolicyStatus.PENDING_OWNER_APPROVAL:
            if any(
                signature.decision is AppealPolicyDecision.REJECT
                for signature in self.signatures
            ):
                raise ValueError("a rejected signature requires REJECTED status")
            if self.decided_at is not None:
                raise ValueError("pending appeal policy cannot carry a decision timestamp")
            return self

        if self.decided_at is None:
            raise ValueError("final appeal policy requires a decision timestamp")
        if self.decided_at.tzinfo is None:
            raise ValueError("appeal policy decision requires a timezone-aware timestamp")
        if self.signatures and self.decided_at < max(
            signature.signed_at for signature in self.signatures
        ):
            raise ValueError("appeal policy cannot be decided before its signatures")

        if self.status is AppealPolicyStatus.REJECTED:
            if not any(
                signature.decision is AppealPolicyDecision.REJECT
                for signature in self.signatures
            ):
                raise ValueError("rejected appeal policy requires a rejecting human signature")
            return self

        required_roles = set(AppealPolicyRole)
        if set(roles) != required_roles:
            raise ValueError("approved appeal policy is missing required signer roles")
        if any(
            signature.decision is not AppealPolicyDecision.APPROVE
            for signature in self.signatures
        ):
            raise ValueError("approved appeal policy requires unanimous approval")
        content = json.dumps(
            _json_value(self.scope.model_dump(mode="python")),
            ensure_ascii=False,
            sort_keys=True,
        ).lower()
        evidence_refs = " ".join(
            signature.evidence_ref.lower() for signature in self.signatures
        )
        if any(
            marker in f"{content} {evidence_refs}"
            for marker in ("synthetic", "test-only", "pending")
        ):
            raise ValueError("approved appeal policy cannot use non-authoritative content")
        return self


def appeal_policy_gate_ref(policy: HumanGateAppealPolicyContract) -> str:
    return (
        f"appeal-policy:{policy.policy_id}:sha256:"
        f"{policy.scope.subject_sha256()}"
    )


def bind_human_gate_appeal_policy(
    *,
    task_authorization: ControlledTaskAuthorizationContract,
    module_package: ModuleExecutionPackageContract | None,
    policy: HumanGateAppealPolicyContract,
) -> AppealPolicyStatus:
    task_scope = task_authorization.scope
    policy_scope = policy.scope
    if (
        policy_scope.organization_id != task_scope.organization_id
        or policy_scope.module_key is not task_scope.module_key
        or policy_scope.build_contract_ref != task_scope.build_contract_ref
        or policy_scope.task_authorization_id != task_authorization.authorization_id
        or policy_scope.task_authorization_scope_sha256 != task_scope.subject_sha256()
    ):
        raise ValueError("appeal policy does not bind the supplied task authorization")
    if (
        policy_scope.visibility != task_scope.visibility
        or policy_scope.data_classification is not task_scope.data_classification
        or policy_scope.retention_policy != task_scope.retention_policy
    ):
        raise ValueError("appeal policy evidence governance differs from task authorization")

    if module_package is None:
        if policy_scope.module_package_id is not None:
            raise ValueError("appeal policy has an unexpected module package binding")
    elif (
        policy_scope.module_package_id != module_package.package_id
        or policy_scope.module_package_scope_sha256
        != module_package.scope.subject_sha256()
        or policy_scope.policy_ref != module_package.scope.appeal_policy.artifact_ref
        or policy_scope.policy_version != module_package.scope.appeal_policy.version
        or policy_scope.policy_sha256 != module_package.scope.appeal_policy.sha256
    ):
        raise ValueError("appeal policy does not bind the supplied module package")

    if policy.status is AppealPolicyStatus.APPROVED:
        if (
            task_authorization.status
            is not TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
        ):
            raise ValueError("approved appeal policy requires an approved controlled task")
        if (
            module_package is not None
            and module_package.status is not ModulePackageStatus.APPROVED
        ):
            raise ValueError("approved appeal policy requires an approved module package")
    return policy.status


class AppealReviewerAssignmentContract(SharedContractModel):
    contract_version: str = Field(
        default="appeal-reviewer-assignment.v1",
        pattern=r"^appeal-reviewer-assignment\.v1$",
    )
    assignment_id: uuid.UUID
    organization_id: uuid.UUID
    person_id: uuid.UUID
    appeal_id: uuid.UUID
    gate_id: uuid.UUID
    policy_id: uuid.UUID
    policy_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_person_ids: tuple[uuid.UUID, ...] = Field(min_length=1)
    assigned_by_person_id: uuid.UUID
    assigned_at: datetime
    evidence_ref: str = Field(min_length=3, max_length=300)
    attestation_kind: str = Field(
        default="REAL_HUMAN_ASSIGNMENT",
        pattern=r"^REAL_HUMAN_ASSIGNMENT$",
    )

    @model_validator(mode="after")
    def validate_assignment(self) -> Self:
        if len(set(self.reviewer_person_ids)) != len(self.reviewer_person_ids):
            raise ValueError("appeal reviewer assignment must not duplicate people")
        if self.person_id in self.reviewer_person_ids:
            raise ValueError("the appellant cannot review their own appeal")
        if self.assigned_by_person_id in self.reviewer_person_ids:
            raise ValueError("Appeal Reviewer Owner cannot assign themselves")
        if self.assigned_at.tzinfo is None:
            raise ValueError("appeal assignment requires a timezone-aware timestamp")
        return self


class ResolvedAppealCaseContract(SharedContractModel):
    appeal: AppealContract
    assignment: AppealReviewerAssignmentContract
    policy: HumanGateAppealPolicyContract

    @model_validator(mode="after")
    def validate_case_links(self) -> Self:
        if (
            self.appeal.appeal_id != self.assignment.appeal_id
            or self.appeal.gate_id != self.assignment.gate_id
            or self.appeal.organization_id != self.assignment.organization_id
            or self.appeal.person_id != self.assignment.person_id
            or self.assignment.policy_id != self.policy.policy_id
            or self.assignment.policy_scope_sha256 != self.policy.scope.subject_sha256()
            or set(self.appeal.independent_reviewer_ids)
            != set(self.assignment.reviewer_person_ids)
        ):
            raise ValueError("resolved appeal case links do not match")
        if self.appeal.status not in {
            AppealStatus.UPHELD,
            AppealStatus.OVERTURNED,
            AppealStatus.RETURNED_FOR_REVIEW,
        }:
            raise ValueError("resolved appeal case requires a final resolution")
        return self


class AppealReplacementGateContract(SharedContractModel):
    original_gate: HumanGateContract
    appeal_case: ResolvedAppealCaseContract
    resolution_evidence: EvidenceContract
    replacement_gate: HumanGateContract

    @model_validator(mode="after")
    def validate_replacement_lineage(self) -> Self:
        if (
            self.replacement_gate.supersedes_gate_id != self.original_gate.gate_id
            or self.replacement_gate.source_appeal_id
            != self.appeal_case.appeal.appeal_id
            or self.resolution_evidence.evidence_id
            not in self.replacement_gate.evidence_ids
        ):
            raise ValueError("replacement Human Gate must preserve appeal lineage")
        return self


class GrowthPlanAppealImpactContract(SharedContractModel):
    growth_plan: GrowthPlanContract
    appeal: AppealContract
    status: GrowthPlanAppealImpactStatus
    affected_evidence_ids: tuple[uuid.UUID, ...]
    affected_gate_ids: tuple[uuid.UUID, ...]
    reason: str = Field(min_length=10, max_length=1_000)

    @model_validator(mode="after")
    def validate_impact(self) -> Self:
        if not self.affected_evidence_ids and not self.affected_gate_ids:
            raise ValueError("Growth Plan appeal impact requires an affected source")
        blocking = self.appeal.status in {
            AppealStatus.SUBMITTED,
            AppealStatus.IN_REVIEW,
            AppealStatus.OVERTURNED,
            AppealStatus.RETURNED_FOR_REVIEW,
        }
        if blocking != (
            self.status is GrowthPlanAppealImpactStatus.RECONFIRMATION_REQUIRED
        ):
            raise ValueError("Growth Plan impact status does not match the appeal")
        return self


def open_human_gate_appeal(
    *,
    gate: HumanGateContract,
    task_authorization: ControlledTaskAuthorizationContract,
    module_package: ModuleExecutionPackageContract | None,
    policy: HumanGateAppealPolicyContract,
    appeal_id: uuid.UUID,
    appellant_id: uuid.UUID,
    reason: str,
    submitted_at: datetime,
    evidence_ids: tuple[uuid.UUID, ...] = (),
) -> AppealContract:
    policy_status = bind_human_gate_appeal_policy(
        task_authorization=task_authorization,
        module_package=module_package,
        policy=policy,
    )
    if policy_status is not AppealPolicyStatus.APPROVED:
        raise ValueError("appeal cannot open before policy approval")
    if (
        gate.organization_id != policy.scope.organization_id
        or gate.module_key is not policy.scope.module_key
        or gate.gate_kind is not policy.scope.applicable_gate_kind
        or gate.appeal_policy_ref != appeal_policy_gate_ref(policy)
    ):
        raise ValueError("Human Gate does not bind the supplied appeal policy")
    expected_window_end = gate.signed_at + timedelta(
        days=policy.scope.appeal_window_days
    )
    if gate.appeal_window_ends_at != expected_window_end:
        raise ValueError("Human Gate appeal window differs from approved policy")
    if submitted_at < gate.signed_at or submitted_at > expected_window_end:
        raise ValueError("appeal is outside its allowed window")
    require_shared_domain_permission(
        action=SharedDomainAction.SUBMIT_APPEAL,
        actor_id=appellant_id,
        actor_roles=frozenset({SharedDomainRole.PERSON}),
        person_id=gate.person_id,
    )
    return AppealContract(
        appeal_id=appeal_id,
        organization_id=gate.organization_id,
        person_id=gate.person_id,
        gate_id=gate.gate_id,
        appellant_id=appellant_id,
        reason=reason,
        submitted_at=submitted_at,
        status=AppealStatus.SUBMITTED,
        original_signer_ids=gate.signed_by_person_ids,
        evidence_ids=evidence_ids,
    )


def assign_appeal_reviewers(
    *,
    appeal: AppealContract,
    gate: HumanGateContract,
    policy: HumanGateAppealPolicyContract,
    assignment_id: uuid.UUID,
    reviewer_person_ids: tuple[uuid.UUID, ...],
    assigned_by_person_id: uuid.UUID,
    assigned_at: datetime,
    evidence_ref: str,
) -> AppealReviewerAssignmentContract:
    if appeal.status is not AppealStatus.SUBMITTED:
        raise ValueError("only a submitted appeal can receive reviewer assignment")
    if (
        appeal.gate_id != gate.gate_id
        or appeal.organization_id != gate.organization_id
        or appeal.person_id != gate.person_id
        or policy.status is not AppealPolicyStatus.APPROVED
    ):
        raise ValueError("appeal assignment scope does not match Gate and policy")
    if set(reviewer_person_ids) & set(gate.signed_by_person_ids):
        raise ValueError("original Gate signers cannot receive appeal assignment")
    if assigned_at < appeal.submitted_at:
        raise ValueError("appeal cannot be assigned before submission")
    return AppealReviewerAssignmentContract(
        assignment_id=assignment_id,
        organization_id=appeal.organization_id,
        person_id=appeal.person_id,
        appeal_id=appeal.appeal_id,
        gate_id=appeal.gate_id,
        policy_id=policy.policy_id,
        policy_scope_sha256=policy.scope.subject_sha256(),
        reviewer_person_ids=reviewer_person_ids,
        assigned_by_person_id=assigned_by_person_id,
        assigned_at=assigned_at,
        evidence_ref=evidence_ref,
    )


def resolve_human_gate_appeal(
    *,
    appeal: AppealContract,
    assignment: AppealReviewerAssignmentContract,
    policy: HumanGateAppealPolicyContract,
    resolution_status: AppealStatus,
    resolution_reason: str,
    resolved_at: datetime,
) -> ResolvedAppealCaseContract:
    if resolution_status not in {
        AppealStatus.UPHELD,
        AppealStatus.OVERTURNED,
        AppealStatus.RETURNED_FOR_REVIEW,
    }:
        raise ValueError("appeal resolution must be final")
    if (
        appeal.status not in {AppealStatus.SUBMITTED, AppealStatus.IN_REVIEW}
        or appeal.appeal_id != assignment.appeal_id
        or appeal.gate_id != assignment.gate_id
        or assignment.policy_id != policy.policy_id
        or assignment.policy_scope_sha256 != policy.scope.subject_sha256()
    ):
        raise ValueError("appeal resolution does not match its assignment and policy")
    if resolved_at < assignment.assigned_at:
        raise ValueError("appeal cannot resolve before reviewer assignment")
    for reviewer_id in assignment.reviewer_person_ids:
        require_shared_domain_permission(
            action=SharedDomainAction.RESOLVE_APPEAL,
            actor_id=reviewer_id,
            actor_roles=frozenset({SharedDomainRole.APPEAL_REVIEWER}),
            person_id=appeal.person_id,
            assigned_reviewer_ids=frozenset(assignment.reviewer_person_ids),
            original_gate_signer_ids=frozenset(appeal.original_signer_ids),
        )
    resolved_values = appeal.model_dump()
    resolved_values.update(
        {
            "status": resolution_status,
            "independent_reviewer_ids": assignment.reviewer_person_ids,
            "resolution_reason": resolution_reason,
            "resolved_at": resolved_at,
        }
    )
    resolved = AppealContract(**resolved_values)
    return ResolvedAppealCaseContract(
        appeal=resolved,
        assignment=assignment,
        policy=policy,
    )


def create_appeal_replacement_gate(
    *,
    original_gate: HumanGateContract,
    original_evidence: tuple[EvidenceContract, ...],
    appeal_case: ResolvedAppealCaseContract,
    decision: HumanGateDecision,
    reason: str,
    signed_at: datetime,
) -> AppealReplacementGateContract:
    appeal = appeal_case.appeal
    policy = appeal_case.policy
    if appeal.status not in {
        AppealStatus.OVERTURNED,
        AppealStatus.RETURNED_FOR_REVIEW,
    }:
        raise ValueError("only an overturned or returned appeal can replace a Gate")
    if (
        appeal.gate_id != original_gate.gate_id
        or appeal.organization_id != original_gate.organization_id
        or appeal.person_id != original_gate.person_id
        or set(item.evidence_id for item in original_evidence)
        != set(original_gate.evidence_ids)
    ):
        raise ValueError("replacement Gate requires the complete original scope")
    if appeal.resolved_at is None or signed_at < appeal.resolved_at:
        raise ValueError("replacement Gate cannot predate appeal resolution")

    resolution_evidence_id = uuid.uuid5(
        APPEAL_NAMESPACE,
        f"resolution-evidence:{appeal.appeal_id}",
    )
    resolution_evidence = EvidenceContract(
        evidence_id=resolution_evidence_id,
        organization_id=original_gate.organization_id,
        person_id=original_gate.person_id,
        module_key=original_gate.module_key,
        authority=EvidenceAuthority.HUMAN_OBSERVATION,
        authorized_source_ref=f"appeal:{appeal.appeal_id}:resolution",
        created_by=appeal.independent_reviewer_ids[0],
        occurred_at=appeal.resolved_at,
        revision=1,
        ai_use=AiUseDisclosure(used=False),
        visibility=policy.scope.visibility,
        data_classification=policy.scope.data_classification,
        retention_policy=policy.scope.retention_policy,
    )
    replacement_gate_id = uuid.uuid5(
        APPEAL_NAMESPACE,
        f"replacement-gate:{original_gate.gate_id}:{appeal.appeal_id}",
    )
    replacement_evidence = (*original_evidence, resolution_evidence)
    replacement_gate = HumanGateContract(
        gate_id=replacement_gate_id,
        organization_id=original_gate.organization_id,
        person_id=original_gate.person_id,
        module_key=original_gate.module_key,
        gate_kind=original_gate.gate_kind,
        evidence_ids=tuple(item.evidence_id for item in replacement_evidence),
        rubric_version=original_gate.rubric_version,
        decision=decision,
        reason=reason,
        signed_by_person_ids=appeal.independent_reviewer_ids,
        signed_at=signed_at,
        appeal_policy_ref=appeal_policy_gate_ref(policy),
        appeal_window_ends_at=signed_at
        + timedelta(days=policy.scope.appeal_window_days),
        revision=original_gate.revision + 1,
        supersedes_gate_id=original_gate.gate_id,
        source_appeal_id=appeal.appeal_id,
    )
    if decision is HumanGateDecision.PASS:
        require_formal_result_basis(
            person=PersonContract(
                organization_id=original_gate.organization_id,
                person_id=original_gate.person_id,
            ),
            evidence=replacement_evidence,
            gate=replacement_gate,
        )
    return AppealReplacementGateContract(
        original_gate=original_gate,
        appeal_case=appeal_case,
        resolution_evidence=resolution_evidence,
        replacement_gate=replacement_gate,
    )


def assess_growth_plan_appeal_impact(
    *,
    growth_plan: GrowthPlanContract,
    appeal: AppealContract,
) -> GrowthPlanAppealImpactContract:
    affected_gate_ids = tuple(
        gate_id for gate_id in growth_plan.based_on_gate_ids if gate_id == appeal.gate_id
    )
    affected_evidence_ids = tuple(
        evidence_id
        for evidence_id in growth_plan.based_on_evidence_ids
        if evidence_id in appeal.evidence_ids
    )
    if not affected_gate_ids and not affected_evidence_ids:
        raise ValueError("appeal does not affect this Growth Plan")
    blocking = appeal.status in {
        AppealStatus.SUBMITTED,
        AppealStatus.IN_REVIEW,
        AppealStatus.OVERTURNED,
        AppealStatus.RETURNED_FOR_REVIEW,
    }
    status = (
        GrowthPlanAppealImpactStatus.RECONFIRMATION_REQUIRED
        if blocking
        else GrowthPlanAppealImpactStatus.CURRENT
    )
    return GrowthPlanAppealImpactContract(
        growth_plan=growth_plan,
        appeal=appeal,
        status=status,
        affected_evidence_ids=affected_evidence_ids,
        affected_gate_ids=affected_gate_ids,
        reason=(
            "Growth Plan source is disputed and requires a new confirmed version."
            if blocking
            else "Independent appeal review left the Growth Plan source effective."
        ),
    )
