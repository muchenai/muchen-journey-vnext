from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from journey_api.db import Base


class UserStatus(str, enum.Enum):
    PENDING_IDENTITY = "PENDING_IDENTITY"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Role(str, enum.Enum):
    LEARNER = "LEARNER"
    REVIEWER = "REVIEWER"
    OPERATOR = "OPERATOR"
    CONTENT_EDITOR = "CONTENT_EDITOR"


class EnrollmentStatus(str, enum.Enum):
    PENDING_IDENTITY = "PENDING_IDENTITY"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InviteStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class JoinContextStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REVOKED = "REVOKED"


class IdentityLinkStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class AssignmentStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    NEEDS_REVISION = "NEEDS_REVISION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskDefinitionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class ContentDraftStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PUBLISHED = "PUBLISHED"


class JourneyDefinitionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class JourneyStageKind(str, enum.Enum):
    DAY_0 = "DAY_0"
    TREASURE = "TREASURE"
    ASSESSMENT = "ASSESSMENT"


class JourneyCompletionPolicy(str, enum.Enum):
    LEARNER_EVIDENCE = "LEARNER_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ReviewStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    IN_REVIEW = "IN_REVIEW"
    FINALIZED = "FINALIZED"


class Decision(str, enum.Enum):
    PASS = "PASS"
    REVISION_REQUIRED = "REVISION_REQUIRED"


class IncentiveType(str, enum.Enum):
    POINTS = "POINTS"
    XP = "XP"
    BADGE = "BADGE"
    RANK = "RANK"


class NextTrainingStageDecisionValue(str, enum.Enum):
    READY = "READY"
    DEFER = "DEFER"
    NOT_READY = "NOT_READY"


class NextTrainingStageReviewRequestStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"


class NextTrainingStageReviewResolutionStatus(str, enum.Enum):
    UPHELD = "UPHELD"
    OVERTURNED = "OVERTURNED"
    RETURNED_FOR_REVIEW = "RETURNED_FOR_REVIEW"


class ControlledTaskAuthorizationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVALS = "PENDING_APPROVALS"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ControlledTaskAuthorizationApprovalRole(str, enum.Enum):
    NEWCOMER_OPERATIONS_OWNER = "NEWCOMER_OPERATIONS_OWNER"
    PROJECT_OWNER = "PROJECT_OWNER"
    DATA_SECURITY_OWNER = "DATA_SECURITY_OWNER"
    REVIEWER_OWNER = "REVIEWER_OWNER"


class ControlledTaskAuthorizationApprovalDecision(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class FormalAdmissionDecisionType(str, enum.Enum):
    ADMIT = "ADMIT"
    DEFER = "DEFER"
    NOT_ADMIT = "NOT_ADMIT"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


class HandoffStatus(str, enum.Enum):
    READY = "READY"


class NotificationChannel(str, enum.Enum):
    LOCAL_TEST = "LOCAL_TEST"
    FEISHU = "FEISHU"
    EMAIL = "EMAIL"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    DELIVERED = "DELIVERED"
    RETRY_WAIT = "RETRY_WAIT"
    DEAD = "DEAD"


class NotificationAttemptStatus(str, enum.Enum):
    DELIVERED = "DELIVERED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    LEASE_EXPIRED = "LEASE_EXPIRED"


class NotificationEndpointStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class AttachmentStatus(str, enum.Enum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    READY = "READY"
    REJECTED = "REJECTED"
    DELETED = "DELETED"


class AttachmentScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    ERROR = "ERROR"


class DataRightsRequestType(str, enum.Enum):
    DELETE = "DELETE"
    CORRECT = "CORRECT"


class DataRightsRequestStatus(str, enum.Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_users_id_organization"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, native_enum=False), default=UserStatus.ACTIVE)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_role_assignments_user_role"),
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_role_assignments_user_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_identity_provider_subject"),
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_external_identities_id_organization",
        ),
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_external_identities_user_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(180))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revision: Mapped[int] = mapped_column(default=1)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_invites_journey_version_organization",
        ),
        UniqueConstraint("id", "organization_id", name="uq_invites_id_organization"),
        ForeignKeyConstraint(
            ["reviewer_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_invites_reviewer_organization",
        ),
        ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_invites_task_version_organization",
        ),
        ForeignKeyConstraint(
            ["target_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_invites_target_organization",
        ),
        ForeignKeyConstraint(
            ["created_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_invites_creator_organization",
        ),
        ForeignKeyConstraint(
            ["consumed_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_invites_consumer_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    task_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_versions.id"))
    journey_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[InviteStatus] = mapped_column(Enum(InviteStatus, native_enum=False), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    consumed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvitationControl(Base):
    __tablename__ = "invitation_controls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["updated_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_invitation_controls_updater_organization",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), primary_key=True
    )
    new_invites_enabled: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=1)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JoinContext(Base):
    __tablename__ = "join_contexts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invite_id", "organization_id"],
            ["invites.id", "invites.organization_id"],
            name="fk_join_contexts_invite_organization",
        ),
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_join_contexts_user_organization",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "organization_id", "user_id"],
            ["enrollments.id", "enrollments.organization_id", "enrollments.learner_id"],
            name="fk_join_contexts_enrollment_person_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    invite_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invites.id"), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[JoinContextStatus] = mapped_column(Enum(JoinContextStatus, native_enum=False))
    created_user: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdentitySession(Base):
    __tablename__ = "identity_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_identity_sessions_user_organization",
        ),
        ForeignKeyConstraint(
            ["external_identity_id", "organization_id"],
            ["external_identities.id", "external_identities.organization_id"],
            name="fk_identity_sessions_external_identity_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    external_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_identities.id"), nullable=True, index=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    result: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        UniqueConstraint("scope", "subject_hash", "window_started_at", name="uq_auth_rate_limit_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scope: Mapped[str] = mapped_column(String(60))
    subject_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=1)


class ExternalIdentityLink(Base):
    __tablename__ = "external_identity_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_external_identity_links_user_organization",
        ),
        ForeignKeyConstraint(
            ["created_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_external_identity_links_creator_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    provider: Mapped[str] = mapped_column(String(40))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[IdentityLinkStatus] = mapped_column(
        Enum(IdentityLinkStatus, native_enum=False), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthLoginState(Base):
    __tablename__ = "oauth_login_states"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_token_hash: Mapped[str] = mapped_column(String(64))
    identity_link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_identity_links.id"), nullable=True, index=True
    )
    return_to: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskDefinition(Base):
    __tablename__ = "task_definitions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "stable_key", name="uq_task_definitions_organization_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    stable_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[TaskDefinitionStatus] = mapped_column(
        Enum(TaskDefinitionStatus, native_enum=False)
    )
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContentDraft(Base):
    __tablename__ = "content_drafts"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_content_drafts_positive_revision"),
        UniqueConstraint(
            "published_task_version_id",
            name="uq_content_drafts_published_task_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    task_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_definitions.id"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[ContentDraftStatus] = mapped_column(
        Enum(ContentDraftStatus, native_enum=False), index=True
    )
    revision: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_task_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaskVersion(Base):
    __tablename__ = "task_versions"
    __table_args__ = (
        UniqueConstraint(
            "task_definition_id", "version", name="uq_task_versions_definition_version"
        ),
        UniqueConstraint(
            "id", "task_definition_id", name="uq_task_versions_id_definition"
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_task_versions_id_organization"
        ),
        CheckConstraint("version >= 1", name="ck_task_versions_positive_version"),
        CheckConstraint(
            "estimated_duration_minutes BETWEEN 1 AND 480",
            name="ck_task_versions_estimated_duration",
        ),
        CheckConstraint(
            "feedback_sla_business_days BETWEEN 1 AND 10",
            name="ck_task_versions_feedback_sla",
        ),
        CheckConstraint(
            "max_attachment_size_bytes >= 0",
            name="ck_task_versions_attachment_size",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    task_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_definitions.id"), index=True
    )
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(180))
    purpose: Mapped[str] = mapped_column(Text)
    learner_outcome: Mapped[str] = mapped_column(Text)
    instructions: Mapped[list[str]] = mapped_column(JSON)
    completion_criteria: Mapped[list[str]] = mapped_column(JSON)
    required_deliverables: Mapped[list[str]] = mapped_column(JSON)
    content_source_notes: Mapped[list[str]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(Text)
    reviewer_calibration_note: Mapped[str] = mapped_column(Text)
    allowed_attachment_types: Mapped[list[str]] = mapped_column(JSON)
    max_attachment_size_bytes: Mapped[int] = mapped_column(default=0)
    reference_materials: Mapped[list[str]] = mapped_column(JSON)
    learning_materials: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    learning_experience: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_duration_minutes: Mapped[int]
    rubric: Mapped[dict[str, Any]] = mapped_column(JSON)
    rubric_version: Mapped[int]
    reviewer_role: Mapped[str] = mapped_column(String(40))
    feedback_sla_business_days: Mapped[int]
    sensitivity: Mapped[str] = mapped_column(String(40))
    audience: Mapped[str] = mapped_column(String(40))
    published_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningMaterialCompletion(Base):
    __tablename__ = "learning_material_completions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_material_completions_assignment_scope",
        ),
        ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_material_completions_task_version_scope",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "organization_id", "learner_id"],
            ["enrollments.id", "enrollments.organization_id", "enrollments.learner_id"],
            name="fk_material_completions_enrollment_owner_scope",
        ),
        UniqueConstraint(
            "assignment_id",
            "material_key",
            name="uq_material_completions_assignment_key",
        ),
        CheckConstraint(
            "material_key ~ '^[a-z0-9][a-z0-9_-]{2,79}$'",
            name="ck_material_completions_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    task_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    material_key: Mapped[str] = mapped_column(String(80))
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JourneyDefinition(Base):
    __tablename__ = "journey_definitions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "stable_key",
            name="uq_journey_definitions_organization_key",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_journey_definitions_id_organization"
        ),
        CheckConstraint(
            "revision >= 1", name="ck_journey_definitions_positive_revision"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    stable_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[JourneyDefinitionStatus] = mapped_column(
        Enum(JourneyDefinitionStatus, native_enum=False)
    )
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JourneyVersion(Base):
    __tablename__ = "journey_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["journey_definition_id", "organization_id"],
            ["journey_definitions.id", "journey_definitions.organization_id"],
            name="fk_journey_versions_definition_organization",
        ),
        UniqueConstraint(
            "journey_definition_id",
            "version",
            name="uq_journey_versions_definition_version",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_journey_versions_id_organization"
        ),
        CheckConstraint("version >= 1", name="ck_journey_versions_positive_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    journey_definition_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(180))
    purpose: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str] = mapped_column(Text)
    content_review_note: Mapped[str] = mapped_column(Text)
    published_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ModuleContentPackageBinding(Base):
    __tablename__ = "module_content_package_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_mcpb_journey_version_scope",
        ),
        ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_mcpb_task_version_scope",
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_mcpb_owner_scope",
        ),
        ForeignKeyConstraint(
            ["primary_reviewer_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_mcpb_primary_reviewer_scope",
        ),
        ForeignKeyConstraint(
            ["backup_reviewer_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_mcpb_backup_reviewer_scope",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_mcpb_created_by_scope",
        ),
        UniqueConstraint(
            "organization_id",
            "package_id",
            "package_version",
            name="uq_mcpb_package_version",
        ),
        UniqueConstraint(
            "journey_version_id", name="uq_mcpb_journey_version"
        ),
        CheckConstraint(
            "module_key IN ('ai-academy','delivery-guild')",
            name="ck_mcpb_initial_modules",
        ),
        CheckConstraint(
            "package_sha256 ~ '^[0-9a-f]{64}$' AND "
            "task_package_sha256 ~ '^[0-9a-f]{64}$' AND "
            "rubric_package_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_mcpb_hashes",
        ),
        CheckConstraint(
            "owner_user_id <> primary_reviewer_user_id AND "
            "owner_user_id <> backup_reviewer_user_id AND "
            "primary_reviewer_user_id <> backup_reviewer_user_id",
            name="ck_mcpb_separation_of_duties",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_mcpb_validity",
        ),
        CheckConstraint(
            "first_response_sla_minutes >= 1 AND "
            "completion_sla_minutes >= first_response_sla_minutes",
            name="ck_mcpb_sla",
        ),
        CheckConstraint(
            "package_document->>'sha256' = package_sha256 AND "
            "package_document->>'package_id' = package_id AND "
            "package_document->>'version' = package_version AND "
            "package_document->>'module_key' = module_key AND "
            "package_document->'task_versions'->0->>'sha256' = task_package_sha256 AND "
            "package_document->'rubrics'->0->>'sha256' = rubric_package_sha256",
            name="ck_mcpb_document_lineage",
        ),
        CheckConstraint(
            "package_document->'data_policy'->>'production_write_allowed' = 'false' AND "
            "package_document->'data_policy'->>'raw_customer_data_allowed' = 'false' AND "
            "package_document->'data_policy'->>'ai_high_impact_decision_allowed' = 'false' AND "
            "package_document->'task_versions'->0->>'execution_environment' = 'SIMULATION'",
            name="ck_mcpb_safety_boundary",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    journey_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    task_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    package_id: Mapped[str] = mapped_column(String(120))
    package_version: Mapped[str] = mapped_column(String(40))
    module_key: Mapped[str] = mapped_column(String(40), index=True)
    package_sha256: Mapped[str] = mapped_column(String(64))
    task_package_sha256: Mapped[str] = mapped_column(String(64))
    rubric_package_sha256: Mapped[str] = mapped_column(String(64))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    owner_role: Mapped[str] = mapped_column(String(50))
    owner_signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_refs: Mapped[list[str]] = mapped_column(JSON)
    reviewer_pool_ref: Mapped[str] = mapped_column(String(120))
    primary_reviewer_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    backup_reviewer_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    first_response_sla_minutes: Mapped[int]
    completion_sla_minutes: Mapped[int]
    visibility: Mapped[list[str]] = mapped_column(JSON)
    data_classification: Mapped[str] = mapped_column(String(40))
    retention_policy: Mapped[str] = mapped_column(String(120))
    package_document: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by_user_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JourneyStageVersion(Base):
    __tablename__ = "journey_stage_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_journey_stages_version_organization",
        ),
        ForeignKeyConstraint(
            ["task_version_id", "organization_id"],
            ["task_versions.id", "task_versions.organization_id"],
            name="fk_journey_stages_task_organization",
        ),
        UniqueConstraint(
            "journey_version_id", "stable_key", name="uq_journey_stages_version_key"
        ),
        UniqueConstraint(
            "journey_version_id", "position", name="uq_journey_stages_version_position"
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_journey_stages_id_organization"
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "journey_version_id",
            "task_version_id",
            name="uq_jsv_acceptance_lineage",
        ),
        CheckConstraint("position >= 0", name="ck_journey_stages_nonnegative_position"),
        CheckConstraint(
            "(stage_kind IN ('DAY_0', 'TREASURE') AND completion_policy = 'LEARNER_EVIDENCE') "
            "OR (stage_kind = 'ASSESSMENT' AND completion_policy = 'REVIEW_REQUIRED')",
            name="ck_journey_stages_kind_policy",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    journey_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    stable_key: Mapped[str] = mapped_column(String(80))
    position: Mapped[int]
    stage_kind: Mapped[JourneyStageKind] = mapped_column(
        Enum(JourneyStageKind, native_enum=False)
    )
    completion_policy: Mapped[JourneyCompletionPolicy] = mapped_column(
        Enum(JourneyCompletionPolicy, native_enum=False)
    )
    task_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    title: Mapped[str] = mapped_column(String(180))
    short_description: Mapped[str] = mapped_column(String(300))


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "learner_id",
            name="uq_enrollments_fixed_owner_scope",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_enrollments_id_organization"
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "learner_id",
            "journey_version_id",
            "reviewer_id",
            name="uq_enrollments_acceptance_lineage",
        ),
        ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_enrollments_journey_version_organization",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    journey_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(Enum(EnrollmentStatus, native_enum=False))
    revision: Mapped[int] = mapped_column(default=1)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_version_id", "task_definition_id"],
            ["task_versions.id", "task_versions.task_definition_id"],
            name="fk_assignments_task_version_definition",
        ),
        ForeignKeyConstraint(
            ["journey_stage_version_id", "organization_id"],
            ["journey_stage_versions.id", "journey_stage_versions.organization_id"],
            name="fk_assignments_journey_stage_organization",
        ),
        UniqueConstraint(
            "enrollment_id", "task_definition_id", name="uq_assignments_enrollment_task"
        ),
        UniqueConstraint("enrollment_id", "position", name="uq_assignments_enrollment_position"),
        UniqueConstraint(
            "enrollment_id",
            "journey_stage_version_id",
            name="uq_assignments_enrollment_journey_stage",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "enrollment_id",
            "journey_stage_version_id",
            "task_version_id",
            name="uq_assignments_acceptance_lineage",
        ),
        CheckConstraint("position >= 1", name="ck_assignments_positive_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), index=True)
    task_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id"))
    task_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_versions.id"))
    journey_stage_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(default=1)
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus, native_enum=False))
    revision: Mapped[int] = mapped_column(default=1)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_submissions_assignment_organization",
        ),
        UniqueConstraint("assignment_id", name="uq_submissions_assignment"),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_submissions_id_organization_assignment",
        ),
        CheckConstraint(
            "current_version_no >= 0", name="ck_submissions_nonnegative_current_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    current_version_no: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "version_no", name="uq_submission_versions_submission_version"
        ),
        CheckConstraint("version_no >= 1", name="ck_submission_versions_positive_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    version_no: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    ai_use: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "used": False,
            "purpose": None,
            "model_version": None,
            "prompt_version": None,
            "output_is_advisory_only": True,
        },
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionDraft(Base):
    __tablename__ = "submission_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_submission_drafts_assignment_organization",
        ),
        ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_submission_drafts_owner_organization",
        ),
        UniqueConstraint("assignment_id", name="uq_submission_drafts_assignment"),
        CheckConstraint("revision >= 1", name="ck_submission_drafts_positive_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    owner_id: Mapped[uuid.UUID]
    body: Mapped[str] = mapped_column(Text)
    attachment_ids: Mapped[list[str]] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attachments_owner_organization",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_attachments_assignment_organization",
        ),
        CheckConstraint(
            "purpose IN ('SUBMISSION_EVIDENCE')", name="ck_attachments_purpose"
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 5242880", name="ck_attachments_size"
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_attachments_id_organization_assignment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    original_filename: Mapped[str] = mapped_column(String(180))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[AttachmentStatus] = mapped_column(
        Enum(AttachmentStatus, native_enum=False)
    )
    scan_status: Mapped[AttachmentScanStatus] = mapped_column(
        Enum(AttachmentScanStatus, native_enum=False)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    upload_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    storage_etag: Mapped[str | None] = mapped_column(String(160), nullable=True)
    storage_version_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scan_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SubmissionVersionAttachment(Base):
    __tablename__ = "submission_version_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submission_version_id", "submission_id"],
            ["submission_versions.id", "submission_versions.submission_id"],
            name="fk_submission_attachment_version_submission",
        ),
        ForeignKeyConstraint(
            ["submission_id", "organization_id", "assignment_id"],
            [
                "submissions.id",
                "submissions.organization_id",
                "submissions.assignment_id",
            ],
            name="fk_submission_attachment_submission_scope",
        ),
        ForeignKeyConstraint(
            ["attachment_id", "organization_id", "assignment_id"],
            [
                "attachments.id",
                "attachments.organization_id",
                "attachments.assignment_id",
            ],
            name="fk_submission_attachment_file_scope",
        ),
        UniqueConstraint("attachment_id", name="uq_submission_attachment_file"),
        UniqueConstraint(
            "submission_version_id", "position", name="uq_submission_attachment_position"
        ),
        CheckConstraint("position >= 1", name="ck_submission_attachment_position"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    submission_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    assignment_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    position: Mapped[int]


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "organization_id"],
            ["assignments.id", "assignments.organization_id"],
            name="fk_reviews_assignment_organization",
        ),
        ForeignKeyConstraint(
            ["submission_id", "organization_id", "assignment_id"],
            ["submissions.id", "submissions.organization_id", "submissions.assignment_id"],
            name="fk_reviews_submission_scope",
        ),
        ForeignKeyConstraint(
            ["submission_version_id", "submission_id"],
            ["submission_versions.id", "submission_versions.submission_id"],
            name="fk_reviews_submission_version",
        ),
        ForeignKeyConstraint(
            ["reviewer_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_reviews_reviewer_organization",
        ),
        UniqueConstraint("submission_version_id", name="uq_review_submission_version"),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            "submission_id",
            "submission_version_id",
            "reviewer_id",
            name="uq_reviews_fixed_scope",
        ),
        CheckConstraint("revision >= 1", name="ck_reviews_positive_revision"),
        CheckConstraint(
            "(status = 'ASSIGNED' AND started_at IS NULL AND finalized_at IS NULL) "
            "OR (status = 'IN_REVIEW' AND started_at IS NOT NULL AND finalized_at IS NULL) "
            "OR (status = 'FINALIZED' AND started_at IS NOT NULL AND finalized_at IS NOT NULL)",
            name="ck_reviews_status_timestamps",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    submission_id: Mapped[uuid.UUID]
    submission_version_id: Mapped[uuid.UUID]
    reviewer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, native_enum=False))
    revision: Mapped[int] = mapped_column(default=1)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "review_id",
                "organization_id",
                "assignment_id",
                "submission_id",
                "submission_version_id",
                "reviewer_id",
            ],
            [
                "reviews.id",
                "reviews.organization_id",
                "reviews.assignment_id",
                "reviews.submission_id",
                "reviews.submission_version_id",
                "reviews.reviewer_id",
            ],
            name="fk_evaluations_review_fixed_scope",
        ),
        CheckConstraint(
            "created_by = reviewer_id", name="ck_evaluations_reviewer_is_actor"
        ),
        CheckConstraint(
            "review_revision >= 1", name="ck_evaluations_positive_review_revision"
        ),
        CheckConstraint(
            "(feedback_structure_version = 0 AND structured_feedback IS NULL) "
            "OR (feedback_structure_version = 1 AND structured_feedback IS NOT NULL)",
            name="ck_evaluations_feedback_structure",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "assignment_id",
            name="uq_evaluations_outcome_scope",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_evaluations_id_organization"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    review_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    submission_id: Mapped[uuid.UUID]
    submission_version_id: Mapped[uuid.UUID]
    reviewer_id: Mapped[uuid.UUID]
    review_revision: Mapped[int]
    decision: Mapped[Decision] = mapped_column(Enum(Decision, native_enum=False))
    rubric_scores: Mapped[dict[str, str]] = mapped_column(JSON)
    structured_feedback: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    feedback_structure_version: Mapped[int] = mapped_column(default=1)
    feedback: Mapped[str] = mapped_column(Text)
    ai_use: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "used": False,
            "purpose": None,
            "model_version": None,
            "prompt_version": None,
            "output_is_advisory_only": True,
        },
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IncentiveLedgerEntry(Base):
    __tablename__ = "incentive_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["person_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_incentive_entries_person_organization",
        ),
        ForeignKeyConstraint(
            ["created_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_incentive_entries_creator_organization",
        ),
        ForeignKeyConstraint(
            ["source_outcome_id", "organization_id", "person_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_incentive_entries_outcome_person_scope",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_incentive_entries_id_organization"
        ),
        CheckConstraint(
            "module_key IN ('exploration-camp', 'newcomer-village', "
            "'ai-academy', 'delivery-guild', 'certification-arena', 'career-map')",
            name="ck_incentive_entries_module_key",
        ),
        CheckConstraint(
            "(incentive_type IN ('POINTS', 'XP') AND amount IS NOT NULL "
            "AND amount <> 0 AND label IS NULL) OR "
            "(incentive_type IN ('BADGE', 'RANK') AND amount IS NULL "
            "AND length(trim(label)) BETWEEN 1 AND 120)",
            name="ck_incentive_entries_value_shape",
        ),
        CheckConstraint(
            "(correction_of_entry_id IS NULL AND correction_reason IS NULL) OR "
            "(correction_of_entry_id IS NOT NULL "
            "AND length(trim(correction_reason)) BETWEEN 10 AND 500)",
            name="ck_incentive_entries_correction_shape",
        ),
        CheckConstraint(
            "rule_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_incentive_entries_rule_sha256",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    person_id: Mapped[uuid.UUID] = mapped_column(index=True)
    module_key: Mapped[str] = mapped_column(String(40))
    incentive_type: Mapped[IncentiveType] = mapped_column(
        Enum(IncentiveType, native_enum=False)
    )
    amount: Mapped[int | None] = mapped_column(nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_outcome_id: Mapped[uuid.UUID] = mapped_column(index=True)
    rule_ref: Mapped[str] = mapped_column(String(300))
    rule_sha256: Mapped[str] = mapped_column(String(64))
    correction_of_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incentive_ledger_entries.id"), nullable=True
    )
    correction_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Outcome(Base):
    __tablename__ = "outcomes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["enrollment_id", "organization_id", "learner_id"],
            ["enrollments.id", "enrollments.organization_id", "enrollments.learner_id"],
            name="fk_outcomes_enrollment_owner_scope",
        ),
        ForeignKeyConstraint(
            ["source_evaluation_id", "organization_id", "assignment_id"],
            ["evaluations.id", "evaluations.organization_id", "evaluations.assignment_id"],
            name="fk_outcomes_evaluation_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "enrollment_id",
            "source_evaluation_id",
            "learner_id",
            name="uq_outcomes_fixed_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "enrollment_id",
            "source_evaluation_id",
            name="uq_outcomes_handoff_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "learner_id",
            name="uq_outcomes_recipient_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "enrollment_id",
            name="uq_outcomes_id_organization_enrollment",
        ),
        UniqueConstraint("assignment_id", name="uq_outcomes_assignment"),
        CheckConstraint("status = 'HANDOFF_READY'", name="ck_outcomes_handoff_ready"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID]
    enrollment_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    source_evaluation_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JourneyAdmissionDecision(Base):
    __tablename__ = "journey_admission_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["enrollment_id", "organization_id"],
            ["enrollments.id", "enrollments.organization_id"],
            name="fk_journey_admission_enrollment_scope",
        ),
        ForeignKeyConstraint(
            ["journey_version_id", "organization_id"],
            ["journey_versions.id", "journey_versions.organization_id"],
            name="fk_journey_admission_version_scope",
        ),
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.enrollment_id"],
            name="fk_journey_admission_outcome_scope",
        ),
        ForeignKeyConstraint(
            ["decided_by", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_journey_admission_decider_scope",
        ),
        UniqueConstraint(
            "enrollment_id",
            "journey_version_id",
            name="uq_journey_admission_enrollment_version",
        ),
        CheckConstraint(
            "total_score BETWEEN 0 AND 100",
            name="ck_journey_admission_total_score",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    journey_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    outcome_id: Mapped[uuid.UUID] = mapped_column(index=True)
    total_score: Mapped[int]
    recommendation_tier: Mapped[str] = mapped_column(String(32))
    scorecard: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_evaluation_ids: Mapped[list[str]] = mapped_column(JSON)
    decision: Mapped[FormalAdmissionDecisionType] = mapped_column(
        Enum(FormalAdmissionDecisionType, native_enum=False)
    )
    decision_reason: Mapped[str] = mapped_column(Text)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JourneyOutcomeEvidence(Base):
    __tablename__ = "journey_outcome_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.enrollment_id"],
            name="fk_journey_evidence_outcome_scope",
        ),
        ForeignKeyConstraint(
            ["evaluation_id", "organization_id"],
            ["evaluations.id", "evaluations.organization_id"],
            name="fk_journey_evidence_evaluation_scope",
        ),
        ForeignKeyConstraint(
            ["journey_stage_version_id", "organization_id"],
            ["journey_stage_versions.id", "journey_stage_versions.organization_id"],
            name="fk_journey_evidence_stage_scope",
        ),
        UniqueConstraint(
            "outcome_id",
            "journey_stage_version_id",
            name="uq_journey_outcome_evidence_stage",
        ),
        UniqueConstraint(
            "evaluation_id", name="uq_journey_outcome_evidence_evaluation"
        ),
    )

    outcome_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    journey_stage_version_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Handoff(Base):
    __tablename__ = "handoffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "enrollment_id", "source_evaluation_id"],
            [
                "outcomes.id",
                "outcomes.organization_id",
                "outcomes.enrollment_id",
                "outcomes.source_evaluation_id",
            ],
            name="fk_handoffs_outcome_fixed_scope",
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_handoffs_owner_organization",
        ),
        UniqueConstraint("outcome_id", name="uq_handoffs_outcome"),
        UniqueConstraint("enrollment_id", name="uq_handoffs_enrollment"),
        UniqueConstraint("source_evaluation_id", name="uq_handoffs_evaluation"),
        UniqueConstraint(
            "id",
            "organization_id",
            "outcome_id",
            name="uq_handoffs_next_stage_scope",
        ),
        CheckConstraint("status = 'READY'", name="ck_handoffs_ready"),
        CheckConstraint(
            "next_step_code = 'CONFIRM_HANDOFF'", name="ck_handoffs_next_step"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    enrollment_id: Mapped[uuid.UUID]
    outcome_id: Mapped[uuid.UUID]
    source_evaluation_id: Mapped[uuid.UUID]
    owner_user_id: Mapped[uuid.UUID]
    status: Mapped[HandoffStatus] = mapped_column(
        Enum(HandoffStatus, native_enum=False)
    )
    title: Mapped[str] = mapped_column(String(180))
    next_step_code: Mapped[str] = mapped_column(String(80))
    next_step_title: Mapped[str] = mapped_column(String(240))
    instructions: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NextTrainingStageDecision(Base):
    __tablename__ = "next_training_stage_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["handoff_id", "organization_id", "outcome_id"],
            ["handoffs.id", "handoffs.organization_id", "handoffs.outcome_id"],
            name="fk_ntsd_handoff_scope",
        ),
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "person_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_ntsd_outcome_person_scope",
        ),
        ForeignKeyConstraint(
            ["decided_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsd_decider_scope",
        ),
        UniqueConstraint(
            "organization_id", "handoff_id", "decision_scope", "revision",
            name="uq_ntsd_handoff_scope_revision",
        ),
        UniqueConstraint(
            "source_review_request_id", name="uq_ntsd_source_review_request"
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "handoff_id",
            "decision_scope",
            "decision",
            name="uq_ntsd_review_request_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "handoff_id",
            "decision_scope",
            "decision",
            "person_id",
            name="uq_ntsd_acceptance_person_scope",
        ),
        CheckConstraint(
            "decision_scope = 'NEXT_TRAINING_STAGE'", name="ck_ntsd_scope"
        ),
        CheckConstraint(
            "length(trim(decision_reason)) BETWEEN 10 AND 2000",
            name="ck_ntsd_reason",
        ),
        CheckConstraint(
            "decision_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ntsd_evidence_sha256",
        ),
        CheckConstraint(
            "length(trim(decision_evidence_ref)) BETWEEN 3 AND 500",
            name="ck_ntsd_evidence_ref",
        ),
        CheckConstraint(
            "decided_by_user_id <> person_id", name="ck_ntsd_human_independence"
        ),
        CheckConstraint("revision >= 1", name="ck_ntsd_positive_revision"),
        CheckConstraint(
            "(revision = 1 AND supersedes_decision_id IS NULL "
            "AND source_review_request_id IS NULL) OR "
            "(revision > 1 AND supersedes_decision_id IS NOT NULL "
            "AND source_review_request_id IS NOT NULL)",
            name="ck_ntsd_replacement_lineage_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    handoff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    outcome_id: Mapped[uuid.UUID] = mapped_column(index=True)
    person_id: Mapped[uuid.UUID] = mapped_column(index=True)
    decision_scope: Mapped[str] = mapped_column(String(40))
    decision: Mapped[NextTrainingStageDecisionValue] = mapped_column(
        Enum(NextTrainingStageDecisionValue, native_enum=False)
    )
    decision_reason: Mapped[str] = mapped_column(Text)
    decided_by_user_id: Mapped[uuid.UUID]
    decision_evidence_ref: Mapped[str] = mapped_column(String(500))
    decision_evidence_sha256: Mapped[str] = mapped_column(String(64))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    source_review_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NextTrainingStageReviewRequest(Base):
    __tablename__ = "next_training_stage_review_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "next_training_stage_decision_id",
                "organization_id",
                "handoff_id",
                "decision_scope",
                "source_decision",
            ],
            [
                "next_training_stage_decisions.id",
                "next_training_stage_decisions.organization_id",
                "next_training_stage_decisions.handoff_id",
                "next_training_stage_decisions.decision_scope",
                "next_training_stage_decisions.decision",
            ],
            name="fk_ntsrr_adverse_decision",
        ),
        ForeignKeyConstraint(
            ["requester_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsrr_requester_scope",
        ),
        UniqueConstraint(
            "organization_id",
            "next_training_stage_decision_id",
            "requester_user_id",
            name="uq_ntsrr_decision_person",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "next_training_stage_decision_id",
            "requester_user_id",
            name="uq_ntsrr_assignment_scope",
        ),
        CheckConstraint(
            "decision_scope = 'NEXT_TRAINING_STAGE'", name="ck_ntsrr_scope"
        ),
        CheckConstraint(
            "source_decision IN ('DEFER', 'NOT_READY')",
            name="ck_ntsrr_adverse_decision",
        ),
        CheckConstraint("status = 'RECEIVED'", name="ck_ntsrr_received_only"),
        CheckConstraint(
            "length(trim(reason)) BETWEEN 10 AND 2000", name="ck_ntsrr_reason"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    handoff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    next_training_stage_decision_id: Mapped[uuid.UUID] = mapped_column(index=True)
    decision_scope: Mapped[str] = mapped_column(String(40))
    source_decision: Mapped[NextTrainingStageDecisionValue] = mapped_column(
        Enum(NextTrainingStageDecisionValue, native_enum=False)
    )
    requester_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[NextTrainingStageReviewRequestStatus] = mapped_column(
        Enum(NextTrainingStageReviewRequestStatus, native_enum=False)
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NextTrainingStageReviewAssignment(Base):
    __tablename__ = "next_training_stage_review_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "review_request_id",
                "organization_id",
                "source_decision_id",
                "person_id",
            ],
            [
                "next_training_stage_review_requests.id",
                "next_training_stage_review_requests.organization_id",
                "next_training_stage_review_requests.next_training_stage_decision_id",
                "next_training_stage_review_requests.requester_user_id",
            ],
            name="fk_ntsra_request_scope",
        ),
        ForeignKeyConstraint(
            ["reviewer_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsra_reviewer_scope",
        ),
        ForeignKeyConstraint(
            ["assigned_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ntsra_assigner_scope",
        ),
        UniqueConstraint("review_request_id", name="uq_ntsra_request"),
        UniqueConstraint(
            "id",
            "organization_id",
            "review_request_id",
            "reviewer_user_id",
            name="uq_ntsra_resolution_scope",
        ),
        CheckConstraint(
            "reviewer_user_id <> person_id", name="ck_ntsra_reviewer_not_person"
        ),
        CheckConstraint(
            "assigned_by_user_id <> reviewer_user_id",
            name="ck_ntsra_assigner_not_reviewer",
        ),
        CheckConstraint(
            "length(trim(assignment_reason)) BETWEEN 10 AND 1000",
            name="ck_ntsra_reason",
        ),
        CheckConstraint(
            "length(trim(assignment_evidence_ref)) BETWEEN 3 AND 300",
            name="ck_ntsra_evidence_ref",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    review_request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source_decision_id: Mapped[uuid.UUID] = mapped_column(index=True)
    person_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_reason: Mapped[str] = mapped_column(Text)
    assignment_evidence_ref: Mapped[str] = mapped_column(String(300))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NextTrainingStageReviewResolution(Base):
    __tablename__ = "next_training_stage_review_resolutions"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "assignment_id",
                "organization_id",
                "review_request_id",
                "reviewer_user_id",
            ],
            [
                "next_training_stage_review_assignments.id",
                "next_training_stage_review_assignments.organization_id",
                "next_training_stage_review_assignments.review_request_id",
                "next_training_stage_review_assignments.reviewer_user_id",
            ],
            name="fk_ntsrrs_assignment_scope",
        ),
        UniqueConstraint("review_request_id", name="uq_ntsrrs_request"),
        UniqueConstraint("assignment_id", name="uq_ntsrrs_assignment"),
        CheckConstraint(
            "status IN ('UPHELD', 'OVERTURNED', 'RETURNED_FOR_REVIEW')",
            name="ck_ntsrrs_terminal_status",
        ),
        CheckConstraint(
            "length(trim(resolution_reason)) BETWEEN 10 AND 2000",
            name="ck_ntsrrs_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    review_request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[NextTrainingStageReviewResolutionStatus] = mapped_column(
        Enum(NextTrainingStageReviewResolutionStatus, native_enum=False)
    )
    resolution_reason: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ControlledTaskAuthorization(Base):
    __tablename__ = "controlled_task_authorizations"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "target_journey_stage_version_id",
                "organization_id",
                "target_journey_version_id",
                "task_version_id",
            ],
            [
                "journey_stage_versions.id",
                "journey_stage_versions.organization_id",
                "journey_stage_versions.journey_version_id",
                "journey_stage_versions.task_version_id",
            ],
            name="fk_cta_stage_lineage",
        ),
        *(
            ForeignKeyConstraint(
                [column, "organization_id"],
                ["users.id", "users.organization_id"],
                name=name,
            )
            for column, name in (
                ("project_owner_user_id", "fk_cta_project_owner_scope"),
                ("newcomer_operations_owner_user_id", "fk_cta_operations_owner_scope"),
                ("data_security_owner_user_id", "fk_cta_data_security_owner_scope"),
                ("reviewer_owner_user_id", "fk_cta_reviewer_owner_scope"),
                ("primary_reviewer_user_id", "fk_cta_primary_reviewer_scope"),
                ("backup_reviewer_user_id", "fk_cta_backup_reviewer_scope"),
                ("created_by_user_id", "fk_cta_created_by_scope"),
                ("activated_by_user_id", "fk_cta_activated_by_scope"),
                ("revoked_by_user_id", "fk_cta_revoked_by_scope"),
                ("expired_by_user_id", "fk_cta_expired_by_scope"),
            )
        ),
        UniqueConstraint("id", "organization_id", name="uq_cta_id_org"),
        UniqueConstraint(
            "id", "organization_id", "scope_sha256", name="uq_cta_scope_hash_ref"
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "target_journey_version_id",
            "target_journey_stage_version_id",
            "task_version_id",
            "primary_reviewer_user_id",
            name="uq_cta_acceptance_lineage",
        ),
        UniqueConstraint(
            "organization_id",
            "target_journey_version_id",
            "target_journey_stage_version_id",
            "task_version_id",
            "authorization_version",
            name="uq_cta_stage_business_version",
        ),
        CheckConstraint(
            "authorization_scope = 'NEWCOMER_CONTROLLED_TRAINING'",
            name="ck_cta_scope",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PENDING_APPROVALS','ACTIVE','REVOKED','EXPIRED')",
            name="ck_cta_status",
        ),
        CheckConstraint(
            "authorization_version >= 1 AND revision >= 1",
            name="ck_cta_positive_versions",
        ),
        CheckConstraint(
            "task_version_sha256 ~ '^[0-9a-f]{64}$' AND "
            "scope_sha256 ~ '^[0-9a-f]{64}$' AND "
            "policy_snapshot_sha256 ~ '^[0-9a-f]{64}$' AND "
            "policy_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_cta_hashes",
        ),
        CheckConstraint("valid_from < expires_at", name="ck_cta_validity"),
        CheckConstraint(
            "primary_reviewer_user_id <> backup_reviewer_user_id AND "
            "primary_reviewer_user_id NOT IN (project_owner_user_id, newcomer_operations_owner_user_id, data_security_owner_user_id, reviewer_owner_user_id) AND "
            "backup_reviewer_user_id NOT IN (project_owner_user_id, newcomer_operations_owner_user_id, data_security_owner_user_id, reviewer_owner_user_id)",
            name="ck_cta_distinct_reviewers",
        ),
        CheckConstraint(
            "((status IN ('ACTIVE','REVOKED','EXPIRED')) = (activated_by_user_id IS NOT NULL AND activated_at IS NOT NULL))",
            name="ck_cta_activation_audit",
        ),
        CheckConstraint(
            "(status = 'REVOKED' AND revoked_by_user_id IS NOT NULL AND revoked_at IS NOT NULL AND length(trim(revocation_reason)) BETWEEN 10 AND 500) OR "
            "(status <> 'REVOKED' AND revoked_by_user_id IS NULL AND revoked_at IS NULL AND revocation_reason IS NULL)",
            name="ck_cta_revocation_audit",
        ),
        CheckConstraint(
            "(status = 'EXPIRED' AND expired_by_user_id IS NOT NULL AND expired_at IS NOT NULL) OR "
            "(status <> 'EXPIRED' AND expired_by_user_id IS NULL AND expired_at IS NULL)",
            name="ck_cta_expiration_audit",
        ),
        CheckConstraint(
            "status <> 'EXPIRED' OR expired_at >= expires_at",
            name="ck_cta_expiration_time",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    authorization_scope: Mapped[str] = mapped_column(String(50))
    authorized_project_ref: Mapped[str] = mapped_column(String(500))
    target_journey_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    target_journey_stage_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    task_version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    task_version_sha256: Mapped[str] = mapped_column(String(64))
    authorization_version: Mapped[int]
    scope_sha256: Mapped[str] = mapped_column(String(64))
    project_owner_user_id: Mapped[uuid.UUID]
    newcomer_operations_owner_user_id: Mapped[uuid.UUID]
    data_security_owner_user_id: Mapped[uuid.UUID]
    reviewer_owner_user_id: Mapped[uuid.UUID]
    primary_reviewer_user_id: Mapped[uuid.UUID]
    backup_reviewer_user_id: Mapped[uuid.UUID]
    policy_snapshot_ref: Mapped[str] = mapped_column(String(500))
    policy_snapshot_version: Mapped[str] = mapped_column(String(80))
    policy_snapshot_sha256: Mapped[str] = mapped_column(String(64))
    policy_evidence_ref: Mapped[str] = mapped_column(String(500))
    policy_evidence_sha256: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ControlledTaskAuthorizationStatus] = mapped_column(
        Enum(ControlledTaskAuthorizationStatus, native_enum=False)
    )
    revision: Mapped[int]
    created_by_user_id: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expired_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ControlledTaskAuthorizationApproval(Base):
    __tablename__ = "controlled_task_authorization_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["authorization_id", "organization_id", "signed_scope_sha256"],
            [
                "controlled_task_authorizations.id",
                "controlled_task_authorizations.organization_id",
                "controlled_task_authorizations.scope_sha256",
            ],
            name="fk_ctaa_authorization_scope",
        ),
        ForeignKeyConstraint(
            ["signer_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_ctaa_signer_scope",
        ),
        UniqueConstraint(
            "authorization_id", "approval_role", name="uq_ctaa_authorization_role"
        ),
        CheckConstraint(
            "approval_role IN ('NEWCOMER_OPERATIONS_OWNER','PROJECT_OWNER','DATA_SECURITY_OWNER','REVIEWER_OWNER')",
            name="ck_ctaa_role",
        ),
        CheckConstraint(
            "decision IN ('APPROVE','REJECT')", name="ck_ctaa_decision"
        ),
        CheckConstraint(
            "signed_scope_sha256 ~ '^[0-9a-f]{64}$' AND signature_evidence_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ctaa_hashes",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    authorization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    approval_role: Mapped[ControlledTaskAuthorizationApprovalRole] = mapped_column(
        Enum(ControlledTaskAuthorizationApprovalRole, native_enum=False)
    )
    signer_user_id: Mapped[uuid.UUID]
    decision: Mapped[ControlledTaskAuthorizationApprovalDecision] = mapped_column(
        Enum(ControlledTaskAuthorizationApprovalDecision, native_enum=False)
    )
    signed_scope_sha256: Mapped[str] = mapped_column(String(64))
    signature_evidence_ref: Mapped[str] = mapped_column(String(500))
    signature_evidence_sha256: Mapped[str] = mapped_column(String(64))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HandoffAcceptance(Base):
    __tablename__ = "handoff_acceptances"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "next_training_stage_decision_id",
                "organization_id",
                "handoff_id",
                "decision_scope",
                "decision_value",
                "accepted_by_user_id",
            ],
            [
                "next_training_stage_decisions.id",
                "next_training_stage_decisions.organization_id",
                "next_training_stage_decisions.handoff_id",
                "next_training_stage_decisions.decision_scope",
                "next_training_stage_decisions.decision",
                "next_training_stage_decisions.person_id",
            ],
            name="fk_ha_ready_decision_person",
        ),
        ForeignKeyConstraint(
            [
                "controlled_task_authorization_id",
                "organization_id",
                "target_journey_version_id",
                "target_journey_stage_version_id",
                "target_task_version_id",
                "target_reviewer_user_id",
            ],
            [
                "controlled_task_authorizations.id",
                "controlled_task_authorizations.organization_id",
                "controlled_task_authorizations.target_journey_version_id",
                "controlled_task_authorizations.target_journey_stage_version_id",
                "controlled_task_authorizations.task_version_id",
                "controlled_task_authorizations.primary_reviewer_user_id",
            ],
            name="fk_ha_authorized_lineage",
        ),
        ForeignKeyConstraint(
            [
                "target_enrollment_id",
                "organization_id",
                "accepted_by_user_id",
                "target_journey_version_id",
                "target_reviewer_user_id",
            ],
            [
                "enrollments.id",
                "enrollments.organization_id",
                "enrollments.learner_id",
                "enrollments.journey_version_id",
                "enrollments.reviewer_id",
            ],
            name="fk_ha_target_enrollment_lineage",
        ),
        ForeignKeyConstraint(
            [
                "target_assignment_id",
                "organization_id",
                "target_enrollment_id",
                "target_journey_stage_version_id",
                "target_task_version_id",
            ],
            [
                "assignments.id",
                "assignments.organization_id",
                "assignments.enrollment_id",
                "assignments.journey_stage_version_id",
                "assignments.task_version_id",
            ],
            name="fk_ha_target_assignment_lineage",
        ),
        UniqueConstraint("handoff_id", name="uq_ha_handoff"),
        UniqueConstraint("target_enrollment_id", name="uq_ha_target_enrollment"),
        UniqueConstraint("target_assignment_id", name="uq_ha_target_assignment"),
        CheckConstraint(
            "decision_scope = 'NEXT_TRAINING_STAGE'", name="ck_ha_decision_scope"
        ),
        CheckConstraint("decision_value = 'READY'", name="ck_ha_ready_decision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    handoff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    accepted_by_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    next_training_stage_decision_id: Mapped[uuid.UUID]
    decision_scope: Mapped[str] = mapped_column(String(40))
    decision_value: Mapped[NextTrainingStageDecisionValue] = mapped_column(
        Enum(NextTrainingStageDecisionValue, native_enum=False)
    )
    controlled_task_authorization_id: Mapped[uuid.UUID]
    target_journey_version_id: Mapped[uuid.UUID]
    target_journey_stage_version_id: Mapped[uuid.UUID]
    target_task_version_id: Mapped[uuid.UUID]
    target_reviewer_user_id: Mapped[uuid.UUID]
    target_enrollment_id: Mapped[uuid.UUID]
    target_assignment_id: Mapped[uuid.UUID]
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_outbox_events_owner_scope",
        ),
        ForeignKeyConstraint(
            ["actor_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_outbox_events_actor_scope",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "owner_id",
            "aggregate_id",
            name="uq_outbox_notification_fixed_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_version: Mapped[int] = mapped_column(default=1)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus, native_enum=False), index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lock_token: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outcome_id", "organization_id", "recipient_user_id"],
            ["outcomes.id", "outcomes.organization_id", "outcomes.learner_id"],
            name="fk_notification_deliveries_outcome_recipient",
        ),
        ForeignKeyConstraint(
            ["event_id", "organization_id", "recipient_user_id", "outcome_id"],
            [
                "outbox_events.id",
                "outbox_events.organization_id",
                "outbox_events.owner_id",
                "outbox_events.aggregate_id",
            ],
            name="fk_notification_deliveries_event_scope",
        ),
        UniqueConstraint("event_id", name="uq_notification_deliveries_event"),
        UniqueConstraint(
            "event_id",
            "recipient_user_id",
            "channel",
            "template_version",
            name="uq_notification_deliveries_dedupe",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_notification_deliveries_attempts"),
        CheckConstraint("revision >= 1", name="ck_notification_deliveries_revision"),
        CheckConstraint(
            "redrive_count >= 0 AND attempt_offset >= 0 AND attempt_offset <= attempt_count",
            name="ck_notification_deliveries_redrive",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND attempt_count = attempt_offset AND delivered_at IS NULL) "
            "OR (status = 'SENDING' AND attempt_count > attempt_offset AND delivered_at IS NULL) "
            "OR (status = 'DELIVERED' AND attempt_count >= 1 AND delivered_at IS NOT NULL) "
            "OR (status = 'RETRY_WAIT' AND attempt_count > attempt_offset "
            "AND next_attempt_at IS NOT NULL AND last_error_code IS NOT NULL "
            "AND delivered_at IS NULL) "
            "OR (status = 'DEAD' AND attempt_count > attempt_offset "
            "AND next_attempt_at IS NULL AND last_error_code IS NOT NULL "
            "AND delivered_at IS NULL)",
            name="ck_notification_deliveries_state_fields",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    outcome_id: Mapped[uuid.UUID]
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False)
    )
    template_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False), index=True
    )
    attempt_count: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revision: Mapped[int] = mapped_column(default=1)
    redrive_count: Mapped[int] = mapped_column(default=0)
    attempt_offset: Mapped[int] = mapped_column(default=0)


class NotificationEndpoint(Base):
    __tablename__ = "notification_endpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_notification_endpoints_user_scope",
        ),
        UniqueConstraint(
            "organization_id",
            "user_id",
            "channel",
            name="uq_notification_endpoint_user_channel",
        ),
        CheckConstraint("channel = 'FEISHU'", name="ck_notification_endpoint_channel"),
        CheckConstraint(
            "receive_id_type = 'open_id'",
            name="ck_notification_endpoint_receive_id_type",
        ),
        CheckConstraint("key_version = 1", name="ck_notification_endpoint_key_version"),
        CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')",
            name="ck_notification_endpoint_status",
        ),
        CheckConstraint(
            "source = 'OPERATOR_CONFIG'", name="ck_notification_endpoint_source"
        ),
        CheckConstraint("revision >= 1", name="ck_notification_endpoint_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False)
    )
    receive_id_type: Mapped[str] = mapped_column(String(24))
    encrypted_receive_id: Mapped[str] = mapped_column(Text)
    recipient_fingerprint: Mapped[str] = mapped_column(String(64))
    key_version: Mapped[int] = mapped_column(default=1)
    status: Mapped[NotificationEndpointStatus] = mapped_column(
        Enum(NotificationEndpointStatus, native_enum=False), index=True
    )
    source: Mapped[str] = mapped_column(String(40), default="OPERATOR_CONFIG")
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", "attempt_number", name="uq_notification_attempt_number"
        ),
        CheckConstraint("attempt_number >= 1", name="ck_notification_attempt_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id"), index=True
    )
    attempt_number: Mapped[int]
    status: Mapped[NotificationAttemptStatus] = mapped_column(
        Enum(NotificationAttemptStatus, native_enum=False)
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LocalNotificationReceipt(Base):
    __tablename__ = "local_notification_receipts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", name="uq_local_notification_receipt_delivery"
        ),
        UniqueConstraint("dedupe_key", name="uq_local_notification_receipt_dedupe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id")
    )
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExternalNotificationReceipt(Base):
    __tablename__ = "external_notification_receipts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id", name="uq_external_notification_receipt_delivery"
        ),
        UniqueConstraint(
            "dedupe_key", name="uq_external_notification_receipt_dedupe"
        ),
        CheckConstraint("provider = 'FEISHU'", name="ck_external_receipt_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_message_id: Mapped[str] = mapped_column(String(200))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    release: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("package_id", name="uq_import_batches_package_id"),
        UniqueConstraint("package_checksum", name="uq_import_batches_checksum"),
        UniqueConstraint("id", "organization_id", name="uq_import_batches_fixed_scope"),
        CheckConstraint("schema_version = 1", name="ck_import_batches_schema_v1"),
        CheckConstraint(
            "status IN ('APPLIED', 'APPLIED_WITH_QUARANTINE')",
            name="ck_import_batches_status",
        ),
        CheckConstraint(
            "record_count >= 0 AND imported_count >= 0 AND replayed_count >= 0 "
            "AND quarantined_count >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    package_checksum: Mapped[str] = mapped_column(String(64))
    source_revision: Mapped[str] = mapped_column(String(120))
    schema_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(40))
    record_count: Mapped[int]
    imported_count: Mapped[int]
    replayed_count: Mapped[int]
    quarantined_count: Mapped[int]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImportRecord(Base):
    __tablename__ = "import_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "organization_id"],
            ["import_batches.id", "import_batches.organization_id"],
            name="fk_import_records_batch_scope",
        ),
        UniqueConstraint("batch_id", "source_key", name="uq_import_records_batch_key"),
        CheckConstraint(
            "status IN ('IMPORTED', 'REPLAYED', 'QUARANTINED')",
            name="ck_import_records_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_namespace: Mapped[str] = mapped_column(String(80))
    source_key: Mapped[str] = mapped_column(String(120))
    payload_hash: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(40))
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "command", "key", name="uq_idempotency_actor_command_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    command: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataRightsRequest(Base):
    __tablename__ = "data_rights_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('DELETE', 'CORRECT')",
            name="ck_data_rights_request_type",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'COMPLETED', 'REJECTED')",
            name="ck_data_rights_request_status",
        ),
        CheckConstraint(
            "due_at > requested_at",
            name="ck_data_rights_request_due_after_request",
        ),
        CheckConstraint(
            "(legal_hold = false AND legal_hold_reason IS NULL) "
            "OR (legal_hold = true AND legal_hold_reason IS NOT NULL)",
            name="ck_data_rights_request_legal_hold",
        ),
        CheckConstraint(
            "(status = 'OPEN' AND completed_at IS NULL AND completed_by IS NULL "
            "AND resolution_code IS NULL) "
            "OR (status IN ('COMPLETED', 'REJECTED') AND completed_at IS NOT NULL "
            "AND completed_by IS NOT NULL AND resolution_code IS NOT NULL)",
            name="ck_data_rights_request_resolution",
        ),
        CheckConstraint("revision >= 1", name="ck_data_rights_request_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    subject_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    request_type: Mapped[DataRightsRequestType] = mapped_column(
        Enum(DataRightsRequestType, native_enum=False)
    )
    status: Mapped[DataRightsRequestStatus] = mapped_column(
        Enum(DataRightsRequestStatus, native_enum=False), index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_hold_reason: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    resolution_code: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(default=1)
