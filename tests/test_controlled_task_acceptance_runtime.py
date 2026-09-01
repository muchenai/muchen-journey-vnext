from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from journey_api.controlled_task_authorization import task_version_contract_sha256
from journey_api.controlled_task_runtime import (
    authorization_scope_sha256,
    policy_snapshot_sha256,
)
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
from journey_api.main import app
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    ControlledTaskAuthorization,
    ControlledTaskAuthorizationApproval,
    ControlledTaskAuthorizationApprovalDecision,
    ControlledTaskAuthorizationApprovalRole,
    ControlledTaskAuthorizationStatus,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    Handoff,
    HandoffAcceptance,
    HandoffStatus,
    IdentitySession,
    JourneyCompletionPolicy,
    JourneyDefinition,
    JourneyDefinitionStatus,
    JourneyOutcomeEvidence,
    JourneyStageKind,
    JourneyStageVersion,
    JourneyVersion,
    NextTrainingStageDecision,
    NextTrainingStageDecisionValue,
    Outcome,
    Review,
    ReviewStatus,
    Role,
    RoleAssignment,
    Submission,
    SubmissionVersion,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)


POLICY = {
    "allowed_input_schema_ref": "policy://inputs/v1",
    "data_classification": "INTERNAL",
    "deidentification_rule_ref": "policy://deid/v1",
    "evidence_disposition": "DELETE",
    "evidence_retention_days": 30,
    "help_escalation_ref": "policy://help/v1",
    "learner_visibility": ["OWN_EVIDENCE", "TASK"],
    "operator_visibility": ["AUTHORIZATION_STATUS"],
    "policy_schema": "muchen-journey-controlled-task-policy.v1",
    "policy_version": "policy-2026-08-24.1",
    "production_actions_allowed": False,
    "production_credential_allowed": False,
    "production_isolation_rule_ref": "policy://isolation/v1",
    "prohibited_action_codes": ["AUTOMATIC_PUBLISH", "PRODUCTION_WRITE"],
    "reviewer_substitution_rule_ref": "policy://reviewer-substitution/v1",
    "reviewer_visibility": ["ASSIGNED_SUBMISSION", "RUBRIC", "TASK"],
    "training_purpose": "新手村受控训练",
}


def _task(
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    *,
    key: str,
    now: datetime,
) -> tuple[TaskDefinition, TaskVersion]:
    definition = TaskDefinition(
        id=uuid.uuid4(),
        organization_id=organization_id,
        stable_key=key,
        status=TaskDefinitionStatus.PUBLISHED,
        revision=1,
        created_by=actor_id,
        created_at=now,
    )
    task = TaskVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        task_definition_id=definition.id,
        version=1,
        title=f"合成受控任务 {key}",
        purpose="仅用于机器验证受控训练谱系，不连接或写入生产系统。",
        learner_outcome="形成一份可由真人 Reviewer 独立核验的练习证据。",
        instructions=["在隔离环境完成", "提交固定证据"],
        completion_criteria=["证据可核验"],
        required_deliverables=["练习记录"],
        content_source_notes=["synthetic-machine-test-only"],
        change_summary="合成机器测试固定版本",
        reviewer_calibration_note="仅校验谱系和事务，不代表真人 UAT。",
        allowed_attachment_types=[],
        max_attachment_size_bytes=0,
        reference_materials=[],
        learning_materials=[],
        learning_experience={},
        estimated_duration_minutes=30,
        rubric={"dimensions": []},
        rubric_version=1,
        reviewer_role="REVIEWER",
        feedback_sla_business_days=3,
        sensitivity="INTERNAL",
        audience="LEARNER",
        published_by=actor_id,
        reviewed_by=reviewer_id,
        published_at=now,
    )
    return definition, task


def _journey(
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    tasks: list[TaskVersion],
    *,
    key: str,
    now: datetime,
) -> tuple[JourneyDefinition, JourneyVersion, list[JourneyStageVersion]]:
    definition = JourneyDefinition(
        id=uuid.uuid4(),
        organization_id=organization_id,
        stable_key=key,
        status=JourneyDefinitionStatus.PUBLISHED,
        revision=1,
        created_by=actor_id,
        created_at=now,
    )
    version = JourneyVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        journey_definition_id=definition.id,
        version=1,
        title=f"合成旅程 {key}",
        purpose="机器谱系验证",
        change_summary="synthetic-machine-test-only",
        content_review_note="未产生真人 UAT 结论",
        published_by=actor_id,
        reviewed_by=reviewer_id,
        published_at=now,
    )
    stages = [
        JourneyStageVersion(
            id=uuid.uuid4(),
            organization_id=organization_id,
            journey_version_id=version.id,
            stable_key=f"{key}-stage-{index}",
            position=index,
            stage_kind=JourneyStageKind.ASSESSMENT,
            completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
            task_version_id=task.id,
            title=f"合成阶段 {index}",
            short_description="仅用于机器谱系验证",
        )
        for index, task in enumerate(tasks, start=1)
    ]
    return definition, version, stages


def build_synthetic_ready_handoff_and_authorization() -> dict[str, object]:
    now = (datetime.now(UTC) - timedelta(seconds=1)).replace(microsecond=123456)
    with SessionLocal() as session:
        reviewer = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(RoleAssignment.role == Role.REVIEWER)
            .order_by(User.id)
        )
        assert reviewer is not None
        learner = User(
            id=uuid.uuid4(),
            organization_id=reviewer.organization_id,
            display_name="合成本人确认学员",
            status=UserStatus.ACTIVE,
        )
        session.add(learner)
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=reviewer.organization_id,
                user_id=learner.id,
                role=Role.LEARNER,
            )
        )
        session_token = f"synthetic-session-{uuid.uuid4()}"
        csrf_token = f"synthetic-csrf-{uuid.uuid4()}"
        settings = get_settings()
        session.add(
            IdentitySession(
                id=uuid.uuid4(),
                organization_id=reviewer.organization_id,
                user_id=learner.id,
                external_identity_id=None,
                role=Role.LEARNER,
                token_hash=credential_hash(
                    settings.session_secret, "session", session_token
                ),
                csrf_token_hash=credential_hash(
                    settings.session_secret, "csrf", csrf_token
                ),
                expires_at=now + timedelta(days=1),
                created_at=now,
                revoked_at=None,
            )
        )
        session.flush()
        owner_users = [
            User(
                id=uuid.uuid4(),
                organization_id=learner.organization_id,
                display_name=f"合成责任人 {index}",
                status=UserStatus.ACTIVE,
            )
            for index in range(5)
        ]
        session.add_all(owner_users)
        session.flush()

        source_pairs = [
            _task(
                learner.organization_id,
                owner_users[0].id,
                reviewer.id,
                key=f"synthetic-source-{uuid.uuid4().hex}",
                now=now,
            )
            for _ in range(3)
        ]
        target_definition, target_task = _task(
            learner.organization_id,
            owner_users[0].id,
            reviewer.id,
            key=f"synthetic-target-{uuid.uuid4().hex}",
            now=now,
        )
        session.add_all([pair[0] for pair in source_pairs] + [target_definition])
        session.flush()
        session.add_all([pair[1] for pair in source_pairs] + [target_task])
        session.flush()
        source_definition, source_version, source_stages = _journey(
            learner.organization_id,
            owner_users[0].id,
            reviewer.id,
            [pair[1] for pair in source_pairs],
            key=f"synthetic-source-journey-{uuid.uuid4().hex}",
            now=now,
        )
        target_journey_definition, target_journey_version, target_stages = _journey(
            learner.organization_id,
            owner_users[0].id,
            reviewer.id,
            [target_task],
            key=f"synthetic-target-journey-{uuid.uuid4().hex}",
            now=now,
        )
        session.add_all([source_definition, target_journey_definition])
        session.flush()
        session.add_all([source_version, target_journey_version])
        session.flush()
        session.add_all([*source_stages, *target_stages])
        session.flush()
        source_enrollment = Enrollment(
            id=uuid.uuid4(),
            organization_id=learner.organization_id,
            learner_id=learner.id,
            reviewer_id=reviewer.id,
            journey_version_id=source_version.id,
            status=EnrollmentStatus.COMPLETED,
            revision=1,
        )
        session.add(source_enrollment)
        session.flush()
        evaluations: list[Evaluation] = []
        assignments: list[Assignment] = []
        for index, (task_definition, task) in enumerate(source_pairs, start=1):
            assignment = Assignment(
                id=uuid.uuid4(),
                organization_id=learner.organization_id,
                enrollment_id=source_enrollment.id,
                task_definition_id=task_definition.id,
                task_version_id=task.id,
                journey_stage_version_id=source_stages[index - 1].id,
                position=index,
                status=AssignmentStatus.COMPLETED,
                revision=1,
                assigned_at=now,
            )
            submission = Submission(
                id=uuid.uuid4(),
                organization_id=learner.organization_id,
                assignment_id=assignment.id,
                current_version_no=1,
                created_at=now,
            )
            version = SubmissionVersion(
                id=uuid.uuid4(),
                submission_id=submission.id,
                version_no=1,
                body="合成练习证据，仅用于机器验证，不代表真实业务记录或真人通过。",
                ai_use={
                    "used": False,
                    "purpose": None,
                    "model_version": None,
                    "prompt_version": None,
                    "output_is_advisory_only": True,
                },
                created_by=learner.id,
                created_at=now,
            )
            review = Review(
                id=uuid.uuid4(),
                organization_id=learner.organization_id,
                assignment_id=assignment.id,
                submission_id=submission.id,
                submission_version_id=version.id,
                reviewer_id=reviewer.id,
                status=ReviewStatus.FINALIZED,
                revision=1,
                assigned_at=now,
                started_at=now,
                finalized_at=now,
            )
            evaluation = Evaluation(
                id=uuid.uuid4(),
                review_id=review.id,
                organization_id=learner.organization_id,
                assignment_id=assignment.id,
                submission_id=submission.id,
                submission_version_id=version.id,
                reviewer_id=reviewer.id,
                executor_id=reviewer.id,
                review_revision=1,
                decision=Decision.PASS,
                rubric_scores={},
                structured_feedback=[],
                feedback_structure_version=1,
                feedback="合成机器测试 PASS，仅证明约束可执行，不代表真人评价。",
                ai_use={
                    "used": False,
                    "purpose": None,
                    "model_version": None,
                    "prompt_version": None,
                    "output_is_advisory_only": True,
                },
                created_by=reviewer.id,
                created_at=now,
            )
            session.add(assignment)
            session.flush()
            session.add(submission)
            session.flush()
            session.add(version)
            session.flush()
            session.add(review)
            session.flush()
            session.add(evaluation)
            session.flush()
            assignments.append(assignment)
            evaluations.append(evaluation)
        outcome = Outcome(
            id=uuid.uuid4(),
            organization_id=learner.organization_id,
            learner_id=learner.id,
            assignment_id=assignments[-1].id,
            enrollment_id=source_enrollment.id,
            source_evaluation_id=evaluations[-1].id,
            status="HANDOFF_READY",
            summary="合成探索营结果包，仅用于受控纵切机器测试。",
            created_at=now,
        )
        session.add(outcome)
        session.flush()
        session.add_all(
            [
                JourneyOutcomeEvidence(
                    outcome_id=outcome.id,
                    evaluation_id=evaluation.id,
                    journey_stage_version_id=stage.id,
                    organization_id=learner.organization_id,
                    enrollment_id=source_enrollment.id,
                    created_at=now,
                )
                for evaluation, stage in zip(evaluations, source_stages, strict=True)
            ]
        )
        handoff = Handoff(
            id=uuid.uuid4(),
            organization_id=learner.organization_id,
            enrollment_id=source_enrollment.id,
            outcome_id=outcome.id,
            source_evaluation_id=evaluations[-1].id,
            owner_user_id=reviewer.id,
            status=HandoffStatus.READY,
            title="合成探索营交接",
            next_step_code="CONFIRM_HANDOFF",
            next_step_title="确认进入新手村受控训练",
            instructions="本人查看后主动确认；系统不执行任何生产作业。",
            created_at=now,
        )
        session.add(handoff)
        session.flush()
        decision = NextTrainingStageDecision(
            id=uuid.uuid4(),
            organization_id=learner.organization_id,
            handoff_id=handoff.id,
            outcome_id=outcome.id,
            person_id=learner.id,
            decision_scope="NEXT_TRAINING_STAGE",
            decision=NextTrainingStageDecisionValue.READY,
            decision_reason="合成机器测试的下一训练阶段 READY 决定，不代表真实人才结论。",
            decided_by_user_id=owner_users[0].id,
            decision_evidence_ref="synthetic://next-training-stage/ready",
            decision_evidence_sha256="a" * 64,
            decided_at=now,
            created_at=now,
        )
        session.add(decision)
        session.flush()

        task_hash = task_version_contract_sha256(target_task)
        policy_hash = policy_snapshot_sha256(POLICY)
        scope_values = {
            "organization_id": learner.organization_id,
            "authorized_project_ref": "synthetic://newcomer-controlled-project",
            "target_journey_version_id": target_journey_version.id,
            "target_journey_stage_version_id": target_stages[0].id,
            "task_version_id": target_task.id,
            "task_version_sha256": task_hash,
            "authorization_version": 1,
            "project_owner_user_id": owner_users[0].id,
            "newcomer_operations_owner_user_id": owner_users[1].id,
            "data_security_owner_user_id": owner_users[2].id,
            "reviewer_owner_user_id": owner_users[3].id,
            "primary_reviewer_user_id": reviewer.id,
            "backup_reviewer_user_id": owner_users[4].id,
            "policy_snapshot_ref": "synthetic://policy/newcomer/v1",
            "policy_snapshot_version": "policy-2026-08-24.1",
            "policy_snapshot_sha256": policy_hash,
            "policy_evidence_ref": "synthetic://policy-evidence/newcomer/v1",
            "policy_evidence_sha256": "b" * 64,
            "valid_from": now - timedelta(minutes=5),
            "expires_at": now + timedelta(hours=1),
        }
        scope_hash = authorization_scope_sha256(**scope_values)
        authorization = ControlledTaskAuthorization(
            id=uuid.uuid4(),
            authorization_scope="NEWCOMER_CONTROLLED_TRAINING",
            scope_sha256=scope_hash,
            status=ControlledTaskAuthorizationStatus.DRAFT,
            revision=1,
            created_by_user_id=owner_users[0].id,
            created_at=now,
            updated_at=now,
            **scope_values,
        )
        session.add(authorization)
        session.flush()
        authorization.status = ControlledTaskAuthorizationStatus.PENDING_APPROVALS
        authorization.revision = 2
        session.flush()
        role_signers = {
            ControlledTaskAuthorizationApprovalRole.PROJECT_OWNER: owner_users[0].id,
            ControlledTaskAuthorizationApprovalRole.NEWCOMER_OPERATIONS_OWNER: owner_users[1].id,
            ControlledTaskAuthorizationApprovalRole.DATA_SECURITY_OWNER: owner_users[2].id,
            ControlledTaskAuthorizationApprovalRole.REVIEWER_OWNER: owner_users[3].id,
        }
        session.add_all(
            [
                ControlledTaskAuthorizationApproval(
                    id=uuid.uuid4(),
                    organization_id=learner.organization_id,
                    authorization_id=authorization.id,
                    approval_role=role,
                    signer_user_id=signer,
                    decision=ControlledTaskAuthorizationApprovalDecision.APPROVE,
                    signed_scope_sha256=scope_hash,
                    signature_evidence_ref=f"synthetic://approval/{role.value}",
                    signature_evidence_sha256="c" * 64,
                    signed_at=now,
                    created_at=now,
                )
                for role, signer in role_signers.items()
            ]
        )
        session.flush()
        authorization.status = ControlledTaskAuthorizationStatus.ACTIVE
        authorization.revision = 3
        authorization.activated_by_user_id = owner_users[0].id
        authorization.activated_at = now
        session.commit()
        return {
            "organization_id": learner.organization_id,
            "learner_id": learner.id,
            "reviewer_id": reviewer.id,
            "handoff_id": handoff.id,
            "outcome_id": outcome.id,
            "decision_id": decision.id,
            "authorization_id": authorization.id,
            "authorization_revision": authorization.revision,
            "scope_sha256": scope_hash,
            "task_sha256": task_hash,
            "policy_sha256": policy_hash,
            "target_journey_version_id": target_journey_version.id,
            "target_journey_stage_version_id": target_stages[0].id,
            "target_task_version_id": target_task.id,
            "source_journey_version_id": source_version.id,
            "source_journey_stage_version_id": source_stages[0].id,
            "source_task_version_id": source_pairs[0][1].id,
            "wrong_reviewer_id": owner_users[4].id,
            "session_token": session_token,
            "csrf_token": csrf_token,
        }


def _accept_payload(facts: dict[str, object]) -> dict[str, object]:
    return {
        "next_training_stage_decision_id": str(facts["decision_id"]),
        "controlled_task_authorization_id": str(facts["authorization_id"]),
        "expected_authorization_revision": facts["authorization_revision"],
        "expected_scope_sha256": facts["scope_sha256"],
        "expected_task_version_sha256": facts["task_sha256"],
        "expected_policy_snapshot_sha256": facts["policy_sha256"],
        "expected_target_journey_version_id": str(facts["target_journey_version_id"]),
        "expected_target_journey_stage_version_id": str(
            facts["target_journey_stage_version_id"]
        ),
        "expected_target_task_version_id": str(facts["target_task_version_id"]),
    }


def _client(facts: dict[str, object]) -> TestClient:
    client = TestClient(app, base_url="http://localhost")
    client.cookies.set(SESSION_COOKIE, str(facts["session_token"]))
    client.cookies.set(CSRF_COOKIE, str(facts["csrf_token"]))
    return client


def build_synthetic_operator_target() -> dict[str, object]:
    now = (datetime.now(UTC) - timedelta(seconds=1)).replace(microsecond=123456)
    with SessionLocal() as session:
        operator = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                RoleAssignment.role == Role.OPERATOR,
                User.organization_id == ORGANIZATION_ID,
            )
            .order_by(User.id)
        )
        reviewer = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                RoleAssignment.role == Role.REVIEWER,
                User.organization_id == ORGANIZATION_ID,
            )
            .order_by(User.id)
        )
        assert operator is not None and reviewer is not None
        backup = User(
            id=uuid.uuid4(),
            organization_id=operator.organization_id,
            display_name="合成备 Reviewer",
            status=UserStatus.ACTIVE,
        )
        session.add(backup)
        session.flush()
        definition, task = _task(
            operator.organization_id,
            operator.id,
            reviewer.id,
            key=f"synthetic-ops-target-{uuid.uuid4().hex}",
            now=now,
        )
        session.add(definition)
        session.flush()
        session.add(task)
        session.flush()
        journey_definition, journey_version, stages = _journey(
            operator.organization_id,
            operator.id,
            reviewer.id,
            [task],
            key=f"synthetic-ops-journey-{uuid.uuid4().hex}",
            now=now,
        )
        session.add(journey_definition)
        session.flush()
        session.add(journey_version)
        session.flush()
        session.add(stages[0])
        session.commit()
        return {
            "operator_id": operator.id,
            "reviewer_id": reviewer.id,
            "backup_reviewer_id": backup.id,
            "journey_version_id": journey_version.id,
            "stage_id": stages[0].id,
            "task_id": task.id,
            "now": now,
        }


def test_policy_snapshot_golden_vector_and_set_order_are_stable():
    assert policy_snapshot_sha256(POLICY) == (
        "2b09b2431d4f049e6bcf747fd6a2ef65925ca829561218027ec20af0802eecd9"
    )
    reordered = {key: POLICY[key] for key in reversed(POLICY)}
    reordered["reviewer_visibility"] = list(reversed(POLICY["reviewer_visibility"]))
    assert policy_snapshot_sha256(reordered) == policy_snapshot_sha256(POLICY)


def test_person_acceptance_atomically_creates_one_enrollment_and_assignment():
    facts = build_synthetic_ready_handoff_and_authorization()
    client = _client(facts)
    detail = client.get(f"/api/v1/me/handoffs/{facts['handoff_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["acceptance_status"] == "READY_TO_ACCEPT"
    before = None
    with SessionLocal() as session:
        outcome = session.get(Outcome, facts["outcome_id"])
        handoff = session.get(Handoff, facts["handoff_id"])
        assert outcome is not None and handoff is not None
        before = (outcome.summary, outcome.status, handoff.instructions, handoff.status)

    response = client.post(
        f"/api/v1/me/handoffs/{facts['handoff_id']}/accept",
        headers={
            "Idempotency-Key": f"accept-{uuid.uuid4()}",
            "X-CSRF-Token": str(facts["csrf_token"]),
        },
        json=_accept_payload(facts),
    )
    assert response.status_code == 200, response.text
    accepted = response.json()["data"]
    assert accepted["target_journey_stage_version_id"] == str(
        facts["target_journey_stage_version_id"]
    )
    with SessionLocal() as session:
        acceptance = session.get(HandoffAcceptance, uuid.UUID(accepted["id"]))
        enrollment = session.get(Enrollment, uuid.UUID(accepted["target_enrollment_id"]))
        assignment = session.get(Assignment, uuid.UUID(accepted["target_assignment_id"]))
        outcome = session.get(Outcome, facts["outcome_id"])
        handoff = session.get(Handoff, facts["handoff_id"])
        assert acceptance is not None and enrollment is not None and assignment is not None
        assert enrollment.learner_id == facts["learner_id"]
        assert enrollment.reviewer_id == facts["reviewer_id"]
        assert assignment.enrollment_id == enrollment.id
        assert assignment.journey_stage_version_id == facts["target_journey_stage_version_id"]
        assert assignment.task_version_id == facts["target_task_version_id"]
        assert (outcome.summary, outcome.status, handoff.instructions, handoff.status) == before
        assert session.scalar(
            select(func.count(HandoffAcceptance.id)).where(
                HandoffAcceptance.handoff_id == facts["handoff_id"]
            )
        ) == 1


def test_acceptance_rejects_stale_scope_and_writes_nothing():
    facts = build_synthetic_ready_handoff_and_authorization()
    payload = _accept_payload(facts)
    payload["expected_target_journey_stage_version_id"] = str(uuid.uuid4())
    response = _client(facts).post(
        f"/api/v1/me/handoffs/{facts['handoff_id']}/accept",
        headers={
            "Idempotency-Key": f"reject-{uuid.uuid4()}",
            "X-CSRF-Token": str(facts["csrf_token"]),
        },
        json=payload,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AUTHORIZATION_SCOPE_CHANGED"
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(HandoffAcceptance.id)).where(
                HandoffAcceptance.handoff_id == facts["handoff_id"]
            )
        ) == 0


@pytest.mark.parametrize(
    ("stage_key", "task_key"),
    [
        (None, "target_task_version_id"),
        ("source_journey_stage_version_id", "target_task_version_id"),
        ("target_journey_stage_version_id", "source_task_version_id"),
    ],
)
def test_database_rejects_null_cross_journey_stage_and_wrong_task_lineage(
    stage_key: str | None,
    task_key: str,
):
    facts = build_synthetic_ready_handoff_and_authorization()
    with SessionLocal() as session:
        enrollment = Enrollment(
            id=uuid.uuid4(),
            organization_id=facts["organization_id"],
            learner_id=facts["learner_id"],
            reviewer_id=facts["reviewer_id"],
            journey_version_id=facts["target_journey_version_id"],
            status=EnrollmentStatus.ACTIVE,
            revision=1,
        )
        task = session.get(TaskVersion, facts[task_key])
        assert task is not None
        session.add(enrollment)
        session.flush()
        with pytest.raises(DBAPIError, match="lineage mismatch"):
            with session.begin_nested():
                session.add(
                    Assignment(
                        id=uuid.uuid4(),
                        organization_id=facts["organization_id"],
                        enrollment_id=enrollment.id,
                        task_definition_id=task.task_definition_id,
                        task_version_id=task.id,
                        journey_stage_version_id=(
                            None if stage_key is None else facts[stage_key]
                        ),
                        position=1,
                        status=AssignmentStatus.AVAILABLE,
                        revision=1,
                    )
                )
                session.flush()
        session.rollback()


def test_database_rejects_review_reviewer_different_from_enrollment_reviewer():
    facts = build_synthetic_ready_handoff_and_authorization()
    with SessionLocal() as session:
        enrollment = Enrollment(
            id=uuid.uuid4(),
            organization_id=facts["organization_id"],
            learner_id=facts["learner_id"],
            reviewer_id=facts["reviewer_id"],
            journey_version_id=facts["target_journey_version_id"],
            status=EnrollmentStatus.ACTIVE,
            revision=1,
        )
        task = session.get(TaskVersion, facts["target_task_version_id"])
        assert task is not None
        assignment = Assignment(
            id=uuid.uuid4(),
            organization_id=facts["organization_id"],
            enrollment_id=enrollment.id,
            task_definition_id=task.task_definition_id,
            task_version_id=task.id,
            journey_stage_version_id=facts["target_journey_stage_version_id"],
            position=1,
            status=AssignmentStatus.SUBMITTED,
            revision=1,
        )
        submission = Submission(
            id=uuid.uuid4(),
            organization_id=facts["organization_id"],
            assignment_id=assignment.id,
            current_version_no=1,
        )
        version = SubmissionVersion(
            id=uuid.uuid4(),
            submission_id=submission.id,
            version_no=1,
            body="合成评审谱系负向测试，不代表真实提交。",
            created_by=facts["learner_id"],
        )
        session.add(enrollment)
        session.flush()
        session.add(assignment)
        session.flush()
        session.add(submission)
        session.flush()
        session.add(version)
        session.flush()
        with pytest.raises(DBAPIError, match="review reviewer must equal enrollment reviewer"):
            with session.begin_nested():
                session.add(
                    Review(
                        id=uuid.uuid4(),
                        organization_id=facts["organization_id"],
                        assignment_id=assignment.id,
                        submission_id=submission.id,
                        submission_version_id=version.id,
                        reviewer_id=facts["wrong_reviewer_id"],
                        status=ReviewStatus.ASSIGNED,
                        revision=1,
                    )
                )
                session.flush()
        session.rollback()


def test_handoff_acceptance_is_append_only():
    facts = build_synthetic_ready_handoff_and_authorization()
    client = _client(facts)
    response = client.post(
        f"/api/v1/me/handoffs/{facts['handoff_id']}/accept",
        headers={
            "Idempotency-Key": f"immutable-{uuid.uuid4()}",
            "X-CSRF-Token": str(facts["csrf_token"]),
        },
        json=_accept_payload(facts),
    )
    assert response.status_code == 200, response.text
    acceptance_id = uuid.UUID(response.json()["data"]["id"])
    with SessionLocal() as session:
        acceptance = session.get(HandoffAcceptance, acceptance_id)
        assert acceptance is not None
        acceptance.target_reviewer_user_id = uuid.uuid4()
        with pytest.raises(DBAPIError, match="immutable"):
            session.flush()
        session.rollback()


def test_operator_authorization_lifecycle_requires_exact_scope_and_four_role_approvals():
    target = build_synthetic_operator_target()
    client = TestClient(app, base_url="http://localhost")
    headers = {"X-Fixture-Role": "OPERATOR"}
    now = target["now"]
    create = client.post(
        "/api/v1/ops/controlled-task-authorizations",
        headers={**headers, "Idempotency-Key": f"create-{uuid.uuid4()}"},
        json={
            "authorized_project_ref": "synthetic://ops/newcomer-project",
            "target_journey_version_id": str(target["journey_version_id"]),
            "target_journey_stage_version_id": str(target["stage_id"]),
            "target_task_version_id": str(target["task_id"]),
            "authorization_version": 1,
            "project_owner_user_id": str(target["operator_id"]),
            "newcomer_operations_owner_user_id": str(target["operator_id"]),
            "data_security_owner_user_id": str(target["operator_id"]),
            "reviewer_owner_user_id": str(target["operator_id"]),
            "primary_reviewer_user_id": str(target["reviewer_id"]),
            "backup_reviewer_user_id": str(target["backup_reviewer_id"]),
            "policy_snapshot_ref": "synthetic://policy/ops/v1",
            "policy_snapshot": POLICY,
            "policy_evidence_ref": "synthetic://policy-evidence/ops/v1",
            "policy_evidence_sha256": "d" * 64,
            "valid_from": (now - timedelta(minutes=5)).isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert create.status_code == 200, create.text
    authorization = create.json()["data"]
    assert authorization["status"] == "DRAFT"
    authorization_id = authorization["id"]
    submitted = client.post(
        f"/api/v1/ops/controlled-task-authorizations/{authorization_id}/submit-for-approvals",
        headers={**headers, "Idempotency-Key": f"submit-{uuid.uuid4()}"},
        json={"expected_revision": 1},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "PENDING_APPROVALS"
    for role in (
        "PROJECT_OWNER",
        "NEWCOMER_OPERATIONS_OWNER",
        "DATA_SECURITY_OWNER",
        "REVIEWER_OWNER",
    ):
        approved = client.post(
            f"/api/v1/ops/controlled-task-authorizations/{authorization_id}/approvals",
            headers={**headers, "Idempotency-Key": f"approval-{role}-{uuid.uuid4()}"},
            json={
                "expected_authorization_revision": 2,
                "approval_role": role,
                "decision": "APPROVE",
                "expected_scope_sha256": authorization["scope_sha256"],
                "signature_evidence_ref": f"synthetic://signature/{role}",
                "signature_evidence_sha256": "e" * 64,
                "signed_at": now.isoformat(),
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["signer_user_id"] == str(target["operator_id"])
    activated = client.post(
        f"/api/v1/ops/controlled-task-authorizations/{authorization_id}/activate",
        headers={**headers, "Idempotency-Key": f"activate-{uuid.uuid4()}"},
        json={
            "expected_revision": 2,
            "expected_scope_sha256": authorization["scope_sha256"],
            "expected_task_version_sha256": authorization["task_version_sha256"],
            "expected_policy_snapshot_sha256": authorization["policy_snapshot_sha256"],
        },
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["data"]["status"] == "ACTIVE"
    early_expire = client.post(
        f"/api/v1/ops/controlled-task-authorizations/{authorization_id}/expire",
        headers={**headers, "Idempotency-Key": f"expire-{uuid.uuid4()}"},
        json={"expected_revision": 3},
    )
    assert early_expire.status_code == 409
    assert early_expire.json()["error"]["code"] == "AUTHORIZATION_NOT_YET_EXPIRED"
    revoked = client.post(
        f"/api/v1/ops/controlled-task-authorizations/{authorization_id}/revoke",
        headers={**headers, "Idempotency-Key": f"revoke-{uuid.uuid4()}"},
        json={
            "expected_revision": 3,
            "reason": "合成机器测试主动撤销，不代表真实 Owner 操作。",
        },
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["status"] == "REVOKED"
    assert revoked.json()["data"]["revision"] == 4
