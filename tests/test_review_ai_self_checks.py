import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, func

from journey_api.db import SessionLocal
from journey_api.models import AISelfCheck, Assignment, Enrollment
from journey_api.review_ai_self_checks import submission_documents
from test_reviewer_workbench import create_submission, client_for, assert_ok, REVIEWER_HEADERS


def seed_check(session, flow, token, status="COMPLETED", learner_id=None, source_url=None):
    assignment = session.get(Assignment, uuid.UUID(flow["assignment_id"]))
    enrollment = session.get(Enrollment, assignment.enrollment_id)
    row = AISelfCheck(
        id=uuid.uuid4(), organization_id=assignment.organization_id,
        assignment_id=assignment.id, learner_id=learner_id or enrollment.learner_id,
        document_token=token, document_url=source_url or f"https://test.feishu.cn/docx/{token}",
        document_revision="3", status=status, attempt_id=uuid.uuid4(),
        model="test-model", rule_version="test-rule", result="此文档的 AI 评价与修改建议。",
        comment_id="test-comment" if status == "COMPLETED" else None,
        updated_at=datetime.now(UTC),
    )
    session.add(row)
    return row


def test_review_shows_only_own_submitted_documents_without_side_effects():
    tokens = [uuid.uuid4().hex for _ in range(5)]
    urls = [f"https://test.feishu.cn/docx/{t}" for t in tokens]
    flow = create_submission("ai-review-" + uuid.uuid4().hex,
                             body="\n".join(f"答题链接：{u}" for u in urls[:4]))
    other = create_submission("ai-other-" + uuid.uuid4().hex)
    with SessionLocal.begin() as session:
        shown = seed_check(session, flow, tokens[0])
        seed_check(session, other, tokens[1])  # Same organization, different assignment.
        other_assignment = session.get(Assignment, uuid.UUID(other["assignment_id"]))
        other_learner = session.get(Enrollment, other_assignment.enrollment_id).learner_id
        seed_check(session, flow, tokens[2], learner_id=other_learner)
        seed_check(session, flow, tokens[4])  # Same task, document absent from fixed submission.
        shown_id = str(shown.id)
    reviewer = client_for("ai-review-reader")
    path = f"/api/v1/reviews/{flow['review_id']}"
    with SessionLocal() as session:
        before_count = session.scalar(select(func.count()).select_from(AISelfCheck))
        before_status = session.get(Assignment, uuid.UUID(flow["assignment_id"])).status
    first = assert_ok(reviewer.get(path, headers=REVIEWER_HEADERS))
    second = assert_ok(reviewer.get(path, headers=REVIEWER_HEADERS))
    assert first == second
    checks = first["document_ai_checks"]
    assert [r["document_url"] for r in checks] == urls[:4]
    assert checks[0]["record_id"] == shown_id
    assert checks[0]["result"] == "此文档的 AI 评价与修改建议。"
    assert checks[0]["comment_id"] == "test-comment"
    assert all(r["status"] == "NOT_FOUND" and r["result"] is None for r in checks[1:])
    assert first["ai_advisory"] is None
    assert flow["learner"].get(path).status_code == 403
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(AISelfCheck)) == before_count
        assert session.get(Assignment, uuid.UUID(flow["assignment_id"])).status == before_status


@pytest.mark.parametrize("status", ["RUNNING", "SENDING", "UNCERTAIN", "FAILED", "COMPLETED"])
def test_review_uses_saved_wiki_alias_and_does_not_show_unconfirmed_feedback(status):
    token, wiki_token = uuid.uuid4().hex, uuid.uuid4().hex
    wiki_url = f"https://test.feishu.cn/wiki/{wiki_token}"
    flow = create_submission("ai-status-" + uuid.uuid4().hex,
                             body=f"[答题文档]({wiki_url}?from=review#position)")
    with SessionLocal.begin() as session:
        seed_check(session, flow, token, status=status, source_url=wiki_url)
    detail = assert_ok(client_for("ai-state-reader").get(
        f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS))
    check, = detail["document_ai_checks"]
    assert check["document_url"] == wiki_url
    assert check["status"] == status
    assert bool(check["result"]) == (status == "COMPLETED")
    assert bool(check["generated_at"]) == (status == "COMPLETED")


def test_document_matching_ignores_tracking_and_rejects_untrusted_hosts():
    url = "https://test.feishu.cn/docx/abcdefghijklmno"
    assert submission_documents(f"[答案]({url}?from=one)，另一个 {url}。 https://evil.example/docx/abcdefghijklmno") == [
        (url, ("docx", "abcdefghijklmno")),
    ]


def test_review_preserves_prior_successful_feedback_when_recheck_failed():
    token = uuid.uuid4().hex
    url = f"https://test.feishu.cn/docx/{token}"
    flow = create_submission("ai-history-" + uuid.uuid4().hex, body=f"答题链接：{url}")
    with SessionLocal.begin() as session:
        row = seed_check(session, flow, token, status="FAILED")
        row.archived_results = [{"id": str(uuid.uuid4()), "body": url, "status": "COMPLETED",
                                 "result": "修改前的建议", "generatedAt": datetime.now(UTC).isoformat(),
                                 "model": "old-model", "documentRevision": "2", "commentId": "original"}]
    detail = assert_ok(client_for("ai-history-reader").get(
        f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS))
    check, = detail["document_ai_checks"]
    assert check["status"] == "FAILED" and check["result"] is None
    assert check["history"][0]["result"] == "修改前的建议"
    assert check["history"][0]["document_revision"] == "2"
