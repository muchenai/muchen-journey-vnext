from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import Field, model_validator

from journey_api.models import TaskVersion
from journey_api.shared_domain import (
    DataClassification,
    EvidenceVisibility,
    JourneyModuleKey,
    SharedContractModel,
)


MODULE_BUILD_CONTRACTS = {
    JourneyModuleKey.EXPLORATION_CAMP: (
        "docs/baselines/build-contracts/BC-001_探索营_V1.0_V0.1.md"
    ),
    JourneyModuleKey.NEWCOMER_VILLAGE: (
        "docs/baselines/build-contracts/BC-002_新手村受控任务闭环_V0.1.md"
    ),
    JourneyModuleKey.AI_ACADEMY: (
        "docs/baselines/build-contracts/BC-003_AI学院_V0.1.md"
    ),
    JourneyModuleKey.DELIVERY_GUILD: (
        "docs/baselines/build-contracts/BC-004_公会_V0.1.md"
    ),
}


class TaskAuthorizationStatus(str, enum.Enum):
    APPROVED_CONTROLLED_TASK = "APPROVED_CONTROLLED_TASK"
    PENDING_OWNER_APPROVAL = "PENDING_OWNER_APPROVAL"
    SYNTHETIC_TEST_ONLY = "SYNTHETIC_TEST_ONLY"
    REJECTED = "REJECTED"


class TaskAuthorizationRole(str, enum.Enum):
    MODULE_BUSINESS_OWNER = "MODULE_BUSINESS_OWNER"
    TASK_BUSINESS_OWNER = "TASK_BUSINESS_OWNER"
    CONTENT_OWNER = "CONTENT_OWNER"
    DATA_SECURITY_OWNER = "DATA_SECURITY_OWNER"
    REVIEWER_OWNER = "REVIEWER_OWNER"


class TaskAuthorizationDecision(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class TaskExecutionEnvironment(str, enum.Enum):
    CONTROLLED_NON_PRODUCTION = "CONTROLLED_NON_PRODUCTION"


def required_task_authorization_roles(
    module_key: JourneyModuleKey,
) -> frozenset[TaskAuthorizationRole]:
    if module_key in {
        JourneyModuleKey.EXPLORATION_CAMP,
        JourneyModuleKey.AI_ACADEMY,
    }:
        return frozenset(
            {
                TaskAuthorizationRole.MODULE_BUSINESS_OWNER,
                TaskAuthorizationRole.CONTENT_OWNER,
                TaskAuthorizationRole.DATA_SECURITY_OWNER,
                TaskAuthorizationRole.REVIEWER_OWNER,
            }
        )
    if module_key in {
        JourneyModuleKey.NEWCOMER_VILLAGE,
        JourneyModuleKey.DELIVERY_GUILD,
    }:
        return frozenset(
            {
                TaskAuthorizationRole.MODULE_BUSINESS_OWNER,
                TaskAuthorizationRole.TASK_BUSINESS_OWNER,
                TaskAuthorizationRole.DATA_SECURITY_OWNER,
                TaskAuthorizationRole.REVIEWER_OWNER,
            }
        )
    raise ValueError("module does not use the controlled task authorization contract")


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


def _task_version_contract_document(task: TaskVersion) -> dict[str, Any]:
    return {
        "id": task.id,
        "organization_id": task.organization_id,
        "task_definition_id": task.task_definition_id,
        "version": task.version,
        "title": task.title,
        "purpose": task.purpose,
        "learner_outcome": task.learner_outcome,
        "instructions": task.instructions,
        "completion_criteria": task.completion_criteria,
        "required_deliverables": task.required_deliverables,
        "content_source_notes": task.content_source_notes,
        "change_summary": task.change_summary,
        "reviewer_calibration_note": task.reviewer_calibration_note,
        "allowed_attachment_types": task.allowed_attachment_types,
        "max_attachment_size_bytes": task.max_attachment_size_bytes,
        "reference_materials": task.reference_materials,
        "learning_materials": task.learning_materials,
        "learning_experience": task.learning_experience,
        "estimated_duration_minutes": task.estimated_duration_minutes,
        "rubric": task.rubric,
        "rubric_version": task.rubric_version,
        "reviewer_role": task.reviewer_role,
        "feedback_sla_business_days": task.feedback_sla_business_days,
        "sensitivity": task.sensitivity,
        "audience": task.audience,
        "published_by": task.published_by,
        "reviewed_by": task.reviewed_by,
        "published_at": task.published_at,
    }


def task_version_contract_sha256(task: TaskVersion) -> str:
    """Hash the immutable TaskVersion fields used by a task authorization."""

    return _sha256(_task_version_contract_document(task))


class TaskAuthorizationScopeContract(SharedContractModel):
    contract_version: str = Field(
        default="controlled-task-authorization-scope.v1",
        pattern=r"^controlled-task-authorization-scope\.v1$",
    )
    organization_id: uuid.UUID
    module_key: JourneyModuleKey
    build_contract_ref: str = Field(min_length=3, max_length=300)
    target_journey_version_id: uuid.UUID
    target_journey_stage_version_id: uuid.UUID
    task_version_id: uuid.UUID
    task_definition_id: uuid.UUID
    task_version_number: int = Field(ge=1)
    task_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_task_ref: str = Field(min_length=3, max_length=300)
    purpose_ref: str = Field(min_length=3, max_length=300)
    data_classification: DataClassification
    deidentification_ref: str = Field(min_length=3, max_length=300)
    visibility: tuple[EvidenceVisibility, ...] = Field(min_length=1)
    primary_reviewer_id: uuid.UUID
    backup_reviewer_id: uuid.UUID
    retention_policy: str = Field(min_length=3, max_length=120)
    deletion_or_archive_rule: str = Field(min_length=3, max_length=300)
    help_or_escalation_ref: str = Field(min_length=3, max_length=300)
    execution_environment: TaskExecutionEnvironment = (
        TaskExecutionEnvironment.CONTROLLED_NON_PRODUCTION
    )
    production_system_write_allowed: bool = False
    production_credential_allowed: bool = False
    automatic_production_delivery_allowed: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_controlled_scope(self) -> Self:
        expected_contract = MODULE_BUILD_CONTRACTS.get(self.module_key)
        if expected_contract is None:
            raise ValueError("module does not use a controlled single-reviewer task")
        if self.build_contract_ref != expected_contract:
            raise ValueError("module and Build Contract binding do not match")
        if self.primary_reviewer_id == self.backup_reviewer_id:
            raise ValueError("primary and backup Reviewer must be separate people")
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("task authorization visibility entries must be unique")
        required_visibility = {
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        }
        if not required_visibility.issubset(self.visibility):
            raise ValueError("authorized task must remain visible to the Person and Reviewers")
        if (
            self.production_system_write_allowed
            or self.production_credential_allowed
            or self.automatic_production_delivery_allowed
        ):
            raise ValueError("Journey task authorization cannot permit production execution")
        if self.created_at.tzinfo is None:
            raise ValueError("task authorization scope requires a timezone-aware timestamp")
        return self

    def subject_sha256(self) -> str:
        return _sha256(self.model_dump(mode="python"))


class TaskAuthorizationSignatureContract(SharedContractModel):
    signer_person_id: uuid.UUID
    role: TaskAuthorizationRole
    decision: TaskAuthorizationDecision
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
            raise ValueError("task authorization signature requires a timezone-aware timestamp")
        return self


class ControlledTaskAuthorizationContract(SharedContractModel):
    contract_version: str = Field(
        default="controlled-task-authorization.v1",
        pattern=r"^controlled-task-authorization\.v1$",
    )
    authorization_id: uuid.UUID
    scope: TaskAuthorizationScopeContract
    status: TaskAuthorizationStatus
    signatures: tuple[TaskAuthorizationSignatureContract, ...] = ()
    decided_at: datetime | None = None
    production_action_executed: bool = False

    @model_validator(mode="after")
    def validate_authorization_decision(self) -> Self:
        if self.production_action_executed:
            raise ValueError("task authorization cannot execute production work")
        subject_sha256 = self.scope.subject_sha256()
        roles = [signature.role for signature in self.signatures]
        if len(set(roles)) != len(roles):
            raise ValueError("task authorization roles must be signed at most once")
        if any(signature.subject_sha256 != subject_sha256 for signature in self.signatures):
            raise ValueError("task authorization signatures must bind the exact scope digest")
        if any(signature.signed_at < self.scope.created_at for signature in self.signatures):
            raise ValueError("task authorization cannot be signed before its scope exists")

        task_ref = self.scope.authorized_task_ref.lower()
        prohibited_markers = ("synthetic", "test-only", "pending")
        if self.status is TaskAuthorizationStatus.SYNTHETIC_TEST_ONLY:
            if not any(marker in task_ref for marker in prohibited_markers[:2]):
                raise ValueError("synthetic authorization must be visibly labeled")
            if self.signatures or self.decided_at is not None:
                raise ValueError("synthetic authorization cannot carry human approval")
            return self

        if self.status is TaskAuthorizationStatus.PENDING_OWNER_APPROVAL:
            if any(
                signature.decision is TaskAuthorizationDecision.REJECT
                for signature in self.signatures
            ):
                raise ValueError("a rejected signature requires REJECTED status")
            if self.decided_at is not None:
                raise ValueError("pending authorization cannot carry a decision timestamp")
            return self

        if self.decided_at is None:
            raise ValueError("final task authorization requires a decision timestamp")
        if self.decided_at.tzinfo is None:
            raise ValueError("task authorization decision requires a timezone-aware timestamp")
        if self.signatures and self.decided_at < max(
            signature.signed_at for signature in self.signatures
        ):
            raise ValueError("task authorization cannot be decided before its signatures")

        if self.status is TaskAuthorizationStatus.REJECTED:
            if not any(
                signature.decision is TaskAuthorizationDecision.REJECT
                for signature in self.signatures
            ):
                raise ValueError("rejected authorization requires a rejecting human signature")
            return self

        if any(marker in task_ref for marker in prohibited_markers):
            raise ValueError("approved task authorization cannot use a non-authoritative ref")
        required_roles = required_task_authorization_roles(self.scope.module_key)
        if set(roles) != required_roles:
            raise ValueError("approved task authorization is missing required signer roles")
        if any(
            signature.decision is not TaskAuthorizationDecision.APPROVE
            for signature in self.signatures
        ):
            raise ValueError("approved task authorization requires unanimous approval")
        if self.scope.primary_reviewer_id in {
            signature.signer_person_id
            for signature in self.signatures
            if signature.role
            in {
                TaskAuthorizationRole.MODULE_BUSINESS_OWNER,
                TaskAuthorizationRole.TASK_BUSINESS_OWNER,
                TaskAuthorizationRole.CONTENT_OWNER,
            }
        }:
            raise ValueError("primary Reviewer must be separate from task/content ownership")
        return self


def bind_task_version_authorization(
    *,
    task: TaskVersion,
    authorization: ControlledTaskAuthorizationContract,
) -> TaskAuthorizationStatus:
    scope = authorization.scope
    if task.published_at is None:
        raise ValueError("task authorization requires an immutable published TaskVersion")
    if (
        task.organization_id != scope.organization_id
        or task.id != scope.task_version_id
        or task.task_definition_id != scope.task_definition_id
        or task.version != scope.task_version_number
    ):
        raise ValueError("task authorization does not bind the supplied TaskVersion")
    if task_version_contract_sha256(task) != scope.task_version_sha256:
        raise ValueError("TaskVersion content differs from the authorized digest")
    if authorization.status is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK:
        content = json.dumps(
            _json_value(_task_version_contract_document(task)),
            ensure_ascii=False,
            sort_keys=True,
        ).lower()
        if any(marker in content for marker in ("synthetic", "test-only", "pending")):
            raise ValueError("approved authorization cannot bind synthetic TaskVersion content")
    return authorization.status
