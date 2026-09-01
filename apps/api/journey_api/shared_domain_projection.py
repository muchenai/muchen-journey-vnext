from __future__ import annotations

import enum
import uuid
from datetime import timedelta
from typing import Self

from pydantic import Field, model_validator

from journey_api.models import (
    Assignment,
    Decision,
    Enrollment,
    Evaluation,
    Review,
    ReviewStatus,
    Submission,
    SubmissionVersion,
    TaskVersion,
    User,
)
from journey_api.controlled_task_authorization import (
    ControlledTaskAuthorizationContract,
    MODULE_BUILD_CONTRACTS,
    TaskAuthorizationStatus,
    bind_task_version_authorization,
)
from journey_api.appeal_continuity import (
    AppealPolicyStatus,
    HumanGateAppealPolicyContract,
    appeal_policy_gate_ref,
    bind_human_gate_appeal_policy,
)
from journey_api.module_execution_package import (
    ModuleExecutionPackageContract,
    ModulePackageStatus,
    bind_module_execution_package,
)
from journey_api.shared_domain import (
    AiUseDisclosure,
    DataClassification,
    EvidenceAuthority,
    EvidenceContract,
    EvidenceVisibility,
    HumanGateContract,
    HumanGateDecision,
    HumanGateKind,
    JourneyModuleKey,
    PersonContract,
    SharedContractModel,
    require_formal_result_basis,
)


PROJECTION_NAMESPACE = uuid.UUID("d3169158-36a9-4a45-b8f9-c72a992f4613")


class ModuleProjectionContext(SharedContractModel):
    """Controller-approved context required to interpret runtime facts."""

    module_key: JourneyModuleKey
    build_contract_ref: str = Field(min_length=3, max_length=300)
    task_authorization: ControlledTaskAuthorizationContract | None = None
    module_package: ModuleExecutionPackageContract | None = None
    appeal_policy: HumanGateAppealPolicyContract | None = None
    gate_kind: HumanGateKind
    retention_policy: str = Field(min_length=3, max_length=120)
    visibility: tuple[EvidenceVisibility, ...] = Field(min_length=1)
    data_classification: DataClassification
    production_action_executed: bool = False

    @model_validator(mode="after")
    def validate_controller_binding(self) -> Self:
        expected_contract = MODULE_BUILD_CONTRACTS.get(self.module_key)
        if self.module_key is JourneyModuleKey.CERTIFICATION_ARENA:
            raise ValueError("Certification Arena requires a Panel contract")
        if expected_contract is None:
            raise ValueError("module is not supported by the shared review-cycle projection")
        if self.build_contract_ref != expected_contract:
            raise ValueError("module and Build Contract binding do not match")
        if self.task_authorization is None:
            raise ValueError("module projection requires a controlled task authorization")
        if (
            self.task_authorization.scope.module_key is not self.module_key
            or self.task_authorization.scope.build_contract_ref
            != self.build_contract_ref
        ):
            raise ValueError("module projection and task authorization scope do not match")
        if (
            self.visibility != self.task_authorization.scope.visibility
            or self.data_classification
            is not self.task_authorization.scope.data_classification
            or self.retention_policy != self.task_authorization.scope.retention_policy
        ):
            raise ValueError(
                "projection evidence governance differs from task authorization"
            )
        if len(set(self.visibility)) != len(self.visibility):
            raise ValueError("projection visibility entries must be unique")
        if self.production_action_executed:
            raise ValueError("Journey projection cannot execute a production action")
        package_required = self.module_key in {
            JourneyModuleKey.AI_ACADEMY,
            JourneyModuleKey.DELIVERY_GUILD,
        }
        if package_required and self.module_package is None:
            raise ValueError("module requires a content or guild package binding")
        if not package_required and self.module_package is not None:
            raise ValueError("module package binding is not applicable to this module")
        if self.module_package is not None:
            bind_module_execution_package(
                task_authorization=self.task_authorization,
                package=self.module_package,
            )
        if self.appeal_policy is None:
            raise ValueError("module projection requires a Human Gate appeal policy")
        bind_human_gate_appeal_policy(
            task_authorization=self.task_authorization,
            module_package=self.module_package,
            policy=self.appeal_policy,
        )
        expected_gate_kind = (
            HumanGateKind.TASK_PASS
            if self.module_key is JourneyModuleKey.NEWCOMER_VILLAGE
            else HumanGateKind.CAPABILITY
        )
        if self.gate_kind is not expected_gate_kind:
            raise ValueError("module and Human Gate kind do not match")
        return self

    @property
    def authorized_task_ref(self) -> str:
        assert self.task_authorization is not None
        return self.task_authorization.scope.authorized_task_ref

    @property
    def task_authorization_status(self) -> TaskAuthorizationStatus:
        assert self.task_authorization is not None
        return self.task_authorization.status

    @property
    def module_package_status(self) -> ModulePackageStatus | None:
        if self.module_package is None:
            return None
        return self.module_package.status

    @property
    def module_package_ref(self) -> str | None:
        if self.module_package is None:
            return None
        return self.module_package.scope.package_ref

    @property
    def appeal_policy_status(self) -> AppealPolicyStatus:
        assert self.appeal_policy is not None
        return self.appeal_policy.status

    @property
    def authorization_source_ref(self) -> str:
        assert self.task_authorization is not None
        source_ref = (
            f"task-auth:{self.task_authorization.authorization_id}:sha256:"
            f"{self.task_authorization.scope.task_version_sha256}"
        )
        if self.module_package is None:
            return source_ref
        return (
            f"{source_ref};module-package:{self.module_package.package_id}:sha256:"
            f"{self.module_package.scope.subject_sha256()}"
        )


class ReviewCycleStatus(str, enum.Enum):
    REVISION_REQUIRED = "REVISION_REQUIRED"
    TASK_AUTHORIZATION_PENDING = "TASK_AUTHORIZATION_PENDING"
    TASK_AUTHORIZATION_REJECTED = "TASK_AUTHORIZATION_REJECTED"
    MODULE_GOVERNANCE_PENDING = "MODULE_GOVERNANCE_PENDING"
    MODULE_GOVERNANCE_REJECTED = "MODULE_GOVERNANCE_REJECTED"
    APPEAL_GOVERNANCE_PENDING = "APPEAL_GOVERNANCE_PENDING"
    APPEAL_GOVERNANCE_REJECTED = "APPEAL_GOVERNANCE_REJECTED"
    FORMAL_RESULT_ELIGIBLE = "FORMAL_RESULT_ELIGIBLE"


class ReviewCycleProjection(SharedContractModel):
    person: PersonContract
    practice_evidence: EvidenceContract
    human_evaluation_evidence: EvidenceContract
    human_gate: HumanGateContract
    status: ReviewCycleStatus
    blockers: tuple[str, ...]

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE and self.blockers:
            raise ValueError("eligible review cycle cannot carry blockers")
        if self.status is not ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE and not self.blockers:
            raise ValueError("ineligible review cycle must explain its blockers")
        return self


def _projection_id(kind: str, source_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(PROJECTION_NAMESPACE, f"{kind}:{source_id}")


def project_person(*, user: User) -> PersonContract:
    return PersonContract(
        organization_id=user.organization_id,
        person_id=user.id,
    )


def _require_fixed_practice_scope(
    *,
    person: PersonContract,
    enrollment: Enrollment,
    assignment: Assignment,
    task: TaskVersion,
    submission: Submission,
    version: SubmissionVersion,
) -> None:
    if {
        person.organization_id,
        enrollment.organization_id,
        assignment.organization_id,
        task.organization_id,
        submission.organization_id,
    } != {person.organization_id}:
        raise ValueError("practice projection cannot cross organization scope")
    if enrollment.learner_id != person.person_id:
        raise ValueError("enrollment learner does not match the shared Person")
    if assignment.enrollment_id != enrollment.id:
        raise ValueError("assignment is not bound to the supplied enrollment")
    if assignment.task_version_id != task.id:
        raise ValueError("assignment is not bound to the supplied TaskVersion")
    if submission.assignment_id != assignment.id:
        raise ValueError("submission is not bound to the supplied assignment")
    if version.submission_id != submission.id:
        raise ValueError("SubmissionVersion is not bound to the supplied submission")
    if version.created_by != person.person_id:
        raise ValueError("practice submission must be created by the Person")
    if version.created_at is None:
        raise ValueError("practice submission must have an immutable creation time")


def project_practice_evidence(
    *,
    person: PersonContract,
    enrollment: Enrollment,
    assignment: Assignment,
    task: TaskVersion,
    submission: Submission,
    version: SubmissionVersion,
    context: ModuleProjectionContext,
    ai_use: AiUseDisclosure,
    previous_version: SubmissionVersion | None = None,
) -> EvidenceContract:
    _require_fixed_practice_scope(
        person=person,
        enrollment=enrollment,
        assignment=assignment,
        task=task,
        submission=submission,
        version=version,
    )
    if version.version_no == 1 and previous_version is not None:
        raise ValueError("the first submission version cannot have a predecessor")
    if version.version_no > 1:
        if previous_version is None:
            raise ValueError("a revised submission requires its fixed predecessor")
        if (
            previous_version.submission_id != submission.id
            or previous_version.version_no != version.version_no - 1
        ):
            raise ValueError("submission predecessor must be the immediately prior version")

    return EvidenceContract(
        evidence_id=_projection_id("practice", version.id),
        organization_id=person.organization_id,
        person_id=person.person_id,
        module_key=context.module_key,
        authority=EvidenceAuthority.PRACTICE,
        authorized_source_ref=context.authorization_source_ref,
        task_version_id=task.id,
        assignment_id=assignment.id,
        submission_version_id=version.id,
        created_by=version.created_by,
        occurred_at=version.created_at,
        revision=version.version_no,
        revises_evidence_id=(
            _projection_id("practice", previous_version.id)
            if previous_version is not None
            else None
        ),
        ai_use=ai_use,
        visibility=context.visibility,
        data_classification=context.data_classification,
        retention_policy=context.retention_policy,
    )


def project_human_evaluation_evidence(
    *,
    person: PersonContract,
    enrollment: Enrollment,
    assignment: Assignment,
    task: TaskVersion,
    submission: Submission,
    version: SubmissionVersion,
    review: Review,
    evaluation: Evaluation,
    context: ModuleProjectionContext,
    ai_use: AiUseDisclosure,
) -> EvidenceContract:
    _require_fixed_practice_scope(
        person=person,
        enrollment=enrollment,
        assignment=assignment,
        task=task,
        submission=submission,
        version=version,
    )
    if (
        review.id != evaluation.review_id
        or review.organization_id != person.organization_id
        or review.assignment_id != assignment.id
        or review.submission_id != submission.id
        or review.submission_version_id != version.id
        or review.reviewer_id != evaluation.reviewer_id
    ):
        raise ValueError("Review is not fixed to the supplied Evaluation scope")
    if review.status is not ReviewStatus.FINALIZED or review.finalized_at is None:
        raise ValueError("human Evaluation requires a finalized Review")
    if (
        evaluation.organization_id != person.organization_id
        or evaluation.assignment_id != assignment.id
        or evaluation.submission_id != submission.id
        or evaluation.submission_version_id != version.id
    ):
        raise ValueError("Evaluation is not fixed to the supplied practice evidence")
    if evaluation.created_by != evaluation.reviewer_id:
        raise ValueError("human Evaluation must be created by its Reviewer")
    if evaluation.reviewer_id == person.person_id:
        raise ValueError("a Person cannot provide their own human Evaluation")
    if evaluation.created_at is None:
        raise ValueError("human Evaluation must have an immutable creation time")

    return EvidenceContract(
        evidence_id=_projection_id("human-evaluation", evaluation.id),
        organization_id=person.organization_id,
        person_id=person.person_id,
        module_key=context.module_key,
        authority=EvidenceAuthority.HUMAN_EVALUATION,
        authorized_source_ref=context.authorization_source_ref,
        task_version_id=task.id,
        assignment_id=assignment.id,
        submission_version_id=version.id,
        evaluation_id=evaluation.id,
        created_by=evaluation.created_by,
        occurred_at=evaluation.created_at,
        revision=1,
        ai_use=ai_use,
        visibility=context.visibility,
        data_classification=context.data_classification,
        retention_policy=context.retention_policy,
    )


def project_human_gate(
    *,
    person: PersonContract,
    task: TaskVersion,
    evaluation: Evaluation,
    practice_evidence: EvidenceContract,
    human_evaluation_evidence: EvidenceContract,
    context: ModuleProjectionContext,
) -> HumanGateContract:
    assert context.appeal_policy is not None
    decision = (
        HumanGateDecision.PASS
        if evaluation.decision is Decision.PASS
        else HumanGateDecision.NEEDS_REVISION
    )
    return HumanGateContract(
        gate_id=_projection_id("human-gate", evaluation.id),
        organization_id=person.organization_id,
        person_id=person.person_id,
        module_key=context.module_key,
        gate_kind=context.gate_kind,
        evidence_ids=(
            practice_evidence.evidence_id,
            human_evaluation_evidence.evidence_id,
        ),
        rubric_version=f"task-version:{task.id}:rubric-v{task.rubric_version}",
        decision=decision,
        reason=evaluation.feedback,
        signed_by_person_ids=(evaluation.reviewer_id,),
        signed_at=evaluation.created_at,
        appeal_policy_ref=appeal_policy_gate_ref(context.appeal_policy),
        appeal_window_ends_at=evaluation.created_at
        + timedelta(days=context.appeal_policy.scope.appeal_window_days),
    )


def project_review_cycle(
    *,
    user: User,
    enrollment: Enrollment,
    assignment: Assignment,
    task: TaskVersion,
    submission: Submission,
    version: SubmissionVersion,
    review: Review,
    evaluation: Evaluation,
    context: ModuleProjectionContext,
    submission_ai_use: AiUseDisclosure,
    review_ai_use: AiUseDisclosure,
    previous_version: SubmissionVersion | None = None,
) -> ReviewCycleProjection:
    assert context.task_authorization is not None
    authorization_status = bind_task_version_authorization(
        task=task,
        authorization=context.task_authorization,
    )
    person = project_person(user=user)
    practice = project_practice_evidence(
        person=person,
        enrollment=enrollment,
        assignment=assignment,
        task=task,
        submission=submission,
        version=version,
        context=context,
        ai_use=submission_ai_use,
        previous_version=previous_version,
    )
    human_evaluation = project_human_evaluation_evidence(
        person=person,
        enrollment=enrollment,
        assignment=assignment,
        task=task,
        submission=submission,
        version=version,
        review=review,
        evaluation=evaluation,
        context=context,
        ai_use=review_ai_use,
    )
    gate = project_human_gate(
        person=person,
        task=task,
        evaluation=evaluation,
        practice_evidence=practice,
        human_evaluation_evidence=human_evaluation,
        context=context,
    )

    blockers: list[str] = []
    if gate.decision is not HumanGateDecision.PASS:
        blockers.append("HUMAN_GATE_NEEDS_REVISION")
    if authorization_status is TaskAuthorizationStatus.REJECTED:
        blockers.append("TASK_AUTHORIZATION_REJECTED")
    elif authorization_status is not TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK:
        blockers.append("TASK_AUTHORIZATION_NOT_APPROVED")
    if context.module_package_status is ModulePackageStatus.REJECTED:
        blockers.append("MODULE_PACKAGE_REJECTED")
    elif context.module_package_status is ModulePackageStatus.PENDING_OWNER_APPROVAL:
        blockers.append("MODULE_PACKAGE_NOT_APPROVED")
    if not blockers:
        if context.appeal_policy_status is AppealPolicyStatus.REJECTED:
            blockers.append("APPEAL_POLICY_REJECTED")
        elif context.appeal_policy_status is not AppealPolicyStatus.APPROVED:
            blockers.append("APPEAL_POLICY_NOT_APPROVED")
    if blockers:
        if "HUMAN_GATE_NEEDS_REVISION" in blockers:
            status = ReviewCycleStatus.REVISION_REQUIRED
        elif "TASK_AUTHORIZATION_REJECTED" in blockers:
            status = ReviewCycleStatus.TASK_AUTHORIZATION_REJECTED
        elif "MODULE_PACKAGE_REJECTED" in blockers:
            status = ReviewCycleStatus.MODULE_GOVERNANCE_REJECTED
        elif "MODULE_PACKAGE_NOT_APPROVED" in blockers:
            status = ReviewCycleStatus.MODULE_GOVERNANCE_PENDING
        elif "APPEAL_POLICY_REJECTED" in blockers:
            status = ReviewCycleStatus.APPEAL_GOVERNANCE_REJECTED
        elif "APPEAL_POLICY_NOT_APPROVED" in blockers:
            status = ReviewCycleStatus.APPEAL_GOVERNANCE_PENDING
        else:
            status = ReviewCycleStatus.TASK_AUTHORIZATION_PENDING
    else:
        require_formal_result_basis(
            person=person,
            evidence=(practice, human_evaluation),
            gate=gate,
        )
        status = ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE

    return ReviewCycleProjection(
        person=person,
        practice_evidence=practice,
        human_evaluation_evidence=human_evaluation,
        human_gate=gate,
        status=status,
        blockers=tuple(blockers),
    )
