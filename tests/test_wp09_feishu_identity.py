import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.feishu_oauth import (
    FeishuProfile,
    OAuthProviderError,
    get_feishu_oauth_client,
)
from journey_api.fixtures import OPERATOR_ID, ORGANIZATION_ID
from journey_api.identity import OAUTH_COOKIE, SESSION_COOKIE
from journey_api.main import app
from journey_api.models import (
    AuditEntry,
    ExternalIdentity,
    ExternalIdentityLink,
    IdentitySession,
    Organization,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)
from journey_api.wp09_bootstrap import BootstrapError, create_operator_link

OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}


class FakeFeishuOAuthClient:
    def __init__(self) -> None:
        self.subjects: dict[str, str] = {}
        self.exchange_count = 0

    @staticmethod
    def authorization_url(state: str) -> str:
        return (
            "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
            f"?app_id=cli_test&state={state}"
        )

    def exchange_code(self, code: str) -> FeishuProfile:
        self.exchange_count += 1
        subject = self.subjects.get(code)
        if subject is None:
            raise OAuthProviderError("test provider failure")
        return FeishuProfile(open_id=subject)


@pytest.fixture
def oauth_provider(monkeypatch: pytest.MonkeyPatch):
    values = {
        "APP_ENV": "test",
        "ALLOW_FIXTURE_IDENTITY": "true",
        "SESSION_SECRET": "test-session-secret-independent-00000001",
        "INVITE_SECRET": "test-invite-secret-independent-000000002",
        "IMPORT_SIGNING_KEY": "test-import-secret-independent-000000003",
        "IDENTITY_SUBJECT_SECRET": "test-subject-secret-independent-0000004",
        "FEISHU_OAUTH_ENABLED": "true",
        "FEISHU_APP_ID": "cli_test",
        "FEISHU_APP_SECRET": "test-feishu-app-secret-00005",
        "FEISHU_OAUTH_REDIRECT_URI": "http://localhost/auth/feishu/callback",
        "OAUTH_ATTEMPT_LIMIT": "20",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    get_feishu_oauth_client.cache_clear()
    provider = FakeFeishuOAuthClient()
    app.dependency_overrides[get_feishu_oauth_client] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_feishu_oauth_client, None)
    get_settings.cache_clear()
    get_feishu_oauth_client.cache_clear()


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 50_000))


def assert_ok(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def create_link(role: Role, target_user_id: uuid.UUID) -> dict[str, object]:
    response = client_for(f"operator-link-{uuid.uuid4()}").post(
        "/api/v1/ops/identity-links",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"identity-link-{uuid.uuid4()}",
        },
        json={
            "target_user_id": str(target_user_id),
            "role": role.value,
            "expires_in_minutes": 30,
        },
    )
    return assert_ok(response)


def create_role_user(role: Role) -> uuid.UUID:
    user_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=user_id,
                organization_id=ORGANIZATION_ID,
                display_name=f"WP09 {role.value}",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=user_id,
                role=role,
            )
        )
    return user_id


def begin_oauth(client: TestClient, return_to: str, link_token: str | None = None) -> str:
    body = {"return_to": return_to, "link_token": link_token}
    response = client.post(
        "/api/v1/auth/feishu/start",
        headers={"X-Forwarded-For": "198.51.100.20"},
        json=body,
    )
    data = assert_ok(response)
    assert response.headers["Cache-Control"] == "no-store"
    authorization = urlsplit(data["authorization_url"])
    assert authorization.scheme == "https"
    assert authorization.hostname == "accounts.feishu.cn"
    return parse_qs(authorization.query)["state"][0]


def callback(
    client: TestClient,
    code: str,
    state: str,
    browser_token: str | None = None,
):
    browser_token = browser_token or client.cookies.get(OAUTH_COOKIE)
    assert browser_token
    return client.post(
        "/api/v1/auth/feishu/callback",
        headers={
            "Cookie": f"{OAUTH_COOKIE}={browser_token}",
            "X-Forwarded-For": "198.51.100.20",
        },
        json={"code": code, "state": state},
    )


def test_reviewer_link_oauth_callback_hashes_subject_and_creates_scoped_session(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    link = create_link(Role.REVIEWER, reviewer_id)
    assert link["start_path"].startswith("/auth/feishu?")
    assert link["link_token"] not in link["id"]
    reviewer = client_for("wp09-reviewer-link")
    state = begin_oauth(reviewer, "/review", str(link["link_token"]))
    raw_subject = f"ou_test_{uuid.uuid4().hex}"
    oauth_provider.subjects["reviewer-code"] = raw_subject
    oauth_browser_token = reviewer.cookies.get(OAUTH_COOKIE)
    assert oauth_browser_token

    completed = assert_ok(callback(reviewer, "reviewer-code", state))
    assert completed["safe_entry"] == "/review"
    assert SESSION_COOKIE in reviewer.cookies
    assert assert_ok(reviewer.get("/api/v1/session"))["safe_entry"] == "/review"
    assert reviewer.get("/api/v1/reviews").status_code == 200
    assert reviewer.get("/api/v1/ops/invites").status_code == 403

    with SessionLocal() as session:
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.user_id == reviewer_id,
                ExternalIdentity.provider == "FEISHU",
                ExternalIdentity.revoked_at.is_(None),
            )
        )
        assert identity is not None
        assert identity.subject != raw_subject
        assert len(identity.subject) == 64
        stored_session = session.scalar(
            select(IdentitySession).where(
                IdentitySession.external_identity_id == identity.id,
                IdentitySession.revoked_at.is_(None),
            )
        )
        assert stored_session is not None and stored_session.role == Role.REVIEWER
        audit_entries = session.scalars(
            select(AuditEntry).where(
                AuditEntry.resource_id.in_([identity.id, stored_session.id])
            )
        ).all()
        serialized_audit = " ".join(str(entry.details) for entry in audit_entries)
        assert raw_subject not in serialized_audit
        assert str(link["link_token"]) not in serialized_audit

    replay = callback(reviewer, "reviewer-code", state, oauth_browser_token)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "OAUTH_STATE_REPLAY"
    assert oauth_provider.exchange_count == 1


def test_existing_mapping_login_rotates_old_session_and_rejects_wrong_role(
    oauth_provider: FakeFeishuOAuthClient,
):
    link = create_link(Role.OPERATOR, OPERATOR_ID)
    raw_subject = f"ou_operator_{uuid.uuid4().hex}"
    oauth_provider.subjects["operator-link-code"] = raw_subject
    first = client_for("wp09-operator-first")
    first_state = begin_oauth(first, "/ops", str(link["link_token"]))
    assert_ok(callback(first, "operator-link-code", first_state))
    assert first.get("/api/v1/ops/invites").status_code == 200

    oauth_provider.subjects["operator-login-code"] = raw_subject
    second = client_for("wp09-operator-second")
    second_state = begin_oauth(second, "/ops")
    assert_ok(callback(second, "operator-login-code", second_state))
    assert first.get("/api/v1/session").status_code == 401
    assert second.get("/api/v1/session").status_code == 200

    oauth_provider.subjects["wrong-role-code"] = raw_subject
    wrong_role = client_for("wp09-operator-wrong-role")
    wrong_state = begin_oauth(wrong_role, "/review")
    denied = callback(wrong_role, "wrong-role-code", wrong_state)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_oauth_rejects_open_redirect_browser_mismatch_unlinked_and_provider_failure(
    oauth_provider: FakeFeishuOAuthClient,
):
    invalid_return = client_for("wp09-open-redirect").post(
        "/api/v1/auth/feishu/start",
        json={"return_to": "https://attacker.invalid"},
    )
    assert invalid_return.status_code == 422

    owner = client_for("wp09-browser-owner")
    state = begin_oauth(owner, "/review")
    oauth_provider.subjects["unlinked-code"] = f"ou_unlinked_{uuid.uuid4().hex}"
    mismatched = client_for("wp09-browser-mismatch").post(
        "/api/v1/auth/feishu/callback",
        headers={"Cookie": f"{OAUTH_COOKIE}=wrong-browser-token"},
        json={"code": "unlinked-code", "state": state},
    )
    assert mismatched.status_code == 401
    assert oauth_provider.exchange_count == 0

    unlinked = callback(owner, "unlinked-code", state)
    assert unlinked.status_code == 403
    assert unlinked.json()["error"]["code"] == "IDENTITY_NOT_LINKED"
    assert SESSION_COOKIE not in owner.cookies

    provider_down = client_for("wp09-provider-down")
    failed_state = begin_oauth(provider_down, "/review")
    failed = callback(provider_down, "provider-failure", failed_state)
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "IDENTITY_PROVIDER_UNAVAILABLE"
    assert failed.json()["error"]["retryable"] is True
    replay = callback(provider_down, "provider-failure", failed_state)
    assert replay.status_code == 409


def test_external_identity_revocation_immediately_invalidates_session(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    link = create_link(Role.REVIEWER, reviewer_id)
    raw_subject = f"ou_revoked_{uuid.uuid4().hex}"
    oauth_provider.subjects["revoke-code"] = raw_subject
    reviewer = client_for("wp09-revoked-reviewer")
    state = begin_oauth(reviewer, "/review", str(link["link_token"]))
    assert_ok(callback(reviewer, "revoke-code", state))
    with SessionLocal() as session:
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.user_id == reviewer_id,
                ExternalIdentity.provider == "FEISHU",
                ExternalIdentity.revoked_at.is_(None),
            )
        )
        assert identity is not None
        identity_id = identity.id
        revision = identity.revision

    revoked = client_for("wp09-operator-revoke").post(
        f"/api/v1/ops/external-identities/{identity_id}/revoke",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"external-identity-revoke-{uuid.uuid4()}",
        },
        json={
            "expected_revision": revision,
            "reason": "Alpha 身份撤销窗口验证完成",
        },
    )
    assert assert_ok(revoked)["status"] == "REVOKED"
    assert reviewer.get("/api/v1/session").status_code == 401


def test_external_identity_revocation_is_idempotent(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    link = create_link(Role.REVIEWER, reviewer_id)
    oauth_provider.subjects["idempotent-revoke-code"] = f"ou_{uuid.uuid4().hex}"
    reviewer = client_for("wp09-idempotent-revoke-reviewer")
    state = begin_oauth(reviewer, "/review", str(link["link_token"]))
    assert_ok(callback(reviewer, "idempotent-revoke-code", state))
    with SessionLocal() as session:
        identity = session.scalar(
            select(ExternalIdentity).where(ExternalIdentity.user_id == reviewer_id)
        )
        assert identity is not None
        identity_id = identity.id
        revision = identity.revision

    key = f"external-identity-revoke-{uuid.uuid4()}"
    request = {
        "expected_revision": revision,
        "reason": "Alpha 身份撤销幂等验证完成",
    }
    operator = client_for("wp09-idempotent-revoke-operator")
    first = operator.post(
        f"/api/v1/ops/external-identities/{identity_id}/revoke",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": key},
        json=request,
    )
    replay = operator.post(
        f"/api/v1/ops/external-identities/{identity_id}/revoke",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": key},
        json=request,
    )
    assert assert_ok(first)["idempotency_replay"] is False
    assert assert_ok(replay)["idempotency_replay"] is True


def test_disabled_user_or_removed_role_invalidates_external_session(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    link = create_link(Role.REVIEWER, reviewer_id)
    oauth_provider.subjects["disabled-user-code"] = f"ou_{uuid.uuid4().hex}"
    reviewer = client_for("wp09-disabled-user")
    state = begin_oauth(reviewer, "/review", str(link["link_token"]))
    assert_ok(callback(reviewer, "disabled-user-code", state))
    with SessionLocal.begin() as session:
        user = session.get(User, reviewer_id)
        assert user is not None
        user.status = UserStatus.DISABLED
    assert reviewer.get("/api/v1/session").status_code == 401

    second_id = create_role_user(Role.REVIEWER)
    second_link = create_link(Role.REVIEWER, second_id)
    oauth_provider.subjects["removed-role-code"] = f"ou_{uuid.uuid4().hex}"
    second = client_for("wp09-removed-role")
    second_state = begin_oauth(second, "/review", str(second_link["link_token"]))
    assert_ok(callback(second, "removed-role-code", second_state))
    with SessionLocal.begin() as session:
        assignment = session.scalar(
            select(RoleAssignment).where(
                RoleAssignment.user_id == second_id,
                RoleAssignment.role == Role.REVIEWER,
            )
        )
        assert assignment is not None
        session.delete(assignment)
    assert second.get("/api/v1/session").status_code == 401


def test_identity_link_cannot_target_another_organization(
    oauth_provider: FakeFeishuOAuthClient,
):
    del oauth_provider
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=organization_id, name="Other tenant"))
        session.flush()
        session.add(
            User(
                id=user_id,
                organization_id=organization_id,
                display_name="Other reviewer",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=organization_id,
                user_id=user_id,
                role=Role.REVIEWER,
            )
        )
    denied = client_for("wp09-cross-organization").post(
        "/api/v1/ops/identity-links",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"cross-organization-{uuid.uuid4()}",
        },
        json={
            "target_user_id": str(user_id),
            "role": Role.REVIEWER.value,
            "expires_in_minutes": 30,
        },
    )
    assert denied.status_code == 422


def test_oauth_start_is_rate_limited_by_forwarded_client(
    oauth_provider: FakeFeishuOAuthClient,
    monkeypatch: pytest.MonkeyPatch,
):
    del oauth_provider
    monkeypatch.setenv("OAUTH_ATTEMPT_LIMIT", "5")
    get_settings.cache_clear()
    client = client_for("wp09-rate-limit")
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/feishu/start",
            headers={"X-Forwarded-For": "198.51.100.77"},
            json={"return_to": "/review"},
        )
        assert response.status_code == 200
    limited = client.post(
        "/api/v1/auth/feishu/start",
        headers={"X-Forwarded-For": "198.51.100.77"},
        json={"return_to": "/review"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_identity_link_rejects_role_mismatch_and_can_be_revoked(
    oauth_provider: FakeFeishuOAuthClient,
):
    del oauth_provider
    reviewer_id = create_role_user(Role.REVIEWER)
    link = create_link(Role.REVIEWER, reviewer_id)
    mismatch = client_for("wp09-link-role-mismatch").post(
        "/api/v1/auth/feishu/start",
        json={"return_to": "/ops", "link_token": link["link_token"]},
    )
    assert mismatch.status_code == 422
    revoked = client_for("wp09-link-revoke").post(
        f"/api/v1/ops/identity-links/{link['id']}/revoke",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"identity-link-revoke-{uuid.uuid4()}",
        },
        json={
            "expected_revision": link["revision"],
            "reason": "测试对象不再参与本轮身份绑定",
        },
    )
    assert assert_ok(revoked)["status"] == "REVOKED"
    denied = client_for("wp09-revoked-link").post(
        "/api/v1/auth/feishu/start",
        json={"return_to": "/review", "link_token": link["link_token"]},
    )
    assert denied.status_code == 410


def test_first_operator_bootstrap_is_audited_and_token_hashed():
    secret = "test-subject-secret-independent-0000004"
    operator_id = create_role_user(Role.OPERATOR)
    with SessionLocal() as session:
        created = create_operator_link(
            session,
            target_user_id=operator_id,
            secret=secret,
            authorization_reference="AUTH-20260725-WP09",
            expires_in_minutes=15,
        )
    token = str(created["start_path"]).rsplit("=", 1)[1]
    with SessionLocal() as session:
        link = session.get(ExternalIdentityLink, uuid.UUID(str(created["link_id"])))
        assert link is not None
        assert link.created_by is None
        assert link.token_hash != token
        audit = session.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "identity_link.bootstrap_created",
                AuditEntry.resource_id == link.id,
            )
        )
        assert audit is not None
        assert audit.actor_id is None
        assert token not in str(audit.details)

    with SessionLocal() as session, pytest.raises(BootstrapError, match="unexpired"):
        create_operator_link(
            session,
            target_user_id=operator_id,
            secret=secret,
            authorization_reference="AUTH-20260725-WP09-REPLAY",
        )
