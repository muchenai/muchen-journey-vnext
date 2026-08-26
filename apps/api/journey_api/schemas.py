from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from journey_api.construction_module_content import ConstructionModuleContentPackage
from journey_api.shared_domain import AiUseDisclosure


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevisionCommand(StrictModel):
    expected_revision: int = Field(ge=1)


class CompleteLearningMaterialCommand(StrictModel):
    task_version: int = Field(ge=1)


class SubmissionCommand(RevisionCommand):
    body: str = Field(min_length=40, max_length=8_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)
    ai_use: AiUseDisclosure = Field(
        default_factory=lambda: AiUseDisclosure(used=False)
    )

    @field_validator("attachment_ids")
    @classmethod
    def unique_submission_attachments(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Attachment IDs must be unique")
        return values


class SaveSubmissionDraftCommand(RevisionCommand):
    body: str = Field(default="", max_length=8_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @field_validator("attachment_ids")
    @classmethod
    def unique_draft_attachments(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Attachment IDs must be unique")
        return values


AttachmentContentType = Literal[
    "text/plain", "application/pdf", "image/png", "image/jpeg"
]


class PresignAttachmentCommand(StrictModel):
    assignment_id: UUID
    purpose: Literal["SUBMISSION_EVIDENCE"] = "SUBMISSION_EVIDENCE"
    original_filename: str = Field(min_length=1, max_length=180)
    content_type: AttachmentContentType
    size_bytes: int = Field(ge=1, le=100_000_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CompleteAttachmentCommand(StrictModel):
    size_bytes: int = Field(ge=1, le=5_242_880)
    content_type: AttachmentContentType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


ReviewerDimensionKey = str


class RubricEvaluationCommand(StrictModel):
    dimension_key: ReviewerDimensionKey = Field(
        min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]+$"
    )
    rating: Literal["MEETS", "NEEDS_WORK"]
    score: int | None = Field(default=None, ge=0, le=15)
    feedback: str = Field(min_length=5, max_length=500)

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str) -> str:
        return value.strip()


class FinalizeReviewCommand(RevisionCommand):
    overall_decision: Literal["APPROVE", "REQUEST_REVISION"]
    overall_feedback: str = Field(min_length=10, max_length=2_000)
    rubric_evaluations: list[RubricEvaluationCommand] = Field(
        min_length=1, max_length=6
    )
    ai_use: AiUseDisclosure = Field(
        default_factory=lambda: AiUseDisclosure(used=False)
    )

    @field_validator("overall_feedback")
    @classmethod
    def normalize_overall_feedback(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_rubric_dimensions(self) -> "FinalizeReviewCommand":
        actual = {item.dimension_key for item in self.rubric_evaluations}
        if len(actual) != len(self.rubric_evaluations):
            raise ValueError("Rubric dimensions must be unique")
        return self


class CreateInviteCommand(StrictModel):
    purpose: str = Field(min_length=3, max_length=200)
    expires_in_hours: int = Field(ge=1, le=168)
    role: Literal["LEARNER"] = "LEARNER"
    reviewer_id: UUID
    task_version_id: UUID | None = None
    journey_version_id: UUID | None = None
    target_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_invite_target(self) -> "CreateInviteCommand":
        if (self.task_version_id is None) == (self.journey_version_id is None):
            raise ValueError("Invite must target exactly one task or journey version")
        return self


class CreateLearnerReentryCommand(RevisionCommand):
    expires_in_minutes: int = Field(default=30, ge=5, le=60)
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reentry_reason(cls, value: str) -> str:
        return value.strip()


class RevokeInviteCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)


class UpdateInvitationControlCommand(RevisionCommand):
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_invitation_control_reason(cls, value: str) -> str:
        return value.strip()


class AssignEnrollmentReviewerCommand(RevisionCommand):
    reviewer_id: UUID
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_assignment_reason(cls, value: str) -> str:
        return value.strip()


class CancelEnrollmentCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_cancel_reason(cls, value: str) -> str:
        return value.strip()


class ConfigureNotificationEndpointCommand(StrictModel):
    expected_revision: int = Field(ge=0)
    receive_id: str = Field(pattern=r"^ou_[A-Za-z0-9_-]{8,120}$")
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("receive_id", "reason")
    @classmethod
    def normalize_notification_endpoint_fields(cls, value: str) -> str:
        return value.strip()


class RevokeNotificationEndpointCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_notification_revoke_reason(cls, value: str) -> str:
        return value.strip()


class RedriveNotificationCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_notification_redrive_reason(cls, value: str) -> str:
        return value.strip()


class CreateDataRightsRequestCommand(StrictModel):
    subject_user_id: UUID
    request_type: Literal["DELETE", "CORRECT"]
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_data_rights_reason(cls, value: str) -> str:
        return value.strip()


class SetDataRightsLegalHoldCommand(RevisionCommand):
    legal_hold: bool
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_legal_hold_reason(cls, value: str) -> str:
        return value.strip()


class RejectDataRightsRequestCommand(RevisionCommand):
    resolution_code: Literal["DUPLICATE", "INVALID_SCOPE", "IDENTITY_UNVERIFIED"]
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_data_rights_rejection_reason(cls, value: str) -> str:
        return value.strip()


class CreateTaskDefinitionCommand(StrictModel):
    stable_key: str = Field(min_length=3, max_length=80, pattern=r"^[A-Z][A-Z0-9_-]+$")

    @field_validator("stable_key")
    @classmethod
    def normalize_stable_key(cls, value: str) -> str:
        return value.strip().upper()


RubricDimensionKey = str


class RubricDimensionInput(StrictModel):
    dimension_key: RubricDimensionKey = Field(
        min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]+$"
    )
    title: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=5, max_length=500)
    evidence_expected: str = Field(min_length=5, max_length=500)
    levels: dict[Literal["MEETS", "NEEDS_WORK"], str]
    required: Literal[True] = True
    feedback_prompt: str = Field(min_length=5, max_length=500)
    blocking_rule: Literal["REQUIRE_FEEDBACK"] = "REQUIRE_FEEDBACK"
    max_points: int | None = Field(default=None, ge=1, le=15)
    meets_threshold: int | None = Field(default=None, ge=1, le=15)
    score_category: Literal[
        "rule_decomposition",
        "model_judgement",
        "rationale_writing",
        "data_construction",
    ] | None = None

    @model_validator(mode="after")
    def validate_levels(self) -> "RubricDimensionInput":
        if set(self.levels) != {"MEETS", "NEEDS_WORK"}:
            raise ValueError("Rubric levels must contain MEETS and NEEDS_WORK exactly")
        if any(not value.strip() for value in self.levels.values()):
            raise ValueError("Rubric level descriptions cannot be blank")
        if bool(self.max_points) != bool(self.meets_threshold):
            raise ValueError("Scored rubric dimensions need max points and threshold together")
        if self.meets_threshold and self.max_points and self.meets_threshold > self.max_points:
            raise ValueError("Rubric threshold cannot exceed max points")
        if self.max_points is not None and self.score_category is None:
            raise ValueError("Scored rubric dimensions need a score category")
        return self


class RubricVersionInput(StrictModel):
    version: Literal[1] = 1
    dimensions: list[RubricDimensionInput] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "RubricVersionInput":
        actual = {dimension.dimension_key for dimension in self.dimensions}
        if len(actual) != len(self.dimensions):
            raise ValueError("Rubric dimensions must be unique")
        return self


class LearningMaterialInput(StrictModel):
    key: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9_-]+$",
    )
    title: str = Field(min_length=2, max_length=160)
    kind: Literal["TEXT", "HTTPS_LINK"]
    source_label: str = Field(min_length=2, max_length=160)
    body: str | None = Field(default=None, min_length=20, max_length=20_000)
    url: str | None = Field(
        default=None,
        min_length=12,
        max_length=2_000,
        pattern=r"^https://[^\s]+$",
    )
    estimated_duration_minutes: int = Field(ge=1, le=120)
    required: bool = True

    @model_validator(mode="after")
    def validate_payload(self) -> "LearningMaterialInput":
        if self.kind == "TEXT" and (self.body is None or self.url is not None):
            raise ValueError("TEXT material requires body and forbids url")
        if self.kind == "HTTPS_LINK" and (self.url is None or self.body is not None):
            raise ValueError("HTTPS_LINK material requires url and forbids body")
        return self


class TaskContentInput(StrictModel):
    title: str = Field(min_length=3, max_length=180)
    purpose: str = Field(min_length=10, max_length=2_000)
    learner_outcome: str = Field(min_length=10, max_length=2_000)
    instructions: list[str] = Field(min_length=1, max_length=12)
    completion_criteria: list[str] = Field(min_length=1, max_length=12)
    required_deliverables: list[str] = Field(min_length=1, max_length=12)
    content_source_notes: list[str] = Field(min_length=1, max_length=20)
    change_summary: str = Field(min_length=10, max_length=1_000)
    reviewer_calibration_note: str = Field(min_length=10, max_length=1_000)
    allowed_attachment_types: list[AttachmentContentType] = Field(
        default_factory=list, max_length=4
    )
    max_attachment_size_bytes: int = Field(default=0, ge=0, le=5_242_880)
    reference_materials: list[str] = Field(default_factory=list, max_length=20)
    learning_materials: list[LearningMaterialInput] = Field(
        default_factory=list, max_length=12
    )
    estimated_duration_minutes: int = Field(ge=1, le=480)
    rubric: RubricVersionInput
    reviewer_role: Literal["REVIEWER"] = "REVIEWER"
    feedback_sla_business_days: int = Field(ge=1, le=10)
    sensitivity: Literal["INTERNAL"] = "INTERNAL"
    audience: Literal["LEARNER"] = "LEARNER"
    @model_validator(mode="after")
    def validate_attachment_policy(self) -> "TaskContentInput":
        if len(set(self.allowed_attachment_types)) != len(self.allowed_attachment_types):
            raise ValueError("Attachment content types must be unique")
        if bool(self.allowed_attachment_types) != bool(self.max_attachment_size_bytes):
            raise ValueError("Attachment types and size limit must be configured together")
        material_keys = [material.key for material in self.learning_materials]
        if len(material_keys) != len(set(material_keys)):
            raise ValueError("Learning material keys must be unique")
        return self

    @field_validator(
        "instructions",
        "completion_criteria",
        "required_deliverables",
        "content_source_notes",
        "reference_materials",
    )
    @classmethod
    def validate_text_items(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("Task list items must be non-blank and at most 500 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Task list items must be unique")
        return normalized


class PublishTaskVersionCommand(TaskContentInput):
    expected_revision: int = Field(ge=1)
    reviewed_by: UUID


class CreateContentDraftCommand(StrictModel):
    content: TaskContentInput


class CreateContentEditorCommand(StrictModel):
    display_name: str = Field(min_length=1, max_length=120)
    expected_absent: Literal[True]

    @field_validator("display_name")
    @classmethod
    def normalize_content_editor_name(cls, value: str) -> str:
        return value.strip()


class UpdateContentDraftCommand(RevisionCommand):
    content: TaskContentInput


class SubmitContentDraftCommand(RevisionCommand):
    review_note: str = Field(min_length=10, max_length=1_000)

    @field_validator("review_note")
    @classmethod
    def normalize_review_note(cls, value: str) -> str:
        return value.strip()


class PublishContentDraftCommand(RevisionCommand):
    expected_definition_revision: int = Field(ge=1)
    reviewed_by: UUID
    review_acknowledged: Literal[True]


class LearningMaterialOut(StrictModel):
    key: str
    title: str
    kind: Literal["TEXT", "HTTPS_LINK"]
    source_label: str
    body: str | None = None
    url: str | None = None
    estimated_duration_minutes: int
    required: bool
    completed_at: datetime | None = None


class LearningMaterialCompletionOut(StrictModel):
    assignment_id: UUID
    task_version: int
    material_key: str
    completed_at: datetime
    idempotency_replay: bool = False


class LearningMaterialCompletionResponse(StrictModel):
    data: LearningMaterialCompletionOut
    request_id: str


class InviteOut(StrictModel):
    id: UUID
    purpose: str
    role: Literal["LEARNER"]
    status: str
    expires_at: datetime
    revision: int
    journey_version_id: UUID | None = None


class CreateInviteOut(InviteOut):
    invite_token: str
    idempotency_replay: bool = False


class CreateInviteResponse(StrictModel):
    data: CreateInviteOut
    request_id: str


class InviteListOut(StrictModel):
    items: list[InviteOut]


class InviteListResponse(StrictModel):
    data: InviteListOut
    request_id: str


class InvitationControlOut(StrictModel):
    state: Literal["OPEN", "FROZEN"]
    new_invites_enabled: bool
    revision: int = Field(ge=0)
    reason: str | None
    updated_at: datetime | None
    idempotency_replay: bool = False


class InvitationControlResponse(StrictModel):
    data: InvitationControlOut
    request_id: str


class JoinExchangeCommand(StrictModel):
    token: str = Field(min_length=32, max_length=256)
    return_to: Literal["/app"] = "/app"


class JoinExchangeOut(StrictModel):
    status: Literal["PENDING_IDENTITY", "PENDING_REENTRY"]
    flow: Literal["JOIN", "REENTRY"]
    purpose: str
    expires_at: datetime
    csrf_token: str
    safe_entry: Literal["/app"]


class JoinExchangeResponse(StrictModel):
    data: JoinExchangeOut
    request_id: str


class IdentityConfirmCommand(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    accepted_purpose: Literal[True]
    return_to: Literal["/app"] = "/app"


class IdentityConfirmOut(StrictModel):
    user_id: UUID
    organization_id: UUID
    roles: list[str]
    enrollment_status: Literal["ACTIVE"]
    safe_entry: Literal["/app"]
    expires_at: datetime
    csrf_token: str


class IdentityConfirmResponse(StrictModel):
    data: IdentityConfirmOut
    request_id: str


class CreateIdentityLinkCommand(StrictModel):
    target_user_id: UUID
    role: Literal["REVIEWER", "OPERATOR", "CONTENT_EDITOR"]
    expires_in_minutes: int = Field(default=30, ge=5, le=60)


class IdentityLinkOut(StrictModel):
    id: UUID
    target_user_id: UUID
    role: Literal["REVIEWER", "OPERATOR", "CONTENT_EDITOR"]
    status: str
    expires_at: datetime
    revision: int
    link_token: str
    start_path: str
    idempotency_replay: bool = False


class IdentityLinkResponse(StrictModel):
    data: IdentityLinkOut
    request_id: str


class IdentityAccessOut(StrictModel):
    user_id: UUID
    display_name: str
    role: Literal["REVIEWER", "OPERATOR", "CONTENT_EDITOR"]
    identity_id: UUID | None
    identity_status: Literal["UNLINKED", "LINKED", "REVOKED"]
    identity_revision: int | None
    identity_verified_at: datetime | None
    is_current_actor: bool
    link_id: UUID | None
    link_status: str | None
    link_revision: int | None
    link_expires_at: datetime | None
    allowed_commands: list[
        Literal[
            "create_identity_link",
            "revoke_identity_link",
            "revoke_external_identity",
        ]
    ]


class RevokedIdentityTransferCandidateOut(StrictModel):
    identity_id: UUID
    identity_revision: int
    source_user_id: UUID
    source_display_name: str
    source_roles: list[Literal["REVIEWER", "OPERATOR", "CONTENT_EDITOR"]]
    revoked_at: datetime
    active_session_count: int


class IdentityAccessListOut(StrictModel):
    items: list[IdentityAccessOut]
    revoked_transfer_candidates: list[RevokedIdentityTransferCandidateOut]


class IdentityAccessListResponse(StrictModel):
    data: IdentityAccessListOut
    request_id: str


class RevokeIdentityLinkCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)


class RevokeExternalIdentityCommand(RevisionCommand):
    reason: str = Field(min_length=10, max_length=500)


class TransferRevokedExternalIdentityCommand(RevisionCommand):
    target_user_id: UUID
    target_role: Literal["CONTENT_EDITOR"]
    reason: str = Field(min_length=10, max_length=500)


class OAuthStartCommand(StrictModel):
    return_to: Literal["/review", "/ops", "/content"]
    link_token: str | None = Field(default=None, min_length=32, max_length=256)


class OAuthStartOut(StrictModel):
    authorization_url: str
    expires_at: datetime


class OAuthStartResponse(StrictModel):
    data: OAuthStartOut
    request_id: str


class OAuthCallbackCommand(StrictModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=32, max_length=256)


class OAuthCallbackOut(StrictModel):
    safe_entry: Literal["/review", "/ops", "/content"]
    expires_at: datetime
    csrf_token: str


class OAuthCallbackResponse(StrictModel):
    data: OAuthCallbackOut
    request_id: str


class SessionOut(StrictModel):
    user_id: UUID
    organization_id: UUID
    display_name: str
    roles: list[str]
    scope: dict[str, str]
    safe_entry: str
    expires_at: datetime | None
    csrf_required: bool


class SessionResponse(StrictModel):
    data: SessionOut
    request_id: str


class SessionLogoutOut(StrictModel):
    status: Literal["LOGGED_OUT"]


class SessionLogoutResponse(StrictModel):
    data: SessionLogoutOut
    request_id: str


class CurrentActionOut(StrictModel):
    action_type: str
    stage: str
    resource_id: UUID
    title: str
    reason: str
    allowed_commands: list[str]
    revision: int
    responsible_party: str
    feedback_expectation: str
    journey: "JourneyProgressOut | None" = None


class JourneyProgressNodeOut(StrictModel):
    stable_key: str
    position: int
    stage_kind: Literal["DAY_0", "TREASURE", "ASSESSMENT"]
    completion_policy: Literal["LEARNER_EVIDENCE", "REVIEW_REQUIRED"]
    title: str
    short_description: str
    status: Literal["COMPLETED", "CURRENT", "LOCKED"]
    assignment_id: UUID


class JourneyProgressOut(StrictModel):
    journey_version_id: UUID
    stable_key: str
    version: int
    title: str
    completed_stages: int
    total_stages: int = Field(ge=0)
    current_stage_key: str | None
    nodes: list[JourneyProgressNodeOut]


class CurrentActionResponse(StrictModel):
    data: CurrentActionOut
    request_id: str


class LearnerEnrollmentOut(StrictModel):
    id: UUID
    status: Literal["PENDING_IDENTITY", "ACTIVE", "COMPLETED", "CANCELLED"]
    revision: int
    journey_version_id: UUID | None
    journey_stable_key: str | None
    journey_title: str | None
    journey_version: int | None
    reviewer_display_name: str


class LearnerEnrollmentListOut(StrictModel):
    items: list[LearnerEnrollmentOut]


class LearnerEnrollmentListResponse(StrictModel):
    data: LearnerEnrollmentListOut
    request_id: str


class AssignmentOut(StrictModel):
    id: UUID
    status: str
    revision: int
    allowed_commands: list[str]
    stable_task_key: str
    task_version: int
    task_title: str
    task_purpose: str
    learner_outcome: str
    instructions: list[str]
    completion_criteria: list[str]
    required_deliverables: list[str]
    allowed_attachment_types: list[str]
    max_attachment_size_bytes: int
    reference_materials: list[str]
    learning_materials: list[LearningMaterialOut]
    learning_experience: dict[str, object]
    estimated_duration_minutes: int
    feedback_sla_business_days: int
    rubric: dict[str, object]
    submission: "SubmissionOut | None"
    draft: "SubmissionDraftOut | None"
    available_attachments: list["AttachmentOut"]
    latest_revision_feedback: str | None
    journey_stage: "AssignmentJourneyStageOut | None" = None


class AssignmentJourneyStageOut(StrictModel):
    stable_key: str
    position: int
    stage_kind: Literal["DAY_0", "TREASURE", "ASSESSMENT"]
    completion_policy: Literal["LEARNER_EVIDENCE", "REVIEW_REQUIRED"]
    title: str
    short_description: str


class AssignmentResponse(StrictModel):
    data: AssignmentOut
    request_id: str


class TaskVersionOut(StrictModel):
    id: UUID
    task_definition_id: UUID
    stable_key: str
    version: int
    title: str
    purpose: str
    learner_outcome: str
    instructions: list[str]
    completion_criteria: list[str]
    required_deliverables: list[str]
    content_source_notes: list[str]
    change_summary: str
    reviewer_calibration_note: str
    allowed_attachment_types: list[str]
    max_attachment_size_bytes: int
    reference_materials: list[str]
    learning_materials: list[LearningMaterialInput]
    learning_experience: dict[str, object]
    estimated_duration_minutes: int
    rubric: dict[str, object]
    rubric_version: int
    reviewer_role: str
    feedback_sla_business_days: int
    sensitivity: str
    audience: str
    published_by: UUID
    reviewed_by: UUID
    published_at: datetime
    idempotency_replay: bool = False


class TaskVersionResponse(StrictModel):
    data: TaskVersionOut
    request_id: str


class ContentDraftOut(StrictModel):
    id: UUID
    task_definition_id: UUID
    stable_key: str
    owner_id: UUID
    status: Literal["DRAFT", "SUBMITTED", "PUBLISHED"]
    revision: int
    content: TaskContentInput
    submitted_at: datetime | None
    published_at: datetime | None
    published_task_version_id: UUID | None
    idempotency_replay: bool = False


class ContentDraftResponse(StrictModel):
    data: ContentDraftOut
    request_id: str


class ContentEditorOut(StrictModel):
    user_id: UUID
    display_name: str
    role: Literal["CONTENT_EDITOR"] = "CONTENT_EDITOR"
    status: Literal["ACTIVE"] = "ACTIVE"
    idempotency_replay: bool = False


class ContentEditorResponse(StrictModel):
    data: ContentEditorOut
    request_id: str


class ContentDraftListOut(StrictModel):
    items: list[ContentDraftOut]


class ContentDraftListResponse(StrictModel):
    data: ContentDraftListOut
    request_id: str


class TaskVersionSummaryOut(StrictModel):
    id: UUID
    version: int
    title: str
    published_at: datetime


class TaskDefinitionOut(StrictModel):
    id: UUID
    stable_key: str
    status: str
    revision: int
    content_owner_id: UUID
    versions: list[TaskVersionSummaryOut]
    idempotency_replay: bool = False


class TaskDefinitionResponse(StrictModel):
    data: TaskDefinitionOut
    request_id: str


class TaskDefinitionListOut(StrictModel):
    items: list[TaskDefinitionOut]


class TaskDefinitionListResponse(StrictModel):
    data: TaskDefinitionListOut
    request_id: str


class PublishFormalJourneyCommand(StrictModel):
    reviewed_by: UUID
    catalog_version: Literal[2] = 2
    expected_current_version: int = Field(default=0, ge=0)
    expected_absent: Literal[True] | None = None
    review_acknowledged: Literal[True]


class AssembleFormalJourneyV3Command(StrictModel):
    reviewed_by: UUID
    expected_current_version: int = Field(ge=1)
    task_version_ids: list[UUID] = Field(min_length=8, max_length=8)
    content_review_note: str = Field(min_length=20, max_length=1_000)
    review_acknowledged: Literal[True]

    @field_validator("task_version_ids")
    @classmethod
    def validate_unique_v3_stages(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != 8:
            raise ValueError("Journey V3 must bind eight unique TaskVersions")
        return values

    @field_validator("content_review_note")
    @classmethod
    def normalize_content_review_note(cls, value: str) -> str:
        return value.strip()


class FormalJourneyStageOut(StrictModel):
    id: UUID
    stable_key: str
    position: int
    stage_kind: Literal["DAY_0", "TREASURE", "ASSESSMENT"]
    completion_policy: Literal["LEARNER_EVIDENCE", "REVIEW_REQUIRED"]
    task_version_id: UUID
    title: str
    short_description: str


class FormalJourneyVersionOut(StrictModel):
    id: UUID
    stable_key: str
    version: int
    title: str
    purpose: str
    change_summary: str
    content_review_note: str
    published_at: datetime
    stages: list[FormalJourneyStageOut]
    idempotency_replay: bool = False


class PublishConstructionModulePackageCommand(StrictModel):
    package: ConstructionModuleContentPackage
    task_version_id: UUID
    owner_user_id: UUID
    primary_reviewer_user_id: UUID
    backup_reviewer_user_id: UUID
    reviewed_by: UUID
    expected_current_version: int = Field(ge=0)
    review_acknowledged: Literal[True]


class ConstructionModulePackageOut(StrictModel):
    binding_id: UUID
    module_key: Literal["ai-academy", "delivery-guild"]
    package_id: str
    package_version: str
    package_sha256: str
    journey_version_id: UUID
    journey_version: int
    journey_stage_version_id: UUID
    task_version_id: UUID
    effective_at: datetime
    expires_at: datetime | None
    status: Literal["PUBLISHED_CONTENT_BOUND"]
    idempotency_replay: bool = False


class ConstructionModulePackageResponse(StrictModel):
    data: ConstructionModulePackageOut
    request_id: str


class FormalJourneyVersionResponse(StrictModel):
    data: FormalJourneyVersionOut
    request_id: str


class FormalJourneyVersionListOut(StrictModel):
    items: list[FormalJourneyVersionOut]


class FormalJourneyVersionListResponse(StrictModel):
    data: FormalJourneyVersionListOut
    request_id: str


class CommandOut(StrictModel):
    resource_id: UUID
    status: str
    revision: int
    idempotency_replay: bool = False


class CommandResponse(StrictModel):
    data: CommandOut
    request_id: str


class EnrollmentOpsOut(StrictModel):
    id: UUID
    learner_id: UUID
    learner_display_name: str
    reviewer_id: UUID
    reviewer_display_name: str
    status: str
    revision: int
    journey_version_id: UUID | None
    assignment_statuses: list[str]
    open_review_status: str | None
    allowed_commands: list[str]


class EnrollmentOpsListOut(StrictModel):
    items: list[EnrollmentOpsOut]


class EnrollmentOpsListResponse(StrictModel):
    data: EnrollmentOpsListOut
    request_id: str


class EnrollmentMutationOut(CommandOut):
    reviewer_id: UUID


class EnrollmentMutationResponse(StrictModel):
    data: EnrollmentMutationOut
    request_id: str


class ReviewerWorkloadOut(StrictModel):
    binding_id: UUID
    module_key: Literal["ai-academy", "delivery-guild"]
    package_id: str
    package_version: str
    primary_reviewer_id: UUID
    primary_reviewer_display_name: str
    backup_reviewer_id: UUID
    backup_reviewer_display_name: str
    first_response_sla_minutes: int
    completion_sla_minutes: int
    active_enrollment_count: int
    open_review_count: int
    overdue_review_count: int
    capacity_limit: None = None
    capacity_status: Literal["PENDING_OWNER_CONTENT"]
    replacement_scope: Literal["PRIMARY_OR_NAMED_BACKUP_ONLY"]


class ReviewerWorkloadListOut(StrictModel):
    items: list[ReviewerWorkloadOut]


class ReviewerWorkloadListResponse(StrictModel):
    data: ReviewerWorkloadListOut
    request_id: str


class NotificationEndpointOut(StrictModel):
    id: UUID
    user_id: UUID
    channel: Literal["FEISHU"]
    receive_id_type: Literal["open_id"]
    status: Literal["ACTIVE", "REVOKED"]
    source: Literal["OPERATOR_CONFIG"]
    revision: int
    updated_at: datetime
    idempotency_replay: bool = False


class NotificationEndpointListOut(StrictModel):
    items: list[NotificationEndpointOut]


class NotificationEndpointResponse(StrictModel):
    data: NotificationEndpointOut
    request_id: str


class NotificationEndpointListResponse(StrictModel):
    data: NotificationEndpointListOut
    request_id: str


class NotificationOpsDeliveryOut(StrictModel):
    id: UUID
    recipient_user_id: UUID
    channel: str
    status: str
    attempt_count: int
    redrive_count: int
    revision: int
    last_error_code: str | None
    next_attempt_at: datetime | None
    delivered_at: datetime | None
    external_receipt_recorded: bool


class NotificationOpsDeliveryListOut(StrictModel):
    items: list[NotificationOpsDeliveryOut]


class NotificationOpsDeliveryResponse(StrictModel):
    data: NotificationOpsDeliveryOut
    request_id: str


class NotificationOpsDeliveryListResponse(StrictModel):
    data: NotificationOpsDeliveryListOut
    request_id: str


class DataRightsRequestOut(StrictModel):
    id: UUID
    subject_user_id: UUID
    request_type: Literal["DELETE", "CORRECT"]
    status: Literal["OPEN", "COMPLETED", "REJECTED"]
    requested_at: datetime
    due_at: datetime
    legal_hold: bool
    resolution_code: str | None
    resolved_at: datetime | None
    revision: int
    allowed_commands: list[
        Literal["set_legal_hold", "release_legal_hold", "reject_request"]
    ]
    idempotency_replay: bool = False


class DataRightsRequestResponse(StrictModel):
    data: DataRightsRequestOut
    request_id: str


class DataRightsRequestListOut(StrictModel):
    items: list[DataRightsRequestOut]


class DataRightsRequestListResponse(StrictModel):
    data: DataRightsRequestListOut
    request_id: str


class AuditEntryOut(StrictModel):
    id: UUID
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    result: str
    request_id: str
    safe_details: dict[str, str | int | bool]
    redacted_fields: list[str]
    occurred_at: datetime


class AuditListOut(StrictModel):
    items: list[AuditEntryOut]


class AuditListResponse(StrictModel):
    data: AuditListOut
    request_id: str


class RuntimeComponentOut(StrictModel):
    status: str
    release: str | None = None
    last_seen_at: datetime | None = None
    stale: bool | None = None


class RuntimeMetricsOut(StrictModel):
    outbox_backlog: int
    notification_retry_wait: int
    notification_dead: int
    oldest_pending_seconds: int
    permission_denials_24h: int


class RuntimeStatusOut(StrictModel):
    environment: Literal["local", "test", "staging", "production"]
    release: str
    config_schema_version: Literal[3]
    migration_revision: str
    api: RuntimeComponentOut
    database: RuntimeComponentOut
    worker: RuntimeComponentOut
    observability_mode: Literal["STRUCTURED_STDOUT"]
    external_observability_confirmed: Literal[False] = False
    metrics: RuntimeMetricsOut


class RuntimeStatusResponse(StrictModel):
    data: RuntimeStatusOut
    request_id: str


class AttachmentOut(StrictModel):
    id: UUID
    assignment_id: UUID
    purpose: Literal["SUBMISSION_EVIDENCE"]
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    scan_status: str


class PresignedAttachmentOut(AttachmentOut):
    upload_method: Literal["PUT"]
    upload_url: str
    upload_headers: dict[str, str]
    upload_expires_at: datetime
    idempotency_replay: bool = False


class PresignedAttachmentResponse(StrictModel):
    data: PresignedAttachmentOut
    request_id: str


class AttachmentResponse(StrictModel):
    data: AttachmentOut
    request_id: str


class SubmissionVersionOut(StrictModel):
    id: UUID
    version_no: int
    body: str
    ai_use: AiUseDisclosure
    created_at: datetime
    attachments: list[AttachmentOut]
    review_id: UUID | None
    review_status: str | None
    decision: str | None
    feedback: str | None


class SubmissionOut(StrictModel):
    id: UUID
    assignment_id: UUID
    current_version_no: int
    versions: list[SubmissionVersionOut]


class SubmissionDraftOut(StrictModel):
    body: str
    attachment_ids: list[UUID]
    revision: int
    updated_at: datetime
    idempotency_replay: bool = False


class SubmissionHistoryResponse(StrictModel):
    data: SubmissionOut
    request_id: str


class SubmissionMutationOut(StrictModel):
    assignment_id: UUID
    assignment_status: str
    assignment_revision: int
    submission_id: UUID
    submission_version_id: UUID
    version_no: int
    attachment_ids: list[UUID]
    idempotency_replay: bool = False


class SubmissionMutationResponse(StrictModel):
    data: SubmissionMutationOut
    request_id: str


class SubmissionDraftResponse(StrictModel):
    data: SubmissionDraftOut
    request_id: str


class ReviewQueueItemOut(StrictModel):
    id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version_id: UUID
    status: str
    revision: int
    allowed_commands: list[str]
    learner_name: str
    task_title: str
    task_version: int
    submission_version_no: int
    assigned_at: datetime
    started_at: datetime | None
    priority_reason: str
    material_status: Literal["COMPLETE", "INCOMPLETE"]


class ReviewQueueOut(StrictModel):
    items: list[ReviewQueueItemOut]


class ReviewQueueResponse(StrictModel):
    data: ReviewQueueOut
    request_id: str


class ReviewAttachmentOut(StrictModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    scan_status: str
    download_path: str


class ReviewMaterialOut(StrictModel):
    status: Literal["COMPLETE", "INCOMPLETE"]
    missing_items: list[str]
    required_deliverables: list[str]
    attachments: list[ReviewAttachmentOut]


class RubricEvaluationOut(StrictModel):
    dimension_key: str
    rating: str
    score: int | None = None
    feedback: str | None


class FormalAdmissionScoreInput(StrictModel):
    attendance_discipline: int = Field(ge=0, le=10)
    muchener_understanding: int = Field(ge=0, le=10)
    ai_data_fundamentals: int = Field(ge=0, le=10)
    project_organization_fit: int = Field(ge=0, le=10)


class PreviewFormalAdmissionCommand(StrictModel):
    scores: FormalAdmissionScoreInput


class FormalAdmissionPreviewOut(StrictModel):
    enrollment_id: UUID
    total_score: int
    recommendation_tier: Literal["A", "B", "C", "D"]
    recommended_decision: Literal["ADMIT", "DEFER", "NOT_ADMIT"]
    scorecard: dict[str, object]
    source_evaluation_ids: list[UUID]
    advisory_only: Literal[True] = True


class FormalAdmissionPreviewResponse(StrictModel):
    data: FormalAdmissionPreviewOut
    request_id: str


class CreateFormalAdmissionDecisionCommand(StrictModel):
    expected_absent: Literal[True] = True
    human_judgement_acknowledged: Literal[True]
    scores: FormalAdmissionScoreInput
    score_evidence: str = Field(min_length=20, max_length=2_000)
    decision: Literal["ADMIT", "DEFER", "NOT_ADMIT"]
    decision_reason: str = Field(min_length=20, max_length=2_000)
    override_reason: str | None = Field(default=None, min_length=20, max_length=2_000)

    @field_validator("score_evidence", "decision_reason", "override_reason")
    @classmethod
    def normalize_admission_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class FormalAdmissionDecisionOut(StrictModel):
    id: UUID
    enrollment_id: UUID
    journey_version_id: UUID
    outcome_id: UUID
    total_score: int
    recommendation_tier: Literal["A", "B", "C", "D"]
    scorecard: dict[str, object]
    source_evaluation_ids: list[UUID]
    decision: Literal["ADMIT", "DEFER", "NOT_ADMIT"]
    decision_reason: str
    override_reason: str | None
    decided_by: UUID
    created_at: datetime
    idempotency_replay: bool = False


class FormalAdmissionDecisionResponse(StrictModel):
    data: FormalAdmissionDecisionOut
    request_id: str


class EvaluationOut(StrictModel):
    id: UUID
    decision: str
    overall_decision: Literal["APPROVE", "REQUEST_REVISION"]
    overall_feedback: str
    rubric_evaluations: list[RubricEvaluationOut]
    feedback_structure_version: int
    reviewer_id: UUID
    review_revision: int
    ai_use: AiUseDisclosure
    created_at: datetime


class ReviewDetailOut(ReviewQueueItemOut):
    submission_body: str
    submission_ai_use: AiUseDisclosure
    task_purpose: str
    completion_criteria: list[str]
    required_deliverables: list[str]
    rubric: dict[str, object]
    materials: ReviewMaterialOut
    finalized_at: datetime | None
    evaluation: EvaluationOut | None


class ReviewDetailResponse(StrictModel):
    data: ReviewDetailOut
    request_id: str


class ReviewMutationOut(StrictModel):
    review_id: UUID
    review_status: str
    review_revision: int
    assignment_id: UUID
    assignment_status: str
    assignment_revision: int
    evaluation_id: UUID | None = None
    decision: str | None = None
    idempotency_replay: bool = False


class ReviewMutationResponse(StrictModel):
    data: ReviewMutationOut
    request_id: str


class ResultRubricFeedbackOut(StrictModel):
    dimension_key: str
    title: str
    rating: str
    feedback: str | None


class ResultEvaluationOut(StrictModel):
    id: UUID
    reviewer_id: UUID
    decision: Literal["PASS"]
    overall_feedback: str
    rubric_feedback: list[ResultRubricFeedbackOut]
    ai_use: AiUseDisclosure
    created_at: datetime


class JourneyResultEvaluationOut(ResultEvaluationOut):
    stage_key: str
    stage_title: str


class HandoffOut(StrictModel):
    id: UUID
    status: Literal["READY"]
    owner_user_id: UUID
    owner_display_name: str
    title: str
    next_step_code: Literal["CONFIRM_HANDOFF"]
    next_step_title: str
    instructions: str
    created_at: datetime


class HandoffAcceptanceCommand(StrictModel):
    next_training_stage_decision_id: UUID
    controlled_task_authorization_id: UUID
    expected_authorization_revision: int = Field(ge=1)
    expected_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_task_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_policy_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_target_journey_version_id: UUID
    expected_target_journey_stage_version_id: UUID
    expected_target_task_version_id: UUID


class HandoffAcceptanceOut(StrictModel):
    id: UUID
    handoff_id: UUID
    next_training_stage_decision_id: UUID
    controlled_task_authorization_id: UUID
    target_journey_version_id: UUID
    target_journey_stage_version_id: UUID
    target_task_version_id: UUID
    target_reviewer_user_id: UUID
    target_enrollment_id: UUID
    target_assignment_id: UUID
    accepted_at: datetime
    idempotency_replay: bool = False


class HandoffAcceptanceResponse(StrictModel):
    data: HandoffAcceptanceOut
    request_id: str


class HandoffControlledTaskAuthorizationOut(StrictModel):
    id: UUID
    status: Literal["ACTIVE"]
    revision: int
    target_journey_version_id: UUID
    target_journey_stage_version_id: UUID
    target_task_version_id: UUID
    task_version_sha256: str
    scope_sha256: str
    policy_snapshot_sha256: str
    primary_reviewer_user_id: UUID
    valid_from: datetime
    expires_at: datetime


class HandoffDetailOut(StrictModel):
    handoff: HandoffOut
    next_training_stage_decision_id: UUID | None
    next_training_stage_decision: Literal["READY"] | None
    controlled_task_authorization: HandoffControlledTaskAuthorizationOut | None
    acceptance: HandoffAcceptanceOut | None
    acceptance_status: Literal[
        "DECISION_REQUIRED",
        "AUTHORIZATION_REQUIRED",
        "READY_TO_ACCEPT",
        "ALREADY_ACCEPTED",
    ]
    production_execution_allowed: Literal[False] = False


class HandoffDetailResponse(StrictModel):
    data: HandoffDetailOut
    request_id: str


class ControlledTaskPolicySnapshotCommand(StrictModel):
    policy_schema: Literal["muchen-journey-controlled-task-policy.v1"]
    policy_version: str = Field(min_length=3, max_length=80)
    training_purpose: str = Field(min_length=3, max_length=500)
    allowed_input_schema_ref: str = Field(min_length=3, max_length=500)
    data_classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL_PEOPLE"]
    deidentification_rule_ref: str = Field(min_length=3, max_length=500)
    production_isolation_rule_ref: str = Field(min_length=3, max_length=500)
    production_actions_allowed: Literal[False]
    production_credential_allowed: Literal[False]
    prohibited_action_codes: list[str] = Field(min_length=1, max_length=30)
    learner_visibility: list[str] = Field(min_length=1, max_length=30)
    reviewer_visibility: list[str] = Field(min_length=1, max_length=30)
    operator_visibility: list[str] = Field(min_length=1, max_length=30)
    reviewer_substitution_rule_ref: str = Field(min_length=3, max_length=500)
    evidence_retention_days: int = Field(ge=1, le=3650)
    evidence_disposition: Literal["DELETE", "ARCHIVE"]
    help_escalation_ref: str = Field(min_length=3, max_length=500)


class CreateControlledTaskAuthorizationCommand(StrictModel):
    authorized_project_ref: str = Field(min_length=3, max_length=500)
    target_journey_version_id: UUID
    target_journey_stage_version_id: UUID
    target_task_version_id: UUID
    authorization_version: int = Field(ge=1)
    project_owner_user_id: UUID
    newcomer_operations_owner_user_id: UUID
    data_security_owner_user_id: UUID
    reviewer_owner_user_id: UUID
    primary_reviewer_user_id: UUID
    backup_reviewer_user_id: UUID
    policy_snapshot_ref: str = Field(min_length=3, max_length=500)
    policy_snapshot: ControlledTaskPolicySnapshotCommand
    policy_evidence_ref: str = Field(min_length=3, max_length=500)
    policy_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_from: datetime
    expires_at: datetime


class ControlledTaskAuthorizationOut(StrictModel):
    id: UUID
    authorization_scope: Literal["NEWCOMER_CONTROLLED_TRAINING"]
    authorized_project_ref: str
    target_journey_version_id: UUID
    target_journey_stage_version_id: UUID
    target_task_version_id: UUID
    task_version_sha256: str
    authorization_version: int
    scope_sha256: str
    project_owner_user_id: UUID
    newcomer_operations_owner_user_id: UUID
    data_security_owner_user_id: UUID
    reviewer_owner_user_id: UUID
    primary_reviewer_user_id: UUID
    backup_reviewer_user_id: UUID
    policy_snapshot_ref: str
    policy_snapshot_version: str
    policy_snapshot_sha256: str
    policy_evidence_ref: str
    policy_evidence_sha256: str
    valid_from: datetime
    expires_at: datetime
    status: Literal["DRAFT", "PENDING_APPROVALS", "ACTIVE", "REVOKED", "EXPIRED"]
    revision: int
    activated_at: datetime | None
    revoked_at: datetime | None
    expired_at: datetime | None
    created_at: datetime
    updated_at: datetime
    idempotency_replay: bool = False


class ControlledTaskAuthorizationResponse(StrictModel):
    data: ControlledTaskAuthorizationOut
    request_id: str


class ControlledTaskAuthorizationRevisionCommand(StrictModel):
    expected_revision: int = Field(ge=1)


class ActivateControlledTaskAuthorizationCommand(
    ControlledTaskAuthorizationRevisionCommand
):
    expected_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_task_version_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_policy_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ControlledTaskAuthorizationApprovalCommand(StrictModel):
    expected_authorization_revision: int = Field(ge=1)
    approval_role: Literal[
        "NEWCOMER_OPERATIONS_OWNER",
        "PROJECT_OWNER",
        "DATA_SECURITY_OWNER",
        "REVIEWER_OWNER",
    ]
    decision: Literal["APPROVE", "REJECT"]
    expected_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_evidence_ref: str = Field(min_length=3, max_length=500)
    signature_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signed_at: datetime


class ControlledTaskAuthorizationApprovalOut(StrictModel):
    id: UUID
    authorization_id: UUID
    approval_role: str
    signer_user_id: UUID
    decision: str
    signed_scope_sha256: str
    signature_evidence_ref: str
    signature_evidence_sha256: str
    signed_at: datetime
    created_at: datetime
    idempotency_replay: bool = False


class ControlledTaskAuthorizationApprovalResponse(StrictModel):
    data: ControlledTaskAuthorizationApprovalOut
    request_id: str


class RevokeControlledTaskAuthorizationCommand(
    ControlledTaskAuthorizationRevisionCommand
):
    reason: str = Field(min_length=10, max_length=500)


class NotificationDeliveryOut(StrictModel):
    status: str
    channel: str | None
    display_status: str
    attempt_count: int
    next_attempt_at: datetime | None
    last_error_code: str | None
    delivered_at: datetime | None
    delivery_scope: Literal["LOCAL_TEST_ONLY", "FEISHU"]
    external_delivery_confirmed: bool


class AiSummaryOut(StrictModel):
    status: Literal["NOT_ENABLED"] = "NOT_ENABLED"
    message: str


class ResultLearningCompletionOut(StrictModel):
    status: Literal["COMPLETED"] = "COMPLETED"
    completed_stages: int = Field(ge=1)
    total_stages: int = Field(ge=1)


class ResultReviewerConclusionOut(StrictModel):
    status: Literal["FINALIZED"] = "FINALIZED"
    decision: Literal["PASS"] = "PASS"
    reviewer_id: UUID
    overall_feedback: str
    ai_use: AiUseDisclosure
    concluded_at: datetime


class ResultNextTrainingStageOut(StrictModel):
    decision_scope: Literal["NEXT_TRAINING_STAGE"] = "NEXT_TRAINING_STAGE"
    display_name: Literal["下一训练阶段决定"] = "下一训练阶段决定"
    status: Literal["PENDING_HUMAN_DECISION", "RECORDED"]
    decision_id: UUID | None
    decision: Literal["READY", "DEFER", "NOT_READY"] | None
    decision_reason: str | None
    signed_by: UUID | None
    signed_at: datetime | None
    decision_evidence_ref: str | None
    review_request_status: Literal[
        "NOT_AVAILABLE_UNTIL_DECISION", "NOT_APPLICABLE", "AVAILABLE", "RECEIVED"
    ]
    can_request_review: bool


class NextTrainingStageReviewRequestCommand(StrictModel):
    reason: str = Field(min_length=10, max_length=2_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Evidence references must be unique")
        if any(not 3 <= len(value) <= 300 for value in normalized):
            raise ValueError("Evidence references must contain 3 to 300 characters")
        return normalized


class NextTrainingStageReviewRequestOut(StrictModel):
    id: UUID
    next_training_stage_decision_id: UUID
    source_decision: Literal["DEFER", "NOT_READY"]
    reason: str
    evidence_refs: list[str]
    status: Literal[
        "RECEIVED", "IN_REVIEW", "UPHELD", "OVERTURNED", "RETURNED_FOR_REVIEW"
    ] = "RECEIVED"
    requested_at: datetime
    assigned_reviewer_user_id: UUID | None = None
    assigned_at: datetime | None = None
    resolution_reason: str | None = None
    resolved_at: datetime | None = None
    replacement_decision_id: UUID | None = None
    already_received: bool = False
    idempotency_replay: bool = False


class NextTrainingStageReviewRequestResponse(StrictModel):
    data: NextTrainingStageReviewRequestOut
    request_id: str


class NextTrainingStageReviewRequestListOut(StrictModel):
    items: list[NextTrainingStageReviewRequestOut]


class NextTrainingStageReviewRequestListResponse(StrictModel):
    data: NextTrainingStageReviewRequestListOut
    request_id: str


class NextTrainingStageReviewAssignmentCommand(StrictModel):
    reviewer_user_id: UUID
    assignment_reason: str = Field(min_length=10, max_length=1_000)
    assignment_evidence_ref: str = Field(min_length=3, max_length=300)


class NextTrainingStageReviewAssignmentOut(StrictModel):
    id: UUID
    review_request_id: UUID
    source_decision_id: UUID
    person_id: UUID
    reviewer_user_id: UUID
    assigned_by_user_id: UUID
    assignment_reason: str
    assignment_evidence_ref: str
    assigned_at: datetime
    idempotency_replay: bool = False


class NextTrainingStageReviewAssignmentResponse(StrictModel):
    data: NextTrainingStageReviewAssignmentOut
    request_id: str


class NextTrainingStageReplacementDecisionCommand(StrictModel):
    decision: Literal["READY", "DEFER", "NOT_READY"]
    decision_reason: str = Field(min_length=10, max_length=2_000)
    decision_evidence_ref: str = Field(min_length=3, max_length=500)
    decision_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class NextTrainingStageReviewResolutionCommand(StrictModel):
    status: Literal["UPHELD", "OVERTURNED", "RETURNED_FOR_REVIEW"]
    resolution_reason: str = Field(min_length=10, max_length=2_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    replacement_decision: NextTrainingStageReplacementDecisionCommand | None = None

    @field_validator("evidence_refs")
    @classmethod
    def validate_resolution_evidence_refs(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Evidence references must be unique")
        if any(not 3 <= len(value) <= 300 for value in normalized):
            raise ValueError("Evidence references must contain 3 to 300 characters")
        return normalized

    @model_validator(mode="after")
    def validate_replacement_shape(self):
        if (self.status == "OVERTURNED") != (self.replacement_decision is not None):
            raise ValueError("OVERTURNED requires exactly one replacement decision")
        return self


class NextTrainingStageReviewResolutionOut(StrictModel):
    id: UUID
    review_request_id: UUID
    assignment_id: UUID
    reviewer_user_id: UUID
    status: Literal["UPHELD", "OVERTURNED", "RETURNED_FOR_REVIEW"]
    resolution_reason: str
    evidence_refs: list[str]
    resolved_at: datetime
    replacement_decision_id: UUID | None = None
    idempotency_replay: bool = False


class NextTrainingStageReviewResolutionResponse(StrictModel):
    data: NextTrainingStageReviewResolutionOut
    request_id: str


class ResultOut(StrictModel):
    outcome_id: UUID
    decision: Literal["PASS"]
    status: str
    summary: str
    learning_completion: ResultLearningCompletionOut
    reviewer_conclusion: ResultReviewerConclusionOut
    next_training_stage: ResultNextTrainingStageOut
    evaluation: ResultEvaluationOut
    journey_evaluations: list[JourneyResultEvaluationOut]
    handoff: HandoffOut
    notification: NotificationDeliveryOut
    ai_summary: AiSummaryOut
    created_at: datetime


class ResultResponse(StrictModel):
    data: ResultOut
    request_id: str


class IncentiveLedgerEntryOut(StrictModel):
    id: UUID
    module_key: str
    incentive_type: Literal["POINTS", "XP", "BADGE", "RANK"]
    amount: int | None
    label: str | None
    source_outcome_id: UUID
    rule_ref: str
    rule_sha256: str
    correction_of_entry_id: UUID | None
    correction_reason: str | None
    created_at: datetime


class IncentiveLedgerOut(StrictModel):
    points_total: int
    xp_total: int
    entries: list[IncentiveLedgerEntryOut]
    formal_effect: Literal["NONE"] = "NONE"
    can_unlock_human_gate: Literal[False] = False


class IncentiveLedgerResponse(StrictModel):
    data: IncentiveLedgerOut
    request_id: str


class TimelineItemOut(StrictModel):
    item_id: str
    event_type: str
    title: str
    occurred_at: datetime
    object_type: str
    object_id: UUID
    details: dict[str, str | int | bool | None]


class TimelineOut(StrictModel):
    items: list[TimelineItemOut]
    next_cursor: str | None


class TimelineResponse(StrictModel):
    data: TimelineOut
    request_id: str


class HealthOut(StrictModel):
    status: Literal["ok"]
    release: str


class ErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, object]
    retryable: bool


class ErrorResponse(StrictModel):
    error: ErrorDetail
    request_id: str
