import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
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
from journey_api.fixtures import OPERATOR_ID, REVIEWER_ID
from journey_api.main import app
from journey_api.models import (
    Assignment,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    JourneyAdmissionDecision,
    JourneyOutcomeEvidence,
    Handoff,
    NextTrainingStageDecision,
    NextTrainingStageDecisionValue,
    NextTrainingStageReviewRequest,
    NextTrainingStageReviewAssignment,
    NextTrainingStageReviewResolution,
    NextTrainingStageReviewRequestStatus,
    Outcome,
    Review,
    Submission,
    SubmissionVersion,
    TaskVersion,
    User,
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


OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}
REVIEWER_HEADERS = {"X-Fixture-Role": "REVIEWER"}


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 54_000))


def ok(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def post(client, path: str, *, json: dict, role_headers: dict | None = None):
    headers = {"Idempotency-Key": str(uuid.uuid4()), **(role_headers or {})}
    csrf = client.cookies.get("journey_next_csrf")
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return ok(client.post(path, headers=headers, json=json))


def finalize_current_review(
    reviewer: TestClient,
    assignment_id: str,
    *,
    decision: str,
):
    queue = ok(reviewer.get("/api/v1/reviews", headers=REVIEWER_HEADERS))
    review = next(item for item in queue["items"] if item["assignment_id"] == assignment_id)
    started = post(
        reviewer,
        f"/api/v1/reviews/{review['id']}/start",
        json={"expected_revision": review["revision"]},
        role_headers=REVIEWER_HEADERS,
    )
    detail = ok(
        reviewer.get(
            f"/api/v1/reviews/{review['id']}", headers=REVIEWER_HEADERS
        )
    )
    dimensions = detail["rubric"]["dimensions"]
    assert 1 <= len(dimensions) <= 6
    request_revision = decision == "REQUEST_REVISION"
    rubric = [
        {
            "dimension_key": dimension["dimension_key"],
            "rating": "NEEDS_WORK" if request_revision and index == 0 else "MEETS",
            "score": (
                dimension["meets_threshold"] - 1
                if request_revision and index == 0
                else dimension["max_points"]
            ),
            "feedback": "证据具体，下一步可执行。" if not request_revision or index else "请补充可定位的证据。",
        }
        for index, dimension in enumerate(dimensions)
    ]
    return post(
        reviewer,
        f"/api/v1/reviews/{review['id']}/finalize",
        json={
            "expected_revision": started["review_revision"],
            "overall_decision": decision,
            "overall_feedback": (
                "请补充第一维度的具体依据，再次提交。"
                if request_revision
                else "判断结构清楚，证据与结论能够相互支持。"
            ),
            "rubric_evaluations": rubric,
        },
        role_headers=REVIEWER_HEADERS,
    )


def test_wp19_to_wp22_formal_journey_is_one_locked_vertical_slice():
    operator = client_for("formal-operator")
    reviewer = client_for("formal-reviewer")
    unacknowledged = operator.post(
        "/api/v1/ops/formal-journeys/publish",
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            **OPERATOR_HEADERS,
        },
        json={
            "reviewed_by": str(REVIEWER_ID),
            "catalog_version": 2,
            "expected_current_version": 0,
        },
    )
    assert unacknowledged.status_code == 422
    published = post(
        operator,
        "/api/v1/ops/formal-journeys/publish",
        json={
            "reviewed_by": str(REVIEWER_ID),
            "catalog_version": 2,
            "expected_current_version": 0,
            "review_acknowledged": True,
        },
        role_headers=OPERATOR_HEADERS,
    )
    assert [item["stage_kind"] for item in published["stages"]] == [
        "DAY_0",
        "TREASURE",
        "TREASURE",
        "TREASURE",
        "TREASURE",
        "ASSESSMENT",
        "ASSESSMENT",
        "ASSESSMENT",
    ]
    duplicate = operator.post(
        "/api/v1/ops/formal-journeys/publish",
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            **OPERATOR_HEADERS,
        },
        json={
            "reviewed_by": str(REVIEWER_ID),
            "catalog_version": 2,
            "expected_current_version": 1,
            "review_acknowledged": True,
        },
    )
    assert duplicate.status_code == 409

    invite = post(
        operator,
        "/api/v1/ops/invites",
        json={
            "purpose": "验证 WP-19 至 WP-22 正式探索营最小纵向切片",
            "expires_in_hours": 24,
            "role": "LEARNER",
            "reviewer_id": str(REVIEWER_ID),
            "journey_version_id": published["id"],
            "target_user_id": None,
        },
        role_headers=OPERATOR_HEADERS,
    )
    learner = client_for("formal-learner")
    exchanged = ok(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite["invite_token"], "return_to": "/app"},
        )
    )
    confirmed = ok(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": "Formal Journey Learner",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )

    action = ok(learner.get("/api/v1/me/current-action"))
    assert action["journey"]["total_stages"] == 8
    assert action["journey"]["completed_stages"] == 0
    assert action["responsible_party"] == "由你完成证据"
    assert action["feedback_expectation"] == "提交后进入下一站"
    assert "主管" not in action["reason"]
    day_zero = ok(
        learner.get(f"/api/v1/me/assignments/{action['resource_id']}")
    )
    day_zero_experience = day_zero["learning_experience"]
    assert day_zero["reviewer_display_name"]
    assert day_zero["assigned_at"]
    assert day_zero["reviewer_role"]
    assert day_zero["sensitivity"]
    assert day_zero["audience"]
    assert day_zero_experience["version"] == 2
    assert day_zero_experience["mode"] == "ORIENTATION"
    assert len(day_zero_experience["learning_blocks"]) >= 2
    assert len(day_zero_experience["knowledge_checks"]) >= 2
    assert day_zero_experience["response_sections"]
    locked_id = action["journey"]["nodes"][1]["assignment_id"]
    locked = learner.post(
        f"/api/v1/me/assignments/{locked_id}/start",
        headers={
            "X-CSRF-Token": learner.cookies["journey_next_csrf"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"expected_revision": 1},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "JOURNEY_STAGE_LOCKED"

    revised_once = False
    while action["action_type"] != "VIEW_RESULT_OR_HANDOFF":
        assignment_id = action["resource_id"]
        detail = ok(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
        if "start" in detail["allowed_commands"]:
            post(
                learner,
                f"/api/v1/me/assignments/{assignment_id}/start",
                json={"expected_revision": detail["revision"]},
            )
            detail = ok(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
        command = (
            "submit_revision"
            if "submit_revision" in detail["allowed_commands"]
            else "submit"
        )
        assert command in detail["allowed_commands"]
        submitted = post(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            json={
                "expected_revision": detail["revision"],
                "body": (
                    "我先记录可核对的事实，再根据规则形成判断；遇到规则未覆盖的边界，"
                    "保留不确定性并提出一个可直接回答的问题，同时暂停风险扩散。"
                ),
            },
        )
        stage = detail["journey_stage"]
        if stage["completion_policy"] == "LEARNER_EVIDENCE":
            assert submitted["assignment_status"] == "COMPLETED"
            with SessionLocal() as session:
                assert session.scalar(
                    select(func.count(Review.id)).where(
                        Review.assignment_id == uuid.UUID(assignment_id)
                    )
                ) == 0
        else:
            requested_revision = stage["stable_key"] == "ASM-001-RULE-BREAKDOWN" and not revised_once
            finalized = finalize_current_review(
                reviewer,
                assignment_id,
                decision="REQUEST_REVISION" if requested_revision else "APPROVE",
            )
            if requested_revision:
                revised_once = True
                assert finalized["assignment_status"] == "NEEDS_REVISION"
            else:
                assert finalized["assignment_status"] == "PASSED"
                if stage["stable_key"] != "ASM-003-DATA-CONSTRUCTION":
                    # Intermediate formal stages must not expose a final result.
                    assert learner.get("/api/v1/me/result").status_code == 404
        action = ok(learner.get("/api/v1/me/current-action"))

    result = ok(learner.get("/api/v1/me/result"))
    assert result["decision"] == "PASS"
    assert result["learning_completion"] == {
        "status": "COMPLETED",
        "completed_stages": 8,
        "total_stages": 8,
    }
    assert result["reviewer_conclusion"]["status"] == "FINALIZED"
    assert result["reviewer_conclusion"]["decision"] == "PASS"
    assert result["reviewer_conclusion"]["reviewer_display_name"]
    assert result["reviewer_conclusion"]["submission_version_id"]
    assert result["next_training_stage"] == {
        "decision_scope": "NEXT_TRAINING_STAGE",
        "display_name": "下一训练阶段决定",
        "status": "PENDING_HUMAN_DECISION",
        "decision_id": None,
        "decision": None,
        "decision_reason": None,
        "signed_by": None,
        "signed_at": None,
        "decision_evidence_ref": None,
        "review_request_status": "NOT_AVAILABLE_UNTIL_DECISION",
        "can_request_review": False,
    }
    assert "system_recommendation" not in result
    assert "operator_admission" not in result
    assert len(result["journey_evaluations"]) == 3
    assert [item["stage_key"] for item in result["journey_evaluations"]] == [
        "ASM-001-RULE-BREAKDOWN",
        "ASM-002-MODEL-JUDGEMENT",
        "ASM-003-DATA-CONSTRUCTION",
    ]
    # Completed route nodes remain readable for reflection even though every
    # mutation still requires an ACTIVE enrollment through the lock helper.
    completed_day_zero = ok(
        learner.get(f"/api/v1/me/assignments/{day_zero['id']}")
    )
    assert completed_day_zero["status"] == "COMPLETED"
    assert completed_day_zero["allowed_commands"] == []
    completed_mutation = learner.post(
        f"/api/v1/me/assignments/{day_zero['id']}/start",
        headers={
            "X-CSRF-Token": learner.cookies["journey_next_csrf"],
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"expected_revision": completed_day_zero["revision"]},
    )
    assert completed_mutation.status_code == 404
    assert completed_mutation.json()["error"]["code"] == "NOT_FOUND"
    with SessionLocal() as session:
        enrollment = session.scalar(
            select(Enrollment).where(
                Enrollment.learner_id == uuid.UUID(confirmed["user_id"])
            )
        )
        assert enrollment is not None
        assert enrollment.status == EnrollmentStatus.COMPLETED
        assert session.scalar(
            select(func.count(JourneyOutcomeEvidence.evaluation_id)).where(
                JourneyOutcomeEvidence.enrollment_id == enrollment.id
            )
        ) == 3
        final_evaluation = session.scalar(
            select(Evaluation)
            .join(
                JourneyOutcomeEvidence,
                JourneyOutcomeEvidence.evaluation_id == Evaluation.id,
            )
            .where(JourneyOutcomeEvidence.enrollment_id == enrollment.id)
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
        )
        assert final_evaluation is not None
        assert result["reviewer_conclusion"]["submission_version_id"] == str(
            final_evaluation.submission_version_id
        )
        assignment = session.get(Assignment, final_evaluation.assignment_id)
        submission = session.get(Submission, final_evaluation.submission_id)
        submission_version = session.get(
            SubmissionVersion, final_evaluation.submission_version_id
        )
        user = session.get(User, enrollment.learner_id)
        assert assignment is not None and submission is not None
        assert submission_version is not None and user is not None
        task = session.get(TaskVersion, assignment.task_version_id)
        review = session.get(Review, final_evaluation.review_id)
        assert task is not None and review is not None
        authorization_scope = TaskAuthorizationScopeContract(
            organization_id=task.organization_id,
            module_key=JourneyModuleKey.EXPLORATION_CAMP,
            build_contract_ref=(
                "docs/baselines/build-contracts/BC-001_探索营_V1.0_V0.1.md"
            ),
            target_journey_version_id=uuid.UUID(published["id"]),
            target_journey_stage_version_id=assignment.journey_stage_version_id,
            task_version_id=task.id,
            task_definition_id=task.task_definition_id,
            task_version_number=task.version,
            task_version_sha256=task_version_contract_sha256(task),
            authorized_task_ref="wp24-synthetic-formal-journey-test-only",
            purpose_ref="tests/wp24-formal-journey-purpose",
            data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
            deidentification_ref="tests/wp24-synthetic-deidentification",
            visibility=(
                EvidenceVisibility.PERSON,
                EvidenceVisibility.ASSIGNED_REVIEWERS,
            ),
            primary_reviewer_id=review.reviewer_id,
            backup_reviewer_id=uuid.uuid4(),
            retention_policy="g2-synthetic-evidence-v1",
            deletion_or_archive_rule="tests/wp24-synthetic-disposition",
            help_or_escalation_ref="tests/wp24-synthetic-escalation",
            created_at=task.published_at,
        )
        task_authorization = ControlledTaskAuthorizationContract(
            authorization_id=uuid.uuid4(),
            scope=authorization_scope,
            status=TaskAuthorizationStatus.PENDING_OWNER_APPROVAL,
        )
        appeal_policy = HumanGateAppealPolicyContract(
            policy_id=uuid.uuid4(),
            scope=HumanGateAppealPolicyScopeContract(
                organization_id=authorization_scope.organization_id,
                module_key=authorization_scope.module_key,
                build_contract_ref=authorization_scope.build_contract_ref,
                policy_ref="synthetic-wp24-appeal-policy-test-only",
                policy_version="v1",
                policy_sha256="1" * 64,
                applicable_gate_kind=HumanGateKind.CAPABILITY,
                task_authorization_id=task_authorization.authorization_id,
                task_authorization_scope_sha256=authorization_scope.subject_sha256(),
                appeal_window_days=14,
                resolution_sla_business_days=5,
                reviewer_assignment_rule_ref="tests/wp24-appeal-assignment-rule",
                correction_evidence_rule_ref="tests/wp24-appeal-evidence-rule",
                visibility=authorization_scope.visibility,
                data_classification=authorization_scope.data_classification,
                retention_policy=authorization_scope.retention_policy,
                created_at=authorization_scope.created_at,
            ),
            status=AppealPolicyStatus.PENDING_OWNER_APPROVAL,
        )
        shared_projection = project_review_cycle(
            user=user,
            enrollment=enrollment,
            assignment=assignment,
            task=task,
            submission=submission,
            version=submission_version,
            review=review,
            evaluation=final_evaluation,
            context=ModuleProjectionContext(
                module_key=JourneyModuleKey.EXPLORATION_CAMP,
                build_contract_ref=(
                    "docs/baselines/build-contracts/BC-001_探索营_V1.0_V0.1.md"
                ),
                task_authorization=task_authorization,
                appeal_policy=appeal_policy,
                gate_kind=HumanGateKind.CAPABILITY,
                retention_policy="g2-synthetic-evidence-v1",
                visibility=(
                    EvidenceVisibility.PERSON,
                    EvidenceVisibility.ASSIGNED_REVIEWERS,
                ),
                data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
            ),
            submission_ai_use=AiUseDisclosure(used=False),
            review_ai_use=AiUseDisclosure(used=False),
        )
        assert shared_projection.human_gate.decision.value == "PASS"
        assert shared_projection.status is ReviewCycleStatus.TASK_AUTHORIZATION_PENDING
        assert shared_projection.blockers == ("TASK_AUTHORIZATION_NOT_APPROVED",)
        enrollment_id = str(enrollment.id)

    for path in (
        f"/api/v1/ops/enrollments/{enrollment_id}/formal-admission/preview",
        f"/api/v1/ops/enrollments/{enrollment_id}/formal-admission",
    ):
        response = operator.post(path, headers=OPERATOR_HEADERS, json={})
        assert response.status_code == 404
    with SessionLocal() as session:
        assert session.scalar(select(func.count(JourneyAdmissionDecision.id))) == 0

    with SessionLocal.begin() as session:
        outcome = session.scalar(
            select(Outcome).where(Outcome.enrollment_id == uuid.UUID(enrollment_id))
        )
        assert outcome is not None
        handoff = session.scalar(
            select(Handoff).where(Handoff.outcome_id == outcome.id)
        )
        assert handoff is not None
        next_stage_decision = NextTrainingStageDecision(
            id=uuid.uuid4(),
            organization_id=outcome.organization_id,
            handoff_id=handoff.id,
            outcome_id=outcome.id,
            person_id=outcome.learner_id,
            decision_scope="NEXT_TRAINING_STAGE",
            decision=NextTrainingStageDecisionValue.DEFER,
            decision_reason="先巩固当前三项实操中的证据表达，再由真人安排复测。",
            decided_by_user_id=OPERATOR_ID,
            decision_evidence_ref="tests/next-training-stage/human-signature",
            decision_evidence_sha256="9" * 64,
            decided_at=datetime.now(UTC),
        )
        session.add(next_stage_decision)
        session.flush()
        decision_id = next_stage_decision.id
        decision_organization_id = outcome.organization_id
        decision_handoff_id = handoff.id

    recorded = ok(learner.get("/api/v1/me/result"))["next_training_stage"]
    assert recorded["status"] == "RECORDED"
    assert recorded["decision"] == "DEFER"
    assert recorded["decision_id"] == str(decision_id)
    assert recorded["review_request_status"] == "AVAILABLE"
    assert recorded["can_request_review"] is True

    review_key = f"review-request-{uuid.uuid4()}"
    review_payload = {
        "reason": "我希望独立复核人同时查看最后一次提交中的完整证据。",
        "evidence_refs": ["submission/final-revision"],
    }
    review_headers = {
        "Idempotency-Key": review_key,
        "X-CSRF-Token": learner.cookies["journey_next_csrf"],
    }
    requested = ok(
        learner.post(
            f"/api/v1/me/next-training-stage-decisions/{decision_id}/review-requests",
            headers=review_headers,
            json=review_payload,
        )
    )
    assert requested["status"] == "RECEIVED"
    assert requested["already_received"] is False
    assert requested["idempotency_replay"] is False
    replayed = ok(
        learner.post(
            f"/api/v1/me/next-training-stage-decisions/{decision_id}/review-requests",
            headers=review_headers,
            json=review_payload,
        )
    )
    assert replayed["id"] == requested["id"]
    assert replayed["idempotency_replay"] is True
    listed = ok(
        learner.get("/api/v1/me/next-training-stage-review-requests")
    )["items"]
    assert [item["id"] for item in listed] == [requested["id"]]

    not_independent = operator.post(
        f"/api/v1/ops/next-training-stage-review-requests/{requested['id']}/assignment",
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            **OPERATOR_HEADERS,
        },
        json={
            "reviewer_user_id": str(OPERATOR_ID),
            "assignment_reason": "原决定签署人不能独立复核自己的下一阶段决定。",
            "assignment_evidence_ref": "tests/next-stage/not-independent",
        },
    )
    assert not_independent.status_code == 409
    assigned = post(
        operator,
        f"/api/v1/ops/next-training-stage-review-requests/{requested['id']}/assignment",
        json={
            "reviewer_user_id": str(REVIEWER_ID),
            "assignment_reason": "由未参与原决定的 Reviewer 独立复核完整证据。",
            "assignment_evidence_ref": "tests/next-stage/independent-assignment",
        },
        role_headers=OPERATOR_HEADERS,
    )
    assert assigned["reviewer_user_id"] == str(REVIEWER_ID)
    assert assigned["source_decision_id"] == str(decision_id)
    reviewer_queue = ok(
        reviewer.get(
            "/api/v1/reviews/next-training-stage-review-requests",
            headers=REVIEWER_HEADERS,
        )
    )["items"]
    assert reviewer_queue[-1]["status"] == "IN_REVIEW"
    resolve_key = str(uuid.uuid4())
    resolution_payload = {
        "status": "OVERTURNED",
        "resolution_reason": "独立复核确认原暂缓决定未充分反映最终实操证据。",
        "evidence_refs": ["submission/final-revision", "review/independent"],
        "replacement_decision": {
            "decision": "READY",
            "decision_reason": "独立复核确认三项实操证据充分，建议进入下一训练阶段。",
            "decision_evidence_ref": "tests/next-stage/replacement-signature",
            "decision_evidence_sha256": "a" * 64,
        },
    }
    resolved = ok(
        reviewer.post(
            f"/api/v1/reviews/next-training-stage-review-requests/{requested['id']}/resolution",
            headers={"Idempotency-Key": resolve_key, **REVIEWER_HEADERS},
            json=resolution_payload,
        )
    )
    assert resolved["status"] == "OVERTURNED"
    assert resolved["replacement_decision_id"] is not None
    replayed_resolution = ok(
        reviewer.post(
            f"/api/v1/reviews/next-training-stage-review-requests/{requested['id']}/resolution",
            headers={"Idempotency-Key": resolve_key, **REVIEWER_HEADERS},
            json=resolution_payload,
        )
    )
    assert replayed_resolution["id"] == resolved["id"]
    assert replayed_resolution["idempotency_replay"] is True
    lineage = ok(
        learner.get(
            f"/api/v1/me/next-training-stage-review-requests/{requested['id']}"
        )
    )
    assert lineage["status"] == "OVERTURNED"
    assert lineage["replacement_decision_id"] == resolved["replacement_decision_id"]
    replaced_result = ok(learner.get("/api/v1/me/result"))["next_training_stage"]
    assert replaced_result["decision"] == "READY"
    assert replaced_result["decision_id"] == resolved["replacement_decision_id"]
    after_resolution = ok(learner.get("/api/v1/me/result"))["next_training_stage"]
    assert after_resolution["decision"] == "READY"
    assert after_resolution["review_request_status"] == "NOT_APPLICABLE"
    assert after_resolution["can_request_review"] is False
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(NextTrainingStageDecision.id)).where(
                NextTrainingStageDecision.handoff_id == decision_handoff_id
            )
        ) == 2
        assert session.scalar(
            select(func.count(NextTrainingStageReviewRequest.id)).where(
                NextTrainingStageReviewRequest.next_training_stage_decision_id
                == decision_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(NextTrainingStageReviewAssignment.id)).where(
                NextTrainingStageReviewAssignment.review_request_id
                == uuid.UUID(requested["id"])
            )
        ) == 1
        assert session.scalar(
            select(func.count(NextTrainingStageReviewResolution.id)).where(
                NextTrainingStageReviewResolution.review_request_id
                == uuid.UUID(requested["id"])
            )
        ) == 1
        replacement = session.get(
            NextTrainingStageDecision, uuid.UUID(resolved["replacement_decision_id"])
        )
        assert replacement is not None
        assert replacement.supersedes_decision_id == decision_id
        assert replacement.source_review_request_id == uuid.UUID(requested["id"])
        assert replacement.revision == 2
        assert session.scalar(
            select(func.count(Enrollment.id)).where(
                Enrollment.learner_id == uuid.UUID(confirmed["user_id"])
            )
        ) == 1

    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            session.add(
                NextTrainingStageReviewRequest(
                    id=uuid.uuid4(),
                    organization_id=decision_organization_id,
                    handoff_id=decision_handoff_id,
                    next_training_stage_decision_id=decision_id,
                    decision_scope="NEXT_TRAINING_STAGE",
                    source_decision=NextTrainingStageDecisionValue.DEFER,
                    requester_user_id=REVIEWER_ID,
                    reason="The original reviewer cannot become the target Person.",
                    evidence_refs=[],
                    status=NextTrainingStageReviewRequestStatus.RECEIVED,
                    requested_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()

    for statement in (
        update(NextTrainingStageDecision)
        .where(NextTrainingStageDecision.id == decision_id)
        .values(decision=NextTrainingStageDecisionValue.READY),
        delete(NextTrainingStageDecision).where(
            NextTrainingStageDecision.id == decision_id
        ),
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            with SessionLocal.begin() as session:
                session.execute(statement)

    for statement in (
        update(NextTrainingStageReviewAssignment)
        .where(NextTrainingStageReviewAssignment.id == uuid.UUID(assigned["id"]))
        .values(assignment_reason="Mutation must be rejected by the database."),
        delete(NextTrainingStageReviewAssignment).where(
            NextTrainingStageReviewAssignment.id == uuid.UUID(assigned["id"])
        ),
        update(NextTrainingStageReviewResolution)
        .where(NextTrainingStageReviewResolution.id == uuid.UUID(resolved["id"]))
        .values(resolution_reason="Mutation must be rejected by the database."),
        delete(NextTrainingStageReviewResolution).where(
            NextTrainingStageReviewResolution.id == uuid.UUID(resolved["id"])
        ),
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            with SessionLocal.begin() as session:
                session.execute(statement)
