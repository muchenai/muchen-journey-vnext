"""Publisher rubric versions and decimal pass lines drive real HTTP completion."""
import base64
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.exploration_ai_grading import rubric_fingerprint
from journey_api.exploration_models import ExplorationSelfCheck, ExplorationWork
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Evaluation,
    ExternalIdentity,
    IdentitySession,
    Review,
    Role,
    RoleAssignment,
    Submission,
    SubmissionVersion,
    User,
)
from journey_api.review_admin_models import PublishedTaskContent
from test_dynamic_exploration import command, exploration, publish, read
from test_dynamic_exploration_ai import ai, check, history
from test_exploration_sequence import republish
from test_reviewer_workbench import client_for
from test_wp09_feishu_identity import assert_ok


def additional_learner(exploration):
    """A second authenticated learner in the fixture's isolated organization."""
    learner_id = uuid.uuid4()
    token, csrf = uuid.uuid4().hex + uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
    with SessionLocal.begin() as session:
        organization_id = session.get(User, exploration[2]).organization_id
        session.add(User(id=learner_id, organization_id=organization_id, display_name="新版课程学员"))
        session.flush()
        session.add(RoleAssignment(id=uuid.uuid4(), organization_id=organization_id,
            user_id=learner_id, role=Role.LEARNER))
        identity = ExternalIdentity(id=uuid.uuid4(), organization_id=organization_id,
            user_id=learner_id, provider="NICKNAME_PHONE", subject=uuid.uuid4().hex,
            revision=1, verified_at=datetime.now(UTC))
        session.add(identity)
        session.flush()
        session.add(IdentitySession(id=uuid.uuid4(), organization_id=organization_id,
            user_id=learner_id, external_identity_id=identity.id, external_identity_revision=1,
            role=Role.LEARNER,
            token_hash=credential_hash(get_settings().session_secret, "session", token),
            csrf_token_hash=credential_hash(get_settings().session_secret, "csrf", csrf),
            expires_at=datetime.now(UTC) + timedelta(hours=1)))
    client = client_for("publisher-contract-" + learner_id.hex)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    return client, csrf


def scoring_document(version, standard):
    body = standard.encode("utf-8")
    return dict(id="standard-" + version, name="发布人评分答案-" + version + ".txt",
        type="file", mime="text/plain", size=len(body),
        url="data:text/plain;base64," + base64.b64encode(body).decode())


def assert_uncompleted(task, record):
    assert record["passed"] is False and record["taskCompleted"] is False
    assert task["status"] == "active" and task["submissionHistory"] == []
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(task["assignmentId"]))
        assert assignment.status == AssignmentStatus.IN_PROGRESS
        assert session.scalar(select(Submission.id).where(
            Submission.assignment_id == assignment.id)) is None
        work = session.scalar(select(ExplorationWork).where(
            ExplorationWork.assignment_id == assignment.id))
        assert work is not None and work.completed_at is None


def assert_ai_completion(task, record, expected_policy, pass_score):
    assert record["passed"] is True and record["taskCompleted"] is True
    assert task["status"] == "completed" and task["feedback"]["source"] == "AI"
    assert task["feedback"]["score"] == float(pass_score)
    assert [item["source"] for item in task["submissionHistory"]] == ["AI"]
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(task["assignmentId"]))
        assert assignment.status == AssignmentStatus.COMPLETED
        assert str(assignment.task_version_id) == task["versionId"]
        submission = session.scalar(select(Submission).where(
            Submission.assignment_id == assignment.id))
        assert submission is not None and submission.current_version_no == 1
        versions = list(session.scalars(select(SubmissionVersion).where(
            SubmissionVersion.submission_id == submission.id)))
        assert len(versions) == 1
        proof = versions[0].ai_use["exploration_ai_evaluation"]
        assert proof["source"] == "AI" and proof["taskVersionId"] == task["versionId"]
        assert proof["score"] == float(pass_score)
        assert proof["rubricHash"] == rubric_fingerprint(expected_policy)
        assert [row["id"] for row in proof["dimensions"]] == [
            row["id"] for row in expected_policy["rubric"]]
        attempt = session.get(ExplorationSelfCheck, uuid.UUID(record["id"]))
        assert attempt.details["completion"]["passScore"] == float(pass_score)
        for model in (Review, Evaluation):
            assert session.scalar(select(model.id).where(
                model.assignment_id == assignment.id)) is None


@pytest.mark.parametrize(
    "old_pass,new_pass",
    [
        pytest.param(Decimal("79.99"), Decimal("80"), id="v2-raises-pass-line"),
        pytest.param(Decimal("80"), Decimal("79.99"), id="v2-lowers-pass-line"),
    ],
)
def test_claimed_version_keeps_publisher_standards_and_exact_decimal_pass_line(
    exploration, ai, old_pass, new_pass
):
    _, reviewer = ai
    _, original_learner, _ = exploration
    old_standard = "旧版评分标准：列举两项指定福利，并逐项说明申请条件。"
    new_standard = "新版评分标准：分析质检异常原因，并给出复检及人员调整方案。"
    old_rubric = [dict(id="benefits-v1", name="福利理解", points=100,
        description=old_standard)]
    new_rubric = [dict(id="quality-v2", name="质量方案", points=100,
        description=new_standard)]
    task_id, first_live, first_content = publish(exploration, "assessment",
        reviewMode="ai", passScore=float(old_pass), rubric=old_rubric,
        rubricAttachments=[scoring_document("v1", old_standard)])
    first_task = assert_ok(command(original_learner, read(original_learner, task_id), "claim"))
    assert first_task["versionId"] == first_live["versionId"]
    original_assignment_id = first_task["assignmentId"]

    # Publish through the real administrator endpoint after v1 was claimed.
    second_live, second_content = republish(exploration, task_id, first_live, first_content,
        title="新版质量实践课程", passScore=float(new_pass), rubric=new_rubric,
        rubricAttachments=[scoring_document("v2", new_standard)])
    assert second_live["versionId"] != first_live["versionId"]
    first_task = read(original_learner, task_id)
    assert first_task["versionId"] == first_live["versionId"]
    assert first_task["assignmentId"] == original_assignment_id
    assert first_task["passScore"] == float(old_pass)
    assert [row["id"] for row in first_task["rubric"]] == ["benefits-v1"]

    newcomer = additional_learner(exploration)
    available = read(newcomer, task_id)
    assert available["claimed"] is False and available["versionId"] == second_live["versionId"]
    second_task = assert_ok(command(newcomer, available, "claim"))
    assert second_task["assignmentId"] != original_assignment_id
    assert second_task["passScore"] == float(new_pass)
    assert [row["id"] for row in second_task["rubric"]] == ["quality-v2"]

    # Both directions matter: a newer stricter line cannot fail old passing
    # work, and a newer looser line cannot pass old work below its fixed line.
    cases = [
        (original_learner, first_task, first_content, old_pass, old_standard),
        (newcomer, second_task, second_content, new_pass, new_standard),
    ]
    for learner, task, content, pass_score, standard in cases:
        below = pass_score - Decimal("0.01")
        reviewer.score_factor = float(below / Decimal(100))
        result = assert_ok(check(learner, task,
            "我已分析任务材料，整理对应的事实依据、具体执行步骤以及复核方法。"))
        record = result["record"]
        assert record["status"] == "COMPLETED" and record["score"] == float(below)
        assert record["taskVersionId"] == task["versionId"]
        assert_uncompleted(result["task"], record)

        reviewer.score_factor = float(pass_score / Decimal(100))
        passed = assert_ok(check(learner, result["task"],
            "我已补充全部要求的实践细节，并逐项核对执行步骤、责任人和最终验收方法。"))
        assert passed["record"]["score"] == float(pass_score)
        assert_ai_completion(passed["task"], passed["record"], content, pass_score)
        assert [entry["score"] for entry in history(learner, task)] == [
            float(pass_score), float(below)]

        # These are the actual model inputs, including private descriptions
        # and server-parsed scoring files, rather than just public card labels.
        for evidence in reviewer.calls[-2:]:
            policy = evidence["grading_policy"]
            assert policy["dimensions"] == content["rubric"]
            assert policy["pass_score"] == float(pass_score)
            assert [document["body"] for document in policy["reference_documents"]] == [standard]

    assert len(reviewer.calls) == 4
    with SessionLocal() as session:
        for live, content, pass_score in [
            (first_live, first_content, old_pass), (second_live, second_content, new_pass)
        ]:
            pinned = session.get(PublishedTaskContent, uuid.UUID(live["versionId"]))
            assert pinned.content["rubric"] == content["rubric"]
            assert pinned.content["passScore"] == float(pass_score)
