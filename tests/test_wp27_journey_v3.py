import uuid

from fastapi.testclient import TestClient

from journey_api.fixtures import REVIEWER_ID
from journey_api.journey_service import FORMAL_V3_STAGE_KEYS
from journey_api.main import app


client = TestClient(app, base_url="http://localhost")
OPERATOR = {"X-Fixture-Role": "OPERATOR"}


def data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def command(path: str, payload: dict):
    return client.post(
        path,
        headers={**OPERATOR, "Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )


def task_payload(stable_key: str, revision: int) -> dict:
    return {
        "expected_revision": revision,
        "title": f"{stable_key} 正式内容测试版本",
        "purpose": "验证八站固定版本能够按既定顺序组合，且每站都必须先有真实输入再允许输出。",
        "learner_outcome": "Learner 能辨认当前位置、完成固定输入，并留下与当前主题对应的证据。",
        "instructions": ["完成当前固定材料。", "按题面留下可核对证据。"],
        "completion_criteria": ["输入已显式完成", "证据与当前主题对应"],
        "required_deliverables": ["一份结构化学习或评测记录"],
        "content_source_notes": ["WP-27 合成机器合同；不代表主管批准的正式内容。"],
        "change_summary": "WP-27 Journey V3 固定八站组合与顺序测试。",
        "reviewer_calibration_note": "仅验证机器合同；真人内容与 Reviewer 校准保持未执行。",
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": [],
        "learning_materials": [
            {
                "key": f"material-{stable_key.lower()}",
                "title": f"{stable_key} 固定输入",
                "kind": "TEXT",
                "source_label": "WP-27 测试夹具",
                "body": "这是一段用于验证八站旅程组合的合成材料。它不包含公司、项目或人才判断事实，也不能进入真实发布。",
                "estimated_duration_minutes": 5,
                "required": True,
            }
        ],
        "estimated_duration_minutes": 20,
        "rubric": {
            "version": 1,
            "dimensions": [
                {
                    "dimension_key": "evidence_traceability",
                    "title": "证据可定位",
                    "purpose": "确认结论来自固定题面与材料。",
                    "evidence_expected": "一处可以定位的判断证据。",
                    "levels": {
                        "MEETS": "证据与结论对应",
                        "NEEDS_WORK": "结论缺少证据",
                    },
                    "required": True,
                    "feedback_prompt": "指出缺口与下一步修改。",
                    "blocking_rule": "REQUIRE_FEEDBACK",
                }
            ],
        },
        "reviewer_role": "REVIEWER",
        "feedback_sla_business_days": 2,
        "sensitivity": "INTERNAL",
        "audience": "LEARNER",
        "reviewed_by": str(REVIEWER_ID),
    }


def test_v3_composition_requires_eight_approved_material_bearing_versions():
    existing = data(
        client.get("/api/v1/ops/formal-journeys", headers=OPERATOR)
    )["items"]
    current = existing[0] if existing else data(
        command(
            "/api/v1/ops/formal-journeys/publish",
            {
                "reviewed_by": str(REVIEWER_ID),
                "catalog_version": 2,
                "expected_current_version": 0,
                "expected_absent": True,
                "review_acknowledged": True,
            },
        )
    )
    assert len(current["stages"]) == 8
    existing_ids = [stage["task_version_id"] for stage in current["stages"]]
    missing_inputs = command(
        "/api/v1/ops/formal-journeys/assemble-v3",
        {
            "reviewed_by": str(REVIEWER_ID),
            "expected_current_version": current["version"],
            "task_version_ids": existing_ids,
            "content_review_note": "自动化不得把没有 required material 的 V2 内容伪装成 V3。",
            "review_acknowledged": True,
        },
    )
    assert missing_inputs.status_code == 422
    assert "required material" in missing_inputs.json()["error"]["message"]

    definitions = data(
        client.get("/api/v1/ops/task-definitions", headers=OPERATOR)
    )["items"]
    by_key = {item["stable_key"]: item for item in definitions}
    version_ids: list[str] = []
    for stable_key in FORMAL_V3_STAGE_KEYS:
        definition = by_key[stable_key]
        published = data(
            command(
                f"/api/v1/ops/task-definitions/{definition['id']}/publish",
                task_payload(stable_key, definition["revision"]),
            )
        )
        version_ids.append(published["id"])

    journey = data(
        command(
            "/api/v1/ops/formal-journeys/assemble-v3",
            {
                "reviewed_by": str(REVIEWER_ID),
                "expected_current_version": current["version"],
                "task_version_ids": version_ids,
                "content_review_note": "WP-27 合成机器合同已核对八站顺序、材料门禁和固定版本绑定。",
                "review_acknowledged": True,
            },
        )
    )
    assert journey["version"] == current["version"] + 1
    assert journey["title"].endswith("V3")
    assert [stage["stable_key"] for stage in journey["stages"]] == list(
        FORMAL_V3_STAGE_KEYS
    )
    assert [stage["stage_kind"] for stage in journey["stages"]] == [
        "DAY_0",
        "TREASURE",
        "TREASURE",
        "TREASURE",
        "TREASURE",
        "ASSESSMENT",
        "ASSESSMENT",
        "ASSESSMENT",
    ]
    assert [stage["completion_policy"] for stage in journey["stages"]] == [
        *("LEARNER_EVIDENCE" for _ in range(5)),
        *("REVIEW_REQUIRED" for _ in range(3)),
    ]

    wrong_order = command(
        "/api/v1/ops/formal-journeys/assemble-v3",
        {
            "reviewed_by": str(REVIEWER_ID),
            "expected_current_version": journey["version"],
            "task_version_ids": [version_ids[1], version_ids[0], *version_ids[2:]],
            "content_review_note": "交换 Day 0 与宝藏顺序必须由服务端拒绝，不能由前端约定代替。",
            "review_acknowledged": True,
        },
    )
    assert wrong_order.status_code == 422
    assert "DAY-0" in wrong_order.json()["error"]["message"]
