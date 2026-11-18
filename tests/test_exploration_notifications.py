"""New exploration keeps canonical review reminders and stable assignment links."""
import uuid

from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.models import Review
from test_dynamic_exploration import exploration, publish, read, command, post
from test_novice_tasks import setup as novice_setup, claim as claim_novice
from test_reviewer_workbench import assert_ok, client_for, create_submission, create_other_org_review

BASE = "/api/v1/me/notifications"


def destination(client, assignment_id):
    return client.get(f"/api/v1/me/assignments/{assignment_id}/destination")


def test_new_exploration_review_notifications_and_read_receipts(exploration):
    staff, learner, _ = exploration
    task_id, _, _ = publish(exploration, "assessment")
    task = assert_ok(command(learner, read(learner, task_id), "claim"))
    assignment_id = task["assignmentId"]
    assert assert_ok(destination(learner[0], assignment_id)) == {"module": "exploration", "taskId": task_id}
    assert assert_ok(learner[0].get(BASE))["unreadCount"] == 0
    first_review_id = None
    for decision in ("REQUEST_REVISION", "APPROVE"):
        task = assert_ok(command(learner, task, "submit", answer="完成本课程的任务，整理了具体结果与需要改进的依据。"))
        assert task["status"] == "pending"
        assert assert_ok(learner[0].get(BASE))["unreadCount"] == 0, "a submission is not a review-result notification"
        with SessionLocal() as session:
            review_id = session.scalar(select(Review.id)
                .where(Review.assignment_id == uuid.UUID(assignment_id))
                .order_by(Review.assigned_at.desc()).limit(1))
        detail = assert_ok(staff[0].get(f"/api/v1/review-admin/reviews/{review_id}"))
        lease = assert_ok(post(staff, f"review-admin/reviews/{review_id}/claim",
            dict(action="acquire", expected_revision=detail["revision"])))
        body = dict(expected_revision=lease["revision"], claim_token=lease["token"], decision=decision,
            feedback="通知里不应泄露这段审核正文，只有本人打开任务才能查看。",
            reasons=["依据或论证不足"] if decision == "REQUEST_REVISION" else [])
        key = str(uuid.uuid4())
        for _ in range(2):
            assert_ok(post(staff, f"review-admin/reviews/{review_id}/decision", body, key))
        page = assert_ok(learner[0].get(BASE))
        assert page["unreadCount"] == 1 and len(page["items"]) == 1
        item = page["items"][0]
        assert item["id"] == str(review_id) and item["assignmentId"] == assignment_id
        assert item["decision"] == ("REVISION_REQUIRED" if decision == "REQUEST_REVISION" else "PASS")
        assert item["readAt"] is None
        assert "不应泄露" not in str(page)
        assert assert_ok(learner[0].get(BASE)) == page, "opening the bell must not consume the reminder"
        if first_review_id is None:
            first_review_id = str(review_id)
            assert_ok(learner[0].post(f"{BASE}/{review_id}/read", headers={"X-CSRF-Token": learner[1]}))
        else:
            assert str(review_id) != first_review_id
            assert_ok(learner[0].post(BASE + "/read-all", headers={"X-CSRF-Token": learner[1]}))
        other_device = client_for("exploration-notifications-second-device-" + str(uuid.uuid4()))
        other_device.cookies.update(learner[0].cookies)
        assert assert_ok(other_device.get(BASE)) == {"items": [], "unreadCount": 0, "nextCursor": None}
        task = read(learner, task_id)
        assert task["feedback"]["text"] == body["feedback"]
        assert assert_ok(destination(other_device, assignment_id)) == {"module": "exploration", "taskId": task_id}


def test_assignment_destinations_keep_legacy_and_reject_other_owners_and_orgs(exploration):
    _, learner, _ = exploration
    task_id, _, _ = publish(exploration, "assessment")
    task = assert_ok(command(learner, read(learner, task_id), "claim"))
    other_org = create_submission("notification-destination-other-org-" + uuid.uuid4().hex)
    assert destination(other_org["learner"], task["assignmentId"]).status_code == 404
    assert destination(learner[0], other_org["assignment_id"]).status_code == 404
    assert assert_ok(destination(other_org["learner"], other_org["assignment_id"])) == {"module": "legacy", "taskId": None}
    same_org_other = create_submission("notification-destination-other-owner-" + uuid.uuid4().hex)
    assert destination(other_org["learner"], same_org_other["assignment_id"]).status_code == 404
    foreign_review = create_other_org_review()
    with SessionLocal() as session:
        foreign_assignment = session.get(Review, foreign_review).assignment_id
    assert destination(other_org["learner"], foreign_assignment).status_code == 404
    assert destination(other_org["learner"], uuid.uuid4()).status_code == 404
    assert client_for("notification-destination-anonymous").get(
        f"/api/v1/me/assignments/{task['assignmentId']}/destination").status_code == 401


def test_novice_assignment_destinations_are_not_mistaken_for_exploration(novice_setup):
    _, learner, task_id, published, _ = novice_setup
    task = claim_novice(learner, task_id, published["versionId"])
    assert assert_ok(destination(learner[0], task["assignmentId"])) == {"module": "village", "taskId": task_id}
    other = create_submission("notification-novice-destination-other-" + uuid.uuid4().hex)
    assert destination(other["learner"], task["assignmentId"]).status_code == 404
