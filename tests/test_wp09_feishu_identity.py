import uuid
from datetime import timedelta
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
from journey_api.identity import OAUTH_COOKIE, SESSION_COOKIE, credential_hash, utc_now
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


def test_linked_content_editor_can_receive_separately_audited_reviewer_role(
    oauth_provider: FakeFeishuOAuthClient,
):
    editor_id = create_role_user(Role.CONTENT_EDITOR)
    with SessionLocal.begin() as session:
        session.add(
            ExternalIdentity(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=editor_id,
                provider="FEISHU",
                subject=uuid.uuid4().hex + uuid.uuid4().hex,
                verified_at=utc_now(),
                revision=1,
            )
        )
    operator = client_for("operator-grant-reviewer-role")
    key = f"grant-reviewer-{uuid.uuid4()}"
    payload = {
        "expected_absent": True,
        "reason": "郑田源在保留内容编辑职责的同时兼任本次真人评审",
    }
    granted = assert_ok(
        operator.post(
            f"/api/v1/ops/users/{editor_id}/reviewer-role",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": key},
            json=payload,
        )
    )
    replay = assert_ok(
        operator.post(
            f"/api/v1/ops/users/{editor_id}/reviewer-role",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": key},
            json=payload,
        )
    )
    assert granted["status"] == "ACTIVE"
    assert replay["resource_id"] == granted["resource_id"]
    assert replay["idempotency_replay"] is True
    with SessionLocal() as session:
        roles = set(
            session.scalars(
                select(RoleAssignment.role).where(RoleAssignment.user_id == editor_id)
            ).all()
        )
        assert roles == {Role.CONTENT_EDITOR, Role.REVIEWER}
        audit = session.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "reviewer_role.granted",
                AuditEntry.resource_id == uuid.UUID(granted["resource_id"]),
            )
        )
        assert audit is not None
        assert audit.details["role"] == "REVIEWER"


def test_reviewer_role_grant_rejects_unlinked_content_editor(
    oauth_provider: FakeFeishuOAuthClient,
):
    editor_id = create_role_user(Role.CONTENT_EDITOR)
    response = client_for("operator-grant-unlinked-reviewer").post(
        f"/api/v1/ops/users/{editor_id}/reviewer-role",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"grant-unlinked-{uuid.uuid4()}",
        },
        json={
            "expected_absent": True,
            "reason": "未绑定身份的内容编辑不能直接获得评审权限",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDENTITY_NOT_LINKED"


def test_existing_content_editor_session_uses_live_roles_without_rebinding_identity(
    oauth_provider: FakeFeishuOAuthClient,
):
    editor_id = create_role_user(Role.CONTENT_EDITOR)
    link = create_link(Role.CONTENT_EDITOR, editor_id)
    raw_subject = f"ou_multi_role_{uuid.uuid4().hex}"
    oauth_provider.subjects["multi-role-content-code"] = raw_subject
    editor = client_for("wp09-multi-role-content-editor")
    state = begin_oauth(editor, "/content", str(link["link_token"]))
    assert_ok(callback(editor, "multi-role-content-code", state))
    assert editor.get("/api/v1/content/task-definitions").status_code == 200
    assert editor.get("/api/v1/reviews").status_code == 403

    operator = client_for("wp09-multi-role-operator")
    granted = operator.post(
        f"/api/v1/ops/users/{editor_id}/reviewer-role",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"grant-live-session-{uuid.uuid4()}",
        },
        json={
            "expected_absent": True,
            "reason": "验证同一真实身份的角色授权无需重新绑定或重新登录",
        },
    )
    assert assert_ok(granted)["status"] == "ACTIVE"

    session_view = assert_ok(editor.get("/api/v1/session"))
    assert session_view["roles"] == ["CONTENT_EDITOR", "REVIEWER"]
    assert session_view["allowed_workspaces"] == ["content", "review"]
    assert session_view["capabilities"] == [
        "content:manage",
        "review:decide",
        "review:read",
    ]
    assert session_view["safe_entry"] == "/content"
    assert editor.get("/api/v1/content/task-definitions").status_code == 200
    assert editor.get("/api/v1/reviews").status_code == 200

    revoked = operator.post(
        f"/api/v1/ops/users/{editor_id}/reviewer-role/revoke",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"revoke-live-session-{uuid.uuid4()}",
        },
        json={
            "expected_present": True,
            "reason": "验证撤销评审能力不会影响内容编辑身份和现有会话",
        },
    )
    assert assert_ok(revoked)["status"] == "REVOKED"
    assert editor.get("/api/v1/reviews").status_code == 403
    assert editor.get("/api/v1/content/task-definitions").status_code == 200
    after = assert_ok(editor.get("/api/v1/session"))
    assert after["roles"] == ["CONTENT_EDITOR"]
    assert after["allowed_workspaces"] == ["content"]

    with SessionLocal() as session:
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.user_id == editor_id,
                ExternalIdentity.revoked_at.is_(None),
            )
        )
        active_session = session.scalar(
            select(IdentitySession).where(
                IdentitySession.user_id == editor_id,
                IdentitySession.revoked_at.is_(None),
            )
        )
        assert identity is not None
        assert active_session is not None
        assert active_session.role == Role.CONTENT_EDITOR


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


def test_external_identity_revision_change_invalidates_older_session(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    link = create_link(Role.REVIEWER, reviewer_id)
    oauth_provider.subjects["identity-revision-code"] = f"ou_{uuid.uuid4().hex}"
    reviewer = client_for("wp09-identity-revision-reviewer")
    state = begin_oauth(reviewer, "/review", str(link["link_token"]))
    assert_ok(callback(reviewer, "identity-revision-code", state))
    assert reviewer.get("/api/v1/session").status_code == 200

    with SessionLocal.begin() as session:
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.user_id == reviewer_id,
                ExternalIdentity.revoked_at.is_(None),
            )
        )
        assert identity is not None
        identity.revision += 1

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


def test_operator_transfers_revoked_reviewer_identity_and_owner_reactivates_by_new_link(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    original_link = create_link(Role.REVIEWER, reviewer_id)
    raw_subject = f"ou_transfer_{uuid.uuid4().hex}"
    oauth_provider.subjects["transfer-original-code"] = raw_subject
    original_browser = client_for("wp09-transfer-original-reviewer")
    original_state = begin_oauth(
        original_browser,
        "/review",
        str(original_link["link_token"]),
    )
    assert_ok(callback(original_browser, "transfer-original-code", original_state))
    with SessionLocal() as session:
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.user_id == reviewer_id,
                ExternalIdentity.revoked_at.is_(None),
            )
        )
        assert identity is not None
        identity_id = identity.id
        identity_revision = identity.revision

    revoke_response = client_for("wp09-transfer-operator-revoke").post(
        f"/api/v1/ops/external-identities/{identity_id}/revoke",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"external-identity-revoke-{uuid.uuid4()}",
        },
        json={
            "expected_revision": identity_revision,
            "reason": "历史 Reviewer 身份已完成受控撤销",
        },
    )
    revoked = assert_ok(revoke_response)
    content_editor_id = create_role_user(Role.CONTENT_EDITOR)
    with SessionLocal.begin() as session:
        session.add(
            ExternalIdentity(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=reviewer_id,
                provider="FEISHU",
                subject=uuid.uuid4().hex + uuid.uuid4().hex,
                revision=1,
            )
        )

    reason = "账号持有人已确认，迁移到目标 Content Editor"
    transfer_key = f"external-identity-transfer-{uuid.uuid4()}"
    operator = client_for("wp09-transfer-operator")
    candidate_response = operator.get(
        "/api/v1/ops/identity-access",
        headers=OPERATOR_HEADERS,
    )
    candidates = assert_ok(candidate_response)["revoked_transfer_candidates"]
    candidate = next(
        item for item in candidates if item["identity_id"] == str(identity_id)
    )
    assert candidate["source_roles"] == ["REVIEWER"]
    assert candidate["active_session_count"] == 0
    assert raw_subject not in candidate_response.text

    transfer_response = operator.post(
        f"/api/v1/ops/external-identities/{identity_id}/transfer-revoked",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": transfer_key},
        json={
            "target_user_id": str(content_editor_id),
            "target_role": "CONTENT_EDITOR",
            "expected_revision": revoked["revision"],
            "reason": reason,
        },
    )
    transferred = assert_ok(transfer_response)
    assert transferred["status"] == "TRANSFERRED_REVOKED"
    replay = operator.post(
        f"/api/v1/ops/external-identities/{identity_id}/transfer-revoked",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": transfer_key},
        json={
            "target_user_id": str(content_editor_id),
            "target_role": "CONTENT_EDITOR",
            "expected_revision": revoked["revision"],
            "reason": reason,
        },
    )
    assert assert_ok(replay)["idempotency_replay"] is True

    with SessionLocal() as session:
        transferred_identity = session.get(ExternalIdentity, identity_id)
        assert transferred_identity is not None
        assert transferred_identity.user_id == content_editor_id
        assert transferred_identity.revoked_at is not None
        assert not session.scalars(
            select(IdentitySession).where(
                IdentitySession.external_identity_id == identity_id,
                IdentitySession.revoked_at.is_(None),
            )
        ).all()
        audit = session.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "external_identity.transferred_revoked",
                AuditEntry.resource_id == identity_id,
            )
        )
        assert audit is not None
        assert audit.details["role"] == "CONTENT_EDITOR"
        assert audit.details["status"] == "REVOKED"
        assert reason not in str(audit.details)

    access_response = operator.get(
        "/api/v1/ops/identity-access",
        headers=OPERATOR_HEADERS,
    )
    access = assert_ok(access_response)
    target = next(
        item
        for item in access["items"]
        if item["user_id"] == str(content_editor_id)
    )
    assert target["identity_status"] == "REVOKED"
    assert target["allowed_commands"] == ["create_identity_link"]
    assert raw_subject not in access_response.text

    new_link = create_link(Role.CONTENT_EDITOR, content_editor_id)
    oauth_provider.subjects["transfer-reactivation-code"] = raw_subject
    content_editor = client_for("wp09-transferred-content-editor")
    new_state = begin_oauth(
        content_editor,
        "/content",
        str(new_link["link_token"]),
    )
    completed = assert_ok(
        callback(content_editor, "transfer-reactivation-code", new_state)
    )
    assert completed["safe_entry"] == "/content"
    assert assert_ok(content_editor.get("/api/v1/session"))["safe_entry"] == "/content"
    with SessionLocal() as session:
        reactivated = session.get(ExternalIdentity, identity_id)
        assert reactivated is not None
        assert reactivated.user_id == content_editor_id
        assert reactivated.revoked_at is None
        reactivation_audit = session.scalar(
            select(AuditEntry).where(
                AuditEntry.action == "external_identity.reactivated_by_link",
                AuditEntry.resource_id == identity_id,
            )
        )
        assert reactivation_audit is not None
        assert reactivation_audit.details["role"] == "CONTENT_EDITOR"


def test_revoked_identity_transfer_fails_closed_on_sessions_and_stale_link(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    content_editor_id = create_role_user(Role.CONTENT_EDITOR)
    identity_id = uuid.uuid4()
    revoked_at = utc_now()
    with SessionLocal.begin() as session:
        identity = ExternalIdentity(
            id=identity_id,
            organization_id=ORGANIZATION_ID,
            user_id=reviewer_id,
            provider="FEISHU",
            subject=uuid.uuid4().hex + uuid.uuid4().hex,
            revision=2,
            verified_at=revoked_at,
            revoked_at=revoked_at,
        )
        session.add(identity)
        session.flush()
        session.add(
            ExternalIdentity(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=reviewer_id,
                provider="FEISHU",
                subject=uuid.uuid4().hex + uuid.uuid4().hex,
                revision=1,
            )
        )
        session.add(
            IdentitySession(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=reviewer_id,
                external_identity_id=identity_id,
                external_identity_revision=1,
                role=Role.REVIEWER,
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=revoked_at + timedelta(hours=1),
            )
        )
    blocked = client_for("wp09-transfer-active-session").post(
        f"/api/v1/ops/external-identities/{identity_id}/transfer-revoked",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"external-identity-transfer-{uuid.uuid4()}",
        },
        json={
            "target_user_id": str(content_editor_id),
            "target_role": "CONTENT_EDITOR",
            "expected_revision": 2,
            "reason": "必须拒绝仍有未撤销会话的历史身份",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "ACTIVE_SESSION_EXISTS"

    with SessionLocal.begin() as session:
        active_session = session.scalar(
            select(IdentitySession).where(
                IdentitySession.external_identity_id == identity_id,
                IdentitySession.revoked_at.is_(None),
            )
        )
        assert active_session is not None
        active_session.revoked_at = active_session.expires_at
    transferred = client_for("wp09-transfer-stale-link-operator").post(
        f"/api/v1/ops/external-identities/{identity_id}/transfer-revoked",
        headers={
            **OPERATOR_HEADERS,
            "Idempotency-Key": f"external-identity-transfer-{uuid.uuid4()}",
        },
        json={
            "target_user_id": str(content_editor_id),
            "target_role": "CONTENT_EDITOR",
            "expected_revision": 2,
            "reason": "会话已撤销，迁移后仍必须重新验证",
        },
    )
    transferred_data = assert_ok(transferred)
    stale_link = create_link(Role.CONTENT_EDITOR, content_editor_id)
    with SessionLocal.begin() as session:
        identity = session.get(ExternalIdentity, identity_id)
        link = session.get(ExternalIdentityLink, uuid.UUID(str(stale_link["id"])))
        assert identity is not None and identity.revoked_at is not None
        assert link is not None
        link.created_at = identity.revoked_at - timedelta(minutes=1)
    raw_subject = f"ou_stale_{uuid.uuid4().hex}"
    with SessionLocal.begin() as session:
        identity = session.get(ExternalIdentity, identity_id)
        assert identity is not None
        settings = get_settings()
        identity.subject = credential_hash(
            settings.identity_subject_secret,
            f"external:FEISHU:{settings.feishu_app_id}",
            raw_subject,
        )
    oauth_provider.subjects["stale-reactivation-code"] = raw_subject
    browser = client_for("wp09-stale-reactivation")
    state = begin_oauth(browser, "/content", str(stale_link["link_token"]))
    denied = callback(browser, "stale-reactivation-code", state)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "IDENTITY_REVOKED"
    with SessionLocal() as session:
        identity = session.get(ExternalIdentity, identity_id)
        assert identity is not None and identity.revoked_at is not None
        assert identity.revision == transferred_data["revision"]


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


def test_operator_identity_access_lists_safe_state_and_available_commands(
    oauth_provider: FakeFeishuOAuthClient,
):
    reviewer_id = create_role_user(Role.REVIEWER)
    operator = client_for("wp09-identity-access-operator")

    initial_response = operator.get(
        "/api/v1/ops/identity-access",
        headers=OPERATOR_HEADERS,
    )
    initial = assert_ok(initial_response)
    item = next(
        candidate
        for candidate in initial["items"]
        if candidate["user_id"] == str(reviewer_id)
    )
    assert item["identity_status"] == "UNLINKED"
    assert item["allowed_commands"] == ["create_identity_link"]
    assert "subject" not in initial_response.text
    assert "token" not in initial_response.text

    link = create_link(Role.REVIEWER, reviewer_id)
    pending_response = operator.get(
        "/api/v1/ops/identity-access",
        headers=OPERATOR_HEADERS,
    )
    pending = assert_ok(pending_response)
    item = next(
        candidate
        for candidate in pending["items"]
        if candidate["user_id"] == str(reviewer_id)
    )
    assert item["link_status"] == "PENDING"
    assert item["allowed_commands"] == ["revoke_identity_link"]
    assert str(link["link_token"]) not in pending_response.text

    raw_subject = f"ou_access_{uuid.uuid4().hex}"
    oauth_provider.subjects["identity-access-code"] = raw_subject
    reviewer = client_for("wp09-identity-access-reviewer")
    state = begin_oauth(reviewer, "/review", str(link["link_token"]))
    assert_ok(callback(reviewer, "identity-access-code", state))

    linked_response = operator.get(
        "/api/v1/ops/identity-access",
        headers=OPERATOR_HEADERS,
    )
    linked = assert_ok(linked_response)
    item = next(
        candidate
        for candidate in linked["items"]
        if candidate["user_id"] == str(reviewer_id)
    )
    assert item["identity_status"] == "LINKED"
    assert item["identity_id"]
    assert item["allowed_commands"] == ["revoke_external_identity"]
    assert raw_subject not in linked_response.text

    denied = client_for("wp09-identity-access-reviewer-denied").get(
        "/api/v1/ops/identity-access",
        headers={"X-Fixture-Role": "REVIEWER"},
    )
    assert denied.status_code == 403


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
