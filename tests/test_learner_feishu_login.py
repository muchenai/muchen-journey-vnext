import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, OPERATOR_ID, REVIEWER_ID
from journey_api.identity import utc_now, credential_hash
from journey_api.journey_service import published_formal_journey, publish_catalog_journey
from journey_api.models import Assignment, Enrollment, ExternalIdentity, RoleAssignment, User
from test_wp09_feishu_identity import oauth_provider, begin_oauth, callback, client_for, assert_ok


@pytest.fixture
def learner_provider(oauth_provider, monkeypatch):
    monkeypatch.setenv("FEISHU_LEARNER_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("FEISHU_LEARNER_ORGANIZATION_ID", str(ORGANIZATION_ID))
    monkeypatch.setenv("FEISHU_LEARNER_REVIEWER_ID", str(REVIEWER_ID))
    get_settings.cache_clear()
    with SessionLocal.begin() as session:
        if published_formal_journey(session, ORGANIZATION_ID) is None:
            publish_catalog_journey(session, operator_id=OPERATOR_ID, reviewer_id=REVIEWER_ID,
                                    organization_id=ORGANIZATION_ID, expected_current_version=0)
    yield oauth_provider
    get_settings.cache_clear()


def login(provider, label, subject):
    client = client_for(label)
    code = uuid.uuid4().hex
    provider.subjects[code] = subject
    state = begin_oauth(client, "/app")
    return client, callback(client, code, state)


def test_any_verified_subject_creates_learner_and_repeat_login_preserves_journey(learner_provider):
    subject = "ou_external_personal_" + uuid.uuid4().hex
    client, response = login(learner_provider, "new-personal-learner", subject)
    assert assert_ok(response)["safe_entry"] == "/app"
    principal = assert_ok(client.get("/api/v1/session"))
    assert principal["roles"] == ["LEARNER"]
    action = assert_ok(client.get("/api/v1/me/current-action"))
    assert len(action["journey"]["nodes"]) == 8
    assert action["journey"]["nodes"][0]["status"] == "CURRENT"
    assert all(n["status"] == "LOCKED" for n in action["journey"]["nodes"][1:])
    assert client.get("/api/v1/reviews").status_code == 403
    newer, result = login(learner_provider, "returning-personal-learner", subject)
    assert_ok(result)
    assert assert_ok(newer.get("/api/v1/session"))["user_id"] == principal["user_id"]
    assert assert_ok(newer.get("/api/v1/me/current-action"))["resource_id"] == action["resource_id"]
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Enrollment.id)).where(
            Enrollment.learner_id == uuid.UUID(principal["user_id"]))) == 1
    # The same person cannot self-register as reviewer through its separate entry.
    state = begin_oauth(newer, "/review")
    learner_provider.subjects["staff-escalation"] = subject
    assert callback(newer, "staff-escalation", state).status_code == 403


def test_concurrent_first_callbacks_create_only_one_account(learner_provider):
    subject = "ou_parallel_" + uuid.uuid4().hex
    clients = [client_for("concurrent-" + str(i)) for i in range(2)]
    states = [begin_oauth(client, "/app") for client in clients]
    codes = [uuid.uuid4().hex for _ in clients]
    for code in codes:
        learner_provider.subjects[code] = subject
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda i: callback(clients[i], codes[i], states[i]), range(2)))
    for response in responses:
        assert_ok(response)
    # Both clients remain logged in; DB identity and enrollment remain unique.
    assert all(client.get("/api/v1/session").status_code == 200 for client in clients)
    with SessionLocal() as session:
        hashed = credential_hash(get_settings().identity_subject_secret, "external:FEISHU:cli_test", subject)
        identities = list(session.scalars(select(ExternalIdentity).where(ExternalIdentity.subject == hashed)))
        assert len(identities) == 1
        assert session.scalar(select(func.count(Enrollment.id)).where(Enrollment.learner_id == identities[0].user_id)) == 1


def test_revoked_learner_cannot_reregister(learner_provider):
    subject = "ou_revoked_learner_" + uuid.uuid4().hex
    client, result = login(learner_provider, "revoke-new", subject)
    assert_ok(result)
    user_id = uuid.UUID(assert_ok(client.get("/api/v1/session"))["user_id"])
    with SessionLocal.begin() as session:
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == user_id))
        identity.revoked_at = utc_now()
    _, denied = login(learner_provider, "revoked-return", subject)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "IDENTITY_REVOKED"


def test_missing_reviewer_rolls_back_new_account(learner_provider, monkeypatch):
    monkeypatch.setenv("FEISHU_LEARNER_REVIEWER_ID", str(uuid.uuid4()))
    get_settings.cache_clear()
    with SessionLocal() as session:
        before = session.scalar(select(func.count(User.id)))
    _, denied = login(learner_provider, "missing-reviewer", "ou_missing_" + uuid.uuid4().hex)
    assert denied.status_code == 503
    with SessionLocal() as session:
        assert session.scalar(select(func.count(User.id))) == before


def test_invalid_provider_and_replayed_state_never_register(learner_provider):
    client = client_for("invalid-learner-code")
    state = begin_oauth(client, "/app")
    assert callback(client, "invalid-code", state).status_code == 502
    assert callback(client, "invalid-code", state).status_code == 409
