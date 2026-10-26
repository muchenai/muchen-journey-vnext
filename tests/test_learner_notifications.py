"""Review reminders are private, durable, and independent of opening the list."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest

from sqlalchemy import func, select

from journey_api.db import SessionLocal
from journey_api.models import LearnerNotificationRead, Review
from test_reviewer_workbench import (
    REVIEWER_HEADERS, assert_ok, client_for, create_submission,
    create_other_org_review, finalize_payload, submission_body,
)

BASE = "/api/v1/me/notifications"


def finish(flow, decision="APPROVE"):
    reviewer = client_for("notification-reviewer")
    started = assert_ok(reviewer.post(f"/api/v1/reviews/{flow['review_id']}/start",
        headers={**REVIEWER_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={"expected_revision": 1}))
    payload = finalize_payload(started["review_revision"], decision=decision,
        needs_work_key="evidence_quality" if decision == "REQUEST_REVISION" else None,
        overall_feedback="这段详细评语不应出现在通知接口。")
    headers = {**REVIEWER_HEADERS, "Idempotency-Key": str(uuid.uuid4())}
    path = f"/api/v1/reviews/{flow['review_id']}/finalize"
    assert_ok(reviewer.post(path, headers=headers, json=payload))
    # Replayed successful command must not produce a second reminder.
    assert_ok(reviewer.post(path, headers=headers, json=payload))


def read(flow, suffix="/read-all"):
    return assert_ok(flow["learner"].post(BASE + suffix,
        headers={"X-CSRF-Token": flow["csrf"]}))


def test_finalized_only_no_summary_and_get_does_not_mark_read():
    flow = create_submission("notification-basic")
    assert assert_ok(flow["learner"].get(BASE)) == {"items": [], "unreadCount": 0, "nextCursor": None}
    finish(flow)
    for _ in range(2):
        page = assert_ok(flow["learner"].get(BASE))
        assert page["unreadCount"] == 1 and len(page["items"]) == 1
        item = page["items"][0]
        assert item["id"] == str(flow["review_id"])
        assert item["assignmentId"] == flow["assignment_id"]
        assert item["decision"] == "PASS" and item["readAt"] is None
        assert item["taskTitle"] and item["reviewedAt"]
        assert set(item) == {"id", "assignmentId", "taskTitle", "decision", "reviewedAt", "readAt"}
        assert "这段详细评语" not in str(page)


def test_read_requires_csrf_is_idempotent_and_survives_another_client():
    flow = create_submission("notification-read")
    finish(flow)
    path = f"/{flow['review_id']}/read"
    assert flow["learner"].post(BASE + path).status_code == 403
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: read(flow, path), range(2)))
    other_device = client_for("same-learner-other-device")
    other_device.cookies.update(flow["learner"].cookies)
    page = assert_ok(other_device.get(BASE))
    assert page == {"items": [], "unreadCount": 0, "nextCursor": None}
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(LearnerNotificationRead)
            .where(LearnerNotificationRead.review_id == flow["review_id"])) == 1


def test_notifications_cannot_cross_learners_or_organizations():
    first, second = create_submission("notify-owner"), create_submission("notify-other")
    finish(first)
    finish(second)
    foreign_id = create_other_org_review()
    for review_id in (second["review_id"], foreign_id):
        assert first["learner"].get(BASE, params={"cursor": str(review_id)}).status_code == 404
        assert first["learner"].post(f"{BASE}/{review_id}/read",
            headers={"X-CSRF-Token": first["csrf"]}).status_code == 404
    read(first)
    assert assert_ok(first["learner"].get(BASE))["unreadCount"] == 0
    other_page = assert_ok(second["learner"].get(BASE))
    assert other_page["unreadCount"] == 1
    assert {item["id"] for item in other_page["items"]} == {str(second["review_id"])}
    assert client_for("anonymous-notification").get(BASE).status_code == 401


@pytest.mark.parametrize("mark_old_read", [True, False])
def test_new_review_after_read_all_remains_unread_and_paginates(mark_old_read):
    flow = create_submission("notify-resubmit")
    finish(flow, "REQUEST_REVISION")
    old_id = str(flow["review_id"])
    assert assert_ok(flow["learner"].get(BASE))["items"][0]["decision"] == "REVISION_REQUIRED"
    if mark_old_read:
        read(flow)
        read(flow)
        assert assert_ok(flow["learner"].get(BASE))["items"] == []
    detail = assert_ok(flow["learner"].get(f"/api/v1/me/assignments/{flow['assignment_id']}"))
    submitted = assert_ok(flow["learner"].post(f"/api/v1/me/assignments/{flow['assignment_id']}/submissions",
        headers={"X-CSRF-Token": flow["csrf"], "Idempotency-Key": str(uuid.uuid4())},
        json={"expected_revision": detail["revision"], "body": submission_body("new-version"), "attachment_ids": []}))
    with SessionLocal() as session:
        flow["review_id"] = session.scalar(select(Review.id).where(
            Review.submission_version_id == uuid.UUID(submitted["submission_version_id"])))
    finish(flow)
    first = assert_ok(flow["learner"].get(BASE, params={"limit": 1}))
    assert first["unreadCount"] == (1 if mark_old_read else 2)
    assert first["items"][0]["id"] == str(flow["review_id"])
    assert first["items"][0]["readAt"] is None
    if mark_old_read:
        assert first["nextCursor"] is None
        assert old_id not in {item["id"] for item in first["items"]}
    else:
        # A read cursor still locates the next unread page without skipping it.
        read(flow, f"/{flow['review_id']}/read")
        second = assert_ok(flow["learner"].get(BASE, params={"limit": 1, "cursor": first["nextCursor"]}))
        assert second["items"][0]["id"] == old_id
        assert second["items"][0]["readAt"] is None
        assert second["unreadCount"] == 1 and second["nextCursor"] is None
    read(flow)
    assert assert_ok(flow["learner"].get(BASE)) == {"items": [], "unreadCount": 0, "nextCursor": None}
