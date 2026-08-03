import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.fixtures import (
    OPERATOR_ID,
    ORGANIZATION_ID,
    REVIEWER_ID,
    TASK_VERSION_ID,
)
from journey_api.main import app
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Enrollment,
    EnrollmentStatus,
    JourneyDefinition,
    JourneyStageVersion,
    JourneyVersion,
    Outcome,
    Review,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
)


OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}
REVIEWER_HEADERS = {"X-Fixture-Role": "REVIEWER"}
RUBRIC_KEYS = (
    "problem_clarity",
    "evidence_quality",
    "action_feasibility",
    "validation_design",
)
FORMAL_STAGES = (
    ("DAY-0", "ORIENTATION", "LEARNER_EVIDENCE"),
    ("TRE-001-COMPANY-VALUES", "TREASURE", "LEARNER_EVIDENCE"),
    ("TRE-002-AI-DATA-BASICS", "TREASURE", "LEARNER_EVIDENCE"),
    ("TRE-003-PROJECT-AWARENESS", "TREASURE", "LEARNER_EVIDENCE"),
    ("TRE-004-DELIVERY-FIT", "TREASURE", "LEARNER_EVIDENCE"),
    ("ASM-001-RULE-BREAKDOWN", "ASSESSMENT", "REVIEW_REQUIRED"),
    ("ASM-002-MODEL-JUDGEMENT", "ASSESSMENT", "REVIEW_REQUIRED"),
    ("ASM-003-BOUNDARY-ESCALATION", "ASSESSMENT", "REVIEW_REQUIRED"),
)


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 50_000))


def assert_ok(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def clone_task(stable_key: str) -> uuid.UUID:
    with SessionLocal.begin() as session:
        source = session.get(TaskVersion, TASK_VERSION_ID)
        assert source is not None
        definition = TaskDefinition(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            stable_key=stable_key,
            status=TaskDefinitionStatus.PUBLISHED,
            revision=1,
            created_by=OPERATOR_ID,
        )
        session.add(definition)
        session.flush()
        task = TaskVersion(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            task_definition_id=definition.id,
            version=1,
            title=f"{stable_key} 验证任务",
            purpose=source.purpose,
            learner_outcome=source.learner_outcome,
            instructions=source.instructions,
            completion_criteria=source.completion_criteria,
            required_deliverables=source.required_deliverables,
            content_source_notes=["WP-19 synthetic composition contract"],
            change_summary="为 WP-19 多阶段顺序测试建立独立固定任务版本。",
            reviewer_calibration_note="仅验证编排，不代表正式内容或真人 Reviewer 校准。",
            allowed_attachment_types=[],
            max_attachment_size_bytes=0,
            reference_materials=[],
            estimated_duration_minutes=source.estimated_duration_minutes,
            rubric=source.rubric,
            rubric_version=source.rubric_version,
            reviewer_role=source.reviewer_role,
            feedback_sla_business_days=source.feedback_sla_business_days,
            sensitivity=source.sensitivity,
            audience=source.audience,
            published_by=OPERATOR_ID,
            reviewed_by=REVIEWER_ID,
        )
        session.add(task)
        return task.id


def create_and_publish_alpha(task_ids: list[uuid.UUID]) -> dict[str, object]:
    operator = client_for(f"wp19-operator-{uuid.uuid4()}")
    stable_key = f"JRN-WP19-{uuid.uuid4().hex[:8].upper()}"
    definition = assert_ok(
        operator.post(
            "/api/v1/ops/journey-definitions",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": f"create-{uuid.uuid4()}"},
            json={"stable_key": stable_key, "kind": "ALPHA_VALIDATION"},
        )
    )
    published = assert_ok(
        operator.post(
            f"/api/v1/ops/journey-definitions/{definition['id']}/publish",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": f"publish-{uuid.uuid4()}"},
            json={
                "expected_revision": definition["revision"],
                "title": "WP-19 两阶段验证旅程",
                "change_summary": "验证固定旅程版本、服务端顺序、解锁和最小进度投影。",
                "reviewed_by": str(REVIEWER_ID),
                "stages": [
                    {
                        "stable_key": f"ASM-WP19-{position}",
                        "stage_kind": "ASSESSMENT",
                        "completion_policy": "REVIEW_REQUIRED",
                        "task_version_id": str(task_id),
                    }
                    for position, task_id in enumerate(task_ids, start=1)
                ],
            },
        )
    )
    return published


def approve_payload(expected_revision: int) -> dict[str, object]:
    return {
        "expected_revision": expected_revision,
        "overall_decision": "APPROVE",
        "overall_feedback": "四个维度均有可核对证据，允许进入固定旅程的下一阶段。",
        "rubric_evaluations": [
            {
                "dimension_key": key,
                "rating": "MEETS",
                "feedback": "该维度证据符合当前固定 Rubric 锚点。",
            }
            for key in RUBRIC_KEYS
        ],
    }


def test_journey_publish_is_operator_scoped_validated_and_immutable():
    second_task_id = clone_task(f"TSK-WP19-{uuid.uuid4().hex[:8].upper()}")
    denied = client_for("wp19-learner-denied").post(
        "/api/v1/ops/journey-definitions",
        headers={"X-Fixture-Role": "LEARNER", "Idempotency-Key": f"denied-{uuid.uuid4()}"},
        json={"stable_key": "JRN-WP19-DENIED", "kind": "ALPHA_VALIDATION"},
    )
    assert denied.status_code == 403

    definition = create_and_publish_alpha([TASK_VERSION_ID, second_task_id])
    version = definition["versions"][-1]
    assert [stage["position"] for stage in version["stages"]] == [1, 2]
    assert all(stage["completion_policy"] == "REVIEW_REQUIRED" for stage in version["stages"])

    with pytest.raises(DBAPIError, match="immutable"):
        with SessionLocal.begin() as session:
            session.execute(
                update(JourneyVersion)
                .where(JourneyVersion.id == uuid.UUID(str(version["id"])))
                .values(title="非法原地改版")
            )

    formal = assert_ok(
        client_for("wp19-formal-create").post(
            "/api/v1/ops/journey-definitions",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": f"formal-{uuid.uuid4()}"},
            json={
                "stable_key": f"JRN-FORMAL-{uuid.uuid4().hex[:8].upper()}",
                "kind": "FORMAL_EXPLORATION",
            },
        )
    )
    malformed = client_for("wp19-formal-publish").post(
        f"/api/v1/ops/journey-definitions/{formal['id']}/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": f"formal-publish-{uuid.uuid4()}"},
        json={
            "expected_revision": 1,
            "title": "不完整正式旅程",
            "change_summary": "故意缺少四宝藏与三评测，用于验证正式结构失败关闭。",
            "reviewed_by": str(REVIEWER_ID),
            "stages": [
                {
                    "stable_key": "ASM-WP19-INVALID",
                    "stage_kind": "ASSESSMENT",
                    "completion_policy": "REVIEW_REQUIRED",
                    "task_version_id": str(second_task_id),
                }
            ],
        },
    )
    assert malformed.status_code == 422


def test_exact_formal_structure_can_be_published_but_cannot_be_invited_before_wp20_21():
    operator = client_for("wp19-formal-operator")
    definition = assert_ok(
        operator.post(
            "/api/v1/ops/journey-definitions",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": f"formal-{uuid.uuid4()}"},
            json={
                "stable_key": f"JRN-FORMAL-{uuid.uuid4().hex[:8].upper()}",
                "kind": "FORMAL_EXPLORATION",
            },
        )
    )
    task_ids = [
        clone_task(f"TSK-WP19-FORMAL-{position}-{uuid.uuid4().hex[:6].upper()}")
        for position in range(1, len(FORMAL_STAGES) + 1)
    ]
    published = assert_ok(
        operator.post(
            f"/api/v1/ops/journey-definitions/{definition['id']}/publish",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": f"publish-{uuid.uuid4()}"},
            json={
                "expected_revision": definition["revision"],
                "title": "正式探索营结构验证",
                "change_summary": "只发布固定结构，不激活尚未关闭内容与结果合同的正式旅程。",
                "reviewed_by": str(REVIEWER_ID),
                "stages": [
                    {
                        "stable_key": stable_key,
                        "stage_kind": stage_kind,
                        "completion_policy": completion_policy,
                        "task_version_id": str(task_id),
                    }
                    for (stable_key, stage_kind, completion_policy), task_id in zip(
                        FORMAL_STAGES, task_ids, strict=True
                    )
                ],
            },
        )
    )
    version = published["versions"][-1]
    assert [stage["stable_key"] for stage in version["stages"]] == [
        stage[0] for stage in FORMAL_STAGES
    ]

    invite = operator.post(
        "/api/v1/ops/invites",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": f"invite-{uuid.uuid4()}"},
        json={
            "purpose": "正式旅程仍须失败关闭",
            "expires_in_hours": 24,
            "role": "LEARNER",
            "reviewer_id": str(REVIEWER_ID),
            "journey_version_id": version["id"],
            "target_user_id": None,
        },
    )
    assert invite.status_code == 409
    assert invite.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_invite_fixes_full_journey_current_action_waits_and_pass_unlocks_next_stage():
    second_task_id = clone_task(f"TSK-WP19-{uuid.uuid4().hex[:8].upper()}")
    definition = create_and_publish_alpha([TASK_VERSION_ID, second_task_id])
    journey_version = definition["versions"][-1]
    operator = client_for("wp19-invite-operator")
    invite = assert_ok(
        operator.post(
            "/api/v1/ops/invites",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": f"invite-{uuid.uuid4()}"},
            json={
                "purpose": "验证 WP-19 固定两阶段旅程",
                "expires_in_hours": 24,
                "role": "LEARNER",
                "reviewer_id": str(REVIEWER_ID),
                "journey_version_id": journey_version["id"],
                "target_user_id": None,
            },
        )
    )
    learner = client_for("wp19-two-stage-learner")
    exchanged = assert_ok(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite["invite_token"], "return_to": "/app"},
        )
    )
    confirmed = assert_ok(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": "WP-19 两阶段新人",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    learner_id = uuid.UUID(str(confirmed["user_id"]))
    with SessionLocal() as session:
        enrollment = session.scalar(
            select(Enrollment).where(Enrollment.learner_id == learner_id)
        )
        assert enrollment is not None
        assignments = session.scalars(
            select(Assignment)
            .where(Assignment.enrollment_id == enrollment.id)
            .order_by(Assignment.position)
        ).all()
        assert [item.status for item in assignments] == [
            AssignmentStatus.AVAILABLE,
            AssignmentStatus.LOCKED,
        ]
        assert all(item.journey_version_id == enrollment.journey_version_id for item in assignments)
        first_id, second_id = assignments[0].id, assignments[1].id
        enrollment_id = enrollment.id

    locked_start = learner.post(
        f"/api/v1/me/assignments/{second_id}/start",
        headers={
            "Idempotency-Key": f"locked-{uuid.uuid4()}",
            "X-CSRF-Token": confirmed["csrf_token"],
        },
        json={"expected_revision": 1},
    )
    assert locked_start.status_code == 409

    current = assert_ok(learner.get("/api/v1/me/current-action"))
    assert current["resource_id"] == str(first_id)
    assert current["journey"] == {
        "stable_key": definition["stable_key"],
        "version": journey_version["version"],
        "title": journey_version["title"],
        "current_stage_key": "ASM-WP19-1",
        "current_stage_kind": "ASSESSMENT",
        "current_position": 1,
        "completed_stages": 0,
        "total_stages": 2,
    }
    started = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{first_id}/start",
            headers={
                "Idempotency-Key": f"start-{uuid.uuid4()}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={"expected_revision": current["revision"]},
        )
    )
    submitted = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{first_id}/submissions",
            headers={
                "Idempotency-Key": f"submit-{uuid.uuid4()}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={
                "expected_revision": started["revision"],
                "body": (
                    "WP-19 多阶段顺序验证：事实一与事实二均可核对；第一步由责任人执行，"
                    "两周内观察完成率，低于目标即停止扩量并调整。"
                ),
                "attachment_ids": [],
            },
        )
    )
    waiting = assert_ok(learner.get("/api/v1/me/current-action"))
    assert waiting["resource_id"] == str(first_id)
    assert waiting["action_type"] == "WAIT_FOR_REVIEW"

    with SessionLocal() as session:
        review = session.scalar(
            select(Review).where(
                Review.submission_version_id
                == uuid.UUID(str(submitted["submission_version_id"]))
            )
        )
        assert review is not None
        review_id = review.id
    reviewer = client_for("wp19-reviewer")
    review_started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{review_id}/start",
            headers={**REVIEWER_HEADERS, "Idempotency-Key": f"review-start-{uuid.uuid4()}"},
            json={"expected_revision": 1},
        )
    )
    assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{review_id}/finalize",
            headers={**REVIEWER_HEADERS, "Idempotency-Key": f"review-final-{uuid.uuid4()}"},
            json=approve_payload(review_started["review_revision"]),
        )
    )

    with SessionLocal() as session:
        enrollment = session.get(Enrollment, enrollment_id)
        second = session.get(Assignment, second_id)
        assert enrollment is not None and enrollment.status == EnrollmentStatus.ACTIVE
        assert second is not None and second.status == AssignmentStatus.AVAILABLE
        assert session.scalar(
            select(func.count(Outcome.id)).where(Outcome.enrollment_id == enrollment_id)
        ) == 0
    next_action = assert_ok(learner.get("/api/v1/me/current-action"))
    assert next_action["resource_id"] == str(second_id)
    assert next_action["journey"]["completed_stages"] == 1
    assert next_action["journey"]["current_position"] == 2
