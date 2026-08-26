from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import Field, model_validator

from journey_api.appeal_continuity import AppealReplacementGateContract
from journey_api.models import Handoff, HandoffStatus, Outcome
from journey_api.shared_domain import (
    AppealContract,
    AppealStatus,
    EvidenceContract,
    HumanGateContract,
    HumanGateDecision,
    JourneyModuleKey,
    PersonContract,
    SharedContractModel,
    require_formal_result_basis,
)
from journey_api.shared_domain_projection import ReviewCycleProjection, ReviewCycleStatus


FORMAL_RESULT_NAMESPACE = uuid.UUID("f067549f-111f-43bb-aa86-0af4205b807b")


class FormalResultStatus(str, enum.Enum):
    EFFECTIVE = "EFFECTIVE"
    EFFECTIVE_AFTER_APPEAL = "EFFECTIVE_AFTER_APPEAL"
    DISPUTED = "DISPUTED"
    INVALIDATED_BY_APPEAL = "INVALIDATED_BY_APPEAL"


class ControlledHandoffStatus(str, enum.Enum):
    BLOCKED_BY_APPEAL = "BLOCKED_BY_APPEAL"
    REISSUE_REQUIRED = "REISSUE_REQUIRED"
    PENDING_HUMAN_CONFIRMATION = "PENDING_HUMAN_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"


class HandoffSignatureRole(str, enum.Enum):
    PERSON = "PERSON"
    HANDOFF_OWNER = "HANDOFF_OWNER"


class HandoffSignatureDecision(str, enum.Enum):
    CONFIRM = "CONFIRM"
    DECLINE = "DECLINE"


NEXT_STAGE: dict[JourneyModuleKey, JourneyModuleKey] = {
    JourneyModuleKey.EXPLORATION_CAMP: JourneyModuleKey.NEWCOMER_VILLAGE,
    JourneyModuleKey.NEWCOMER_VILLAGE: JourneyModuleKey.AI_ACADEMY,
    JourneyModuleKey.AI_ACADEMY: JourneyModuleKey.DELIVERY_GUILD,
    JourneyModuleKey.DELIVERY_GUILD: JourneyModuleKey.CERTIFICATION_ARENA,
}


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


class FormalResultPackageContract(SharedContractModel):
    """Read-only shared-domain interpretation of an existing runtime Outcome."""

    contract_version: str = Field(
        default="formal-result-package.v1",
        pattern=r"^formal-result-package\.v1$",
    )
    package_id: uuid.UUID
    organization_id: uuid.UUID
    person: PersonContract
    module_key: JourneyModuleKey
    outcome_id: uuid.UUID
    enrollment_id: uuid.UUID
    assignment_id: uuid.UUID
    source_evaluation_id: uuid.UUID
    source_outcome_status: str = Field(pattern=r"^HANDOFF_READY$")
    source_summary: str = Field(min_length=10, max_length=2_000)
    evidence: tuple[EvidenceContract, ...] = Field(min_length=2)
    human_gate: HumanGateContract
    appeals: tuple[AppealContract, ...] = ()
    status: FormalResultStatus
    formed_at: datetime
    developmental_result_only: bool = True
    automatic_talent_status_change_allowed: bool = False
    employment_decision_created: bool = False
    production_action_executed: bool = False

    @model_validator(mode="after")
    def validate_result_boundaries(self) -> Self:
        if (
            self.person.organization_id != self.organization_id
            or self.human_gate.organization_id != self.organization_id
            or self.person.person_id != self.human_gate.person_id
            or self.module_key is not self.human_gate.module_key
        ):
            raise ValueError("formal result cannot cross person, organization or module scope")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("formal result evidence must be unique")
        if self.formed_at.tzinfo is None:
            raise ValueError("formal result requires a timezone-aware formation time")
        if (
            not self.developmental_result_only
            or self.automatic_talent_status_change_allowed
            or self.employment_decision_created
            or self.production_action_executed
        ):
            raise ValueError("formal result must remain developmental and non-production")
        if any(
            appeal.organization_id != self.organization_id
            or appeal.person_id != self.person.person_id
            for appeal in self.appeals
        ):
            raise ValueError("formal result appeals cannot cross person or organization scope")
        open_statuses = {AppealStatus.SUBMITTED, AppealStatus.IN_REVIEW}
        overturn_statuses = {
            AppealStatus.OVERTURNED,
            AppealStatus.RETURNED_FOR_REVIEW,
        }
        appeal_statuses = {appeal.status for appeal in self.appeals}
        if self.status is FormalResultStatus.DISPUTED:
            if not appeal_statuses.intersection(open_statuses):
                raise ValueError("disputed formal result requires an unresolved appeal")
        elif self.status is FormalResultStatus.INVALIDATED_BY_APPEAL:
            if not appeal_statuses.intersection(overturn_statuses):
                raise ValueError("invalidated formal result requires an overturning appeal")
        elif self.status is FormalResultStatus.EFFECTIVE_AFTER_APPEAL:
            matching = [
                appeal
                for appeal in self.appeals
                if appeal.status in overturn_statuses
                and appeal.appeal_id == self.human_gate.source_appeal_id
                and appeal.gate_id == self.human_gate.supersedes_gate_id
            ]
            if (
                len(matching) != 1
                or self.human_gate.revision <= 1
                or self.human_gate.decision is not HumanGateDecision.PASS
            ):
                raise ValueError("post-appeal result requires an exact PASS replacement Gate")
        elif appeal_statuses.intersection(open_statuses | overturn_statuses):
            raise ValueError("effective formal result cannot ignore a blocking appeal")
        if self.status in {
            FormalResultStatus.EFFECTIVE,
            FormalResultStatus.EFFECTIVE_AFTER_APPEAL,
        }:
            require_formal_result_basis(
                person=self.person,
                evidence=self.evidence,
                gate=self.human_gate,
            )
        return self

    def subject_sha256(self) -> str:
        return _sha256(self.model_dump(mode="python"))


class ControlledHandoffScopeContract(SharedContractModel):
    contract_version: str = Field(
        default="controlled-handoff-scope.v1",
        pattern=r"^controlled-handoff-scope\.v1$",
    )
    organization_id: uuid.UUID
    person_id: uuid.UUID
    handoff_id: uuid.UUID
    outcome_id: uuid.UUID
    formal_result_package_id: uuid.UUID
    formal_result_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    from_module_key: JourneyModuleKey
    to_module_key: JourneyModuleKey
    owner_person_id: uuid.UUID
    title: str = Field(min_length=3, max_length=180)
    next_step_code: str = Field(pattern=r"^CONFIRM_HANDOFF$")
    next_step_title: str = Field(min_length=3, max_length=240)
    instructions: str = Field(min_length=10, max_length=2_000)
    created_at: datetime
    developmental_recommendation_only: bool = True
    automatic_enrollment_allowed: bool = False
    automatic_talent_status_change_allowed: bool = False
    production_action_executed: bool = False

    @model_validator(mode="after")
    def validate_handoff_scope(self) -> Self:
        if NEXT_STAGE.get(self.from_module_key) is not self.to_module_key:
            raise ValueError("handoff must target the exact next Journey stage")
        if self.to_module_key is JourneyModuleKey.CAREER_MAP:
            raise ValueError("Career Map is cross-cutting and cannot be a sequential handoff")
        if self.owner_person_id == self.person_id:
            raise ValueError("Person cannot be the sole owner of their own handoff")
        if self.created_at.tzinfo is None:
            raise ValueError("handoff scope requires a timezone-aware creation time")
        if (
            not self.developmental_recommendation_only
            or self.automatic_enrollment_allowed
            or self.automatic_talent_status_change_allowed
            or self.production_action_executed
        ):
            raise ValueError("handoff cannot automate enrollment, talent status or production")
        return self

    def subject_sha256(self) -> str:
        return _sha256(self.model_dump(mode="python"))


class HandoffSignatureContract(SharedContractModel):
    signer_person_id: uuid.UUID
    role: HandoffSignatureRole
    decision: HandoffSignatureDecision
    subject_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_at: datetime
    evidence_ref: str = Field(min_length=3, max_length=300)
    attestation_kind: str = Field(
        default="REAL_HUMAN_SIGNATURE",
        pattern=r"^REAL_HUMAN_SIGNATURE$",
    )

    @model_validator(mode="after")
    def validate_signature_time(self) -> Self:
        if self.signed_at.tzinfo is None:
            raise ValueError("handoff signature requires a timezone-aware timestamp")
        return self


class ControlledHandoffProjection(SharedContractModel):
    formal_result: FormalResultPackageContract
    scope: ControlledHandoffScopeContract
    status: ControlledHandoffStatus
    signatures: tuple[HandoffSignatureContract, ...] = ()
    blockers: tuple[str, ...]

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if (
            self.scope.formal_result_package_id != self.formal_result.package_id
            or self.scope.formal_result_package_sha256
            != self.formal_result.subject_sha256()
            or self.scope.outcome_id != self.formal_result.outcome_id
        ):
            raise ValueError("handoff does not bind the exact formal result package")
        if self.status is ControlledHandoffStatus.CONFIRMED and self.blockers:
            raise ValueError("confirmed handoff cannot carry blockers")
        if self.status is not ControlledHandoffStatus.CONFIRMED and not self.blockers:
            raise ValueError("unconfirmed handoff must expose its blocker")
        return self


def _validate_appeal_lineage(
    *,
    original_gate: HumanGateContract,
    appeals: tuple[AppealContract, ...],
) -> None:
    if len({appeal.appeal_id for appeal in appeals}) != len(appeals):
        raise ValueError("formal result appeals must be unique")
    if len(appeals) > 1:
        raise ValueError("v1 formal result package supports one appeal per Gate")
    if any(appeal.gate_id != original_gate.gate_id for appeal in appeals):
        raise ValueError("appeal does not belong to the original Human Gate")


def bind_formal_result_package(
    *,
    outcome: Outcome,
    review_cycle: ReviewCycleProjection,
    appeals: tuple[AppealContract, ...] = (),
    replacement: AppealReplacementGateContract | None = None,
) -> FormalResultPackageContract:
    """Bind an eligible review cycle to an existing Outcome without writing state."""

    if review_cycle.status is not ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE:
        raise ValueError("formal result package requires an eligible review cycle")
    original_evidence = (
        review_cycle.practice_evidence,
        review_cycle.human_evaluation_evidence,
    )
    require_formal_result_basis(
        person=review_cycle.person,
        evidence=original_evidence,
        gate=review_cycle.human_gate,
    )
    if (
        outcome.organization_id != review_cycle.person.organization_id
        or outcome.learner_id != review_cycle.person.person_id
        or outcome.assignment_id != review_cycle.practice_evidence.assignment_id
        or outcome.source_evaluation_id
        != review_cycle.human_evaluation_evidence.evaluation_id
        or outcome.status != "HANDOFF_READY"
    ):
        raise ValueError("Outcome does not match the fixed shared review-cycle scope")
    if outcome.created_at is None or outcome.created_at.tzinfo is None:
        raise ValueError("Outcome requires a timezone-aware creation time")
    if outcome.created_at < review_cycle.human_gate.signed_at:
        raise ValueError("Outcome cannot predate its Human Gate")

    _validate_appeal_lineage(
        original_gate=review_cycle.human_gate,
        appeals=appeals,
    )
    current_gate = review_cycle.human_gate
    evidence = original_evidence
    if replacement is not None:
        if replacement.original_gate != review_cycle.human_gate:
            raise ValueError("replacement does not supersede the review-cycle Gate")
        if not appeals or replacement.appeal_case.appeal != appeals[0]:
            raise ValueError("replacement requires its exact resolved appeal")
        current_gate = replacement.replacement_gate
        evidence = (*original_evidence, replacement.resolution_evidence)

    appeal = appeals[0] if appeals else None
    if appeal is None or appeal.status in {AppealStatus.UPHELD, AppealStatus.WITHDRAWN}:
        status = FormalResultStatus.EFFECTIVE
    elif appeal.status in {AppealStatus.SUBMITTED, AppealStatus.IN_REVIEW}:
        if replacement is not None:
            raise ValueError("unresolved appeal cannot have a replacement Gate")
        status = FormalResultStatus.DISPUTED
    elif replacement is None:
        status = FormalResultStatus.INVALIDATED_BY_APPEAL
    elif current_gate.decision is HumanGateDecision.PASS:
        require_formal_result_basis(
            person=review_cycle.person,
            evidence=evidence,
            gate=current_gate,
        )
        status = FormalResultStatus.EFFECTIVE_AFTER_APPEAL
    else:
        status = FormalResultStatus.INVALIDATED_BY_APPEAL

    package_id = uuid.uuid5(
        FORMAL_RESULT_NAMESPACE,
        f"result:{outcome.id}:gate:{current_gate.gate_id}:revision:{current_gate.revision}",
    )
    return FormalResultPackageContract(
        package_id=package_id,
        organization_id=outcome.organization_id,
        person=review_cycle.person,
        module_key=current_gate.module_key,
        outcome_id=outcome.id,
        enrollment_id=outcome.enrollment_id,
        assignment_id=outcome.assignment_id,
        source_evaluation_id=outcome.source_evaluation_id,
        source_outcome_status=outcome.status,
        source_summary=outcome.summary,
        evidence=evidence,
        human_gate=current_gate,
        appeals=appeals,
        status=status,
        formed_at=outcome.created_at,
    )


def project_controlled_handoff(
    *,
    handoff: Handoff,
    formal_result: FormalResultPackageContract,
    signatures: tuple[HandoffSignatureContract, ...] = (),
) -> ControlledHandoffProjection:
    """Interpret READY as a human-confirmation request, never an automatic transition."""

    if formal_result.module_key not in NEXT_STAGE:
        raise ValueError("module has no sequential v1 handoff target")
    if (
        handoff.organization_id != formal_result.organization_id
        or handoff.enrollment_id != formal_result.enrollment_id
        or handoff.outcome_id != formal_result.outcome_id
        or handoff.source_evaluation_id != formal_result.source_evaluation_id
        or handoff.status is not HandoffStatus.READY
        or handoff.next_step_code != "CONFIRM_HANDOFF"
    ):
        raise ValueError("Handoff does not match the fixed formal result scope")
    if handoff.created_at is None or handoff.created_at.tzinfo is None:
        raise ValueError("Handoff requires a timezone-aware creation time")
    if handoff.created_at < formal_result.formed_at:
        raise ValueError("Handoff cannot predate its formal result")

    scope = ControlledHandoffScopeContract(
        organization_id=formal_result.organization_id,
        person_id=formal_result.person.person_id,
        handoff_id=handoff.id,
        outcome_id=formal_result.outcome_id,
        formal_result_package_id=formal_result.package_id,
        formal_result_package_sha256=formal_result.subject_sha256(),
        from_module_key=formal_result.module_key,
        to_module_key=NEXT_STAGE[formal_result.module_key],
        owner_person_id=handoff.owner_user_id,
        title=handoff.title,
        next_step_code=handoff.next_step_code,
        next_step_title=handoff.next_step_title,
        instructions=handoff.instructions,
        created_at=handoff.created_at,
    )
    digest = scope.subject_sha256()
    roles = [signature.role for signature in signatures]
    if len(set(roles)) != len(roles):
        raise ValueError("handoff roles may sign at most once")
    for signature in signatures:
        expected_signer = (
            formal_result.person.person_id
            if signature.role is HandoffSignatureRole.PERSON
            else handoff.owner_user_id
        )
        if signature.signer_person_id != expected_signer:
            raise ValueError("handoff signature role and signer do not match")
        if signature.subject_sha256 != digest:
            raise ValueError("handoff signature must bind the exact scope digest")
        if signature.signed_at < scope.created_at:
            raise ValueError("handoff cannot be signed before it exists")

    blockers: list[str] = []
    if formal_result.status in {
        FormalResultStatus.DISPUTED,
        FormalResultStatus.INVALIDATED_BY_APPEAL,
    }:
        if signatures:
            raise ValueError("appeal-blocked handoff cannot accept signatures")
        status = ControlledHandoffStatus.BLOCKED_BY_APPEAL
        blockers.append("FORMAL_RESULT_APPEAL_BLOCKS_HANDOFF")
    elif (
        handoff.owner_user_id not in formal_result.human_gate.signed_by_person_ids
        or handoff.created_at < formal_result.human_gate.signed_at
    ):
        if signatures:
            raise ValueError("stale handoff owner cannot confirm an appeal replacement")
        status = ControlledHandoffStatus.REISSUE_REQUIRED
        blockers.append("HANDOFF_MUST_FOLLOW_CURRENT_GATE_AND_SIGNER")
    elif any(
        signature.decision is HandoffSignatureDecision.DECLINE
        for signature in signatures
    ):
        status = ControlledHandoffStatus.DECLINED
        blockers.append("HUMAN_HANDOFF_DECLINED")
    elif set(roles) == set(HandoffSignatureRole) and all(
        signature.decision is HandoffSignatureDecision.CONFIRM
        for signature in signatures
    ):
        status = ControlledHandoffStatus.CONFIRMED
    else:
        status = ControlledHandoffStatus.PENDING_HUMAN_CONFIRMATION
        blockers.append("PERSON_AND_HANDOFF_OWNER_CONFIRMATION_REQUIRED")

    return ControlledHandoffProjection(
        formal_result=formal_result,
        scope=scope,
        status=status,
        signatures=signatures,
        blockers=tuple(blockers),
    )
