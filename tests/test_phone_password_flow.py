import secrets
import uuid

import pytest
from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.models import Assignment, AssignmentStatus, Enrollment, Role, RoleAssignment
from test_learner_feishu_login import learner_provider, login
from test_wp09_feishu_identity import oauth_provider, client_for, assert_ok


@pytest.fixture
def password_provider(learner_provider, monkeypatch):
    monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "true")
    get_settings.cache_clear()
    yield learner_provider
    get_settings.cache_clear()


def register(label):
    client = client_for(label + uuid.uuid4().hex)
    credentials = {"phone": "139" + str(secrets.randbelow(10**8)).zfill(8), "password": "test1234"}
    assert assert_ok(client.post("/api/v1/auth/password/login", json=credentials))["is_new_user"]
    return client, credentials


def migrate(client, code):
    return client.post("/api/v1/me/completion-code/migrate", json={"code": code}, headers={
        "X-CSRF-Token": client.cookies["journey_next_csrf"],
        "Idempotency-Key": str(uuid.uuid4()),
    })


def test_returning_password_user_keeps_identity_and_journey(password_provider):
    first, credentials = register("password-first")
    principal = assert_ok(first.get("/api/v1/session"))
    action = assert_ok(first.get("/api/v1/me/current-action"))
    assert assert_ok(first.get("/api/v1/me/completion-code"))["status"] == "LOCKED"
    second = client_for("password-return" + uuid.uuid4().hex)
    wrong = second.post("/api/v1/auth/password/login", json={**credentials, "password": "wrong123"})
    assert wrong.status_code == 401
    assert not assert_ok(second.post("/api/v1/auth/password/login", json=credentials))["is_new_user"]
    assert assert_ok(second.get("/api/v1/session"))["user_id"] == principal["user_id"]
    assert assert_ok(second.get("/api/v1/me/current-action"))["resource_id"] == action["resource_id"]
    assert second.get("/api/v1/reviews").status_code == 403


def test_completion_code_moves_feishu_identity_once_and_retires_phone_login(password_provider):
    source, credentials = register("password-graduate")
    source_id = uuid.UUID(assert_ok(source.get("/api/v1/session"))["user_id"])
    # Fixture-only completed journey; the full review suite proves task transitions.
    with SessionLocal.begin() as session:
        enrollment = session.scalar(select(Enrollment).where(Enrollment.learner_id == source_id))
        assignments = session.scalars(select(Assignment).where(Assignment.enrollment_id == enrollment.id)).all()
        assignment_ids = {str(row.id) for row in assignments}
        for row in assignments:
            row.status = AssignmentStatus.COMPLETED
    code = assert_ok(source.get("/api/v1/me/completion-code"))["code"]
    assert assert_ok(source.get("/api/v1/me/completion-code"))["code"] == code
    assert migrate(source, code).status_code == 403
    target, response = login(password_provider, "graduate-feishu" + uuid.uuid4().hex, "ou_graduate_" + uuid.uuid4().hex)
    assert_ok(response)
    target_id = uuid.UUID(assert_ok(target.get("/api/v1/session"))["user_id"])
    with SessionLocal.begin() as session:
        from journey_api.fixtures import ORGANIZATION_ID
        staff_role = RoleAssignment(id=uuid.uuid4(), user_id=target_id, organization_id=ORGANIZATION_ID, role=Role.REVIEWER)
        session.add(staff_role)
        staff_role_id = staff_role.id
    denied_staff = migrate(target, code)
    assert denied_staff.status_code == 409
    assert denied_staff.json()["error"]["code"] == "TARGET_ACCOUNT_HAS_STAFF_ROLES"
    assert assert_ok(target.get("/api/v1/session"))["user_id"] == str(target_id)
    with SessionLocal.begin() as session:
        session.delete(session.get(RoleAssignment, staff_role_id))
    result = assert_ok(migrate(target, code))
    assert result["migrated_tasks"] == len(assignment_ids)
    assert assert_ok(target.get("/api/v1/session"))["user_id"] == str(source_id)
    assert source.get("/api/v1/session").status_code == 401
    denied = client_for("retired-phone").post("/api/v1/auth/password/login", json=credentials)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "ACCOUNT_MIGRATED"
    assert migrate(target, code).json()["error"]["code"] == "COMPLETION_CODE_USED"
    with SessionLocal() as session:
        enrollment = session.scalar(select(Enrollment).where(Enrollment.learner_id == source_id))
        assert {str(value) for value in session.scalars(select(Assignment.id).where(Assignment.enrollment_id == enrollment.id))} == assignment_ids
