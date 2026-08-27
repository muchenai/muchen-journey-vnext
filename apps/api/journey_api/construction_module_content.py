from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from journey_api.content_hash import canonical_document_sha256


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MODULE_OWNER_ROLES = {
    "exploration-camp": "exploration_camp_owner",
    "newcomer-village": "newcomer_village_owner",
    "ai-academy": "ai_academy_owner",
    "delivery-guild": "delivery_guild_owner",
}


def _verify_root_hash(document: Any, label: str) -> Any:
    if not isinstance(document, dict):
        return document
    supplied = document.get("sha256")
    if not isinstance(supplied, str) or not SHA256_PATTERN.fullmatch(supplied):
        raise ValueError(f"{label} sha256 must be a lowercase SHA-256")
    if supplied != canonical_document_sha256(document):
        raise ValueError(f"{label} sha256 does not match canonical content")
    return document


class ConstructionContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OwnerApproval(ConstructionContractModel):
    role: Literal[
        "exploration_camp_owner",
        "newcomer_village_owner",
        "ai_academy_owner",
        "delivery_guild_owner",
    ]
    person_name: str = Field(min_length=2, max_length=120)
    signed_at: datetime
    decision: Literal["APPROVED"]

    @model_validator(mode="after")
    def require_timezone(self) -> Self:
        if self.signed_at.tzinfo is None:
            raise ValueError("Owner signed_at must include timezone")
        return self


class ContentItem(ConstructionContractModel):
    content_id: str = Field(min_length=3, max_length=120)
    title: str = Field(min_length=2, max_length=180)
    version: str = Field(min_length=1, max_length=40)
    source_ref: str = Field(min_length=3, max_length=300)
    owner: str = Field(min_length=2, max_length=120)
    estimated_minutes: int = Field(ge=1, le=480)
    visibility: tuple[Literal["LEARNER", "REVIEWER", "OPERATOR"], ...] = Field(
        min_length=1
    )
    data_classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL_PEOPLE"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _hash = model_validator(mode="before")(
        lambda cls, value: _verify_root_hash(value, "content_items")
    )

    @model_validator(mode="after")
    def require_unique_visibility(self) -> Self:
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("content item visibility must be unique")
        return self


class PackageTaskVersion(ConstructionContractModel):
    task_key: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{2,79}$")
    version: str = Field(min_length=1, max_length=40)
    purpose: str = Field(min_length=10, max_length=1000)
    non_goals: tuple[str, ...] = Field(min_length=1)
    inputs: tuple[str, ...] = Field(min_length=1)
    deliverables: tuple[str, ...] = Field(min_length=1)
    rubric_id: str = Field(min_length=3, max_length=120)
    reviewer_pool_ref: str = Field(min_length=3, max_length=120)
    help_path: str = Field(min_length=3, max_length=300)
    execution_environment: Literal["SIMULATION", "CONTROLLED_REAL_TASK"]
    controlled_task_authorization_ref: str | None = Field(
        default=None, min_length=3, max_length=300
    )
    retention_policy: str = Field(min_length=3, max_length=120)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _hash = model_validator(mode="before")(
        lambda cls, value: _verify_root_hash(value, "task_versions")
    )

    @model_validator(mode="after")
    def require_real_task_authorization(self) -> Self:
        if (
            self.execution_environment == "CONTROLLED_REAL_TASK"
            and not self.controlled_task_authorization_ref
        ):
            raise ValueError("controlled task authorization is required")
        if (
            self.execution_environment == "SIMULATION"
            and self.controlled_task_authorization_ref is not None
        ):
            raise ValueError("simulation cannot claim a controlled task authorization")
        return self


class PackageRubric(ConstructionContractModel):
    rubric_id: str = Field(min_length=3, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    dimensions: tuple[str, ...] = Field(min_length=1)
    human_decision_required: Literal[True]
    calibration_evidence_ref: str = Field(min_length=3, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _hash = model_validator(mode="before")(
        lambda cls, value: _verify_root_hash(value, "rubrics")
    )


class ReviewerPolicy(ConstructionContractModel):
    pool_ref: str = Field(min_length=3, max_length=120)
    primary_reviewers: tuple[str, ...] = Field(min_length=1)
    backup_reviewers: tuple[str, ...] = Field(min_length=1)
    first_response_sla_minutes: int = Field(ge=1)
    completion_sla_minutes: int = Field(ge=1)
    escalation_owner: str = Field(min_length=2, max_length=120)

    @model_validator(mode="after")
    def validate_roster(self) -> Self:
        primary = set(self.primary_reviewers)
        backup = set(self.backup_reviewers)
        if len(primary) != len(self.primary_reviewers) or len(backup) != len(
            self.backup_reviewers
        ):
            raise ValueError("Reviewer roster entries must be unique")
        if primary & backup:
            raise ValueError("primary and backup Reviewers must be separate")
        if self.first_response_sla_minutes > self.completion_sla_minutes:
            raise ValueError("first response SLA cannot exceed completion SLA")
        return self


class DataPolicy(ConstructionContractModel):
    production_write_allowed: Literal[False]
    raw_customer_data_allowed: Literal[False]
    ai_high_impact_decision_allowed: Literal[False]
    visibility: tuple[
        Literal["PERSON", "ASSIGNED_REVIEWERS", "AUTHORIZED_OPERATORS"], ...
    ] = Field(min_length=1)
    retention_policy: str = Field(min_length=3, max_length=120)

    @model_validator(mode="after")
    def require_person_and_reviewer_visibility(self) -> Self:
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("data policy visibility entries must be unique")
        if not {"PERSON", "ASSIGNED_REVIEWERS"}.issubset(self.visibility):
            raise ValueError("Person and assigned Reviewer visibility are required")
        return self


class ConstructionModuleContentPackage(ConstructionContractModel):
    schema_version: Literal["module-content-package.v1"]
    package_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    module_key: Literal[
        "exploration-camp", "newcomer-village", "ai-academy", "delivery-guild"
    ]
    version: str = Field(min_length=1, max_length=40)
    owner: OwnerApproval
    source_refs: tuple[str, ...] = Field(min_length=1)
    effective_at: datetime
    expires_at: datetime | None = None
    content_items: tuple[ContentItem, ...] = Field(min_length=1)
    task_versions: tuple[PackageTaskVersion, ...] = Field(min_length=1)
    rubrics: tuple[PackageRubric, ...] = Field(min_length=1)
    reviewer_policy: ReviewerPolicy
    data_policy: DataPolicy
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _hash = model_validator(mode="before")(
        lambda cls, value: _verify_root_hash(value, "package")
    )

    @model_validator(mode="after")
    def validate_package_lineage(self) -> Self:
        if self.owner.role != MODULE_OWNER_ROLES[self.module_key]:
            raise ValueError("module package owner role does not match module_key")
        if self.effective_at.tzinfo is None or (
            self.expires_at is not None and self.expires_at.tzinfo is None
        ):
            raise ValueError("package effective timestamps must include timezone")
        if self.owner.signed_at > self.effective_at:
            raise ValueError("package cannot become effective before Owner signature")
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("package expiry must follow effective_at")
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("package source_refs must be unique")
        if any(not re.fullmatch(r"SRC-[A-Z]+-[0-9]{2}", ref) for ref in self.source_refs):
            raise ValueError("package source_refs must use approved source identifiers")
        task_keys = [item.task_key for item in self.task_versions]
        rubric_ids = [item.rubric_id for item in self.rubrics]
        if len(set(task_keys)) != len(task_keys):
            raise ValueError("package TaskVersion keys must be unique")
        if len(set(rubric_ids)) != len(rubric_ids):
            raise ValueError("package rubric identifiers must be unique")
        known_rubrics = set(rubric_ids)
        if any(item.rubric_id not in known_rubrics for item in self.task_versions):
            raise ValueError("every package TaskVersion must bind a package rubric")
        if any(
            item.reviewer_pool_ref != self.reviewer_policy.pool_ref
            for item in self.task_versions
        ):
            raise ValueError("every package TaskVersion must bind the Reviewer pool")
        return self

    def canonical_document(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_unset=True)
