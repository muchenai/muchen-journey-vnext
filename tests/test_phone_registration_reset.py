import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.identity import utc_now
from journey_api.models import ExternalIdentity, PhoneOtpChallenge, PhonePasswordCredential, AuditEntry
from journey_api.phone_auth_routes import phone_subject
from test_phone_password_flow import password_provider, register
from test_learner_feishu_login import learner_provider
from test_wp09_feishu_identity import oauth_provider, client_for, assert_ok


def allow_resend(phone):
    with SessionLocal.begin() as session:
        for row in session.scalars(select(PhoneOtpChallenge).where(
            PhoneOtpChallenge.phone_subject == phone_subject(phone),
        )):
            # Age all challenges equally: retain their original ordering so a
            # consumed registration code cannot appear newer than a reset code.
            row.created_at -= timedelta(minutes=2)


def request_code(client, phone, purpose):
    allow_resend(phone)
    return client.post("/api/v1/auth/phone/request-code", json={"phone": phone, "purpose": purpose})


def test_login_does_not_register_without_phone_verification(password_provider):
    client = client_for("no-auto-registration")
    credentials = {"phone": "13800001234", "password": "test1234"}
    assert client.post("/api/v1/auth/password/login", json=credentials).status_code == 401
    assert client.post("/api/v1/auth/password/register", json=credentials).status_code == 422
    assert client.post("/api/v1/auth/password/register", json={**credentials, "code": "123456"}).status_code == 410
    assert client.get("/api/v1/session").status_code == 401
    with SessionLocal() as session:
        assert session.scalar(select(ExternalIdentity).where(
            ExternalIdentity.subject == phone_subject(credentials["phone"]),
        )) is None


def test_reset_preserves_identity_materials_and_journey_and_revokes_sessions(password_provider):
    first, credentials = register("reset-original")
    principal = assert_ok(first.get("/api/v1/session"))
    action = assert_ok(first.get("/api/v1/me/current-action"))
    detail_path = f"/api/v1/me/assignments/{action['resource_id']}"
    detail = assert_ok(first.get(detail_path))
    material = detail["learning_materials"][0]
    completed = assert_ok(first.post(f"{detail_path}/materials/{material['key']}/complete",
        json={"task_version": detail["task_version"]}, headers={
            "X-CSRF-Token": first.cookies["journey_next_csrf"], "Idempotency-Key": str(uuid.uuid4())}))
    resetter = client_for("password-reset")
    assert_ok(request_code(resetter, credentials["phone"], "reset"))
    command = {**credentials, "code": "123456", "password": "new12345"}
    assert_ok(resetter.post("/api/v1/auth/password/reset", json=command))
    assert first.get("/api/v1/session").status_code == 401
    assert resetter.get("/api/v1/session").status_code == 401
    assert resetter.post("/api/v1/auth/password/reset", json=command).status_code == 410
    assert resetter.post("/api/v1/auth/password/login", json=credentials).status_code == 401
    assert_ok(resetter.post("/api/v1/auth/password/login", json={**credentials, "password": "new12345"}))
    assert assert_ok(resetter.get("/api/v1/session"))["user_id"] == principal["user_id"]
    assert assert_ok(resetter.get("/api/v1/me/current-action"))["resource_id"] == action["resource_id"]
    assert assert_ok(resetter.get(detail_path))["learning_materials"][0]["completed_at"] == completed["completed_at"]
    with SessionLocal() as session:
        audit = session.scalar(select(AuditEntry).where(
            AuditEntry.actor_id == uuid.UUID(principal["user_id"]),
            AuditEntry.action == "password.reset_succeeded",
        ))
        assert audit is not None
        assert "password" not in audit.details and "code" not in audit.details


def test_duplicate_registration_cannot_replace_password(password_provider):
    first, credentials = register("duplicate-registration")
    other = client_for("duplicate-attempt")
    result = request_code(other, credentials["phone"], "register")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "PHONE_ALREADY_REGISTERED"
    assert_ok(request_code(other, credentials["phone"], "reset"))
    wrong_purpose = other.post("/api/v1/auth/password/register", json={
        **credentials, "code": "123456", "password": "changed123",
    })
    assert wrong_purpose.status_code == 401
    assert_ok(other.post("/api/v1/auth/password/login", json=credentials))


@pytest.mark.parametrize("failure", ["expired", "attempts"])
def test_bad_otp_cannot_reset_password(password_provider, failure):
    _, credentials = register("bad-otp")
    client = client_for("bad-reset-" + failure)
    assert_ok(request_code(client, credentials["phone"], "reset"))
    if failure == "expired":
        with SessionLocal.begin() as session:
            challenge = session.scalar(select(PhoneOtpChallenge).where(
                PhoneOtpChallenge.phone_subject == phone_subject(credentials["phone"]),
                PhoneOtpChallenge.consumed_at.is_(None),
            ))
            challenge.expires_at = utc_now() - timedelta(seconds=1)
    else:
        for _ in range(5):
            assert client.post("/api/v1/auth/password/reset", json={
                **credentials, "code": "000000", "password": "changed123",
            }).status_code == 401
    assert client.post("/api/v1/auth/password/reset", json={
        **credentials, "code": "123456", "password": "changed123",
    }).status_code == (410 if failure == "expired" else 401)
    assert_ok(client.post("/api/v1/auth/password/login", json=credentials))


def test_retired_phone_cannot_reset_reregister_or_use_direct_otp(password_provider):
    _, credentials = register("retired")
    client = client_for("retired-reset")
    assert_ok(request_code(client, credentials["phone"], "reset"))
    with SessionLocal.begin() as session:
        identity = session.scalar(select(ExternalIdentity).where(
            ExternalIdentity.subject == phone_subject(credentials["phone"]),
        ))
        identity.revoked_at = utc_now()
    for path in ("reset", "register"):
        denied = client.post(f"/api/v1/auth/password/{path}", json={**credentials, "code": "123456"})
        # Registration OTP cannot be substituted with a reset OTP.
        assert denied.status_code in (401, 409)
        assert request_code(client, credentials["phone"], path).status_code == 409
    assert client.post("/api/v1/auth/phone/verify", json={
        "phone": credentials["phone"], "code": "123456",
    }).status_code == 409
    assert client.get("/api/v1/session").status_code == 401


def test_old_sms_identity_can_set_password_without_duplicate_account(password_provider):
    first, credentials = register("old-sms")
    principal = assert_ok(first.get("/api/v1/session"))
    with SessionLocal.begin() as session:
        identity = session.scalar(select(ExternalIdentity).where(
            ExternalIdentity.subject == phone_subject(credentials["phone"]),
        ))
        credential = session.scalar(select(PhonePasswordCredential).where(
            PhonePasswordCredential.external_identity_id == identity.id,
        ))
        session.delete(credential)
        identity.provider = "PHONE"
    client = client_for("old-sms-reset")
    assert_ok(request_code(client, credentials["phone"], "reset"))
    assert_ok(client.post("/api/v1/auth/password/reset", json={**credentials, "code": "123456"}))
    assert_ok(client.post("/api/v1/auth/password/login", json=credentials))
    assert assert_ok(client.get("/api/v1/session"))["user_id"] == principal["user_id"]
