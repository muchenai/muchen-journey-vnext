"""Atomic completion from server-validated, pinned dynamic exploration scores.

AI decisions have their own immutable provenance. They never impersonate a
human Review/Evaluation or satisfy the formal journey's human Outcome gate.
The caller performs external model/document work first and owns the commit.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from journey_api.ai_rubric_materials import prepare_ai_rubric
from journey_api.errors import ApiError
from journey_api.exploration_ai_authorization import authorize_exploration_learner
from journey_api.exploration_ai_grading import rubric_fingerprint
from journey_api.exploration_models import ExplorationSelfCheck, ExplorationWork
from journey_api.exploration_service import lock_catalog, treasure_view
from journey_api.identity import add_audit
from journey_api.models import (
    AISelfCheck, Assignment, AssignmentStatus, Enrollment, EnrollmentStatus,
    Submission, SubmissionDraft, SubmissionVersion, TaskVersion,
)
from journey_api.outcome_service import add_scoped_outbox_event
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask

_HASH = re.compile(r"[0-9a-f]{64}")
_ACTIVE = {AssignmentStatus.IN_PROGRESS, AssignmentStatus.NEEDS_REVISION}


def _number(value):
    if type(value) not in (float, int):
        raise ValueError("invalid number")
    number = Decimal(str(value))
    if not number.is_finite() or number.as_tuple().exponent < -2:
        raise ValueError("invalid score")
    return number


def _passing_result(result, content):
    """Recheck a persisted server result rather than trusting its pass flag."""
    try:
        policy = prepare_ai_rubric(content)
        if (not isinstance(result, dict) or result.get("validated") is not True
                or result.get("passed") is not True or _number(result.get("maxScore")) != 100
                or result.get("rubricHash") != rubric_fingerprint(content)
                or any(not isinstance(result.get(key), str) or not _HASH.fullmatch(result[key])
                       for key in ("rubricHash", "evidenceHash"))
                or any(not isinstance(result.get(key), str) or not result[key].strip()
                       for key in ("feedback", "model", "promptVersion"))
                or len(result["feedback"]) > 9000 or len(result["model"]) > 200
                or len(result["promptVersion"]) > 200
                or not isinstance(result.get("dimensions"), list)
                or len(result["dimensions"]) != len(policy["dimensions"])):
            return None
        configured = {item["id"]: item for item in policy["dimensions"]}
        total, seen = Decimal(0), set()
        for item in result["dimensions"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return None
            identity = item["id"]
            if identity not in configured or identity in seen:
                return None
            expected = configured[identity]
            maximum, score = _number(item.get("maxScore")), _number(item.get("score"))
            if (maximum != _number(expected["points"]) or not 0 <= score <= maximum
                    or item.get("name") != expected["name"]
                    or any(not isinstance(item.get(key), str) or not item[key].strip()
                           for key in ("evidence", "feedback"))):
                return None
            seen.add(identity)
            total += score
        if _number(result.get("score")) != total or not Decimal(str(policy["pass_score"])) <= total <= 100:
            return None
        return policy["pass_score"]
    except (ValueError, TypeError, InvalidOperation, KeyError, ApiError):
        return None


def _owned_attempt(session, actor, attempt_id):
    return session.scalar(select(ExplorationSelfCheck).where(
        ExplorationSelfCheck.id == attempt_id,
        ExplorationSelfCheck.organization_id == actor.organization_id,
        ExplorationSelfCheck.user_id == actor.id).execution_options(populate_existing=True))


def complete(session, actor, *, attempt_id, expected_request_hash, expected_answer,
             validated_result, request_id, expected_assignment_revision):
    """Retry only atomic database settlement, never model or document work."""
    original_timeout = bounded_timeout = None
    if session.get_bind().dialect.name == "postgresql":
        original_timeout, milliseconds = session.execute(text(
            "SELECT current_setting('lock_timeout'), setting::integer "
            "FROM pg_settings WHERE name = 'lock_timeout'")).one()
        bounded_timeout = f"{min(milliseconds, 250) if milliseconds > 0 else 250}ms"
    for _ in range(3):
        try:
            with session.begin_nested():
                if bounded_timeout is not None:
                    session.execute(text("SELECT set_config('lock_timeout', :value, true)"),
                        {"value": bounded_timeout})
                result = _complete(session, actor, attempt_id=attempt_id,
                    expected_request_hash=expected_request_hash, expected_answer=expected_answer,
                    validated_result=validated_result, request_id=request_id,
                    expected_assignment_revision=expected_assignment_revision)
                session.flush()
                if original_timeout is not None:
                    session.execute(text("SELECT set_config('lock_timeout', :value, true)"),
                        {"value": original_timeout})
            return result
        except DBAPIError as exc:
            # Exiting begin_nested rolled back both partial settlement and its
            # transaction-local timeout. The outer score/comment stays durable.
            state = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
            if state not in {"55P03", "40P01"}:
                raise
    return None


def _complete(session, actor, *, attempt_id, expected_request_hash, expected_answer,
              validated_result, request_id, expected_assignment_revision):
    """Return the durable completion or None; never commit or contact providers."""
    # A live permission check is repeated after external work. SHARE locks also
    # serialize ordinary account updates and role deletion until this commit.
    if not authorize_exploration_learner(session, actor):
        return None
    lock_catalog(session, actor)
    initial = _owned_attempt(session, actor, attempt_id)
    if initial is None:
        return None
    enrollment = session.scalar(select(Enrollment).join(Assignment,
        Assignment.enrollment_id == Enrollment.id).where(
        Assignment.id == initial.assignment_id, Assignment.organization_id == actor.organization_id,
        Enrollment.organization_id == actor.organization_id, Enrollment.learner_id == actor.id)
        .with_for_update(of=Enrollment).execution_options(populate_existing=True))
    if enrollment is None:
        return None
    assignment = session.scalar(select(Assignment).where(Assignment.id == initial.assignment_id,
        Assignment.enrollment_id == enrollment.id, Assignment.organization_id == actor.organization_id)
        .with_for_update().execution_options(populate_existing=True))
    if assignment is None:
        return None
    # History refreshes lock the shared document source before its projection.
    # Preserve that order, even though the actual business serialization is the
    # enrollment/assignment pair above.
    source = None
    source_id = (initial.details or {}).get("aiSelfCheckId")
    if source_id:
        try:
            source = session.scalar(select(AISelfCheck).where(AISelfCheck.id == uuid.UUID(source_id))
                .with_for_update().execution_options(populate_existing=True))
        except (ValueError, TypeError):
            return None
    row = session.scalar(select(ExplorationSelfCheck).where(ExplorationSelfCheck.id == attempt_id,
        ExplorationSelfCheck.organization_id == actor.organization_id, ExplorationSelfCheck.user_id == actor.id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None:
        return None
    details = row.details or {}
    work = session.scalar(select(ExplorationWork).where(
        ExplorationWork.assignment_id == assignment.id,
        ExplorationWork.organization_id == actor.organization_id, ExplorationWork.user_id == actor.id))
    version = session.get(TaskVersion, assignment.task_version_id)
    published = session.get(PublishedTaskContent, assignment.task_version_id)
    # SessionLocal deliberately retains objects across provider-work commits.
    # Refresh the mutable catalog profile after acquiring the publication lock.
    profile = session.scalar(select(ReviewAdminTask).where(
        ReviewAdminTask.task_definition_id == assignment.task_definition_id)
        .execution_options(populate_existing=True))
    if (work is None or version is None or published is None or profile is None
            or version.organization_id != actor.organization_id
            or version.task_definition_id != work.task_id
            or assignment.task_definition_id != work.task_id
            or row.assignment_id != assignment.id or row.task_version_id != assignment.task_version_id
            or published.organization_id != actor.organization_id or profile.organization_id != actor.organization_id
            or profile.status == "deleted" or profile.content.get("camp") != "exploration"
            or enrollment.novice_task_id != work.task_id or enrollment.journey_version_id is not None
            or assignment.journey_stage_version_id is not None):
        return None
    content = published.content
    if (content.get("camp") != "exploration" or content.get("reviewMode") != "ai"
            or (content.get("completionMode") or "assessment") != "assessment"
            or row.status != "COMPLETED" or details.get("analysisCompleted") is not True
            or details.get("requestHash") != expected_request_hash
            or not isinstance(expected_request_hash, str) or not _HASH.fullmatch(expected_request_hash)
            or row.answer != expected_answer
            or details.get("assignmentRevision") != expected_assignment_revision
            or details.get("grading") != validated_result):
        return None
    pass_score = _passing_result(validated_result, content)
    if pass_score is None:
        return None
    if details.get("inputKind") == "document":
        document = details.get("gradingDocument") or {}
        if (details.get("gradingDocumentValidated") is not True or source is None
                or source.organization_id != actor.organization_id or source.learner_id != actor.id
                or source.assignment_id != assignment.id or source.attempt_id != row.id
                or source.input_hash != validated_result["evidenceHash"]
                or source.document_revision != document.get("revision")
                or source.document_hash != document.get("sha256")
                or document.get("url") != details.get("documentUrl")
                or not isinstance(details.get("gradingAnswer"), str)
                or not 1 <= len(details["gradingAnswer"].strip()) <= 80_000):
            return None
    elif details.get("inputKind", "text") != "text" or details.get("gradingAnswer", row.answer) != row.answer:
        return None
    submission = session.scalar(select(Submission).where(Submission.assignment_id == assignment.id)
        .with_for_update().execution_options(populate_existing=True))
    # Replay checks the immutable evidence, not only a mutable projection flag.
    if assignment.status == AssignmentStatus.COMPLETED:
        completion = details.get("completion") or {}
        latest = session.scalar(select(SubmissionVersion).where(
            SubmissionVersion.submission_id == submission.id,
            SubmissionVersion.version_no == submission.current_version_no)) if submission else None
        proof = (latest.ai_use or {}).get("exploration_ai_evaluation", {}) if latest else {}
        if (latest is not None and enrollment.status == EnrollmentStatus.COMPLETED and work.completed_at
                and completion.get("submissionVersionId") == str(latest.id)):
            if proof.get("attemptId") == str(row.id) and proof.get("source") == "AI":
                return copy.deepcopy(completion)
        return None
    if (assignment.status not in _ACTIVE or enrollment.status != EnrollmentStatus.ACTIVE
            or assignment.revision != expected_assignment_revision):
        return None
    # Newer local edits/attempts must not be overwritten by a delayed old score.
    draft = session.scalar(select(SubmissionDraft).where(
        SubmissionDraft.assignment_id == assignment.id).with_for_update())
    if draft and draft.updated_at > row.created_at and draft.body.strip() != row.answer.strip():
        return None
    newer = session.scalar(select(ExplorationSelfCheck.id).where(
        ExplorationSelfCheck.assignment_id == assignment.id,
        ExplorationSelfCheck.organization_id == actor.organization_id,
        ExplorationSelfCheck.user_id == actor.id,
        ExplorationSelfCheck.created_at > row.created_at,
        ExplorationSelfCheck.answer != row.answer,
        # A concurrent document request can join this exact canonical attempt.
        # Its projection is not a separately evaluated, newer answer.
        ExplorationSelfCheck.details["canonicalRecordId"].as_string().is_distinct_from(str(row.id)),
    ).limit(1))
    if newer is not None:
        return None
    now = datetime.now(UTC)
    if submission is None:
        submission = Submission(id=uuid.uuid4(), organization_id=actor.organization_id,
            assignment_id=assignment.id, current_version_no=0)
        session.add(submission)
        session.flush()
    version_no = submission.current_version_no + 1
    proof = dict(kind="EXPLORATION_AI", source="AI", attemptId=str(row.id),
        requestHash=expected_request_hash, taskVersionId=str(row.task_version_id),
        assignmentId=str(assignment.id), originalInput=row.answer, completedAt=now.isoformat(),
        **copy.deepcopy(validated_result))
    if details.get("gradingDocument"):
        proof["document"] = copy.deepcopy(details["gradingDocument"])
    submitted = SubmissionVersion(id=uuid.uuid4(), submission_id=submission.id,
        version_no=version_no, created_by=actor.id, created_at=now,
        body=details["gradingAnswer"] if details.get("inputKind") == "document" else row.answer,
        ai_use=dict(used=True, purpose="DYNAMIC_EXPLORATION_AI_ASSESSMENT",
            model_version=validated_result["model"], prompt_version=validated_result["promptVersion"],
            output_is_advisory_only=False, exploration_ai_evaluation=proof))
    session.add(submitted)
    submission.current_version_no = version_no
    assignment.status, assignment.revision = AssignmentStatus.COMPLETED, assignment.revision + 1
    enrollment.status, enrollment.revision = EnrollmentStatus.COMPLETED, enrollment.revision + 1
    work.completed_at = now
    completion = dict(source="AI", status="COMPLETED", score=validated_result["score"], passScore=pass_score,
        completedAt=now.isoformat(), submissionId=str(submission.id), submissionVersionId=str(submitted.id),
        versionNo=version_no, attemptId=str(row.id), notificationId=str(row.id))
    row.details = {**details, "completion": completion}
    session.execute(delete(SubmissionDraft).where(SubmissionDraft.assignment_id == assignment.id))
    add_audit(session, request_id=request_id, action="exploration.ai_completed",
        resource_type="submission_version", resource_id=submitted.id, result="SUCCESS",
        organization_id=actor.organization_id, actor_id=actor.id,
        details=dict(decisionSource="AI", assignmentId=str(assignment.id), attemptId=str(row.id),
            taskVersionId=str(row.task_version_id), score=validated_result["score"], passScore=pass_score,
            rubricHash=validated_result["rubricHash"], evidenceHash=validated_result["evidenceHash"]))
    add_scoped_outbox_event(session, event_id=uuid.uuid4(), event_type="exploration.ai_completed.v1",
        aggregate_type="assignment", aggregate_id=assignment.id, organization_id=actor.organization_id,
        owner_id=actor.id, actor_id=actor.id, request_id=request_id,
        dedupe_key=f"exploration.ai_completed:{assignment.id}",
        payload=dict(assignment_id=str(assignment.id), submission_version_id=str(submitted.id),
            attempt_id=str(row.id), source="AI"), occurred_at=now)
    session.flush()
    treasure_view(session, actor)
    return copy.deepcopy(completion)
