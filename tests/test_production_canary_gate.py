from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from journey_api import auth
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.fixtures import OPERATOR_ID, ORGANIZATION_ID, REVIEWER_ID, TASK_VERSION_ID
from journey_api.identity import SESSION_COOKIE
from journey_api.main import app
from journey_api.models import Invite, Role, RoleAssignment, User, UserStatus
from journey_api.config import Settings


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "allow_fixture_identity": False,
        "release_marker": "PRODUCTION_CANARY_UAT",
        "session_secret": "production-session-secret-example-123456",
        "invite_secret": "production-invite-secret-example-1234567",
        "import_signing_key": "production-import-signing-key-example-123456",
        "identity_subject_secret": "production-identity-subject-key-example-123456",
        "feishu_oauth_enabled": True,
        "feishu_app_id": "cli_production",
        "feishu_app_secret": "production-feishu-secret-123",
        "feishu_oauth_redirect_uri": (
            "https://journey.example.test/auth/feishu/callback"
        ),
        "attachments_enabled": False,
        "notification_channel": "FEISHU",
        "notification_recipients_enabled": False,
        "notification_recipient_key": (
            "bm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm4"
        ),
    }
    values.update(overrides)
    return Settings(**values)


def actor(role: Role, user_id: UUID | None = None) -> auth.Actor:
    return auth.Actor(
        id=user_id or uuid4(),
        organization_id=ORGANIZATION_ID,
        roles=frozenset({role}),
        display_name="Canary test actor",
        entry_role=role,
    )


def canary_guard(name: str):
    guard = getattr(auth, name, None)
    assert callable(guard), f"{name} must enforce the production Canary boundary"
    return guard


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 51_000))


def invite_payload(*, target_user_id: UUID | None = None) -> dict[str, object]:
    return {
        "purpose": "P0-05 production Canary scope test",
        "expires_in_hours": 24,
        "role": "LEARNER",
        "reviewer_id": str(REVIEWER_ID),
        "task_version_id": str(TASK_VERSION_ID),
        "target_user_id": str(target_user_id) if target_user_id else None,
    }


def override_operator() -> None:
    app.dependency_overrides[auth.get_actor] = lambda: actor(Role.OPERATOR, OPERATOR_ID)


def clear_operator_override() -> None:
    app.dependency_overrides.pop(auth.get_actor, None)


def test_canary_configuration_is_runtime_visible_bounded_unique_and_marker_scoped():
    assert {"release_marker", "canary_learner_user_ids"} <= set(
        Settings.model_fields
    )

    learner_ids = [uuid4() for _ in range(8)]
    configured = production_settings(
        canary_learner_user_ids=",".join(str(item) for item in learner_ids)
    )
    assert configured.release_marker == "PRODUCTION_CANARY_UAT"
    assert configured.canary_learner_user_ids == learner_ids

    with pytest.raises(ValidationError, match="at most 8 learners"):
        production_settings(canary_learner_user_ids=[*learner_ids, uuid4()])
    with pytest.raises(ValidationError, match="must be unique"):
        production_settings(canary_learner_user_ids=[learner_ids[0], learner_ids[0]])
    with pytest.raises(ValidationError, match="require RELEASE_MARKER"):
        production_settings(
            release_marker="CONTROLLED_ALPHA",
            canary_learner_user_ids=[learner_ids[0]],
        )


def test_canary_marker_requires_production_and_never_allows_fixture_identity():
    assert "release_marker" in Settings.model_fields

    with pytest.raises(ValidationError, match="requires APP_ENV=production"):
        Settings(release_marker="PRODUCTION_CANARY_UAT")
    with pytest.raises(ValidationError, match="ALLOW_FIXTURE_IDENTITY"):
        production_settings(allow_fixture_identity=True)


def test_canary_defaults_to_zero_learner_access_and_preserves_staff_access(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = production_settings(canary_learner_user_ids=[])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    enforce_scope = canary_guard("enforce_canary_learner_scope")

    with pytest.raises(ApiError) as denied:
        enforce_scope(actor(Role.LEARNER))
    assert denied.value.status_code == 403
    assert denied.value.code == "CANARY_ACCESS_DENIED"

    reviewer = actor(Role.REVIEWER)
    operator = actor(Role.OPERATOR)
    assert enforce_scope(reviewer) is reviewer
    assert enforce_scope(operator) is operator


def test_canary_allows_only_configured_learner(
    monkeypatch: pytest.MonkeyPatch,
):
    allowed_id = uuid4()
    settings = production_settings(canary_learner_user_ids=[allowed_id])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    enforce_scope = canary_guard("enforce_canary_learner_scope")

    allowed = actor(Role.LEARNER, allowed_id)
    assert enforce_scope(allowed) is allowed
    with pytest.raises(ApiError, match="受控内测"):
        enforce_scope(actor(Role.LEARNER))


def test_authenticated_learner_session_cannot_bypass_canary_scope(
    monkeypatch: pytest.MonkeyPatch,
):
    allowed_id = uuid4()
    denied_id = uuid4()
    settings = production_settings(canary_learner_user_ids=[allowed_id])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    identity_session = SimpleNamespace(id=uuid4(), role=Role.LEARNER)
    user = SimpleNamespace(
        id=denied_id,
        organization_id=ORGANIZATION_ID,
        display_name="Denied learner",
    )
    class Result:
        def first(self):
            return identity_session, user

    class ScalarResult:
        def all(self):
            return [Role.LEARNER]

    class Session:
        def execute(self, _query):
            return Result()

        def scalars(self, _query):
            return ScalarResult()

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/session",
            "raw_path": b"/api/v1/session",
            "query_string": b"",
            "headers": [
                (b"cookie", f"{SESSION_COOKIE}=canary-session-token".encode())
            ],
            "client": ("canary-auth-test", 51_001),
            "server": ("localhost", 80),
            "scheme": "http",
        }
    )

    with pytest.raises(ApiError) as denied:
        auth.get_actor(request, session=Session())
    assert denied.value.status_code == 403
    assert denied.value.code == "CANARY_ACCESS_DENIED"


def test_canary_blocks_untargeted_and_non_allowlisted_invites(
    monkeypatch: pytest.MonkeyPatch,
):
    allowed_id = uuid4()
    settings = production_settings(canary_learner_user_ids=[allowed_id])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    enforce_target = canary_guard("enforce_canary_invite_target")

    enforce_target(allowed_id)
    for denied_target in (None, uuid4()):
        with pytest.raises(ApiError) as denied:
            enforce_target(denied_target)
        assert denied.value.status_code == 403
        assert denied.value.code == "CANARY_ACCESS_DENIED"


def test_canary_create_invite_rejects_before_persisting(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = production_settings(canary_learner_user_ids=[])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    with SessionLocal() as session:
        before = session.scalar(select(func.count(Invite.id)))

    override_operator()
    try:
        response = client_for("canary-create-denied").post(
            "/api/v1/ops/invites",
            headers={"Idempotency-Key": f"canary-create-{uuid4()}"},
            json=invite_payload(),
        )
    finally:
        clear_operator_override()

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CANARY_ACCESS_DENIED"
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Invite.id))) == before


def test_existing_untargeted_invite_cannot_bypass_canary_at_exchange(
    monkeypatch: pytest.MonkeyPatch,
):
    override_operator()
    try:
        created = client_for("canary-exchange-setup").post(
            "/api/v1/ops/invites",
            headers={"Idempotency-Key": f"canary-exchange-{uuid4()}"},
            json=invite_payload(),
        )
    finally:
        clear_operator_override()
    assert created.status_code == 200, created.text
    token = created.json()["data"]["invite_token"]

    settings = production_settings(canary_learner_user_ids=[])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    exchanged = client_for("canary-exchange-denied").post(
        "/api/v1/join/exchange",
        json={"token": token, "return_to": "/app"},
    )

    assert exchanged.status_code == 403, exchanged.text
    assert exchanged.json()["error"]["code"] == "CANARY_ACCESS_DENIED"


def test_identity_confirmation_rechecks_current_canary_allowlist(
    monkeypatch: pytest.MonkeyPatch,
):
    target_user_id = uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=target_user_id,
                organization_id=ORGANIZATION_ID,
                display_name="Canary target learner",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=target_user_id,
                role=Role.LEARNER,
            )
        )

    override_operator()
    try:
        created = client_for("canary-confirm-setup").post(
            "/api/v1/ops/invites",
            headers={"Idempotency-Key": f"canary-confirm-{uuid4()}"},
            json=invite_payload(target_user_id=target_user_id),
        )
    finally:
        clear_operator_override()
    assert created.status_code == 200, created.text
    token = created.json()["data"]["invite_token"]

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: production_settings(canary_learner_user_ids=[target_user_id]),
    )
    learner = client_for("canary-confirm-denied")
    exchanged = learner.post(
        "/api/v1/join/exchange",
        json={"token": token, "return_to": "/app"},
    )
    assert exchanged.status_code == 200, exchanged.text
    csrf_token = exchanged.json()["data"]["csrf_token"]

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: production_settings(canary_learner_user_ids=[]),
    )
    confirmed = learner.post(
        "/api/v1/identity/confirm",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "display_name": None,
            "accepted_purpose": True,
            "return_to": "/app",
        },
    )

    assert confirmed.status_code == 403, confirmed.text
    assert confirmed.json()["error"]["code"] == "CANARY_ACCESS_DENIED"


def test_non_canary_release_does_not_apply_invite_allowlist(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(release_marker="CONTROLLED_ALPHA")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    enforce_target = canary_guard("enforce_canary_invite_target")

    enforce_target(None)
    enforce_target(uuid4())
