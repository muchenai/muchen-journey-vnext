"""Dynamic AI completion uses real immutable evidence, with no human forgery."""
import copy
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.auth import Actor
from journey_api.db import SessionLocal
from journey_api.exploration_ai_completion import complete
from journey_api.exploration_ai_grading import grade_feedback
from journey_api.exploration_models import ExplorationProgress, ExplorationSelfCheck, ExplorationWork
from journey_api.learner_notification_routes import with_read_state
from journey_api.models import (
    AISelfCheck, Assignment, AssignmentStatus, AuditEntry, Enrollment, EnrollmentStatus,
    Evaluation, LearnerNotificationRead, Outcome, OutboxEvent, Review, Role,
    RoleAssignment, Submission, SubmissionDraft, SubmissionVersion, User, UserStatus,
)
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask
from test_dynamic_exploration import command, exploration, publish, read
from test_wp09_feishu_identity import assert_ok

ANSWER = "我已根据本课程的真实任务要求分析材料，并且说明了自己的具体操作方法、判断依据和后续改进计划。" * 2
RUBRIC = [
    dict(id="analysis", name="任务分析", description="说明任务要求与完整的判断依据。", points=60),
    dict(id="practice", name="实践方案", description="提出可执行方法和具体改进计划。", points=40),
]


def attempt(exploration, *, mode="ai", score=80, document=False, rubric=None):
    _, learner, _ = exploration
    rubric = rubric or RUBRIC
    task_id, _, _ = publish(exploration, "assessment", reviewMode=mode, rubric=rubric)
    task = assert_ok(command(learner, read(learner, task_id), "claim"))
    identity = uuid.uuid4()
    raw = json.dumps(dict(task_match=dict(status="matched", reason="题干和当前任务对应。"),
        summary="任务分析有依据，方案能够执行。", dimensions=[
            dict(id=rubric[0].get("id") or "dimension-1",
                score=min(score, 60), evidence="说明了判断依据", feedback="可补充详细例子"),
            dict(id=rubric[1].get("id") or "dimension-2",
                score=max(score - 60, 0), evidence="提出改进计划", feedback="继续细化执行步骤")],
        next_steps=["细化执行时间。"]), ensure_ascii=False)
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(task["assignmentId"]))
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        actor = Actor(enrollment.learner_id, enrollment.organization_id, frozenset({Role.LEARNER}), "课程学员")
        pinned = session.get(PublishedTaskContent, assignment.task_version_id)
        result = grade_feedback(raw, pinned.content)
        result.update(model="offline-model", evidenceHash=hashlib.sha256(ANSWER.encode()).hexdigest())
        request_hash = hashlib.sha256(str(identity).encode()).hexdigest()
        answer = "https://answers.feishu.cn/docx/CurrentTaskAnswer1234" if document else ANSWER
        details = dict(requestHash=request_hash, analysisCompleted=True, assignmentRevision=assignment.revision,
            grading=result, gradingAnswer=ANSWER if document else answer,
            inputKind="document" if document else "text", commentStatus="SENT" if document else "NOT_REQUIRED")
        if document:
            source_id = uuid.uuid4()
            fingerprint = hashlib.sha256(b"document-snapshot").hexdigest()
            details.update(aiSelfCheckId=str(source_id), documentUrl=answer, gradingDocumentValidated=True,
                gradingDocument=dict(url=answer, revision="7", sha256=fingerprint))
            session.add(AISelfCheck(id=source_id, organization_id=actor.organization_id,
                learner_id=actor.id, assignment_id=assignment.id, document_token=uuid.uuid4().hex,
                document_url=answer, document_revision="7", document_hash=fingerprint,
                status="COMPLETED", attempt_id=identity, model="offline-model", rule_version="test",
                input_hash=result["evidenceHash"], result=result["feedback"], error_message=""))
        row = ExplorationSelfCheck(id=identity, organization_id=actor.organization_id, user_id=actor.id,
            assignment_id=assignment.id, task_version_id=assignment.task_version_id,
            answer=answer, result=result["feedback"], status="COMPLETED", details=details)
        session.add(row)
    return dict(actor=actor, task=task, learner=learner, id=identity, hash=request_hash,
        answer=answer, result=result, revision=task["revision"])


def finish(case, **changes):
    values = dict(attempt_id=case["id"], expected_request_hash=case["hash"],
        expected_answer=case["answer"], validated_result=case["result"],
        request_id="ai-completion-test", expected_assignment_revision=case["revision"])
    values.update(changes)
    with SessionLocal.begin() as session:
        return complete(session, case["actor"], **values)


def proof_for(session, case):
    submission = session.scalar(select(Submission).where(
        Submission.assignment_id == uuid.UUID(case["task"]["assignmentId"])))
    versions = list(session.scalars(select(SubmissionVersion).where(
        SubmissionVersion.submission_id == submission.id))) if submission else []
    return submission, versions


def assert_untouched(case):
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(case["task"]["assignmentId"]))
        assert assignment.status == AssignmentStatus.IN_PROGRESS
        assert assignment.revision == case["revision"]
        assert proof_for(session, case) == (None, [])
        assert session.scalar(select(OutboxEvent.id).where(
            OutboxEvent.aggregate_id == assignment.id,
            OutboxEvent.event_type == "exploration.ai_completed.v1")) is None


def test_threshold_completes_with_immutable_ai_provenance_and_one_settlement(exploration):
    case = attempt(exploration, score=60)
    first = finish(case)
    assert first["source"] == "AI" and first["score"] == first["passScore"] == 60
    assert finish(case) == first
    current = read(case["learner"], case["task"]["id"])
    assert current["status"] == "completed" and current["answer"] == ANSWER
    assert current["submissionHistory"][0]["status"] == "COMPLETED"
    assert current["submissionHistory"][0]["source"] == "AI"
    assert current["feedback"]["source"] == "AI" and current["feedback"]["score"] == 60
    assert current["feedbackRecords"][0]["dimensions"] == case["result"]["dimensions"]
    assert all(not item["description"] for item in current["rubric"])
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(case["task"]["assignmentId"]))
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        assert assignment.status == AssignmentStatus.COMPLETED and assignment.revision == case["revision"] + 1
        assert enrollment.status == EnrollmentStatus.COMPLETED
        work = session.get(ExplorationWork, (case["actor"].organization_id, case["actor"].id,
            uuid.UUID(case["task"]["id"])))
        assert work.completed_at is not None
        submission, versions = proof_for(session, case)
        assert submission.current_version_no == len(versions) == 1
        version = versions[0]
        proof = version.ai_use["exploration_ai_evaluation"]
        assert version.body == ANSWER and version.created_by == case["actor"].id
        assert proof["source"] == "AI" and proof["attemptId"] == str(case["id"])
        assert proof["dimensions"] == case["result"]["dimensions"]
        assert proof["rubricHash"] == case["result"]["rubricHash"]
        assert version.ai_use["output_is_advisory_only"] is False
        for model in (Review, Evaluation, Outcome):
            assert session.scalar(select(func.count()).select_from(model).where(
                model.assignment_id == assignment.id)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEntry).where(
            AuditEntry.resource_id == version.id, AuditEntry.action == "exploration.ai_completed")) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.aggregate_id == assignment.id,
            OutboxEvent.event_type == "exploration.ai_completed.v1")) == 1
        progress = session.get(ExplorationProgress, (case["actor"].organization_id, case["actor"].id))
        assert len([row for row in progress.treasures["attempts"] if row["taskId"] == case["task"]["id"]]) == 1
        version_id = version.id
    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            session.execute(update(SubmissionVersion).where(
                SubmissionVersion.id == version_id).values(body="伪造修改不可变结果"))


@pytest.mark.parametrize("mutation", [
    "below", "missing_dimension", "duplicate_dimension", "negative", "over_maximum", "nan",
    "wrong_total", "wrong_rubric", "missing_evidence", "wrong_name", "not_validated", "not_passed",
    "wrong_maximum", "incomplete_model", "wrong_evidence_hash", "bool_score",
])
def test_invalid_and_partial_scores_do_not_complete(exploration, mutation):
    case = attempt(exploration, score=59 if mutation == "below" else 80)
    result = copy.deepcopy(case["result"])
    if mutation == "missing_dimension": result["dimensions"].pop()
    elif mutation == "duplicate_dimension": result["dimensions"][1] = copy.deepcopy(result["dimensions"][0])
    elif mutation == "negative": result["dimensions"][1]["score"] = -1
    elif mutation == "over_maximum": result["dimensions"][1]["score"] = 101
    elif mutation == "nan": result["score"] = float("nan")
    elif mutation == "wrong_total": result["score"] = 81
    elif mutation == "wrong_rubric": result["rubricHash"] = "0" * 64
    elif mutation == "missing_evidence": result["dimensions"][0]["evidence"] = ""
    elif mutation == "wrong_name": result["dimensions"][0]["name"] = "其他评分"
    elif mutation == "not_validated": result["validated"] = False
    elif mutation == "not_passed": result["passed"] = False
    elif mutation == "wrong_maximum": result["maxScore"] = 120
    elif mutation == "incomplete_model": result["model"] = ""
    elif mutation == "wrong_evidence_hash": result["evidenceHash"] = "not-a-hash"
    elif mutation == "bool_score": result["score"] = True
    # PostgreSQL JSON cannot store NaN. All other invalid values are persisted
    # to verify the completion boundary independently revalidates server output.
    if mutation != "nan":
        with SessionLocal.begin() as session:
            row = session.get(ExplorationSelfCheck, case["id"])
            row.details = {**row.details, "grading": result}
    case["result"] = result
    assert finish(case) is None
    assert_untouched(case)


@pytest.mark.parametrize("field,value", [
    ("expected_request_hash", "0" * 64), ("expected_answer", "不同的作答"),
    ("expected_assignment_revision", 999), ("attempt_id", uuid.UUID(int=1)),
])
def test_request_activity_and_answer_binding(exploration, field, value):
    case = attempt(exploration)
    assert finish(case, **{field: value}) is None
    assert_untouched(case)


def test_supplied_result_must_equal_persisted_server_result(exploration):
    case = attempt(exploration)
    forged = {**case["result"], "score": 100}
    assert finish(case, validated_result=forged) is None
    assert_untouched(case)


@pytest.mark.parametrize("boundary", ["manual", "disabled", "revoked", "cancelled", "revision",
    "deleted", "wrong_version", "wrong_owner", "wrong_org", "new_draft", "new_attempt"])
def test_live_assignment_and_permission_boundaries(exploration, boundary):
    case = attempt(exploration, mode="manual" if boundary == "manual" else "ai")
    with SessionLocal.begin() as session:
        actor = case["actor"]
        assignment = session.get(Assignment, uuid.UUID(case["task"]["assignmentId"]))
        if boundary == "disabled": session.get(User, actor.id).status = UserStatus.DISABLED
        elif boundary == "revoked":
            session.execute(delete(RoleAssignment).where(RoleAssignment.user_id == actor.id,
                RoleAssignment.role == Role.LEARNER))
        elif boundary == "cancelled": assignment.status = AssignmentStatus.CANCELLED
        elif boundary == "revision": assignment.revision += 1
        elif boundary == "deleted": session.get(ReviewAdminTask, uuid.UUID(case["task"]["id"])).status = "deleted"
        elif boundary == "wrong_version":
            # A different existing version remains valid FK data.
            other = session.scalar(select(PublishedTaskContent.task_version_id).where(
                PublishedTaskContent.task_version_id != assignment.task_version_id))
            session.get(ExplorationSelfCheck, case["id"]).task_version_id = other
        elif boundary == "wrong_owner":
            case["actor"] = Actor(exploration[2], actor.organization_id, frozenset({Role.LEARNER}), "其他人")
        elif boundary == "wrong_org":
            case["actor"] = Actor(actor.id, uuid.uuid4(), frozenset({Role.LEARNER}), "其他组织")
        elif boundary == "new_draft":
            session.add(SubmissionDraft(id=uuid.uuid4(), organization_id=actor.organization_id,
                assignment_id=assignment.id, owner_id=actor.id, body="新编辑的另一份答案",
                attachment_ids=[], revision=1, updated_at=datetime.now(UTC) + timedelta(seconds=1)))
        elif boundary == "new_attempt":
            original = session.get(ExplorationSelfCheck, case["id"])
            session.add(ExplorationSelfCheck(id=uuid.uuid4(), organization_id=actor.organization_id,
                user_id=actor.id, assignment_id=assignment.id, task_version_id=assignment.task_version_id,
                answer="较新的不同答案", result="", status="RUNNING", details={},
                created_at=original.created_at + timedelta(seconds=1)))
    assert finish(case) is None
    with SessionLocal() as session:
        assert proof_for(session, case) == (None, [])


@pytest.mark.parametrize("boundary", ["valid", "unverified", "superseded", "source_owner",
    "source_assignment", "source_hash", "source_revision", "changed_result", "uncertain_comment"])
def test_document_owner_revision_source_and_actual_snapshot(exploration, boundary):
    case = attempt(exploration, document=True)
    with SessionLocal.begin() as session:
        row = session.get(ExplorationSelfCheck, case["id"])
        source = session.get(AISelfCheck, uuid.UUID(row.details["aiSelfCheckId"]))
        if boundary == "unverified": row.details = {**row.details, "gradingDocumentValidated": False}
        elif boundary == "superseded": source.attempt_id = uuid.uuid4()
        elif boundary == "source_owner": source.learner_id = exploration[2]
        elif boundary == "source_assignment":
            other = session.scalar(select(Assignment.id).where(Assignment.id != source.assignment_id))
            source.assignment_id = other
        elif boundary == "source_hash": source.input_hash = "0" * 64
        elif boundary == "source_revision": source.document_revision = "8"
        elif boundary == "changed_result":
            row.details = {**row.details, "grading": {**case["result"], "score": 100}}
        elif boundary == "uncertain_comment":
            source.status = "UNCERTAIN"
            row.details = {**row.details, "commentStatus": "UNCERTAIN"}
    result = finish(case)
    if boundary in {"valid", "uncertain_comment"}:
        assert result["status"] == "COMPLETED"
        with SessionLocal() as session:
            _, versions = proof_for(session, case)
            assert versions[0].body == ANSWER
            assert versions[0].ai_use["exploration_ai_evaluation"]["originalInput"] == case["answer"]
            assert versions[0].ai_use["exploration_ai_evaluation"]["document"]["revision"] == "7"
    else:
        assert result is None
        assert_untouched(case)


@pytest.mark.parametrize("document", [False, True])
def test_simultaneous_retries_complete_exactly_once(exploration, document):
    case = attempt(exploration, document=document)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: finish(case), range(3)))
    assert results[0] == results[1] == results[2]
    with SessionLocal() as session:
        submission, versions = proof_for(session, case)
        assert len(versions) == submission.current_version_no == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.aggregate_id == uuid.UUID(case["task"]["assignmentId"]),
            OutboxEvent.event_type == "exploration.ai_completed.v1")) == 1


def test_completion_reloads_catalog_profile_after_external_work(exploration):
    case = attempt(exploration)
    with SessionLocal.begin() as session:
        stale = session.get(ReviewAdminTask, uuid.UUID(case["task"]["id"]))
        assert stale.status == "published"
        with SessionLocal.begin() as other:
            other.get(ReviewAdminTask, stale.task_definition_id).status = "deleted"
        assert complete(session, case["actor"], attempt_id=case["id"],
            expected_request_hash=case["hash"], expected_answer=case["answer"],
            validated_result=case["result"], request_id="retained-session-test",
            expected_assignment_revision=case["revision"]) is None
    with SessionLocal() as session:
        assert proof_for(session, case) == (None, [])


def test_two_passing_attempts_have_only_one_winner(exploration):
    case = attempt(exploration)
    other = copy.copy(case)
    other["id"], other["hash"] = uuid.uuid4(), hashlib.sha256(b"second-attempt").hexdigest()
    with SessionLocal.begin() as session:
        original = session.get(ExplorationSelfCheck, case["id"])
        session.add(ExplorationSelfCheck(id=other["id"], organization_id=case["actor"].organization_id,
            user_id=case["actor"].id, assignment_id=original.assignment_id, task_version_id=original.task_version_id,
            answer=original.answer, result=original.result, status="COMPLETED",
            details={**original.details, "requestHash": other["hash"]}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, [case, other]))
    assert len([result for result in results if result]) == 1
    with SessionLocal() as session:
        assert len(proof_for(session, case)[1]) == 1


def test_generic_human_submission_cannot_bypass_dynamic_ai(exploration):
    case = attempt(exploration)
    learner, task = case["learner"], case["task"]
    response = learner[0].post(f"/api/v1/me/assignments/{task['assignmentId']}/submissions",
        headers={"X-CSRF-Token": learner[1], "Idempotency-Key": str(uuid.uuid4())},
        json=dict(expected_revision=task["revision"], body=ANSWER, attachment_ids=[]))
    assert response.status_code == 409 and response.json()["error"]["code"] == "AI_ASSESSMENT_REQUIRED"
    assert_untouched(case)


def test_ai_notifications_are_scoped_durable_and_concurrently_readable(exploration):
    case = attempt(exploration)
    finish(case)
    learner = case["learner"]
    base = "/api/v1/me/notifications"
    first = assert_ok(learner[0].get(base))
    assert first["unreadCount"] == 1 and len(first["items"]) == 1
    assert first["items"][0]["id"] == str(case["id"])
    assert first["items"][0]["decision"] == "PASS" and first["items"][0]["source"] == "AI"
    assert "反馈" not in json.dumps(first, ensure_ascii=False)
    assert assert_ok(learner[0].get(base)) == first
    with SessionLocal() as session:
        for actor in [
            Actor(exploration[2], case["actor"].organization_id, frozenset({Role.LEARNER}), "其他人"),
            Actor(case["actor"].id, uuid.uuid4(), frozenset({Role.LEARNER}), "其他组织"),
        ]:
            assert session.execute(select(with_read_state(actor))).all() == []
    assert learner[0].post(f"{base}/{case['id']}/read").status_code == 403
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: learner[0].post(f"{base}/{case['id']}/read",
            headers={"X-CSRF-Token": learner[1]}), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert assert_ok(learner[0].get(base))["unreadCount"] == 0
    assert finish(case)["source"] == "AI"
    assert assert_ok(learner[0].get(base))["unreadCount"] == 0
    with SessionLocal() as session:
        row = session.get(ExplorationSelfCheck, case["id"])
        assert row.details["notificationReadAt"]
        assert session.scalar(select(LearnerNotificationRead.review_id).where(
            LearnerNotificationRead.review_id == case["id"])) is None


def test_ai_read_all_snapshot_keeps_later_results_unread(exploration):
    first = attempt(exploration)
    finish(first)
    learner, base = first["learner"], "/api/v1/me/notifications"
    assert_ok(learner[0].post(base + "/read-all", headers={"X-CSRF-Token": learner[1]}))
    second = attempt(exploration)
    finish(second)
    page = assert_ok(learner[0].get(base, params={"limit": 1, "cursor": str(first["id"])}))
    assert page["unreadCount"] == 1
    page = assert_ok(learner[0].get(base))
    assert [row["id"] for row in page["items"]] == [str(second["id"])]


@pytest.mark.parametrize("kind", ["manual", "missing_attempt", "wrong_assignment",
    "wrong_version", "wrong_owner", "unvalidated", "grade_mismatch", "low_score"])
def test_database_rejects_forged_ai_submission_proof(exploration, kind):
    case = attempt(exploration, mode="manual" if kind == "manual" else "ai",
        score=59 if kind == "low_score" else 80)
    now = datetime.now(UTC)
    result = copy.deepcopy(case["result"])
    if kind == "unvalidated": result["validated"] = False
    elif kind == "grade_mismatch": result["score"] = 100
    proof = dict(kind="EXPLORATION_AI", source="AI", attemptId=str(case["id"]),
        requestHash=case["hash"], taskVersionId=case["task"]["versionId"],
        assignmentId=case["task"]["assignmentId"], originalInput=case["answer"],
        completedAt=now.isoformat(), **result)
    if kind == "missing_attempt": proof["attemptId"] = str(uuid.uuid4())
    elif kind == "wrong_assignment": proof["assignmentId"] = str(uuid.uuid4())
    elif kind == "wrong_version": proof["taskVersionId"] = str(uuid.uuid4())
    disclosure = dict(used=True, purpose="DYNAMIC_EXPLORATION_AI_ASSESSMENT",
        model_version=result["model"], prompt_version=result["promptVersion"],
        output_is_advisory_only=False, exploration_ai_evaluation=proof)
    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            submission = Submission(id=uuid.uuid4(), organization_id=case["actor"].organization_id,
                assignment_id=uuid.UUID(case["task"]["assignmentId"]), current_version_no=1)
            session.add(submission)
            session.flush()
            session.add(SubmissionVersion(id=uuid.uuid4(), submission_id=submission.id, version_no=1,
                body=case["answer"], created_by=exploration[2] if kind == "wrong_owner" else case["actor"].id,
                ai_use=disclosure, created_at=now))


def test_database_keeps_legacy_advisory_shape_and_evaluation_gate(exploration):
    case = attempt(exploration)
    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            submission = Submission(id=uuid.uuid4(), organization_id=case["actor"].organization_id,
                assignment_id=uuid.UUID(case["task"]["assignmentId"]), current_version_no=1)
            session.add(submission)
            session.flush()
            session.add(SubmissionVersion(id=uuid.uuid4(), submission_id=submission.id, version_no=1,
                body=ANSWER, created_by=case["actor"].id,
                ai_use=dict(used=True, purpose="编写作答", model_version="offline",
                    prompt_version="v1", output_is_advisory_only=False)))
    with SessionLocal() as session:
        from sqlalchemy import text
        expression = session.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_evaluations_ai_provenance'"))
        assert "exploration_ai_evaluation" not in expression
        assert "output_is_advisory_only" in expression


@pytest.mark.parametrize("legacy", [False, True])
def test_normalized_empty_dimension_id_and_unicode_name_can_complete(exploration, monkeypatch, legacy):
    if legacy:
        # Recreate an old, still-immutable publication without a private policy
        # snapshot, without disabling any database trigger.
        from journey_api.ai_rubric_materials import canonicalize_ai_rubric

        def without_snapshot(content, **kwargs):
            result = canonicalize_ai_rubric(content, **kwargs)
            result.pop("aiRubricSnapshot", None)
            return result

        monkeypatch.setattr("journey_api.review_admin_routes.canonicalize_ai_rubric", without_snapshot)
    rubric = [{**RUBRIC[0], "id": "", "name": "\u3000\t任务分析\n\u00a0"}, RUBRIC[1]]
    case = attempt(exploration, rubric=rubric)
    assert case["result"]["dimensions"][0]["id"] == "dimension-1"
    assert case["result"]["dimensions"][0]["name"] == "任务分析"
    assert finish(case)["status"] == "COMPLETED"


@pytest.mark.parametrize("document", [False, True])
def test_generic_submission_and_assignment_workspace_project_ai_source(exploration, document):
    case = attempt(exploration, document=document)
    completed = finish(case)
    history = assert_ok(case["learner"][0].get(
        "/api/v1/me/submissions/" + completed["submissionId"]))
    version = history["versions"][0]
    assert version["decision"] == "PASS" and version["review_id"] is None
    assert version["review_status"] is None and version["review_kind"] is None
    assert version["ai_use"]["exploration_ai_evaluation"]["source"] == "AI"
    assert version["feedback"] == case["result"]["feedback"]
    assert all(item["source"] == "AI" for item in version["rubric_feedback"])
    assert version["body"] == ANSWER
    detail = assert_ok(case["learner"][0].get(
        "/api/v1/me/assignments/" + case["task"]["assignmentId"]))
    assert detail["submission"]["versions"][0]["ai_use"]["exploration_ai_evaluation"]["source"] == "AI"
    from journey_api.schemas import FinalizeReviewCommand, SubmissionCommand, SubmissionVersionOut
    assert SubmissionVersionOut.model_validate(version).ai_use.exploration_ai_evaluation.source == "AI"
    for schema, payload in [
        (SubmissionCommand, dict(expected_revision=1, body=ANSWER)),
        (FinalizeReviewCommand, dict(expected_revision=1, overall_decision="APPROVE",
            overall_feedback="这是一条有效且完整的人工审核意见。", rubric_evaluations=[])),
    ]:
        schema.model_validate(payload)
        with pytest.raises(ValidationError) as caught:
            schema.model_validate({**payload, "ai_use": version["ai_use"]})
        assert all(error["loc"][0] == "ai_use" for error in caught.value.errors())
