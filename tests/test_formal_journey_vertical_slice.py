import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID
from journey_api.main import app
from journey_api.models import (
    Enrollment,
    EnrollmentStatus,
    JourneyAdmissionDecision,
    JourneyOutcomeEvidence,
    Review,
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
                assert finalized["assignment_status"] == "COMPLETED"
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
    assert result["system_recommendation"] == {
        "status": "PENDING_OPERATOR_INPUT",
        "advisory_only": True,
        "recommendation_tier": None,
        "recommended_decision": None,
    }
    assert result["operator_admission"] == {
        "status": "PENDING",
        "decision": None,
        "decision_reason": None,
        "total_score": None,
        "decided_at": None,
    }
    assert len(result["journey_evaluations"]) == 3
    assert [item["stage_key"] for item in result["journey_evaluations"]] == [
        "ASM-001-RULE-BREAKDOWN",
        "ASM-002-MODEL-JUDGEMENT",
        "ASM-003-DATA-CONSTRUCTION",
    ]
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
        enrollment_id = str(enrollment.id)

    preview = ok(
        operator.post(
            f"/api/v1/ops/enrollments/{enrollment_id}/formal-admission/preview",
            headers=OPERATOR_HEADERS,
            json={
                "scores": {
                    "attendance_discipline": 10,
                    "muchener_understanding": 10,
                    "ai_data_fundamentals": 10,
                    "project_organization_fit": 10,
                }
            },
        )
    )
    assert preview["total_score"] == 100
    assert preview["recommendation_tier"] == "A"
    assert preview["recommended_decision"] == "ADMIT"
    assert preview["advisory_only"] is True
    with SessionLocal() as session:
        assert session.scalar(select(func.count(JourneyAdmissionDecision.id))) == 0

    mismatched = operator.post(
        f"/api/v1/ops/enrollments/{enrollment_id}/formal-admission",
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            **OPERATOR_HEADERS,
        },
        json={
            "expected_absent": True,
            "human_judgement_acknowledged": True,
            "scores": {
                "attendance_discipline": 10,
                "muchener_understanding": 10,
                "ai_data_fundamentals": 10,
                "project_organization_fit": 10,
            },
            "score_evidence": "全天八站均完成；学习记录与三项评测证据相互一致，且遵守隐私与升级边界。",
            "decision": "DEFER",
            "decision_reason": "人工希望覆盖系统 A 档建议，但还没有给出独立且可审计的覆盖理由。",
            "override_reason": None,
        },
    )
    assert mismatched.status_code == 422

    admission = post(
        operator,
        f"/api/v1/ops/enrollments/{enrollment_id}/formal-admission",
        json={
            "expected_absent": True,
            "human_judgement_acknowledged": True,
            "scores": {
                "attendance_discipline": 10,
                "muchener_understanding": 10,
                "ai_data_fundamentals": 10,
                "project_organization_fit": 10,
            },
            "score_evidence": "全天八站均完成；学习记录与三项评测证据相互一致，且遵守隐私与升级边界。",
            "decision": "ADMIT",
            "decision_reason": "综合固定量化评分和人工观察，允许进入下一阶段；该结论由 Operator 独立作出。",
            "override_reason": None,
        },
        role_headers=OPERATOR_HEADERS,
    )
    assert admission["total_score"] == 100
    assert admission["recommendation_tier"] == "A"
    assert admission["decision"] == "ADMIT"
    decided_result = ok(learner.get("/api/v1/me/result"))
    assert decided_result["system_recommendation"] == {
        "status": "RECORDED",
        "advisory_only": True,
        "recommendation_tier": "A",
        "recommended_decision": "ADMIT",
    }
    assert decided_result["operator_admission"]["status"] == "DECIDED"
    assert decided_result["operator_admission"]["decision"] == "ADMIT"
    assert decided_result["operator_admission"]["total_score"] == 100
    assert "Operator 独立作出" in decided_result["operator_admission"]["decision_reason"]
