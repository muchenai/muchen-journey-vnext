import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from journey_api.db import SessionLocal
from journey_api.fixtures import LEARNER_ID
from journey_api.main import app
from journey_api.models import Organization, User, UserStatus


client = TestClient(app, base_url="http://localhost")
operator_headers = {"X-Fixture-Role": "OPERATOR"}
learner_headers = {"X-Fixture-Role": "LEARNER"}
reviewer_headers = {"X-Fixture-Role": "REVIEWER"}


def assert_ok(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def command_headers(key: str) -> dict[str, str]:
    return {**operator_headers, "Idempotency-Key": key}


def test_data_rights_workflow_is_operator_only_scoped_and_idempotent():
    create_body = {
        "subject_user_id": str(LEARNER_ID),
        "request_type": "DELETE",
        "reason": "试点用户提出删除请求，先登记并完成范围核验。",
    }
    for headers in ({}, learner_headers, reviewer_headers):
        assert client.get("/api/v1/ops/data-rights-requests", headers=headers).status_code in {
            401,
            403,
        }
        assert client.post(
            "/api/v1/ops/data-rights-requests",
            headers={**headers, "Idempotency-Key": f"denied-{uuid.uuid4()}"},
            json=create_body,
        ).status_code in {401, 403}

    key = f"rights-create-{uuid.uuid4()}"
    created = assert_ok(
        client.post(
            "/api/v1/ops/data-rights-requests",
            headers=command_headers(key),
            json=create_body,
        )
    )
    assert created["subject_user_id"] == str(LEARNER_ID)
    assert created["request_type"] == "DELETE"
    assert created["status"] == "OPEN"
    assert created["legal_hold"] is False
    assert created["revision"] == 1
    assert created["allowed_commands"] == ["set_legal_hold", "reject_request"]
    due_seconds = (
        datetime.fromisoformat(created["due_at"])
        - datetime.fromisoformat(created["requested_at"])
    ).total_seconds()
    assert due_seconds == 30 * 24 * 60 * 60

    replay = assert_ok(
        client.post(
            "/api/v1/ops/data-rights-requests",
            headers=command_headers(key),
            json=create_body,
        )
    )
    assert replay["id"] == created["id"]
    assert replay["idempotency_replay"] is True

    listed = assert_ok(
        client.get(
            "/api/v1/ops/data-rights-requests",
            headers=operator_headers,
            params={"status": "OPEN"},
        )
    )
    assert created["id"] in {item["id"] for item in listed["items"]}

    hold = assert_ok(
        client.put(
            f"/api/v1/ops/data-rights-requests/{created['id']}/legal-hold",
            headers=command_headers(f"rights-hold-{uuid.uuid4()}"),
            json={
                "expected_revision": 1,
                "legal_hold": True,
                "reason": "正在核验法定保留边界，暂时停止后续处理。",
            },
        )
    )
    assert hold["legal_hold"] is True
    assert hold["revision"] == 2
    assert hold["allowed_commands"] == ["release_legal_hold"]
    blocked = client.post(
        f"/api/v1/ops/data-rights-requests/{created['id']}/reject",
        headers=command_headers(f"rights-reject-held-{uuid.uuid4()}"),
        json={
            "expected_revision": 2,
            "resolution_code": "INVALID_SCOPE",
            "reason": "请求范围当前无法确认，需要先解除法定保留。",
        },
    )
    assert blocked.status_code == 409

    released = assert_ok(
        client.put(
            f"/api/v1/ops/data-rights-requests/{created['id']}/legal-hold",
            headers=command_headers(f"rights-release-{uuid.uuid4()}"),
            json={
                "expected_revision": 2,
                "legal_hold": False,
                "reason": "法定保留核验完成，可以恢复请求处理。",
            },
        )
    )
    assert released["legal_hold"] is False
    assert released["revision"] == 3

    rejected = assert_ok(
        client.post(
            f"/api/v1/ops/data-rights-requests/{created['id']}/reject",
            headers=command_headers(f"rights-reject-{uuid.uuid4()}"),
            json={
                "expected_revision": 3,
                "resolution_code": "IDENTITY_UNVERIFIED",
                "reason": "无法验证请求人与数据主体关系，拒绝本次请求。",
            },
        )
    )
    assert rejected["status"] == "REJECTED"
    assert rejected["resolution_code"] == "IDENTITY_UNVERIFIED"
    assert rejected["revision"] == 4
    assert rejected["allowed_commands"] == []

    audit = assert_ok(
        client.get(
            "/api/v1/ops/audit",
            headers=operator_headers,
            params={"action": "data_rights_request.rejected"},
        )
    )
    entry = next(
        item for item in audit["items"] if item["resource_id"] == created["id"]
    )
    assert entry["safe_details"] == {
        "request_type": "DELETE",
        "resolution_code": "IDENTITY_UNVERIFIED",
        "status": "REJECTED",
    }
    assert entry["redacted_fields"] == ["reason"]


def test_data_rights_subject_and_requests_are_hidden_across_organizations():
    other_org_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=other_org_id, name="WP-12 isolated rights org"))
        session.flush()
        session.add(
            User(
                id=other_user_id,
                organization_id=other_org_id,
                display_name="isolated rights subject",
                status=UserStatus.ACTIVE,
            )
        )
    response = client.post(
        "/api/v1/ops/data-rights-requests",
        headers=command_headers(f"rights-cross-org-{uuid.uuid4()}"),
        json={
            "subject_user_id": str(other_user_id),
            "request_type": "CORRECT",
            "reason": "跨组织主体必须按不存在处理，不能创建请求。",
        },
    )
    assert response.status_code == 404


def test_data_rights_reject_requires_current_revision_and_valid_code():
    created = assert_ok(
        client.post(
            "/api/v1/ops/data-rights-requests",
            headers=command_headers(f"rights-conflict-create-{uuid.uuid4()}"),
            json={
                "subject_user_id": str(LEARNER_ID),
                "request_type": "CORRECT",
                "reason": "登记纠错请求并等待运营人员核验具体范围。",
            },
        )
    )
    stale = client.post(
        f"/api/v1/ops/data-rights-requests/{created['id']}/reject",
        headers=command_headers(f"rights-conflict-{uuid.uuid4()}"),
        json={
            "expected_revision": 2,
            "resolution_code": "DUPLICATE",
            "reason": "这是重复登记，请合并到已有请求继续处理。",
        },
    )
    assert stale.status_code == 409
    invalid = client.post(
        f"/api/v1/ops/data-rights-requests/{created['id']}/reject",
        headers=command_headers(f"rights-invalid-{uuid.uuid4()}"),
        json={
            "expected_revision": 1,
            "resolution_code": "ARBITRARY_REASON",
            "reason": "不允许使用未批准的任意解决代码关闭请求。",
        },
    )
    assert invalid.status_code == 422
