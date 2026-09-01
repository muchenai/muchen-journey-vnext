from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    Review,
    ReviewStatus,
    Submission,
    SubmissionVersion,
    TaskVersion,
    User,
    UserStatus,
)
from journey_api.controlled_task_authorization import (
    ControlledTaskAuthorizationContract,
    TaskAuthorizationDecision,
    TaskAuthorizationRole,
    TaskAuthorizationScopeContract,
    TaskAuthorizationSignatureContract,
    TaskAuthorizationStatus,
    required_task_authorization_roles,
    task_version_contract_sha256,
)
from journey_api.appeal_continuity import (
    AppealPolicyDecision,
    AppealPolicyRole,
    AppealPolicySignatureContract,
    AppealPolicyStatus,
    HumanGateAppealPolicyContract,
    HumanGateAppealPolicyScopeContract,
)
from journey_api.module_execution_package import (
    AiLearningUnitPackageScopeContract,
    GuildPluginPackageScopeContract,
    ModuleExecutionPackageContract,
    ModulePackageDecision,
    ModulePackageRole,
    ModulePackageSignatureContract,
    ModulePackageStatus,
    VersionedArtifactRefContract,
    required_module_package_roles,
)
from journey_api.shared_domain import (
    AiUseDisclosure,
    DataClassification,
    EvidenceVisibility,
    HumanGateKind,
    JourneyModuleKey,
)
from journey_api.shared_domain_projection import (
    ModuleProjectionContext,
    ReviewCycleStatus,
    project_person,
    project_practice_evidence,
    project_review_cycle,
)


NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("40000000-0000-4000-8000-000000000001")
PERSON_ID = UUID("40000000-0000-4000-8000-000000000002")
REVIEWER_ID = UUID("40000000-0000-4000-8000-000000000003")
BACKUP_REVIEWER_ID = UUID("40000000-0000-4000-8000-000000000004")


def no_ai() -> AiUseDisclosure:
    return AiUseDisclosure(used=False)


def artifact(name: str) -> VersionedArtifactRefContract:
    return VersionedArtifactRefContract(
        artifact_ref=f"contracts/module-packages/{name}",
        version="v1",
        sha256="1" * 64,
    )


def execution_package(
    task_authorization: ControlledTaskAuthorizationContract,
    *,
    status: ModulePackageStatus = ModulePackageStatus.PENDING_OWNER_APPROVAL,
    package_ref: str | None = None,
) -> ModuleExecutionPackageContract:
    task_scope = task_authorization.scope
    common = {
        "organization_id": task_scope.organization_id,
        "build_contract_ref": task_scope.build_contract_ref,
        "package_ref": package_ref or (
            "ai-learning-unit-package-v1"
            if task_scope.module_key is JourneyModuleKey.AI_ACADEMY
            else "delivery-guild-plugin-package-v1"
        ),
        "package_version": "v1",
        "task_authorization_id": task_authorization.authorization_id,
        "task_authorization_scope_sha256": task_scope.subject_sha256(),
        "task_version_id": task_scope.task_version_id,
        "task_version_sha256": task_scope.task_version_sha256,
        "target_capability_ref": "capabilities/evidence-led-delivery-v1",
        "rubric": artifact("rubric"),
        "practice_output_schema": artifact("practice-output-schema"),
        "reviewer_calibration": artifact("reviewer-calibration"),
        "ai_use_policy": artifact("ai-use-policy"),
        "appeal_policy": artifact("appeal-policy"),
        "evidence_rule": artifact("evidence-rule"),
        "primary_reviewer_id": task_scope.primary_reviewer_id,
        "backup_reviewer_id": task_scope.backup_reviewer_id,
        "feedback_sla_business_days": 2,
        "evidence_validity_days": 365,
        "visibility": task_scope.visibility,
        "data_classification": task_scope.data_classification,
        "retention_policy": task_scope.retention_policy,
        "created_at": NOW,
    }
    if task_scope.module_key is JourneyModuleKey.AI_ACADEMY:
        scope = AiLearningUnitPackageScopeContract(
            **common,
            unit_title="Evidence-led AI practice",
            applicable_role_refs=("roles/all-learners",),
            content_sources=(artifact("content-source"),),
            learning_materials=(artifact("learning-material"),),
            example=artifact("example"),
            counterexample=artifact("counterexample"),
            estimated_duration_minutes=45,
        )
    else:
        scope = GuildPluginPackageScopeContract(
            **common,
            guild_name="Delivery Practice Guild",
            mission=artifact("guild-mission"),
            capability_model=artifact("capability-model"),
            membership_rules=artifact("membership-rules"),
            mentor_pool=artifact("mentor-pool"),
            activity_cadence=artifact("activity-cadence"),
            collaboration_boundary=artifact("collaboration-boundary"),
            next_action_rule=artifact("next-action-rule"),
        )
    signatures = ()
    decided_at = None
    if status is ModulePackageStatus.APPROVED:
        signatures = tuple(
            ModulePackageSignatureContract(
                signer_person_id=uuid4(),
                role=role,
                decision=ModulePackageDecision.APPROVE,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW,
                evidence_ref=f"evidence/module-package/{role.value.lower()}",
            )
            for role in sorted(
                required_module_package_roles(task_scope.module_key),
                key=lambda item: item.value,
            )
        )
        decided_at = NOW
    elif status is ModulePackageStatus.REJECTED:
        signatures = (
            ModulePackageSignatureContract(
                signer_person_id=uuid4(),
                role=ModulePackageRole.DATA_SECURITY_OWNER,
                decision=ModulePackageDecision.REJECT,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW,
                evidence_ref="evidence/module-package/data-security-rejection",
            ),
        )
        decided_at = NOW
    return ModuleExecutionPackageContract(
        package_id=uuid4(),
        scope=scope,
        status=status,
        signatures=signatures,
        decided_at=decided_at,
    )


def gate_appeal_policy(
    task_authorization: ControlledTaskAuthorizationContract,
    *,
    module_package: ModuleExecutionPackageContract | None,
    status: AppealPolicyStatus,
) -> HumanGateAppealPolicyContract:
    task_scope = task_authorization.scope
    if module_package is not None:
        policy_artifact = module_package.scope.appeal_policy
        policy_ref = policy_artifact.artifact_ref
        policy_version = policy_artifact.version
        policy_sha256 = policy_artifact.sha256
    else:
        policy_ref = (
            "governance/appeals/controlled-review-cycle-v1"
            if status is AppealPolicyStatus.APPROVED
            else "synthetic-appeal-policy-test-only"
        )
        policy_version = "v1"
        policy_sha256 = "2" * 64
    scope = HumanGateAppealPolicyScopeContract(
        organization_id=task_scope.organization_id,
        module_key=task_scope.module_key,
        build_contract_ref=task_scope.build_contract_ref,
        policy_ref=policy_ref,
        policy_version=policy_version,
        policy_sha256=policy_sha256,
        applicable_gate_kind=(
            HumanGateKind.TASK_PASS
            if task_scope.module_key is JourneyModuleKey.NEWCOMER_VILLAGE
            else HumanGateKind.CAPABILITY
        ),
        task_authorization_id=task_authorization.authorization_id,
        task_authorization_scope_sha256=task_scope.subject_sha256(),
        module_package_id=(
            module_package.package_id if module_package is not None else None
        ),
        module_package_scope_sha256=(
            module_package.scope.subject_sha256()
            if module_package is not None
            else None
        ),
        appeal_window_days=14,
        resolution_sla_business_days=5,
        reviewer_assignment_rule_ref="governance/appeals/assignment-rule-v1",
        correction_evidence_rule_ref="governance/appeals/evidence-rule-v1",
        visibility=task_scope.visibility,
        data_classification=task_scope.data_classification,
        retention_policy=task_scope.retention_policy,
        created_at=NOW,
    )
    signatures = ()
    decided_at = None
    if status is AppealPolicyStatus.APPROVED:
        signatures = tuple(
            AppealPolicySignatureContract(
                signer_person_id=uuid4(),
                role=role,
                decision=AppealPolicyDecision.APPROVE,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW,
                evidence_ref=f"evidence/appeal-policy/{role.value.lower()}",
            )
            for role in AppealPolicyRole
        )
        decided_at = NOW
    elif status is AppealPolicyStatus.REJECTED:
        signatures = (
            AppealPolicySignatureContract(
                signer_person_id=uuid4(),
                role=AppealPolicyRole.DATA_SECURITY_OWNER,
                decision=AppealPolicyDecision.REJECT,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW,
                evidence_ref="evidence/appeal-policy/data-security-rejection",
            ),
        )
        decided_at = NOW
    return HumanGateAppealPolicyContract(
        policy_id=uuid4(),
        scope=scope,
        status=status,
        signatures=signatures,
        decided_at=decided_at,
    )


def context(
    *,
    task: TaskVersion,
    module_key: JourneyModuleKey = JourneyModuleKey.NEWCOMER_VILLAGE,
    authorization: TaskAuthorizationStatus = TaskAuthorizationStatus.SYNTHETIC_TEST_ONLY,
    package_status: ModulePackageStatus = ModulePackageStatus.PENDING_OWNER_APPROVAL,
    appeal_status: AppealPolicyStatus | None = None,
) -> ModuleProjectionContext:
    contract = {
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
    }[module_key]
    task_ref = (
        "approved-controlled-task-v1"
        if authorization is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
        else "pending-owner-task-v1"
        if authorization is TaskAuthorizationStatus.PENDING_OWNER_APPROVAL
        else "rejected-controlled-task-v1"
        if authorization is TaskAuthorizationStatus.REJECTED
        else "synthetic-g2-contract-test-only"
    )
    scope = TaskAuthorizationScopeContract(
        organization_id=task.organization_id,
        module_key=module_key,
        build_contract_ref=contract,
        target_journey_version_id=uuid4(),
        target_journey_stage_version_id=uuid4(),
        task_version_id=task.id,
        task_definition_id=task.task_definition_id,
        task_version_number=task.version,
        task_version_sha256=task_version_contract_sha256(task),
        authorized_task_ref=task_ref,
        purpose_ref="contracts/task-purpose-v1",
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
        deidentification_ref="contracts/task-deidentification-v1",
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        primary_reviewer_id=REVIEWER_ID,
        backup_reviewer_id=BACKUP_REVIEWER_ID,
        retention_policy=(
            "controlled-task-evidence-v1"
            if authorization is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
            else "g2-synthetic-evidence-v1"
        ),
        deletion_or_archive_rule="contracts/task-retention-disposition-v1",
        help_or_escalation_ref="contracts/task-escalation-v1",
        created_at=NOW,
    )
    signatures = ()
    decided_at = None
    if authorization is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK:
        signatures = tuple(
            TaskAuthorizationSignatureContract(
                signer_person_id=uuid4(),
                role=role,
                decision=TaskAuthorizationDecision.APPROVE,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW,
                evidence_ref=f"evidence/task-authorization/{role.value.lower()}",
            )
            for role in sorted(
                required_task_authorization_roles(module_key),
                key=lambda item: item.value,
            )
        )
        decided_at = NOW
    elif authorization is TaskAuthorizationStatus.REJECTED:
        signatures = (
            TaskAuthorizationSignatureContract(
                signer_person_id=uuid4(),
                role=TaskAuthorizationRole.DATA_SECURITY_OWNER,
                decision=TaskAuthorizationDecision.REJECT,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW,
                evidence_ref="evidence/task-authorization/data-security-rejection",
            ),
        )
        decided_at = NOW
    task_authorization = ControlledTaskAuthorizationContract(
        authorization_id=uuid4(),
        scope=scope,
        status=authorization,
        signatures=signatures,
        decided_at=decided_at,
    )
    module_package = (
        execution_package(task_authorization, status=package_status)
        if module_key
        in {JourneyModuleKey.AI_ACADEMY, JourneyModuleKey.DELIVERY_GUILD}
        else None
    )
    if appeal_status is None:
        appeal_status = (
            AppealPolicyStatus.APPROVED
            if authorization is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
            and (
                module_package is None
                or module_package.status is ModulePackageStatus.APPROVED
            )
            else AppealPolicyStatus.PENDING_OWNER_APPROVAL
        )
    return ModuleProjectionContext(
        module_key=module_key,
        build_contract_ref=contract,
        task_authorization=task_authorization,
        module_package=module_package,
        appeal_policy=gate_appeal_policy(
            task_authorization,
            module_package=module_package,
            status=appeal_status,
        ),
        gate_kind=(
            HumanGateKind.TASK_PASS
            if module_key is JourneyModuleKey.NEWCOMER_VILLAGE
            else HumanGateKind.CAPABILITY
        ),
        retention_policy=scope.retention_policy,
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
    )


def runtime_facts(
    *,
    decision: Decision = Decision.PASS,
    version_no: int = 1,
    person_id: UUID = PERSON_ID,
    reviewer_id: UUID = REVIEWER_ID,
    authorized_content: bool = False,
):
    task_definition_id = uuid4()
    task = TaskVersion(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        task_definition_id=task_definition_id,
        version=1,
        title=(
            "Approved controlled task candidate"
            if authorized_content
            else "Synthetic controlled task"
        ),
        purpose="Exercise the existing immutable submission and human review loop.",
        learner_outcome="Leave fixed practice evidence and receive human feedback.",
        instructions=["Complete the bounded action outside production systems."],
        completion_criteria=["Submit fixed evidence for human review."],
        required_deliverables=["A reviewable evidence note."],
        content_source_notes=(
            ["Owner-reviewed controlled task source package."]
            if authorized_content
            else ["Synthetic G2 contract test only."]
        ),
        change_summary=(
            "Bind the approved non-production controlled task."
            if authorized_content
            else "Create a non-production G2 compatibility fixture."
        ),
        reviewer_calibration_note="No human calibration is inferred by this fixture.",
        allowed_attachment_types=[],
        max_attachment_size_bytes=0,
        reference_materials=[],
        learning_materials=[],
        learning_experience={},
        estimated_duration_minutes=30,
        rubric={"version": 1, "dimensions": []},
        rubric_version=1,
        reviewer_role="REVIEWER",
        feedback_sla_business_days=2,
        sensitivity="INTERNAL",
        audience="LEARNER",
        published_by=uuid4(),
        reviewed_by=reviewer_id,
        published_at=NOW,
    )
    user = User(
        id=person_id,
        organization_id=ORGANIZATION_ID,
        display_name="Synthetic Person",
        status=UserStatus.ACTIVE,
    )
    enrollment = Enrollment(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        learner_id=person_id,
        reviewer_id=reviewer_id,
        status=EnrollmentStatus.ACTIVE,
        revision=1,
    )
    assignment = Assignment(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        enrollment_id=enrollment.id,
        task_definition_id=task_definition_id,
        task_version_id=task.id,
        position=1,
        status=AssignmentStatus.COMPLETED,
        revision=5,
        assigned_at=NOW,
    )
    submission = Submission(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        assignment_id=assignment.id,
        current_version_no=version_no,
        created_at=NOW,
    )
    version = SubmissionVersion(
        id=uuid4(),
        submission_id=submission.id,
        version_no=version_no,
        body="Synthetic evidence body that is fixed for the contract test only.",
        created_by=person_id,
        created_at=NOW,
    )
    review = Review(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        assignment_id=assignment.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=reviewer_id,
        status=ReviewStatus.FINALIZED,
        revision=2,
        assigned_at=NOW,
        started_at=NOW,
        finalized_at=NOW,
    )
    evaluation = Evaluation(
        id=uuid4(),
        review_id=review.id,
        organization_id=ORGANIZATION_ID,
        assignment_id=assignment.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=reviewer_id,
        executor_id=reviewer_id,
        review_revision=2,
        decision=decision,
        rubric_scores={"evidence": "MEETS"},
        structured_feedback=[{"dimension_key": "evidence", "rating": "MEETS"}],
        feedback_structure_version=1,
        feedback="Human reviewer checked the fixed evidence and recorded a reason.",
        created_by=reviewer_id,
        created_at=NOW,
    )
    return user, enrollment, assignment, task, submission, version, review, evaluation


def project(facts, *, projection_context):
    user, enrollment, assignment, task, submission, version, review, evaluation = facts
    return project_review_cycle(
        user=user,
        enrollment=enrollment,
        assignment=assignment,
        task=task,
        submission=submission,
        version=version,
        review=review,
        evaluation=evaluation,
        context=projection_context,
        submission_ai_use=no_ai(),
        review_ai_use=no_ai(),
    )


def test_module_binding_must_match_the_authoritative_build_contract():
    task = runtime_facts()[3]
    scope_values = context(task=task).task_authorization.scope.model_dump()
    scope_values["build_contract_ref"] = (
        "docs/baselines/build-contracts/BC-001_探索营_V1.0_V0.1.md"
    )
    with pytest.raises(ValidationError, match="Build Contract binding"):
        TaskAuthorizationScopeContract(**scope_values)


def test_projection_contract_rejects_any_production_action_claim():
    values = context(task=runtime_facts()[3]).model_dump()
    values["production_action_executed"] = True
    with pytest.raises(ValidationError, match="cannot execute a production action"):
        ModuleProjectionContext(**values)


@pytest.mark.parametrize(
    "module_key",
    [
        JourneyModuleKey.EXPLORATION_CAMP,
        JourneyModuleKey.NEWCOMER_VILLAGE,
        JourneyModuleKey.AI_ACADEMY,
        JourneyModuleKey.DELIVERY_GUILD,
    ],
)
def test_passed_review_projects_continuous_person_evidence_and_human_gate(module_key):
    facts = runtime_facts()
    result = project(
        facts,
        projection_context=context(task=facts[3], module_key=module_key),
    )

    assert result.person.person_id == result.practice_evidence.person_id
    assert result.practice_evidence.module_key == module_key
    assert result.human_evaluation_evidence.module_key == module_key
    assert result.human_gate.evidence_ids == (
        result.practice_evidence.evidence_id,
        result.human_evaluation_evidence.evidence_id,
    )
    assert result.human_gate.signed_by_person_ids == (REVIEWER_ID,)


def test_certification_arena_cannot_use_the_single_reviewer_projection():
    with pytest.raises(ValidationError, match="requires a Panel contract"):
        ModuleProjectionContext(
            module_key=JourneyModuleKey.CERTIFICATION_ARENA,
            build_contract_ref=(
                "docs/baselines/build-contracts/BC-005_认证竞技场_V0.1.md"
            ),
            gate_kind=HumanGateKind.CERTIFICATION,
            retention_policy="synthetic-v1",
            visibility=(EvidenceVisibility.PERSON,),
            data_classification=DataClassification.INTERNAL,
        )


@pytest.mark.parametrize(
    "module_key",
    [JourneyModuleKey.AI_ACADEMY, JourneyModuleKey.DELIVERY_GUILD],
)
def test_ai_and_guild_require_approved_module_package_before_formal_result(module_key):
    facts = runtime_facts(authorized_content=True)
    pending = project(
        facts,
        projection_context=context(
            task=facts[3],
            module_key=module_key,
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
        ),
    )
    assert pending.status is ReviewCycleStatus.MODULE_GOVERNANCE_PENDING
    assert pending.blockers == ("MODULE_PACKAGE_NOT_APPROVED",)

    approved = project(
        facts,
        projection_context=context(
            task=facts[3],
            module_key=module_key,
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            package_status=ModulePackageStatus.APPROVED,
        ),
    )
    assert approved.status is ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE


def test_approved_module_package_cannot_point_to_a_synthetic_candidate():
    task = runtime_facts(authorized_content=True)[3]
    projection_context = context(
        task=task,
        module_key=JourneyModuleKey.AI_ACADEMY,
        authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
    )
    assert projection_context.task_authorization is not None
    with pytest.raises(ValidationError, match="non-authoritative content"):
        execution_package(
            projection_context.task_authorization,
            status=ModulePackageStatus.APPROVED,
            package_ref="synthetic-ai-academy-candidate",
        )


def test_rejected_module_package_blocks_formal_result():
    facts = runtime_facts(authorized_content=True)
    result = project(
        facts,
        projection_context=context(
            task=facts[3],
            module_key=JourneyModuleKey.DELIVERY_GUILD,
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            package_status=ModulePackageStatus.REJECTED,
        ),
    )

    assert result.status is ReviewCycleStatus.MODULE_GOVERNANCE_REJECTED
    assert result.blockers == ("MODULE_PACKAGE_REJECTED",)


def test_formal_result_waits_for_approved_appeal_policy_and_exposes_its_window():
    facts = runtime_facts(authorized_content=True)
    pending = project(
        facts,
        projection_context=context(
            task=facts[3],
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            appeal_status=AppealPolicyStatus.PENDING_OWNER_APPROVAL,
        ),
    )
    assert pending.status is ReviewCycleStatus.APPEAL_GOVERNANCE_PENDING
    assert pending.blockers == ("APPEAL_POLICY_NOT_APPROVED",)

    approved_context = context(
        task=facts[3],
        authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
        appeal_status=AppealPolicyStatus.APPROVED,
    )
    approved = project(facts, projection_context=approved_context)
    assert approved.status is ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE
    assert approved_context.appeal_policy is not None
    assert approved.human_gate.appeal_policy_ref is not None
    assert approved.human_gate.appeal_window_ends_at == (
        approved.human_gate.signed_at
        + timedelta(days=approved_context.appeal_policy.scope.appeal_window_days)
    )


def test_rejected_appeal_policy_blocks_formal_result():
    facts = runtime_facts(authorized_content=True)
    rejected = project(
        facts,
        projection_context=context(
            task=facts[3],
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            appeal_status=AppealPolicyStatus.REJECTED,
        ),
    )
    assert rejected.status is ReviewCycleStatus.APPEAL_GOVERNANCE_REJECTED
    assert rejected.blockers == ("APPEAL_POLICY_REJECTED",)


def test_machine_pass_stays_blocked_until_task_authorization_is_approved():
    facts = runtime_facts()
    result = project(facts, projection_context=context(task=facts[3]))

    assert result.status is ReviewCycleStatus.TASK_AUTHORIZATION_PENDING
    assert result.blockers == ("TASK_AUTHORIZATION_NOT_APPROVED",)


def test_rejected_task_authorization_cannot_become_formal_result_eligible():
    facts = runtime_facts(authorized_content=True)
    result = project(
        facts,
        projection_context=context(
            task=facts[3],
            authorization=TaskAuthorizationStatus.REJECTED,
        ),
    )

    assert result.status is ReviewCycleStatus.TASK_AUTHORIZATION_REJECTED
    assert result.blockers == ("TASK_AUTHORIZATION_REJECTED",)


def test_human_revision_gate_never_becomes_formal_result_eligible():
    facts = runtime_facts(
        decision=Decision.REVISION_REQUIRED,
        authorized_content=True,
    )
    result = project(
        facts,
        projection_context=context(
            task=facts[3],
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
        ),
    )

    assert result.status is ReviewCycleStatus.REVISION_REQUIRED
    assert result.blockers == ("HUMAN_GATE_NEEDS_REVISION",)


def test_approved_task_plus_human_pass_is_formal_result_eligible():
    facts = runtime_facts(authorized_content=True)
    result = project(
        facts,
        projection_context=context(
            task=facts[3],
            authorization=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
        ),
    )

    assert result.status is ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE
    assert result.blockers == ()


def test_projection_ids_are_stable_for_the_same_immutable_facts():
    facts = runtime_facts()
    first = project(facts, projection_context=context(task=facts[3]))
    second = project(facts, projection_context=context(task=facts[3]))

    assert first.practice_evidence.evidence_id == second.practice_evidence.evidence_id
    assert first.human_gate.gate_id == second.human_gate.gate_id


def test_revised_practice_evidence_requires_the_immediately_prior_version():
    facts = runtime_facts(version_no=2)
    user, enrollment, assignment, task, submission, version, _, _ = facts
    person = project_person(user=user)

    with pytest.raises(ValueError, match="requires its fixed predecessor"):
        project_practice_evidence(
            person=person,
            enrollment=enrollment,
            assignment=assignment,
            task=task,
            submission=submission,
            version=version,
            context=context(task=task),
            ai_use=no_ai(),
        )

    predecessor = SubmissionVersion(
        id=uuid4(),
        submission_id=submission.id,
        version_no=1,
        body="Prior immutable synthetic evidence version for revision lineage.",
        created_by=user.id,
        created_at=NOW,
    )
    projected = project_practice_evidence(
        person=person,
        enrollment=enrollment,
        assignment=assignment,
        task=task,
        submission=submission,
        version=version,
        previous_version=predecessor,
        context=context(task=task),
        ai_use=no_ai(),
    )
    assert projected.revision == 2
    assert projected.revises_evidence_id is not None


def test_projection_rejects_self_review_even_when_database_objects_are_supplied():
    facts = runtime_facts(reviewer_id=PERSON_ID)

    with pytest.raises(ValueError, match="own human Evaluation"):
        project(facts, projection_context=context(task=facts[3]))
