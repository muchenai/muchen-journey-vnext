import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID
from journey_api.main import app
from journey_api.models import LearningMaterialCompletion, Review


OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}
REVIEWER_HEADERS = {"X-Fixture-Role": "REVIEWER"}


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 55_000))


def data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def command(
    client: TestClient,
    path: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    key: str | None = None,
):
    command_headers = {
        "Idempotency-Key": key or str(uuid.uuid4()),
        **(headers or {}),
    }
    csrf = client.cookies.get("journey_next_csrf")
    if csrf:
        command_headers["X-CSRF-Token"] = csrf
    return client.post(path, headers=command_headers, json=payload)


def publish_one_treasure(operator: TestClient) -> dict:
    stable_key = f"WP26-TREASURE-{uuid.uuid4().hex[:8].upper()}"
    definition = data(
        command(
            operator,
            "/api/v1/ops/task-definitions",
            {"stable_key": stable_key},
            headers=OPERATOR_HEADERS,
        )
    )
    return data(
        command(
            operator,
            f"/api/v1/ops/task-definitions/{definition['id']}/publish",
            {
                "expected_revision": definition["revision"],
                "title": "宝藏一：公司认知",
                "purpose": "先完成两份固定材料，再用可核对的证据说明自己的理解。",
                "learner_outcome": "能够区分公司命题、个人判断和下一步可观察行动。",
                "instructions": ["完成两份必读材料。", "按固定结构提交一份小任务。"],
                "completion_criteria": ["包含材料证据", "行动可以被观察"],
                "required_deliverables": ["一份 100–300 字学习记录"],
                "content_source_notes": ["WP-26 合成测试材料，不代表已批准公司事实。"],
                "change_summary": "WP-26 单宝藏材料完成与修订闭环测试版本。",
                "reviewer_calibration_note": "只按证据是否可定位和行动是否可观察评审。",
                "learning_materials": [
                    {
                        "key": "company-thesis",
                        "title": "公司命题（合成测试）",
                        "kind": "TEXT",
                        "source_label": "WP-26 测试夹具",
                        "body": "这是一段用于验证材料完成合同的合成文本，不包含任何真实公司经营事实。Learner 必须主动确认完成，页面停留不会自动记为完成。",
                        "estimated_duration_minutes": 5,
                        "required": True,
                    },
                    {
                        "key": "evidence-guide",
                        "title": "证据记录指南（合成测试）",
                        "kind": "HTTPS_LINK",
                        "source_label": "公开测试域名",
                        "url": "https://example.com/wp26-evidence-guide",
                        "estimated_duration_minutes": 5,
                        "required": True,
                    },
                ],
                "estimated_duration_minutes": 20,
                "rubric": {
                    "version": 1,
                    "dimensions": [
                        {
                            "dimension_key": "evidence_traceability",
                            "title": "证据可定位",
                            "purpose": "确认判断引用了固定材料中的具体证据。",
                            "evidence_expected": "至少一处材料证据与对应判断。",
                            "levels": {
                                "MEETS": "证据和判断可以对应",
                                "NEEDS_WORK": "只有结论，没有可定位证据",
                            },
                            "required": True,
                            "feedback_prompt": "指出缺少的证据和下一步修改。",
                            "blocking_rule": "REQUIRE_FEEDBACK",
                        }
                    ],
                },
                "feedback_sla_business_days": 2,
                "reviewed_by": str(REVIEWER_ID),
            },
            headers=OPERATOR_HEADERS,
        )
    )


def finalize_review(reviewer: TestClient, assignment_id: str, decision: str) -> dict:
    queue = data(reviewer.get("/api/v1/reviews", headers=REVIEWER_HEADERS))
    item = next(row for row in queue["items"] if row["assignment_id"] == assignment_id)
    started = data(
        command(
            reviewer,
            f"/api/v1/reviews/{item['id']}/start",
            {"expected_revision": item["revision"]},
            headers=REVIEWER_HEADERS,
        )
    )
    return data(
        command(
            reviewer,
            f"/api/v1/reviews/{item['id']}/finalize",
            {
                "expected_revision": started["review_revision"],
                "overall_decision": decision,
                "overall_feedback": (
                    "请补充一处能够定位到固定材料的证据，再提交修订版本。"
                    if decision == "REQUEST_REVISION"
                    else "证据与判断能够对应，本次小任务通过。"
                ),
                "rubric_evaluations": [
                    {
                        "dimension_key": "evidence_traceability",
                        "rating": (
                            "NEEDS_WORK" if decision == "REQUEST_REVISION" else "MEETS"
                        ),
                        "score": None,
                        "feedback": (
                            "请补充固定材料中的具体证据。"
                            if decision == "REQUEST_REVISION"
                            else "证据具体且可定位。"
                        ),
                    }
                ],
            },
            headers=REVIEWER_HEADERS,
        )
    )


def test_wp26_required_materials_are_immutable_server_side_facts():
    operator = client_for("wp26-operator")
    reviewer = client_for("wp26-reviewer")
    task_version = publish_one_treasure(operator)
    invite = data(
        command(
            operator,
            "/api/v1/ops/invites",
            {
                "purpose": "WP-26 单宝藏真实纵向切片机器合同",
                "expires_in_hours": 24,
                "role": "LEARNER",
                "reviewer_id": str(REVIEWER_ID),
                "task_version_id": task_version["id"],
                "journey_version_id": None,
                "target_user_id": None,
            },
            headers=OPERATOR_HEADERS,
        )
    )
    learner = client_for("wp26-learner")
    exchanged = data(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite["invite_token"], "return_to": "/app"},
        )
    )
    data(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": "WP26 Synthetic Learner",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    action = data(learner.get("/api/v1/me/current-action"))
    assignment_id = action["resource_id"]
    detail = data(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
    assert [item["key"] for item in detail["learning_materials"]] == [
        "company-thesis",
        "evidence-guide",
    ]
    assert all(item["completed_at"] is None for item in detail["learning_materials"])

    early_start = command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/start",
        {"expected_revision": detail["revision"]},
    )
    assert early_start.status_code == 409
    assert early_start.json()["error"]["code"] == "LEARNING_MATERIALS_INCOMPLETE"
    assert early_start.json()["error"]["details"]["missing_material_keys"] == [
        "company-thesis",
        "evidence-guide",
    ]

    forged_key = command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/materials/not-in-version/complete",
        {"task_version": detail["task_version"]},
    )
    assert forged_key.status_code == 404
    wrong_version = command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/materials/company-thesis/complete",
        {"task_version": detail["task_version"] + 1},
    )
    assert wrong_version.status_code == 409
    assert wrong_version.json()["error"]["code"] == "VERSION_CONFLICT"

    completion_key = str(uuid.uuid4())
    first_completion = command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/materials/company-thesis/complete",
        {"task_version": detail["task_version"]},
        key=completion_key,
    )
    first = data(first_completion)
    replay = data(
        command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/materials/company-thesis/complete",
            {"task_version": detail["task_version"]},
            key=completion_key,
        )
    )
    assert replay["completed_at"] == first["completed_at"]
    assert replay["idempotency_replay"] is True

    still_locked = command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/start",
        {"expected_revision": detail["revision"]},
    )
    assert still_locked.status_code == 409
    assert still_locked.json()["error"]["details"]["missing_material_keys"] == [
        "evidence-guide"
    ]
    data(
        command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/materials/evidence-guide/complete",
            {"task_version": detail["task_version"]},
        )
    )
    started = data(
        command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/start",
            {"expected_revision": detail["revision"]},
        )
    )
    submitted = data(
        command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            {
                "expected_revision": started["revision"],
                "body": "材料指出完成必须由学习者主动确认。我据此把判断和证据分开记录，并把下一步写成可以被观察的行动。",
            },
        )
    )
    assert submitted["assignment_status"] == "SUBMITTED"
    revised = finalize_review(reviewer, assignment_id, "REQUEST_REVISION")
    assert revised["assignment_status"] == "NEEDS_REVISION"
    revision_detail = data(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
    assert "固定材料" in revision_detail["latest_revision_feedback"]
    resubmitted = data(
        command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            {
                "expected_revision": revision_detail["revision"],
                "body": "固定材料明确写明：页面停留不会自动记为完成。因此我主动确认两份材料，并把可定位证据与个人判断分开；下一步是一周内复核行动记录。",
            },
        )
    )
    assert resubmitted["assignment_status"] == "SUBMITTED"
    approved = finalize_review(reviewer, assignment_id, "APPROVE")
    assert approved["assignment_status"] == "PASSED"

    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(LearningMaterialCompletion.id)).where(
                LearningMaterialCompletion.assignment_id == uuid.UUID(assignment_id)
            )
        ) == 2
        assert session.scalar(
            select(func.count(Review.id)).where(
                Review.assignment_id == uuid.UUID(assignment_id)
            )
        ) == 2
