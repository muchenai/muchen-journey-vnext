import uuid

from fastapi.testclient import TestClient

from journey_api.fixtures import REVIEWER_ID, TASK_VERSION_ID
from journey_api.main import app


OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}


def ok(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def post(client: TestClient, path: str, payload: dict):
    return ok(
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid.uuid4()), **OPERATOR_HEADERS},
            json=payload,
        )
    )


def invite_payload(purpose: str) -> dict:
    return {
        "purpose": purpose,
        "expires_in_hours": 24,
        "role": "LEARNER",
        "reviewer_id": str(REVIEWER_ID),
        "task_version_id": str(TASK_VERSION_ID),
        "journey_version_id": None,
        "target_user_id": None,
    }


def test_invitation_freeze_blocks_only_new_invites_and_preserves_existing_facts():
    client = TestClient(app, base_url="http://localhost", client=("wp30-operator", 62_000))
    initial = ok(client.get("/api/v1/ops/invitation-control", headers=OPERATOR_HEADERS))
    assert initial["state"] == "OPEN"

    existing = post(client, "/api/v1/ops/invites", invite_payload("WP30 freeze preservation baseline"))
    frozen = post(
        client,
        "/api/v1/ops/invitation-control/freeze",
        {
            "expected_revision": initial["revision"],
            "reason": "Controlled launch stop condition; freeze only future invitations.",
        },
    )
    assert frozen["state"] == "FROZEN"
    blocked = client.post(
        "/api/v1/ops/invites",
        headers={"Idempotency-Key": str(uuid.uuid4()), **OPERATOR_HEADERS},
        json=invite_payload("This invite must be rejected while frozen"),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INVITES_FROZEN"

    listed = ok(client.get("/api/v1/ops/invites", headers=OPERATOR_HEADERS))["items"]
    preserved = next(item for item in listed if item["id"] == existing["id"])
    assert preserved["status"] == "ACTIVE"

    resumed = post(
        client,
        "/api/v1/ops/invitation-control/resume",
        {
            "expected_revision": frozen["revision"],
            "reason": "Independent Operator authorization restored controlled invitations.",
        },
    )
    assert resumed["state"] == "OPEN"
    created_after_resume = post(
        client,
        "/api/v1/ops/invites",
        invite_payload("Invitation created after explicit controlled resume"),
    )
    assert created_after_resume["status"] == "ACTIVE"
