from __future__ import annotations

import enum
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SharedContractModel(BaseModel):
    """Strict, immutable API contract shared by every Journey module."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class JourneyModuleKey(str, enum.Enum):
    EXPLORATION_CAMP = "exploration-camp"
    NEWCOMER_VILLAGE = "newcomer-village"
    AI_ACADEMY = "ai-academy"
    DELIVERY_GUILD = "delivery-guild"
    CERTIFICATION_ARENA = "certification-arena"
    CAREER_MAP = "career-map"


class PersonContract(SharedContractModel):
    """Read-only cross-map reference to the existing User fact."""

    contract_version: str = Field(default="person.v1", pattern=r"^person\.v1$")
    organization_id: UUID
    person_id: UUID
    source: str = Field(default="users.id", pattern=r"^users\.id$")


class EvidenceAuthority(str, enum.Enum):
    PRACTICE = "PRACTICE"
    HUMAN_EVALUATION = "HUMAN_EVALUATION"
    HUMAN_OBSERVATION = "HUMAN_OBSERVATION"
    SYSTEM_FACT = "SYSTEM_FACT"
    AI_ADVISORY = "AI_ADVISORY"
    SELF_ATTESTATION = "SELF_ATTESTATION"
    INCENTIVE_LEDGER = "INCENTIVE_LEDGER"


class EvidenceVisibility(str, enum.Enum):
    PERSON = "PERSON"
    ASSIGNED_REVIEWERS = "ASSIGNED_REVIEWERS"
    AUTHORIZED_OPERATORS = "AUTHORIZED_OPERATORS"


class DataClassification(str, enum.Enum):
    INTERNAL = "INTERNAL"
    CONFIDENTIAL_PEOPLE = "CONFIDENTIAL_PEOPLE"


class AiUseDisclosure(SharedContractModel):
    used: bool
    purpose: str | None = Field(default=None, min_length=3, max_length=200)
    model_version: str | None = Field(default=None, min_length=1, max_length=200)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=200)
    output_is_advisory_only: bool = True

    @model_validator(mode="after")
    def complete_disclosure(self) -> Self:
        provenance = (self.purpose, self.model_version, self.prompt_version)
        if self.used and any(value is None for value in provenance):
            raise ValueError("AI use requires purpose, model_version and prompt_version")
        if not self.used and any(value is not None for value in provenance):
            raise ValueError("AI provenance is only allowed when used=true")
        if self.used and not self.output_is_advisory_only:
            raise ValueError("AI output must remain advisory only")
        return self


class EvidenceContract(SharedContractModel):
    contract_version: str = Field(default="evidence.v1", pattern=r"^evidence\.v1$")
    evidence_id: UUID
    organization_id: UUID
    person_id: UUID
    module_key: JourneyModuleKey
    authority: EvidenceAuthority
    authorized_source_ref: str = Field(min_length=3, max_length=300)
    task_version_id: UUID | None = None
    assignment_id: UUID | None = None
    submission_version_id: UUID | None = None
    evaluation_id: UUID | None = None
    created_by: UUID
    occurred_at: datetime
    revision: int = Field(ge=1)
    revises_evidence_id: UUID | None = None
    ai_use: AiUseDisclosure
    visibility: tuple[EvidenceVisibility, ...] = Field(min_length=1)
    data_classification: DataClassification
    retention_policy: str = Field(min_length=3, max_length=120)

    @model_validator(mode="after")
    def validate_authority_and_lineage(self) -> Self:
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("visibility entries must be unique")
        if self.revision == 1 and self.revises_evidence_id is not None:
            raise ValueError("first evidence revision cannot revise another record")
        if self.revision > 1 and self.revises_evidence_id is None:
            raise ValueError("later evidence revisions must reference the prior record")
        if self.authority is EvidenceAuthority.PRACTICE:
            practice_refs = (
                self.task_version_id,
                self.assignment_id,
                self.submission_version_id,
            )
            if any(value is None for value in practice_refs):
                raise ValueError(
                    "practice evidence requires task, assignment and submission versions"
                )
        if self.authority is EvidenceAuthority.HUMAN_EVALUATION:
            if self.evaluation_id is None:
                raise ValueError("human evaluation evidence requires evaluation_id")
        elif self.evaluation_id is not None:
            raise ValueError("evaluation_id is reserved for human evaluation evidence")
        if self.authority is EvidenceAuthority.AI_ADVISORY and not self.ai_use.used:
            raise ValueError("AI advisory evidence requires AI provenance")
        return self


class HumanGateKind(str, enum.Enum):
    NEXT_TRAINING_STAGE = "NEXT_TRAINING_STAGE"
    CAPABILITY = "CAPABILITY"
    TASK_PASS = "TASK_PASS"
    CERTIFICATION = "CERTIFICATION"
    HIGH_IMPACT_PEOPLE_RESULT = "HIGH_IMPACT_PEOPLE_RESULT"
    GROWTH_PLAN_CONFIRMATION = "GROWTH_PLAN_CONFIRMATION"


class HumanGateDecision(str, enum.Enum):
    PASS = "PASS"
    NEEDS_REVISION = "NEEDS_REVISION"
    NOT_PASSED = "NOT_PASSED"
    NOT_CONFIRMED = "NOT_CONFIRMED"


class HumanGateContract(SharedContractModel):
    contract_version: str = Field(default="human-gate.v1", pattern=r"^human-gate\.v1$")
    gate_id: UUID
    organization_id: UUID
    person_id: UUID
    module_key: JourneyModuleKey
    gate_kind: HumanGateKind
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    rubric_version: str = Field(min_length=1, max_length=120)
    decision: HumanGateDecision
    reason: str = Field(min_length=10, max_length=2_000)
    signed_by_person_ids: tuple[UUID, ...] = Field(min_length=1)
    signed_at: datetime
    appeal_policy_ref: str | None = Field(default=None, min_length=3, max_length=300)
    appeal_window_ends_at: datetime | None = None
    ai_advisory_evidence_ids: tuple[UUID, ...] = ()
    revision: int = Field(default=1, ge=1)
    supersedes_gate_id: UUID | None = None
    source_appeal_id: UUID | None = None

    @model_validator(mode="after")
    def validate_human_accountability(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("gate evidence_ids must be unique")
        if len(set(self.signed_by_person_ids)) != len(self.signed_by_person_ids):
            raise ValueError("gate signer ids must be unique")
        if self.person_id in self.signed_by_person_ids:
            raise ValueError("a person cannot be the sole authority for their own formal gate")
        if not set(self.ai_advisory_evidence_ids).issubset(self.evidence_ids):
            raise ValueError("AI advisory references must be part of gate evidence")
        if self.gate_kind is HumanGateKind.HIGH_IMPACT_PEOPLE_RESULT:
            if self.appeal_policy_ref is None or self.appeal_window_ends_at is None:
                raise ValueError("high-impact gates require an appeal policy and window")
            if self.appeal_window_ends_at <= self.signed_at:
                raise ValueError("appeal window must end after the gate is signed")
        if self.revision == 1 and (
            self.supersedes_gate_id is not None or self.source_appeal_id is not None
        ):
            raise ValueError("the first Human Gate cannot supersede another Gate")
        if self.revision > 1 and self.supersedes_gate_id is None:
            raise ValueError("later Human Gate revisions must reference the prior Gate")
        if self.source_appeal_id is not None and self.supersedes_gate_id is None:
            raise ValueError("an appeal replacement must preserve prior Gate lineage")
        return self


NON_FORMAL_AUTHORITIES = frozenset(
    {
        EvidenceAuthority.AI_ADVISORY,
        EvidenceAuthority.SELF_ATTESTATION,
        EvidenceAuthority.INCENTIVE_LEDGER,
    }
)


def require_formal_result_basis(
    *,
    person: PersonContract,
    evidence: tuple[EvidenceContract, ...],
    gate: HumanGateContract,
) -> None:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    if set(evidence_by_id) != set(gate.evidence_ids):
        raise ValueError("the complete fixed gate evidence set must be supplied")
    if gate.decision is not HumanGateDecision.PASS:
        raise ValueError("a formal result requires a PASS human gate")
    if gate.person_id != person.person_id or gate.organization_id != person.organization_id:
        raise ValueError("gate and person must share person and organization scope")
    if any(
        item.person_id != person.person_id
        or item.organization_id != person.organization_id
        or item.module_key != gate.module_key
        for item in evidence
    ):
        raise ValueError("evidence cannot cross person, organization or module scope")
    authorities = {item.authority for item in evidence}
    if EvidenceAuthority.PRACTICE not in authorities:
        raise ValueError("a formal result requires practice evidence")
    if EvidenceAuthority.HUMAN_EVALUATION not in authorities:
        raise ValueError("a formal result requires human evaluation evidence")
    if authorities and authorities.issubset(NON_FORMAL_AUTHORITIES):
        raise ValueError("AI, points and self-attestation cannot create a formal result")


class AppealStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    UPHELD = "UPHELD"
    OVERTURNED = "OVERTURNED"
    RETURNED_FOR_REVIEW = "RETURNED_FOR_REVIEW"
    WITHDRAWN = "WITHDRAWN"


RESOLVED_APPEAL_STATUSES = frozenset(
    {
        AppealStatus.UPHELD,
        AppealStatus.OVERTURNED,
        AppealStatus.RETURNED_FOR_REVIEW,
    }
)


class AppealContract(SharedContractModel):
    contract_version: str = Field(default="appeal.v1", pattern=r"^appeal\.v1$")
    appeal_id: UUID
    organization_id: UUID
    person_id: UUID
    gate_id: UUID
    appellant_id: UUID
    reason: str = Field(min_length=10, max_length=2_000)
    submitted_at: datetime
    status: AppealStatus
    original_signer_ids: tuple[UUID, ...] = Field(min_length=1)
    independent_reviewer_ids: tuple[UUID, ...] = ()
    resolution_reason: str | None = Field(default=None, min_length=10, max_length=2_000)
    resolved_at: datetime | None = None
    evidence_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def validate_independent_review(self) -> Self:
        if self.appellant_id != self.person_id:
            raise ValueError("only the Person can submit their own appeal")
        if len(set(self.original_signer_ids)) != len(self.original_signer_ids):
            raise ValueError("original signer ids must be unique")
        if len(set(self.independent_reviewer_ids)) != len(
            self.independent_reviewer_ids
        ):
            raise ValueError("appeal reviewer ids must be unique")
        conflicts = set(self.original_signer_ids) & set(self.independent_reviewer_ids)
        if conflicts:
            raise ValueError("original gate signers cannot review their own appeal")
        if self.person_id in self.independent_reviewer_ids:
            raise ValueError("the Person cannot review their own appeal")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("appeal evidence ids must be unique")
        if self.submitted_at.tzinfo is None:
            raise ValueError("appeal submission requires a timezone-aware timestamp")
        if self.status not in {AppealStatus.SUBMITTED, AppealStatus.WITHDRAWN}:
            if not self.independent_reviewer_ids:
                raise ValueError("an active or resolved appeal requires an independent reviewer")
        if self.status in RESOLVED_APPEAL_STATUSES:
            if self.resolution_reason is None or self.resolved_at is None:
                raise ValueError("resolved appeals require a reason and timestamp")
            if self.resolved_at < self.submitted_at:
                raise ValueError("appeal cannot resolve before submission")
            if self.resolved_at.tzinfo is None:
                raise ValueError("appeal resolution requires a timezone-aware timestamp")
        elif self.resolution_reason is not None or self.resolved_at is not None:
            raise ValueError("unresolved appeals cannot carry resolution fields")
        return self


class GrowthPlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"
    CLOSED = "CLOSED"


class GrowthPlanActionStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    DROPPED = "DROPPED"


class GrowthPlanActionContract(SharedContractModel):
    action_id: UUID
    capability_key: str = Field(
        min_length=3, max_length=120, pattern=r"^[a-z][a-z0-9_-]+$"
    )
    action: str = Field(min_length=10, max_length=1_000)
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    status: GrowthPlanActionStatus
    target_at: datetime | None = None

    @model_validator(mode="after")
    def unique_evidence(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("growth action evidence_ids must be unique")
        return self


class GrowthPlanContract(SharedContractModel):
    contract_version: str = Field(default="growth-plan.v1", pattern=r"^growth-plan\.v1$")
    growth_plan_id: UUID
    organization_id: UUID
    person_id: UUID
    version: int = Field(ge=1)
    status: GrowthPlanStatus
    based_on_evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    based_on_gate_ids: tuple[UUID, ...] = Field(min_length=1)
    actions: tuple[GrowthPlanActionContract, ...] = Field(min_length=1)
    created_by: UUID
    created_at: datetime
    confirmed_by_person_at: datetime | None = None
    confirmation_gate_id: UUID | None = None
    supersedes_growth_plan_id: UUID | None = None
    ai_use: AiUseDisclosure

    @model_validator(mode="after")
    def validate_version_and_confirmation(self) -> Self:
        if len(set(self.based_on_evidence_ids)) != len(self.based_on_evidence_ids):
            raise ValueError("growth plan evidence ids must be unique")
        if len(set(self.based_on_gate_ids)) != len(self.based_on_gate_ids):
            raise ValueError("growth plan gate ids must be unique")
        action_ids = [item.action_id for item in self.actions]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("growth plan action ids must be unique")
        confirmation_values = (
            self.confirmed_by_person_at,
            self.confirmation_gate_id,
        )
        if any(value is None for value in confirmation_values) and any(
            value is not None for value in confirmation_values
        ):
            raise ValueError(
                "growth plan person and human Gate confirmations must stay together"
            )
        if self.status is GrowthPlanStatus.CONFIRMED and any(
            value is None for value in confirmation_values
        ):
            raise ValueError(
                "confirmed growth plans require person confirmation and human Gate confirmation"
            )
        if self.status is GrowthPlanStatus.DRAFT and any(
            value is not None for value in confirmation_values
        ):
            raise ValueError("draft growth plans cannot carry confirmation")
        if (
            self.confirmed_by_person_at is not None
            and self.confirmed_by_person_at < self.created_at
        ):
            raise ValueError("growth plan cannot be confirmed before creation")
        if (
            self.confirmation_gate_id is not None
            and self.confirmation_gate_id not in self.based_on_gate_ids
        ):
            raise ValueError("growth plan confirmation Gate must be part of its basis")
        if self.version == 1 and self.supersedes_growth_plan_id is not None:
            raise ValueError("the first growth plan cannot supersede another plan")
        if self.version > 1 and self.supersedes_growth_plan_id is None:
            raise ValueError("later growth plan versions must reference the prior plan")
        return self


class SharedDomainRole(str, enum.Enum):
    PERSON = "PERSON"
    REVIEWER = "REVIEWER"
    PANELIST = "PANELIST"
    APPEAL_REVIEWER = "APPEAL_REVIEWER"
    COACH = "COACH"
    OPERATOR = "OPERATOR"
    PROGRAM_CONTROLLER = "PROGRAM_CONTROLLER"


class SharedDomainAction(str, enum.Enum):
    READ_PERSON = "READ_PERSON"
    READ_EVIDENCE = "READ_EVIDENCE"
    SIGN_HUMAN_GATE = "SIGN_HUMAN_GATE"
    SUBMIT_APPEAL = "SUBMIT_APPEAL"
    RESOLVE_APPEAL = "RESOLVE_APPEAL"
    DRAFT_GROWTH_PLAN = "DRAFT_GROWTH_PLAN"
    SIGN_GROWTH_PLAN_GATE = "SIGN_GROWTH_PLAN_GATE"
    CONFIRM_GROWTH_PLAN = "CONFIRM_GROWTH_PLAN"


def require_shared_domain_permission(
    *,
    action: SharedDomainAction,
    actor_id: UUID,
    actor_roles: frozenset[SharedDomainRole],
    person_id: UUID,
    assigned_reviewer_ids: frozenset[UUID] = frozenset(),
    original_gate_signer_ids: frozenset[UUID] = frozenset(),
) -> None:
    is_person = actor_id == person_id and SharedDomainRole.PERSON in actor_roles
    is_assigned_reviewer = (
        actor_id in assigned_reviewer_ids
        and bool(
            actor_roles
            & {
                SharedDomainRole.REVIEWER,
                SharedDomainRole.PANELIST,
                SharedDomainRole.APPEAL_REVIEWER,
            }
        )
    )
    allowed = {
        SharedDomainAction.READ_PERSON: is_person
        or SharedDomainRole.PROGRAM_CONTROLLER in actor_roles,
        SharedDomainAction.READ_EVIDENCE: is_person
        or is_assigned_reviewer
        or SharedDomainRole.PROGRAM_CONTROLLER in actor_roles,
        SharedDomainAction.SIGN_HUMAN_GATE: is_assigned_reviewer
        and actor_id != person_id,
        SharedDomainAction.SUBMIT_APPEAL: is_person,
        SharedDomainAction.RESOLVE_APPEAL: is_assigned_reviewer
        and SharedDomainRole.APPEAL_REVIEWER in actor_roles
        and actor_id not in original_gate_signer_ids,
        SharedDomainAction.DRAFT_GROWTH_PLAN: is_person
        or SharedDomainRole.COACH in actor_roles,
        SharedDomainAction.SIGN_GROWTH_PLAN_GATE: actor_id != person_id
        and actor_id in assigned_reviewer_ids
        and SharedDomainRole.COACH in actor_roles,
        SharedDomainAction.CONFIRM_GROWTH_PLAN: is_person,
    }[action]
    if not allowed:
        raise PermissionError(f"actor is not allowed to {action}")
