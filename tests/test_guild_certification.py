"""Real HTTP + isolated PostgreSQL coverage of applications and review authority."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.guild_models import GuildCertificationRequest
from journey_api.guild_catalog import TASKS
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
from journey_api.main import app
from journey_api.models import CompletionCode, IdentitySession, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_models import MedalDefinition, MedalRedemption, ReviewAdminAccess


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def account(org, *, admin=False, user_id=None):
    user_id = user_id or uuid.uuid4()
    role = Role.REVIEWER if admin else Role.LEARNER
    token, csrf = uuid.uuid4().hex, uuid.uuid4().hex
    secret = get_settings().session_secret
    with SessionLocal.begin() as session:
        if session.get(User, user_id) is None:
            session.add(User(id=user_id, organization_id=org, display_name="隔离工会测试", status=UserStatus.ACTIVE))
            session.flush()
        if not session.scalar(select(RoleAssignment.id).where(RoleAssignment.user_id == user_id, RoleAssignment.role == role)):
            session.add(RoleAssignment(id=uuid.uuid4(), organization_id=org, user_id=user_id, role=role))
        if admin and session.get(ReviewAdminAccess, user_id) is None:
            session.add(ReviewAdminAccess(user_id=user_id, organization_id=org, access_role="admin", level="初级", domain="产品开发", granted_by=user_id))
        session.add(IdentitySession(id=uuid.uuid4(), organization_id=org, user_id=user_id, role=role,
            token_hash=credential_hash(secret, "session", token), csrf_token_hash=credential_hash(secret, "csrf", csrf),
            expires_at=datetime.now(UTC) + timedelta(hours=1)))
    client = TestClient(app, base_url="http://localhost", client=(str(user_id), 52000))
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    return dict(client=client, csrf=csrf, id=user_id, org=org)


@pytest.fixture
def users():
    org = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=org, name="隔离公会认证测试"))
    learner, staff = account(org), account(org, admin=True)
    ok(post(learner, "me/guild/join", {"guildId": "multilingual"}))
    return learner, staff


def post(user, path, payload):
    return user["client"].post("/api/v1/" + path, json=payload, headers={"X-CSRF-Token": user["csrf"]})


def snapshot(user):
    return ok(user["client"].get("/api/v1/me/guild"))


def add_badge(user, grade=1, *, style=None):
    medal_id, redemption_id = uuid.uuid4(), uuid.uuid4()
    style = style or {1: "blue", 2: "purple", 3: "gold"}[grade]
    with SessionLocal.begin() as session:
        session.add(MedalDefinition(id=medal_id, organization_id=user["org"], created_by=user["id"], revision=1,
            content=dict(name="发布原名", style=style, status="published", costs=[], stock=None)))
        session.flush()
        session.add(MedalRedemption(id=redemption_id, organization_id=user["org"], user_id=user["id"], medal_id=medal_id,
            content=dict(medalName="获得时名称", style=style, artworkLevel=grade if style not in ("unknown", "green") else None,
                         image="", artworkId="", costs=[])))
    return medal_id, redemption_id


def apply(user, level=1):
    # Existing authority scenarios now run through a genuine scoped task.
    state = snapshot(user)
    if state["joinedGuild"] != "multilingual":
        state = ok(post(user, "me/guild/join", {"guildId": "multilingual"}))
    if type(level) is int and 1 <= level <= 3 and state["requirements"][level - 1]["entryEligible"]:
        submission = next((item for item in state["submissions"] if item["guildId"] == "multilingual" and item["level"] == level), None)
        if submission is None or submission["status"] != "submitted":
            ok(post(user, "me/guild/tasks", dict(guildId="multilingual", level=level, artifact="有证据的需求、质量、验收与客户确认方案。" * 5,
                checks=TASKS[level - 1]["checks"], submit=True, expectedRevision=submission["revision"] if submission else 0)))
    state = snapshot(user)
    submission = next((item for item in state["submissions"] if item["guildId"] == "multilingual" and item["level"] == level), None)
    return post(user, "me/guild/requests", {"guildId": "multilingual", "level": level,
        "expectedRevision": submission["revision"] if submission else 1})


def review(user, request_id, decision="approved", reason=""):
    return post(user, f"review-admin/guild-requests/{request_id}/review", dict(decision=decision, reason=reason))


def test_zero_state_and_server_owned_evidence_required(users):
    learner, staff = users
    initial = snapshot(learner)
    assert initial["level"] == 0 and initial["levelName"] == "未认证" and initial["requests"] == []
    assert initial["requirements"][0]["previousMet"] and not initial["requirements"][0]["eligible"]
    assert apply(learner).status_code == 409
    add_badge(learner, style="unknown")
    assert apply(learner).status_code == 409
    assert post(learner, "me/guild/requests", {"level": 1, "evidence": [{"grade": 1}]}).status_code == 422
    for level in (0, 4, True, "1"):
        assert apply(learner, level).status_code == 422
    add_badge(learner, 1)
    assert snapshot(learner)["requirements"][0]["entryEligible"]
    assert apply(learner, 2).status_code == 409


def test_pending_review_progression_persistence_and_no_wallet_mutation(users):
    learner, staff = users
    for grade in (1, 2, 3):
        add_badge(learner, grade)
    before = ok(learner["client"].get("/api/v1/me/novice/wallet"))
    for level in (1, 2, 3):
        submitted = ok(apply(learner, level))
        item = submitted["requests"][0]
        assert item["level"] == level and item["status"] == "pending"
        assert submitted["level"] == level - 1
        assert not any(r["eligible"] for r in submitted["requirements"])
        assert {e["grade"] for e in item["evidence"]} == set(range(1, level + 1))
        listed = ok(staff["client"].get("/api/v1/review-admin/guild-requests"))
        assert listed["requests"][0]["studentId"] == str(learner["id"])
        assert listed["counts"]["pending"] == 1
        ok(review(staff, item["id"], reason="已核对真实徽章凭证"))
        refreshed = snapshot(learner)
        assert refreshed["level"] == level and refreshed["requests"][0]["reviewerName"]
        assert refreshed["requests"][0]["reviewedAt"] and refreshed["requests"][0]["reason"] == "已核对真实徽章凭证"
        assert apply(learner, level).status_code == 409
    assert snapshot(account(learner["org"], user_id=learner["id"]))["level"] == 3
    assert ok(learner["client"].get("/api/v1/me/novice/wallet")) == before


def test_return_requires_feedback_allows_resubmit_and_keeps_history(users):
    learner, staff = users
    add_badge(learner, 1)
    first = ok(apply(learner))["requests"][0]
    assert review(staff, first["id"], "returned", "  ").status_code == 422
    ok(review(staff, first["id"], "returned", "补充学习证明"))
    assert snapshot(learner)["level"] == 0
    assert snapshot(learner)["requirements"][0]["entryEligible"]
    second = ok(apply(learner))["requests"][0]
    assert second["id"] != first["id"]
    ok(review(staff, second["id"]))
    states = {item["id"]: item["status"] for item in snapshot(learner)["requests"]}
    assert states == {first["id"]: "returned", second["id"]: "approved"}


def test_concurrent_submission_and_competing_reviews(users):
    learner, staff = users
    other_staff = account(learner["org"], admin=True)
    add_badge(learner, 1)
    ok(post(learner, "me/guild/tasks", dict(guildId="multilingual", level=1, artifact="并发申请前已经提交的真实测试成果。" * 6,
        checks=TASKS[0]["checks"], submit=True, expectedRevision=0)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: ok(apply(learner))["requests"][0], range(2)))
    assert results[0]["id"] == results[1]["id"]
    request_id = results[0]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda data: review(*data), [(staff, request_id, "approved", ""), (other_staff, request_id, "returned", "需要补充")]))
    assert sorted(result.status_code for result in outcomes) == [200, 409]
    final = snapshot(learner)["requests"][0]
    ok(review(staff, request_id, final["status"], "幂等重试"))
    assert snapshot(learner)["requests"][0]["reason"] == final["reason"]
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(GuildCertificationRequest).where(GuildCertificationRequest.user_id == learner["id"])) == 1


def test_snapshot_ignores_publication_edits_and_keeps_delisted_evidence(users):
    learner, staff = users
    medal_id, _ = add_badge(learner, 1)
    with SessionLocal.begin() as session:
        medal = session.get(MedalDefinition, medal_id)
        medal.content = {**medal.content, "style": "gold", "name": "改名", "status": "unpublished"}
    submitted = ok(apply(learner))["requests"][0]
    assert submitted["evidence"][0]["name"] == "获得时名称" and submitted["evidence"][0]["grade"] == 1
    assert snapshot(learner)["requirements"][2]["counts"][-1]["count"] == 0
    ok(review(staff, submitted["id"]))


def test_review_revalidates_missing_ownership(users, monkeypatch):
    learner, staff = users
    add_badge(learner, 1)
    request_id = ok(apply(learner))["requests"][0]["id"]
    # Economy history is DB-immutable. Simulate a failed ownership re-read to
    # ensure review fails closed without weakening that database protection.
    from journey_api import guild_routes
    monkeypatch.setattr(guild_routes, "owned_evidence", lambda *_: [])
    assert review(staff, request_id).status_code == 409
    assert snapshot(learner)["level"] == 0
    ok(review(staff, request_id, "returned", "徽章凭证需要重新核对"))


def test_permissions_cross_account_cross_org_and_self_review(users):
    learner, staff = users
    add_badge(learner, 1)
    request_id = ok(apply(learner))["requests"][0]["id"]
    other = account(learner["org"])
    assert snapshot(other)["requests"] == []
    assert other["client"].get("/api/v1/review-admin/guild-requests").status_code == 403
    assert review(other, request_id).status_code == 403
    assert learner["client"].post("/api/v1/me/guild/requests", json={"level": 1}).status_code == 403
    assert staff["client"].get("/api/v1/me/guild").status_code == 401
    assert TestClient(app, base_url="http://localhost").get("/api/v1/me/guild").status_code == 401
    own_admin = account(learner["org"], admin=True, user_id=learner["id"])
    assert review(own_admin, request_id).status_code == 403
    org = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=org, name="另一隔离组织"))
    outsider = account(org, admin=True)
    assert ok(outsider["client"].get("/api/v1/review-admin/guild-requests"))["requests"] == []
    assert review(outsider, request_id).status_code == 404


def test_revoked_admin_cannot_review(users):
    learner, staff = users
    add_badge(learner, 1)
    request_id = ok(apply(learner))["requests"][0]["id"]
    with SessionLocal.begin() as session:
        session.get(ReviewAdminAccess, staff["id"]).revoked_at = datetime.now(UTC)
    assert review(staff, request_id).status_code == 401
    assert snapshot(learner)["level"] == 0


def test_staff_with_learner_roles_can_review_each_other_without_deadlock(users):
    first, _ = users
    second = account(first["org"])
    first_staff = account(first["org"], admin=True, user_id=first["id"])
    second_staff = account(second["org"], admin=True, user_id=second["id"])
    add_badge(first, 1)
    add_badge(second, 1)
    first_id = ok(apply(first))["requests"][0]["id"]
    second_id = ok(apply(second))["requests"][0]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda pair: review(*pair), [(first_staff, second_id), (second_staff, first_id)]))
    assert all(response.status_code == 200 for response in outcomes)
    assert snapshot(first)["level"] == snapshot(second)["level"] == 1


def test_legacy_green_matches_learner_grade_one(users):
    learner, _ = users
    add_badge(learner, style="green")
    assert snapshot(learner)["requirements"][0]["entryEligible"]
    assert ok(apply(learner))["requests"][0]["evidence"][0]["grade"] == 1


def test_inherited_learner_history_cannot_be_self_reviewed_from_staff_identity(users):
    learner, staff = users
    add_badge(learner, 1)
    request_id = ok(apply(learner))["requests"][0]["id"]
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        session.add(CompletionCode(id=uuid.uuid4(), organization_id=learner["org"], user_id=learner["id"],
            code_hash=uuid.uuid4().hex + uuid.uuid4().hex, code_ciphertext="isolated-test-unused-ciphertext",
            code_hint="test", expires_at=now + timedelta(hours=1), used_at=now, migrated_to_user_id=staff["id"]))
    corporate_learner = account(staff["org"], user_id=staff["id"])
    assert snapshot(corporate_learner)["requests"][0]["id"] == request_id
    assert review(staff, request_id).status_code == 403


def test_disabled_learner_cannot_receive_approval(users):
    learner, staff = users
    add_badge(learner, 1)
    request_id = ok(apply(learner))["requests"][0]["id"]
    with SessionLocal.begin() as session:
        session.get(User, learner["id"]).status = UserStatus.DISABLED
    assert review(staff, request_id).status_code == 409
    ok(review(staff, request_id, "returned", "账号已停用，请重新核对资格"))
