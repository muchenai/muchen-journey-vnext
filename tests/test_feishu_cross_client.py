import uuid

from sqlalchemy import func, select

from journey_api.db import SessionLocal
from journey_api.config import get_settings
from journey_api.identity import OAUTH_COOKIE, SESSION_COOKIE, utc_now
from journey_api.models import Enrollment, ExternalIdentity, Review
from test_learner_feishu_login import learner_provider, login
from test_wp09_feishu_identity import oauth_provider, assert_ok, begin_oauth, callback, client_for
from test_reviewer_workbench import client_for_linked_reviewer, create_linked_reviewer
from test_shared_learner_reviews import approval, review_command


def client_callback(client, code, state, browser_token=None):
    token = browser_token or client.cookies.get(OAUTH_COOKIE)
    # TestClient's direct API call needs the scoped BFF cookie forwarded.
    cookie = f"{OAUTH_COOKIE}={token}"
    if client.cookies.get(SESSION_COOKIE):
        cookie += f"; {SESSION_COOKIE}={client.cookies.get(SESSION_COOKIE)}"
    return client.post("/api/v1/auth/feishu/callback", headers={"Cookie": cookie},
        json={"code": code, "state": state, "authorization_method": "client"})


def test_two_clients_share_submissions_and_feedback_without_logging_each_other_out(learner_provider, monkeypatch):
    reviewer_id = create_linked_reviewer("Cross-client feedback reviewer")
    monkeypatch.setenv("FEISHU_LEARNER_REVIEWER_ID", str(reviewer_id))
    get_settings.cache_clear()
    subject = "ou_cross_client_" + uuid.uuid4().hex
    browser, logged_in = login(learner_provider, "cross-browser", subject)
    csrf = assert_ok(logged_in)["csrf_token"]
    user_id = assert_ok(browser.get("/api/v1/session"))["user_id"]
    native = client_for("cross-feishu")
    state = begin_oauth(native, "/app")
    learner_provider.subjects["native-code"] = subject
    assert_ok(client_callback(native, "native-code", state))
    assert assert_ok(native.get("/api/v1/session"))["user_id"] == user_id
    assert browser.get("/api/v1/session").status_code == 200
    action = assert_ok(browser.get("/api/v1/me/current-action"))
    path = "/api/v1/me/assignments/" + action["resource_id"]

    def command(url, body):
        return assert_ok(browser.post(url, json=body,
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}))

    detail = assert_ok(browser.get(path))
    for material in detail["learning_materials"]:
        if material["required"]:
            command(path + "/materials/" + material["key"] + "/complete", {"task_version": detail["task_version"]})
    detail = assert_ok(browser.get(path))
    started = command(path + "/start", {"expected_revision": detail["revision"]})
    body = "跨端学习记录：在浏览器整理学习材料，在飞书客户端回看相同的提交内容和任务进度。" * 4
    submitted = command(path + "/submissions", {"expected_revision": started["revision"], "body": body, "attachment_ids": []})
    browser_detail = assert_ok(browser.get(path))
    native_detail = assert_ok(native.get(path))
    assert native_detail == browser_detail
    assert body in str(native_detail)
    assert assert_ok(browser.get("/api/v1/me/current-action")) == assert_ok(native.get("/api/v1/me/current-action"))
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Enrollment.id)).where(Enrollment.learner_id == uuid.UUID(user_id))) == 1
        assert session.scalar(select(func.count(ExternalIdentity.id)).where(ExternalIdentity.user_id == uuid.UUID(user_id))) == 1
        review_id = session.scalar(select(Review.id).where(Review.submission_version_id == uuid.UUID(submitted["submission_version_id"])))
        assert review_id

    reviewer, reviewer_csrf = client_for_linked_reviewer(reviewer_id)
    review_detail = assert_ok(reviewer.get(f"/api/v1/reviews/{review_id}"))
    review_started = assert_ok(review_command(reviewer, reviewer_csrf, review_id, "start", {"expected_revision": review_detail["revision"]}))
    feedback = approval(review_detail, review_started["review_revision"])
    assert_ok(review_command(reviewer, reviewer_csrf, review_id, "finalize", feedback))
    reviewed = assert_ok(browser.get(path))
    assert reviewed == assert_ok(native.get(path))
    assert feedback["overall_feedback"] in str(reviewed)

    # Re-login in the same client rotates its old cookie, preserving the other.
    old_token = native.cookies.get(SESSION_COOKIE)
    state = begin_oauth(native, "/app")
    learner_provider.subjects["native-again"] = subject
    assert_ok(client_callback(native, "native-again", state))
    stale = client_for("stale-native")
    assert stale.get("/api/v1/session", headers={"Cookie": f"{SESSION_COOKIE}={old_token}"}).status_code == 401
    assert browser.get("/api/v1/session").status_code == 200
    assert native.get("/api/v1/session").status_code == 200

    # Revoking an identity continues to invalidate all devices.
    with SessionLocal.begin() as session:
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == uuid.UUID(user_id)))
        identity.revoked_at = utc_now()
    assert browser.get("/api/v1/session").status_code == 401
    assert native.get("/api/v1/session").status_code == 401


def test_client_callback_requires_bound_state_and_rejects_staff_entry(learner_provider):
    owner = client_for("client-state-owner")
    state = begin_oauth(owner, "/app")
    learner_provider.subjects["bound-code"] = "ou_bound_" + uuid.uuid4().hex
    stranger = client_for("client-state-stranger")
    begin_oauth(stranger, "/app")
    assert client_callback(stranger, "bound-code", state).status_code == 401
    token = owner.cookies.get(OAUTH_COOKIE)
    assert_ok(client_callback(owner, "bound-code", state))
    assert client_callback(owner, "bound-code", state, token).status_code == 409
    staff_state = begin_oauth(owner, "/review")
    assert client_callback(owner, "bound-code", staff_state).status_code == 422
