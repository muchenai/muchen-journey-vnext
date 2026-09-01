import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID, TASK_VERSION_V2_ID
from journey_api.main import app
from journey_api.models import (
    Assignment,
    Enrollment,
    Evaluation,
    Outcome,
    Review,
    Submission,
    SubmissionVersion,
    TaskVersion,
    User,
)
from journey_api.controlled_task_authorization import (
    ControlledTaskAuthorizationContract,
    TaskAuthorizationScopeContract,
    TaskAuthorizationStatus,
    task_version_contract_sha256,
)
from journey_api.appeal_continuity import (
    AppealPolicyStatus,
    HumanGateAppealPolicyContract,
    HumanGateAppealPolicyScopeContract,
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
    project_review_cycle,
)


REVIEWER_HEADERS = {"X-Fixture-Role": "REVIEWER"}
OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}
RUBRIC_KEYS = (
    "problem_clarity",
    "evidence_quality",
    "action_feasibility",
    "validation_design",
)


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 55_000))


def data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def submission_body(label: str) -> str:
    return (
        f"{label}：我在隔离测试中完成受控行动，没有写入任何生产系统。"
        "提交固定记录包括目标、边界、两条可核对观察、下一步责任人，"
        "并说明两周内的验证指标与停止条件，供真人 Reviewer 审核。"
    )


def finalize_payload(
    revision: int, *, approve: bool, feedback: str
) -> dict[str, object]:
    needs_work_key = None if approve else "evidence_quality"
    return {
        "expected_revision": revision,
        "overall_decision": "APPROVE" if approve else "REQUEST_REVISION",
        "overall_feedback": feedback,
        "rubric_evaluations": [
            {
                "dimension_key": key,
                "rating": "NEEDS_WORK" if key == needs_work_key else "MEETS",
                "feedback": (
                    "请补充这一维度的固定来源并再次提交。"
                    if key == needs_work_key
                    else "固定提交中的该维度达到合成测试 Rubric。"
                ),
            }
            for key in RUBRIC_KEYS
        ],
    }


def synthetic_newcomer_context(task: TaskVersion) -> ModuleProjectionContext:
    scope = TaskAuthorizationScopeContract(
        organization_id=task.organization_id,
        module_key=JourneyModuleKey.NEWCOMER_VILLAGE,
        build_contract_ref=(
            "docs/baselines/build-contracts/BC-002_新手村受控任务闭环_V0.1.md"
        ),
        target_journey_version_id=uuid.uuid4(),
        target_journey_stage_version_id=uuid.uuid4(),
        task_version_id=task.id,
        task_definition_id=task.task_definition_id,
        task_version_number=task.version,
        task_version_sha256=task_version_contract_sha256(task),
        authorized_task_ref="synthetic-g2-vertical-loop-only",
        purpose_ref="tests/g2-synthetic-purpose",
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
        deidentification_ref="tests/g2-synthetic-deidentification",
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        primary_reviewer_id=REVIEWER_ID,
        backup_reviewer_id=uuid.UUID("10000000-0000-4000-8000-00000000000d"),
        retention_policy="g2-synthetic-evidence-v1",
        deletion_or_archive_rule="tests/g2-synthetic-disposition",
        help_or_escalation_ref="tests/g2-synthetic-escalation",
        created_at=task.published_at,
    )
    task_authorization = ControlledTaskAuthorizationContract(
        authorization_id=uuid.uuid4(),
        scope=scope,
        status=TaskAuthorizationStatus.SYNTHETIC_TEST_ONLY,
    )
    appeal_policy = HumanGateAppealPolicyContract(
        policy_id=uuid.uuid4(),
        scope=HumanGateAppealPolicyScopeContract(
            organization_id=scope.organization_id,
            module_key=scope.module_key,
            build_contract_ref=scope.build_contract_ref,
            policy_ref="synthetic-g2-appeal-policy-test-only",
            policy_version="v1",
            policy_sha256="1" * 64,
            applicable_gate_kind=HumanGateKind.TASK_PASS,
            task_authorization_id=task_authorization.authorization_id,
            task_authorization_scope_sha256=scope.subject_sha256(),
            appeal_window_days=14,
            resolution_sla_business_days=5,
            reviewer_assignment_rule_ref="tests/g2-appeal-assignment-rule",
            correction_evidence_rule_ref="tests/g2-appeal-evidence-rule",
            visibility=scope.visibility,
            data_classification=scope.data_classification,
            retention_policy=scope.retention_policy,
            created_at=scope.created_at,
        ),
        status=AppealPolicyStatus.PENDING_OWNER_APPROVAL,
    )
    return ModuleProjectionContext(
        module_key=JourneyModuleKey.NEWCOMER_VILLAGE,
        build_contract_ref=(
            "docs/baselines/build-contracts/BC-002_新手村受控任务闭环_V0.1.md"
        ),
        task_authorization=task_authorization,
        appeal_policy=appeal_policy,
        gate_kind=HumanGateKind.TASK_PASS,
        retention_policy="g2-synthetic-evidence-v1",
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
    )


def project_cycle(
    *,
    assignment_id: uuid.UUID,
    submission_version_id: uuid.UUID,
    previous_version_id: uuid.UUID | None = None,
):
    with SessionLocal() as session:
        assignment = session.get(Assignment, assignment_id)
        assert assignment is not None
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        task = session.get(TaskVersion, assignment.task_version_id)
        assert enrollment is not None and task is not None
        user = session.get(User, enrollment.learner_id)
        version = session.get(SubmissionVersion, submission_version_id)
        assert user is not None and version is not None
        submission = session.get(Submission, version.submission_id)
        assert submission is not None
        evaluation = session.scalar(
            select(Evaluation).where(
                Evaluation.submission_version_id == submission_version_id
            )
        )
        assert evaluation is not None
        review = session.get(Review, evaluation.review_id)
        assert review is not None
        previous_version = (
            session.get(SubmissionVersion, previous_version_id)
            if previous_version_id is not None
            else None
        )
        return project_review_cycle(
            user=user,
            enrollment=enrollment,
            assignment=assignment,
            task=task,
            submission=submission,
            version=version,
            review=review,
            evaluation=evaluation,
            context=synthetic_newcomer_context(task),
            submission_ai_use=AiUseDisclosure(used=False),
            review_ai_use=AiUseDisclosure(used=False),
            previous_version=previous_version,
        )


def test_g2_synthetic_loop_preserves_revision_and_human_gate_without_formal_promotion():
    suffix = uuid.uuid4().hex
    operator = client_for(f"g2-operator-{suffix}")
    invite = data(
        operator.post(
            "/api/v1/ops/invites",
            headers={
                **OPERATOR_HEADERS,
                "Idempotency-Key": f"g2-invite-{suffix}",
            },
            json={
                "purpose": "G2 合成受控任务纵向闭环，不连接生产系统",
                "expires_in_hours": 24,
                "role": "LEARNER",
                "reviewer_id": str(REVIEWER_ID),
                "task_version_id": str(TASK_VERSION_V2_ID),
                "target_user_id": None,
            },
        )
    )
    learner = client_for(f"g2-learner-{suffix}")
    exchange = data(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite["invite_token"], "return_to": "/app"},
        )
    )
    confirmed = data(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchange["csrf_token"]},
            json={
                "display_name": f"G2 合成人员 {suffix[:6]}",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    current = data(learner.get("/api/v1/me/current-action"))
    assignment_id = uuid.UUID(current["resource_id"])
    started = data(
        learner.post(
            f"/api/v1/me/assignments/{assignment_id}/start",
            headers={
                "Idempotency-Key": f"g2-start-{suffix}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={"expected_revision": current["revision"]},
        )
    )
    first_submission = data(
        learner.post(
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            headers={
                "Idempotency-Key": f"g2-submit-1-{suffix}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={
                "expected_revision": started["revision"],
                "body": submission_body("第一版"),
                "attachment_ids": [],
            },
        )
    )
    first_version_id = uuid.UUID(first_submission["submission_version_id"])
    with SessionLocal() as session:
        first_review = session.scalar(
            select(Review).where(Review.submission_version_id == first_version_id)
        )
        assert first_review is not None
        first_review_id = first_review.id

    reviewer = client_for(f"g2-reviewer-{suffix}")
    first_review_started = data(
        reviewer.post(
            f"/api/v1/reviews/{first_review_id}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"g2-review-start-1-{suffix}",
            },
            json={"expected_revision": 1},
        )
    )
    first_final = data(
        reviewer.post(
            f"/api/v1/reviews/{first_review_id}/finalize",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"g2-review-final-1-{suffix}",
            },
            json=finalize_payload(
                first_review_started["review_revision"],
                approve=False,
                feedback="第一版缺少一条固定来源，请保留原版并提交修订。",
            ),
        )
    )
    first_projection = project_cycle(
        assignment_id=assignment_id,
        submission_version_id=first_version_id,
    )
    assert first_projection.status is ReviewCycleStatus.REVISION_REQUIRED
    assert first_projection.blockers == (
        "HUMAN_GATE_NEEDS_REVISION",
        "TASK_AUTHORIZATION_NOT_APPROVED",
    )

    second_submission = data(
        learner.post(
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            headers={
                "Idempotency-Key": f"g2-submit-2-{suffix}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={
                "expected_revision": first_final["assignment_revision"],
                "body": submission_body("第二版补充固定来源"),
                "attachment_ids": [],
            },
        )
    )
    second_version_id = uuid.UUID(second_submission["submission_version_id"])
    with SessionLocal() as session:
        second_review = session.scalar(
            select(Review).where(Review.submission_version_id == second_version_id)
        )
        assert second_review is not None
        second_review_id = second_review.id

    second_review_started = data(
        reviewer.post(
            f"/api/v1/reviews/{second_review_id}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"g2-review-start-2-{suffix}",
            },
            json={"expected_revision": 1},
        )
    )
    second_final = data(
        reviewer.post(
            f"/api/v1/reviews/{second_review_id}/finalize",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"g2-review-final-2-{suffix}",
            },
            json=finalize_payload(
                second_review_started["review_revision"],
                approve=True,
                feedback="第二版保留原始记录并补齐固定来源，真人 Reviewer 同意通过。",
            ),
        )
    )
    assert second_final["assignment_status"] == "PASSED"

    second_projection = project_cycle(
        assignment_id=assignment_id,
        submission_version_id=second_version_id,
        previous_version_id=first_version_id,
    )
    assert second_projection.practice_evidence.revision == 2
    assert second_projection.practice_evidence.revises_evidence_id == (
        first_projection.practice_evidence.evidence_id
    )
    assert second_projection.human_gate.decision.value == "PASS"
    assert second_projection.status is ReviewCycleStatus.TASK_AUTHORIZATION_PENDING
    assert second_projection.blockers == ("TASK_AUTHORIZATION_NOT_APPROVED",)

    with SessionLocal() as session:
        outcome = session.scalar(
            select(Outcome).where(Outcome.assignment_id == assignment_id)
        )
        assert outcome is not None
        assert outcome.source_evaluation_id == second_projection.human_evaluation_evidence.evaluation_id
