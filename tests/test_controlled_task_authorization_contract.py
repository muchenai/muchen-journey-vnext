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
    bind_task_version_authorization,
    required_task_authorization_roles,
    task_version_contract_sha256,
)
from journey_api.models import TaskVersion
from journey_api.main import app
from journey_api.shared_domain import (
    DataClassification,
    EvidenceVisibility,
    JourneyModuleKey,
)


NOW = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("50000000-0000-4000-8000-000000000001")
PRIMARY_REVIEWER_ID = UUID("50000000-0000-4000-8000-000000000002")
BACKUP_REVIEWER_ID = UUID("50000000-0000-4000-8000-000000000003")
SIGNER_NAMESPACE = UUID("50000000-0000-4000-8000-000000000004")


def task_version(**overrides) -> TaskVersion:
    values = {
        "id": uuid4(),
        "organization_id": ORGANIZATION_ID,
        "task_definition_id": uuid4(),
        "version": 1,
        "title": "Controlled newcomer delivery practice",
        "purpose": "Produce a bounded artifact outside production and submit evidence for review.",
        "learner_outcome": "The learner can complete a controlled delivery and respond to review.",
        "instructions": ["Work only in the approved non-production environment."],
        "completion_criteria": ["Submit immutable evidence for human review."],
        "required_deliverables": ["A reviewable delivery artifact."],
        "content_source_notes": ["BC-002 first controlled task candidate."],
        "change_summary": "Initial controlled-task authorization candidate.",
        "reviewer_calibration_note": "Reviewer calibration remains a human Gate.",
        "allowed_attachment_types": ["text/plain"],
        "max_attachment_size_bytes": 1024,
        "reference_materials": [],
        "learning_materials": [],
        "learning_experience": {},
        "estimated_duration_minutes": 45,
        "rubric": {"version": 1, "dimensions": ["evidence"]},
        "rubric_version": 1,
        "reviewer_role": "REVIEWER",
        "feedback_sla_business_days": 2,
        "sensitivity": "INTERNAL",
        "audience": "LEARNER",
        "published_by": uuid4(),
        "reviewed_by": PRIMARY_REVIEWER_ID,
        "published_at": NOW,
    }
    values.update(overrides)
    return TaskVersion(**values)


def authorization_scope(
    task: TaskVersion,
    *,
    module_key: JourneyModuleKey = JourneyModuleKey.NEWCOMER_VILLAGE,
    task_ref: str = "approved-newcomer-controlled-task-v1",
    **overrides,
) -> TaskAuthorizationScopeContract:
    build_contract = {
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
    values = {
        "organization_id": task.organization_id,
        "module_key": module_key,
        "build_contract_ref": build_contract,
        "target_journey_version_id": uuid4(),
        "target_journey_stage_version_id": uuid4(),
        "task_version_id": task.id,
        "task_definition_id": task.task_definition_id,
        "task_version_number": task.version,
        "task_version_sha256": task_version_contract_sha256(task),
        "authorized_task_ref": task_ref,
        "purpose_ref": "contracts/tasks/newcomer-controlled-purpose-v1",
        "data_classification": DataClassification.CONFIDENTIAL_PEOPLE,
        "deidentification_ref": "contracts/tasks/newcomer-deidentification-v1",
        "visibility": (
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        "primary_reviewer_id": PRIMARY_REVIEWER_ID,
        "backup_reviewer_id": BACKUP_REVIEWER_ID,
        "retention_policy": "controlled-task-evidence-v1",
        "deletion_or_archive_rule": "contracts/tasks/disposition-v1",
        "help_or_escalation_ref": "contracts/tasks/escalation-v1",
        "created_at": NOW,
    }
    values.update(overrides)
    return TaskAuthorizationScopeContract(**values)


def signatures(
    scope: TaskAuthorizationScopeContract,
    *,
    roles: frozenset[TaskAuthorizationRole] | None = None,
    decision: TaskAuthorizationDecision = TaskAuthorizationDecision.APPROVE,
) -> tuple[TaskAuthorizationSignatureContract, ...]:
    return tuple(
        TaskAuthorizationSignatureContract(
            signer_person_id=uuid5(SIGNER_NAMESPACE, role.value),
            role=role,
            decision=decision,
            subject_sha256=scope.subject_sha256(),
            signed_at=NOW + timedelta(minutes=5),
            evidence_ref=f"evidence/task-authorization/{role.value.lower()}",
        )
        for role in sorted(
            roles or required_task_authorization_roles(scope.module_key),
            key=lambda item: item.value,
        )
    )


def approved_authorization(
    task: TaskVersion,
    *,
    scope: TaskAuthorizationScopeContract | None = None,
) -> ControlledTaskAuthorizationContract:
    scope = scope or authorization_scope(task)
    return ControlledTaskAuthorizationContract(
        authorization_id=uuid4(),
        scope=scope,
        status=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
        signatures=signatures(scope),
        decided_at=NOW + timedelta(minutes=10),
    )


def test_task_version_digest_is_stable_and_covers_executable_content():
    task = task_version()
    first = task_version_contract_sha256(task)
    second = task_version_contract_sha256(task)
    task.instructions = ["Changed instruction after the authorization snapshot."]

    assert first == second
    assert task_version_contract_sha256(task) != first


def test_scope_requires_all_six_control_fields_and_forbids_production_execution():
    task = task_version()
    values = authorization_scope(task).model_dump()
    values["production_system_write_allowed"] = True
    with pytest.raises(ValidationError, match="cannot permit production execution"):
        TaskAuthorizationScopeContract(**values)

    values = authorization_scope(task).model_dump()
    values["backup_reviewer_id"] = PRIMARY_REVIEWER_ID
    with pytest.raises(ValidationError, match="backup Reviewer"):
        TaskAuthorizationScopeContract(**values)


def test_synthetic_authorization_is_visible_and_cannot_carry_human_approval():
    task = task_version()
    scope = authorization_scope(task, task_ref="synthetic-newcomer-task-test-only")
    synthetic = ControlledTaskAuthorizationContract(
        authorization_id=uuid4(),
        scope=scope,
        status=TaskAuthorizationStatus.SYNTHETIC_TEST_ONLY,
    )
    assert synthetic.status is TaskAuthorizationStatus.SYNTHETIC_TEST_ONLY

    with pytest.raises(ValidationError, match="cannot carry human approval"):
        ControlledTaskAuthorizationContract(
            authorization_id=uuid4(),
            scope=scope,
            status=TaskAuthorizationStatus.SYNTHETIC_TEST_ONLY,
            signatures=signatures(scope),
            decided_at=NOW + timedelta(minutes=10),
        )


def test_approved_authorization_requires_all_human_roles_on_the_exact_subject():
    task = task_version()
    scope = authorization_scope(task)
    missing_role = frozenset(
        required_task_authorization_roles(scope.module_key)
        - {TaskAuthorizationRole.DATA_SECURITY_OWNER}
    )
    with pytest.raises(ValidationError, match="missing required signer roles"):
        ControlledTaskAuthorizationContract(
            authorization_id=uuid4(),
            scope=scope,
            status=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            signatures=signatures(scope, roles=missing_role),
            decided_at=NOW + timedelta(minutes=10),
        )

    wrong_subject = signatures(scope)[0].model_copy(
        update={"subject_sha256": "0" * 64}
    )
    with pytest.raises(ValidationError, match="exact scope digest"):
        ControlledTaskAuthorizationContract(
            authorization_id=uuid4(),
            scope=scope,
            status=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            signatures=(wrong_subject, *signatures(scope)[1:]),
            decided_at=NOW + timedelta(minutes=10),
        )


def test_ai_or_self_attestation_cannot_sign_task_authorization():
    values = signatures(authorization_scope(task_version()))[0].model_dump()
    values["attestation_kind"] = "AI_ATTESTATION"
    with pytest.raises(ValidationError):
        TaskAuthorizationSignatureContract(**values)


def test_approved_authorization_rejects_synthetic_refs_and_owner_self_review():
    task = task_version()
    synthetic_scope = authorization_scope(
        task,
        task_ref="synthetic-newcomer-task-test-only",
    )
    with pytest.raises(ValidationError, match="non-authoritative ref"):
        ControlledTaskAuthorizationContract(
            authorization_id=uuid4(),
            scope=synthetic_scope,
            status=TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK,
            signatures=signatures(synthetic_scope),
            decided_at=NOW + timedelta(minutes=10),
        )

    owner_id = uuid5(SIGNER_NAMESPACE, TaskAuthorizationRole.TASK_BUSINESS_OWNER.value)
    self_review_scope = authorization_scope(task, primary_reviewer_id=owner_id)
    with pytest.raises(ValidationError, match="separate from task/content ownership"):
        approved_authorization(task, scope=self_review_scope)


def test_binding_rejects_any_task_version_or_digest_drift():
    task = task_version()
    authorization = approved_authorization(task)
    assert bind_task_version_authorization(
        task=task,
        authorization=authorization,
    ) is TaskAuthorizationStatus.APPROVED_CONTROLLED_TASK

    task.title = "Changed after authorization"
    with pytest.raises(ValueError, match="differs from the authorized digest"):
        bind_task_version_authorization(task=task, authorization=authorization)

    other = task_version()
    with pytest.raises(ValueError, match="does not bind"):
        bind_task_version_authorization(task=other, authorization=authorization)

    synthetic_task = task_version(
        content_source_notes=["Synthetic test-only package."],
    )
    synthetic_content_authorization = approved_authorization(synthetic_task)
    with pytest.raises(ValueError, match="cannot bind synthetic TaskVersion content"):
        bind_task_version_authorization(
            task=synthetic_task,
            authorization=synthetic_content_authorization,
        )


def test_rejected_authorization_requires_a_human_rejection_and_never_approves():
    task = task_version()
    scope = authorization_scope(task, task_ref="rejected-newcomer-task-v1")
    rejected = ControlledTaskAuthorizationContract(
        authorization_id=uuid4(),
        scope=scope,
        status=TaskAuthorizationStatus.REJECTED,
        signatures=signatures(
            scope,
            roles=frozenset({TaskAuthorizationRole.DATA_SECURITY_OWNER}),
            decision=TaskAuthorizationDecision.REJECT,
        ),
        decided_at=NOW + timedelta(minutes=10),
    )

    assert bind_task_version_authorization(
        task=task,
        authorization=rejected,
    ) is TaskAuthorizationStatus.REJECTED
    assert rejected.model_dump().get("formal_talent_status") is None


def test_machine_contract_remains_separate_from_the_bounded_acceptance_runtime():
    assert not hasattr(ControlledTaskAuthorizationContract, "__tablename__")
    paths = app.openapi()["paths"]
    assert "/api/v1/me/handoffs/{handoff_id}/accept" in paths
    assert {
        "/api/v1/ops/controlled-task-authorizations",
        "/api/v1/ops/controlled-task-authorizations/{authorization_id}",
        "/api/v1/ops/controlled-task-authorizations/{authorization_id}/submit-for-approvals",
        "/api/v1/ops/controlled-task-authorizations/{authorization_id}/approvals",
        "/api/v1/ops/controlled-task-authorizations/{authorization_id}/activate",
        "/api/v1/ops/controlled-task-authorizations/{authorization_id}/expire",
        "/api/v1/ops/controlled-task-authorizations/{authorization_id}/revoke",
    }.issubset(paths)
