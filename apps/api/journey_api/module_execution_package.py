from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from journey_api.controlled_task_authorization import (
    ControlledTaskAuthorizationContract,
    MODULE_BUILD_CONTRACTS,
    TaskAuthorizationStatus,
    TaskExecutionEnvironment,
)
from journey_api.shared_domain import (
    DataClassification,
    EvidenceVisibility,
    JourneyModuleKey,
    SharedContractModel,
)


class ModulePackageStatus(str, enum.Enum):
    PENDING_OWNER_APPROVAL = "PENDING_OWNER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ModulePackageRole(str, enum.Enum):
    MODULE_BUSINESS_OWNER = "MODULE_BUSINESS_OWNER"
    CONTENT_OWNER = "CONTENT_OWNER"
    TASK_BUSINESS_OWNER = "TASK_BUSINESS_OWNER"
    MENTOR_OWNER = "MENTOR_OWNER"
    DATA_SECURITY_OWNER = "DATA_SECURITY_OWNER"
    REVIEWER_OWNER = "REVIEWER_OWNER"


class ModulePackageDecision(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


def required_module_package_roles(
    module_key: JourneyModuleKey,
) -> frozenset[ModulePackageRole]:
    if module_key is JourneyModuleKey.AI_ACADEMY:
        return frozenset(
            {
                ModulePackageRole.MODULE_BUSINESS_OWNER,
                ModulePackageRole.CONTENT_OWNER,
                ModulePackageRole.DATA_SECURITY_OWNER,
                ModulePackageRole.REVIEWER_OWNER,
            }
        )
    if module_key is JourneyModuleKey.DELIVERY_GUILD:
        return frozenset(
            {
                ModulePackageRole.MODULE_BUSINESS_OWNER,
                ModulePackageRole.TASK_BUSINESS_OWNER,
                ModulePackageRole.MENTOR_OWNER,
                ModulePackageRole.DATA_SECURITY_OWNER,
                ModulePackageRole.REVIEWER_OWNER,
            }
        )
    raise ValueError("module does not use an AI Academy or Guild package")


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


class VersionedArtifactRefContract(SharedContractModel):
    artifact_ref: str = Field(min_length=3, max_length=300)
    version: str = Field(min_length=1, max_length=80)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModuleExecutionPackageScopeContract(SharedContractModel):
    contract_version: str = Field(
        default="module-execution-package-scope.v1",
        pattern=r"^module-execution-package-scope\.v1$",
    )
    organization_id: uuid.UUID
    module_key: JourneyModuleKey
    build_contract_ref: str = Field(min_length=3, max_length=300)
    package_ref: str = Field(min_length=3, max_length=300)
    package_version: str = Field(min_length=1, max_length=80)
    task_authorization_id: uuid.UUID
    task_authorization_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_version_id: uuid.UUID
    task_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_capability_ref: str = Field(min_length=3, max_length=300)
    rubric: VersionedArtifactRefContract
    practice_output_schema: VersionedArtifactRefContract
    reviewer_calibration: VersionedArtifactRefContract
    ai_use_policy: VersionedArtifactRefContract
    appeal_policy: VersionedArtifactRefContract
    evidence_rule: VersionedArtifactRefContract
    primary_reviewer_id: uuid.UUID
    backup_reviewer_id: uuid.UUID
    feedback_sla_business_days: int = Field(ge=1, le=30)
    evidence_validity_days: int = Field(ge=1, le=3650)
    visibility: tuple[EvidenceVisibility, ...] = Field(min_length=1)
    data_classification: DataClassification
    retention_policy: str = Field(min_length=3, max_length=120)
    execution_environment: TaskExecutionEnvironment = (
        TaskExecutionEnvironment.CONTROLLED_NON_PRODUCTION
    )
    production_system_write_allowed: bool = False
    production_credential_allowed: bool = False
    automatic_production_delivery_allowed: bool = False
    ai_advisory_cannot_finalize: bool = True
    human_review_required: bool = True
    created_at: datetime

    @model_validator(mode="after")
    def validate_shared_package_scope(self) -> Self:
        if self.module_key not in {
            JourneyModuleKey.AI_ACADEMY,
            JourneyModuleKey.DELIVERY_GUILD,
        }:
            raise ValueError("module package supports only AI Academy or Guild")
        if self.build_contract_ref != MODULE_BUILD_CONTRACTS[self.module_key]:
            raise ValueError("module package and Build Contract binding do not match")
        if self.primary_reviewer_id == self.backup_reviewer_id:
            raise ValueError("primary and backup Reviewer must be separate people")
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("module package visibility entries must be unique")
        if not {
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        }.issubset(self.visibility):
            raise ValueError("module package evidence must remain visible to Person and Reviewers")
        if (
            self.production_system_write_allowed
            or self.production_credential_allowed
            or self.automatic_production_delivery_allowed
        ):
            raise ValueError("module package cannot permit production execution")
        if not self.ai_advisory_cannot_finalize or not self.human_review_required:
            raise ValueError("AI advice cannot replace required human review")
        if self.created_at.tzinfo is None:
            raise ValueError("module package scope requires a timezone-aware timestamp")
        return self

    def subject_sha256(self) -> str:
        return _sha256(self.model_dump(mode="python"))


class AiLearningUnitPackageScopeContract(ModuleExecutionPackageScopeContract):
    module_key: Literal[JourneyModuleKey.AI_ACADEMY] = JourneyModuleKey.AI_ACADEMY
    unit_title: str = Field(min_length=3, max_length=200)
    applicable_role_refs: tuple[str, ...] = Field(min_length=1)
    prerequisite_refs: tuple[str, ...] = ()
    content_sources: tuple[VersionedArtifactRefContract, ...] = Field(min_length=1)
    learning_materials: tuple[VersionedArtifactRefContract, ...] = Field(min_length=1)
    example: VersionedArtifactRefContract
    counterexample: VersionedArtifactRefContract
    estimated_duration_minutes: int = Field(ge=5, le=1440)
    ai_use_disclosure_required: bool = True

    @model_validator(mode="after")
    def validate_learning_unit(self) -> Self:
        if len(set(self.applicable_role_refs)) != len(self.applicable_role_refs):
            raise ValueError("AI learning unit role refs must be unique")
        if len(set(self.prerequisite_refs)) != len(self.prerequisite_refs):
            raise ValueError("AI learning unit prerequisite refs must be unique")
        if not self.ai_use_disclosure_required:
            raise ValueError("AI learning unit must require AI-use disclosure")
        return self


class GuildPluginPackageScopeContract(ModuleExecutionPackageScopeContract):
    module_key: Literal[JourneyModuleKey.DELIVERY_GUILD] = (
        JourneyModuleKey.DELIVERY_GUILD
    )
    guild_name: str = Field(min_length=2, max_length=120)
    mission: VersionedArtifactRefContract
    capability_model: VersionedArtifactRefContract
    membership_rules: VersionedArtifactRefContract
    mentor_pool: VersionedArtifactRefContract
    activity_cadence: VersionedArtifactRefContract
    collaboration_boundary: VersionedArtifactRefContract
    next_action_rule: VersionedArtifactRefContract
    human_membership_decision_required: bool = True

    @model_validator(mode="after")
    def validate_guild_plugin(self) -> Self:
        if not self.human_membership_decision_required:
            raise ValueError("Guild membership cannot be decided by AI or points alone")
        return self


ModuleExecutionPackageScope = (
    AiLearningUnitPackageScopeContract | GuildPluginPackageScopeContract
)


class ModulePackageSignatureContract(SharedContractModel):
    signer_person_id: uuid.UUID
    role: ModulePackageRole
    decision: ModulePackageDecision
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
            raise ValueError("module package signature requires a timezone-aware timestamp")
        return self


class ModuleExecutionPackageContract(SharedContractModel):
    contract_version: str = Field(
        default="module-execution-package.v1",
        pattern=r"^module-execution-package\.v1$",
    )
    package_id: uuid.UUID
    scope: ModuleExecutionPackageScope
    status: ModulePackageStatus
    signatures: tuple[ModulePackageSignatureContract, ...] = ()
    decided_at: datetime | None = None
    production_action_executed: bool = False

    @model_validator(mode="after")
    def validate_package_decision(self) -> Self:
        if self.production_action_executed:
            raise ValueError("module package cannot execute production work")
        subject_sha256 = self.scope.subject_sha256()
        roles = [signature.role for signature in self.signatures]
        if len(set(roles)) != len(roles):
            raise ValueError("module package roles must be signed at most once")
        if any(signature.subject_sha256 != subject_sha256 for signature in self.signatures):
            raise ValueError("module package signatures must bind the exact scope digest")
        if any(signature.signed_at < self.scope.created_at for signature in self.signatures):
            raise ValueError("module package cannot be signed before its scope exists")

        if self.status is ModulePackageStatus.PENDING_OWNER_APPROVAL:
            if any(
                signature.decision is ModulePackageDecision.REJECT
                for signature in self.signatures
            ):
                raise ValueError("a rejected signature requires REJECTED status")
            if self.decided_at is not None:
                raise ValueError("pending module package cannot carry a decision timestamp")
            return self

        if self.decided_at is None:
            raise ValueError("final module package requires a decision timestamp")
        if self.decided_at.tzinfo is None:
            raise ValueError("module package decision requires a timezone-aware timestamp")
        if self.signatures and self.decided_at < max(
            signature.signed_at for signature in self.signatures
        ):
            raise ValueError("module package cannot be decided before its signatures")

        if self.status is ModulePackageStatus.REJECTED:
            if not any(
                signature.decision is ModulePackageDecision.REJECT
                for signature in self.signatures
            ):
                raise ValueError("rejected module package requires a rejecting human signature")
            return self

        scope_content = json.dumps(
            _json_value(self.scope.model_dump(mode="python")),
            ensure_ascii=False,
            sort_keys=True,
        ).lower()
        signature_evidence = " ".join(
            signature.evidence_ref.lower() for signature in self.signatures
        )
        if any(
            marker in f"{scope_content} {signature_evidence}"
            for marker in ("synthetic", "test-only", "pending")
        ):
            raise ValueError("approved module package cannot use non-authoritative content")
        required_roles = required_module_package_roles(self.scope.module_key)
        if set(roles) != required_roles:
            raise ValueError("approved module package is missing required signer roles")
        if any(
            signature.decision is not ModulePackageDecision.APPROVE
            for signature in self.signatures
        ):
            raise ValueError("approved module package requires unanimous approval")
        ownership_roles = {
            ModulePackageRole.MODULE_BUSINESS_OWNER,
            ModulePackageRole.CONTENT_OWNER,
            ModulePackageRole.TASK_BUSINESS_OWNER,
            ModulePackageRole.MENTOR_OWNER,
        }
        if self.scope.primary_reviewer_id in {
            signature.signer_person_id
            for signature in self.signatures
            if signature.role in ownership_roles
        }:
            raise ValueError("primary Reviewer must be separate from module package ownership")
        return self


def bind_module_execution_package(
    *,
    task_authorization: ControlledTaskAuthorizationContract,
    package: ModuleExecutionPackageContract,
) -> ModulePackageStatus:
    task_scope = task_authorization.scope
    package_scope = package.scope
    if (
        package_scope.organization_id != task_scope.organization_id
        or package_scope.module_key is not task_scope.module_key
        or package_scope.build_contract_ref != task_scope.build_contract_ref
        or package_scope.task_authorization_id != task_authorization.authorization_id
        or package_scope.task_authorization_scope_sha256 != task_scope.subject_sha256()
        or package_scope.task_version_id != task_scope.task_version_id
        or package_scope.task_version_sha256 != task_scope.task_version_sha256
    ):
        raise ValueError("module package does not bind the supplied task authorization")
    if (
        package_scope.primary_reviewer_id != task_scope.primary_reviewer_id
        or package_scope.backup_reviewer_id != task_scope.backup_reviewer_id
        or package_scope.visibility != task_scope.visibility
        or package_scope.data_classification is not task_scope.data_classification
        or package_scope.retention_policy != task_scope.retention_policy
    ):
        raise ValueError("module package evidence governance differs from task authorization")
    if (
        package.status is ModulePackageStatus.APPROVED
        and task_authorization.status
        is not TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
    ):
        raise ValueError("approved module package requires an approved controlled task")
    return package.status
