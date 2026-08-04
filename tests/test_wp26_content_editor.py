import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID
from journey_api.main import app
from journey_api.models import (
    ContentDraft,
    ContentDraftStatus,
    Role,
    RoleAssignment,
    TaskVersion,
    User,
)


OPERATOR = {"X-Fixture-Role": "OPERATOR"}
EDITOR = {"X-Fixture-Role": "CONTENT_EDITOR"}
client = TestClient(app, base_url="http://localhost")


def payload(title: str = "宝藏一：公司认知") -> dict[str, object]:
    return {
        "title": title,
        "purpose": "让新人先学习一份固定材料，再留下与主题直接相关的判断证据。",
        "learner_outcome": "能够区分材料中的事实、自己的判断与下一步可观察行动。",
        "instructions": ["完成必读材料。", "按固定结构完成小任务。"],
        "completion_criteria": ["引用材料证据", "写出可观察行动"],
        "required_deliverables": ["一份 100–300 字学习记录"],
        "content_source_notes": ["WP-26 合成测试材料，不代表批准的公司事实。"],
        "change_summary": "验证 Content Editor 草稿、预览、提交和精确发布边界。",
        "reviewer_calibration_note": "只验证证据是否可定位，真人校准仍保持未执行。",
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": [],
        "learning_materials": [
            {
                "key": "company-intro",
                "title": "公司认知测试材料",
                "kind": "TEXT",
                "source_label": "WP-26 测试夹具",
                "body": "这是一段只用于验证内容工作流的合成材料，不包含真实公司经营信息，也不能替代主管批准的正式材料。",
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
                    "purpose": "确认判断引用固定材料中的具体证据。",
                    "evidence_expected": "一处材料证据与对应判断。",
                    "levels": {
                        "MEETS": "证据与判断能够对应",
                        "NEEDS_WORK": "只有结论而没有证据",
                    },
                    "required": True,
                    "feedback_prompt": "指出缺少的证据与修改方向。",
                    "blocking_rule": "REQUIRE_FEEDBACK",
                }
            ],
        },
        "reviewer_role": "REVIEWER",
        "feedback_sla_business_days": 2,
        "sensitivity": "INTERNAL",
        "audience": "LEARNER",
    }


def request(method: str, path: str, body: dict, role: dict[str, str]):
    return client.request(
        method,
        path,
        headers={**role, "Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )


def data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def test_content_editor_can_submit_but_only_operator_can_publish_exact_snapshot():
    with SessionLocal() as session:
        editor_id = session.scalar(
            select(User.id)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.organization_id == ORGANIZATION_ID,
                RoleAssignment.organization_id == ORGANIZATION_ID,
                RoleAssignment.role == Role.CONTENT_EDITOR,
            )
        )
    if editor_id is None:
        created_editor = data(
            request(
                "POST",
                "/api/v1/ops/content-editors",
                {
                    "display_name": "WP26 Synthetic Content Editor",
                    "expected_absent": True,
                },
                OPERATOR,
            )
        )
        editor_id = uuid.UUID(created_editor["user_id"])
        assert created_editor["role"] == "CONTENT_EDITOR"

    definition = data(
        request(
            "POST",
            "/api/v1/ops/task-definitions",
            {"stable_key": f"WP26-EDITOR-{uuid.uuid4().hex[:8].upper()}"},
            OPERATOR,
        )
    )
    forbidden = request(
        "POST",
        f"/api/v1/content/task-definitions/{definition['id']}/drafts",
        {"content": payload()},
        OPERATOR,
    )
    assert forbidden.status_code == 403

    draft = data(
        request(
            "POST",
            f"/api/v1/content/task-definitions/{definition['id']}/drafts",
            {"content": payload()},
            EDITOR,
        )
    )
    assert draft["status"] == "DRAFT"
    assert draft["owner_id"] == str(editor_id)
    assert draft["content"]["learning_materials"][0]["key"] == "company-intro"

    updated = data(
        request(
            "PUT",
            f"/api/v1/content/drafts/{draft['id']}",
            {
                "expected_revision": draft["revision"],
                "content": payload("宝藏一：公司认知（复核稿）"),
            },
            EDITOR,
        )
    )
    assert updated["content"]["title"] == "宝藏一：公司认知（复核稿）"
    submitted = data(
        request(
            "POST",
            f"/api/v1/content/drafts/{draft['id']}/submit",
            {
                "expected_revision": updated["revision"],
                "review_note": "材料来源和任务边界已经完成线下复核，请 Operator 发布固定版本。",
            },
            EDITOR,
        )
    )
    assert submitted["status"] == "SUBMITTED"

    rewrite = request(
        "PUT",
        f"/api/v1/content/drafts/{draft['id']}",
        {
            "expected_revision": submitted["revision"],
            "content": payload("不应被接受的原地修改"),
        },
        EDITOR,
    )
    assert rewrite.status_code == 409

    try:
        with SessionLocal.begin() as session:
            session.execute(
                update(ContentDraft)
                .where(ContentDraft.id == uuid.UUID(draft["id"]))
                .values(content=payload("数据库直接改写也应失败"))
            )
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("submitted content draft rewrite unexpectedly succeeded")

    published = data(
        request(
            "POST",
            f"/api/v1/ops/content-drafts/{draft['id']}/publish",
            {
                "expected_revision": submitted["revision"],
                "expected_definition_revision": definition["revision"],
                "reviewed_by": str(REVIEWER_ID),
                "review_acknowledged": True,
            },
            OPERATOR,
        )
    )
    assert published["title"] == "宝藏一：公司认知（复核稿）"
    assert published["learning_materials"] == submitted["content"]["learning_materials"]
    assert published["published_by"] != str(editor_id)

    with SessionLocal() as session:
        stored = session.get(ContentDraft, uuid.UUID(draft["id"]))
        version = session.get(TaskVersion, uuid.UUID(published["id"]))
        assert stored is not None and stored.status == ContentDraftStatus.PUBLISHED
        assert stored.published_task_version_id == version.id
        assert version.learning_materials == stored.content["learning_materials"]
        assert session.scalar(
            select(ContentDraft.id).where(ContentDraft.id == stored.id)
        )
