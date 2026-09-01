from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError

from journey_api.controlled_task_authorization import (
    ControlledTaskAuthorizationContract,
    TaskAuthorizationDecision,
    TaskAuthorizationRole,
    TaskAuthorizationScopeContract,
    TaskAuthorizationSignatureContract,
    TaskAuthorizationStatus,
    required_task_authorization_roles,
)
from journey_api.main import app
from journey_api.module_execution_package import (
    AiLearningUnitPackageScopeContract,
    GuildPluginPackageScopeContract,
    ModuleExecutionPackageContract,
    ModulePackageDecision,
    ModulePackageRole,
    ModulePackageSignatureContract,
    ModulePackageStatus,
    VersionedArtifactRefContract,
    bind_module_execution_package,
    required_module_package_roles,
)
from journey_api.shared_domain import (
    DataClassification,
    EvidenceVisibility,
    JourneyModuleKey,
)


NOW = datetime(2026, 8, 24, 13, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("60000000-0000-4000-8000-000000000001")
TASK_VERSION_ID = UUID("60000000-0000-4000-8000-000000000002")
TASK_DEFINITION_ID = UUID("60000000-0000-4000-8000-000000000003")
PRIMARY_REVIEWER_ID = UUID("60000000-0000-4000-8000-000000000004")
BACKUP_REVIEWER_ID = UUID("60000000-0000-4000-8000-000000000005")
SIGNER_NAMESPACE = UUID("60000000-0000-4000-8000-000000000006")


def artifact(name: str, *, digest: str = "a" * 64) -> VersionedArtifactRefContract:
    return VersionedArtifactRefContract(
        artifact_ref=f"governance/module-packages/{name}",
        version="v1.0",
        sha256=digest,
    )


def task_authorization(
    module_key: JourneyModuleKey,
    *,
    status: TaskAuthorizationStatus = TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
) -> ControlledTaskAuthorizationContract:
    build_contract_ref = {
        JourneyModuleKey.AI_ACADEMY: (
            "docs/baselines/build-contracts/BC-003_AI学院_V0.1.md"
        ),
        JourneyModuleKey.DELIVERY_GUILD: (
            "docs/baselines/build-contracts/BC-004_公会_V0.1.md"
        ),
    }[module_key]
    scope = TaskAuthorizationScopeContract(
        organization_id=ORGANIZATION_ID,
        module_key=module_key,
        build_contract_ref=build_contract_ref,
        target_journey_version_id=uuid4(),
        target_journey_stage_version_id=uuid4(),
        task_version_id=TASK_VERSION_ID,
        task_definition_id=TASK_DEFINITION_ID,
        task_version_number=1,
        task_version_sha256="b" * 64,
        authorized_task_ref=(
            "authorized-module-practice-v1"
            if status is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK
            else "pending-owner-module-practice-v1"
        ),
        purpose_ref="governance/tasks/module-practice-purpose-v1",
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
        deidentification_ref="governance/tasks/deidentification-v1",
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        primary_reviewer_id=PRIMARY_REVIEWER_ID,
        backup_reviewer_id=BACKUP_REVIEWER_ID,
        retention_policy="controlled-module-evidence-v1",
        deletion_or_archive_rule="governance/tasks/disposition-v1",
        help_or_escalation_ref="governance/tasks/escalation-v1",
        created_at=NOW,
    )
    signatures = ()
    decided_at = None
    if status is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK:
        signatures = tuple(
            TaskAuthorizationSignatureContract(
                signer_person_id=uuid5(SIGNER_NAMESPACE, f"task:{role.value}"),
                role=role,
                decision=TaskAuthorizationDecision.APPROVE,
                subject_sha256=scope.subject_sha256(),
                signed_at=NOW + timedelta(minutes=1),
                evidence_ref=f"evidence/task-authorization/{role.value.lower()}",
            )
            for role in sorted(
                required_task_authorization_roles(module_key),
                key=lambda item: item.value,
            )
        )
        decided_at = NOW + timedelta(minutes=2)
    return ControlledTaskAuthorizationContract(
        authorization_id=uuid4(),
        scope=scope,
        status=status,
        signatures=signatures,
        decided_at=decided_at,
    )


def package_scope(
    authorization: ControlledTaskAuthorizationContract,
    **overrides,
):
    task_scope = authorization.scope
    values = {
        "organization_id": task_scope.organization_id,
        "build_contract_ref": task_scope.build_contract_ref,
        "package_ref": (
            "authorized-ai-learning-unit-v1"
            if task_scope.module_key is JourneyModuleKey.AI_ACADEMY
            else "authorized-delivery-guild-plugin-v1"
        ),
        "package_version": "v1.0",
        "task_authorization_id": authorization.authorization_id,
        "task_authorization_scope_sha256": task_scope.subject_sha256(),
        "task_version_id": task_scope.task_version_id,
        "task_version_sha256": task_scope.task_version_sha256,
        "target_capability_ref": "capabilities/evidence-led-practice-v1",
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
        "created_at": NOW + timedelta(minutes=3),
    }
    values.update(overrides)
    if task_scope.module_key is JourneyModuleKey.AI_ACADEMY:
        return AiLearningUnitPackageScopeContract(
            **values,
            unit_title="Evidence-led AI practice",
            applicable_role_refs=("roles/company-learner",),
            content_sources=(artifact("content-source"),),
            learning_materials=(artifact("learning-material"),),
            example=artifact("example"),
            counterexample=artifact("counterexample"),
            estimated_duration_minutes=45,
        )
    return GuildPluginPackageScopeContract(
        **values,
        guild_name="Delivery Practice Guild",
        mission=artifact("guild-mission"),
        capability_model=artifact("guild-capability-model"),
        membership_rules=artifact("guild-membership-rules"),
        mentor_pool=artifact("guild-mentor-pool"),
        activity_cadence=artifact("guild-activity-cadence"),
        collaboration_boundary=artifact("guild-collaboration-boundary"),
        next_action_rule=artifact("guild-next-action-rule"),
    )


def package_signatures(
    scope,
    *,
    roles: frozenset[ModulePackageRole] | None = None,
    decision: ModulePackageDecision = ModulePackageDecision.APPROVE,
) -> tuple[ModulePackageSignatureContract, ...]:
    return tuple(
        ModulePackageSignatureContract(
            signer_person_id=uuid5(SIGNER_NAMESPACE, f"package:{role.value}"),
            role=role,
            decision=decision,
            subject_sha256=scope.subject_sha256(),
            signed_at=NOW + timedelta(minutes=4),
            evidence_ref=f"evidence/module-package/{role.value.lower()}",
        )
        for role in sorted(
            roles or required_module_package_roles(scope.module_key),
            key=lambda item: item.value,
        )
    )


def approved_package(
    authorization: ControlledTaskAuthorizationContract,
    *,
    scope=None,
) -> ModuleExecutionPackageContract:
    scope = scope or package_scope(authorization)
    return ModuleExecutionPackageContract(
        package_id=uuid4(),
        scope=scope,
        status=ModulePackageStatus.APPROVED,
        signatures=package_signatures(scope),
        decided_at=NOW + timedelta(minutes=5),
    )


@pytest.mark.parametrize(
    "module_key",
    [JourneyModuleKey.AI_ACADEMY, JourneyModuleKey.DELIVERY_GUILD],
)
def test_approved_package_binds_exact_task_authorization_and_governance(module_key):
    authorization = task_authorization(module_key)
    package = approved_package(authorization)

    assert bind_module_execution_package(
        task_authorization=authorization,
        package=package,
    ) is ModulePackageStatus.APPROVED


def test_scope_digest_covers_versioned_content_and_module_rules():
    authorization = task_authorization(JourneyModuleKey.AI_ACADEMY)
    scope = package_scope(authorization)
    values = scope.model_dump()
    values["learning_materials"] = (artifact("different-material", digest="c" * 64),)
    changed = AiLearningUnitPackageScopeContract(**values)

    assert scope.subject_sha256() != changed.subject_sha256()


def test_ai_unit_requires_disclosure_and_guild_requires_human_membership_decision():
    ai_authorization = task_authorization(JourneyModuleKey.AI_ACADEMY)
    ai_values = package_scope(ai_authorization).model_dump()
    ai_values["ai_use_disclosure_required"] = False
    with pytest.raises(ValidationError, match="AI-use disclosure"):
        AiLearningUnitPackageScopeContract(**ai_values)

    guild_authorization = task_authorization(JourneyModuleKey.DELIVERY_GUILD)
    guild_values = package_scope(guild_authorization).model_dump()
    guild_values["human_membership_decision_required"] = False
    with pytest.raises(ValidationError, match="AI or points alone"):
        GuildPluginPackageScopeContract(**guild_values)


def test_package_never_permits_production_execution_or_ai_finalization():
    authorization = task_authorization(JourneyModuleKey.AI_ACADEMY)
    values = package_scope(authorization).model_dump()
    values["production_system_write_allowed"] = True
    with pytest.raises(ValidationError, match="cannot permit production execution"):
        AiLearningUnitPackageScopeContract(**values)

    values = package_scope(authorization).model_dump()
    values["ai_advisory_cannot_finalize"] = False
    with pytest.raises(ValidationError, match="cannot replace required human review"):
        AiLearningUnitPackageScopeContract(**values)


def test_approval_requires_all_real_human_roles_on_exact_digest():
    authorization = task_authorization(JourneyModuleKey.DELIVERY_GUILD)
    scope = package_scope(authorization)
    missing_mentor = frozenset(
        required_module_package_roles(scope.module_key)
        - {ModulePackageRole.MENTOR_OWNER}
    )
    with pytest.raises(ValidationError, match="missing required signer roles"):
        ModuleExecutionPackageContract(
            package_id=uuid4(),
            scope=scope,
            status=ModulePackageStatus.APPROVED,
            signatures=package_signatures(scope, roles=missing_mentor),
            decided_at=NOW + timedelta(minutes=5),
        )

    wrong_subject = package_signatures(scope)[0].model_copy(
        update={"subject_sha256": "0" * 64}
    )
    with pytest.raises(ValidationError, match="exact scope digest"):
        ModuleExecutionPackageContract(
            package_id=uuid4(),
            scope=scope,
            status=ModulePackageStatus.APPROVED,
            signatures=(wrong_subject, *package_signatures(scope)[1:]),
            decided_at=NOW + timedelta(minutes=5),
        )

    signature_values = package_signatures(scope)[0].model_dump()
    signature_values["attestation_kind"] = "AI_ATTESTATION"
    with pytest.raises(ValidationError):
        ModulePackageSignatureContract(**signature_values)


def test_approved_package_rejects_candidate_markers_and_owner_self_review():
    authorization = task_authorization(JourneyModuleKey.AI_ACADEMY)
    values = package_scope(authorization).model_dump()
    values["package_ref"] = "synthetic-ai-unit-test-only"
    synthetic_scope = AiLearningUnitPackageScopeContract(**values)
    with pytest.raises(ValidationError, match="non-authoritative content"):
        approved_package(authorization, scope=synthetic_scope)

    content_owner_id = uuid5(
        SIGNER_NAMESPACE,
        f"package:{ModulePackageRole.CONTENT_OWNER.value}",
    )
    self_review_scope = package_scope(
        authorization,
        primary_reviewer_id=content_owner_id,
    )
    with pytest.raises(ValidationError, match="separate from module package ownership"):
        approved_package(authorization, scope=self_review_scope)


def test_binding_rejects_authorization_or_governance_drift():
    authorization = task_authorization(JourneyModuleKey.DELIVERY_GUILD)
    package = approved_package(authorization)
    other_authorization = task_authorization(JourneyModuleKey.DELIVERY_GUILD)
    with pytest.raises(ValueError, match="does not bind"):
        bind_module_execution_package(
            task_authorization=other_authorization,
            package=package,
        )

    scope_values = package.scope.model_dump()
    scope_values["retention_policy"] = "different-retention-v1"
    drifted_scope = GuildPluginPackageScopeContract(**scope_values)
    drifted_package = approved_package(authorization, scope=drifted_scope)
    with pytest.raises(ValueError, match="evidence governance differs"):
        bind_module_execution_package(
            task_authorization=authorization,
            package=drifted_package,
        )


def test_approved_package_requires_approved_controlled_task():
    pending_authorization = task_authorization(
        JourneyModuleKey.AI_ACADEMY,
        status=TaskAuthorizationStatus.PENDING_OWNER_APPROVAL,
    )
    package = approved_package(pending_authorization)
    with pytest.raises(ValueError, match="requires an approved controlled task"):
        bind_module_execution_package(
            task_authorization=pending_authorization,
            package=package,
        )


def test_rejected_package_requires_human_rejection_and_never_approves():
    authorization = task_authorization(JourneyModuleKey.DELIVERY_GUILD)
    scope = package_scope(authorization)
    rejected = ModuleExecutionPackageContract(
        package_id=uuid4(),
        scope=scope,
        status=ModulePackageStatus.REJECTED,
        signatures=package_signatures(
            scope,
            roles=frozenset({ModulePackageRole.DATA_SECURITY_OWNER}),
            decision=ModulePackageDecision.REJECT,
        ),
        decided_at=NOW + timedelta(minutes=5),
    )
    assert bind_module_execution_package(
        task_authorization=authorization,
        package=rejected,
    ) is ModulePackageStatus.REJECTED

    with pytest.raises(ValidationError, match="requires a rejecting human signature"):
        ModuleExecutionPackageContract(
            package_id=uuid4(),
            scope=scope,
            status=ModulePackageStatus.REJECTED,
            decided_at=NOW + timedelta(minutes=5),
        )


def test_machine_candidate_opens_no_runtime_api_or_database_model():
    assert not hasattr(ModuleExecutionPackageContract, "__tablename__")
    assert all("module-package" not in path for path in app.openapi()["paths"])
