"""Real authenticated AI checks keep migrated learner facts and login separate.

The fixture uses the actual completion-code migration HTTP endpoint. Only the
document reader and model are simulated; OAuth/auth dependencies are untouched.
Each case belongs to the existing isolated ``exploration`` organization.
"""
import copy
from datetime import UTC, datetime, timedelta
import secrets
from time import monotonic
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import delete, select, text

from journey_api.auth import Actor
from journey_api.config import get_settings
from journey_api.db import SessionLocal, engine
from journey_api.exploration_models import ExplorationSelfCheck, ExplorationWork
from journey_api.identity import CSRF_COOKIE, SESSION_COOKIE, credential_hash
from journey_api.models import (
    AISelfCheck,
    Assignment,
    AssignmentStatus,
    AuditEntry,
    CompletionCode,
    Enrollment,
    Evaluation,
    ExternalIdentity,
    IdentitySession,
    Organization,
    OutboxEvent,
    Review,
    Role,
    RoleAssignment,
    Submission,
    User,
    UserStatus,
)
from journey_api.phone_auth_routes import encrypt_completion_code
from test_dynamic_exploration import command, exploration, post, publish, read
from test_dynamic_exploration_ai import ANSWER, ai, check, history
from test_exploration_ai_publisher_contract import (
    assert_ai_completion,
    assert_uncompleted,
)
from test_reviewer_workbench import client_for
from test_wp09_feishu_identity import assert_ok


RUBRIC = [
    dict(
        id="analysis",
        name="任务分析",
        points=100,
        description="依据课程要求核对学习成果、判断依据和实际执行步骤。",
    )
]
TEXT_ANSWER = "我已阅读本课程材料，按任务要求说明事实依据、自己的执行步骤和后续改进办法。"


@pytest.fixture
def migrated_exploration(exploration):
    """Retire a real phone record while retaining its claimed exploration task."""
    _, phone, _ = exploration
    source_id = uuid.UUID(assert_ok(phone[0].get("/api/v1/session"))["user_id"])
    task_id, _, content = publish(
        exploration, "assessment", reviewMode="ai", passScore=60, rubric=RUBRIC
    )
    original = assert_ok(command(phone, read(phone, task_id), "claim"))
    now = datetime.now(UTC)
    principal_id, identity_id, session_id, code_id = (
        uuid.uuid4() for _ in range(4)
    )
    token, csrf = uuid.uuid4().hex + uuid.uuid4().hex, uuid.uuid4().hex
    raw_code = "MJ-" + "".join(
        secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8)
    )
    with SessionLocal.begin() as session:
        source = session.get(User, source_id)
        organization_id = source.organization_id
        phone_identity = session.scalar(
            select(ExternalIdentity).where(ExternalIdentity.user_id == source_id)
        )
        # The generic exploration fixture starts with a nickname identity;
        # actual phone-to-Feishu migration accepts PHONE/PHONE_PASSWORD.
        phone_identity.provider = "PHONE_PASSWORD"
        phone_identity_id = phone_identity.id
        session.add(
            User(
                id=principal_id,
                organization_id=organization_id,
                display_name="迁入记录的飞书学员",
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=organization_id,
                user_id=principal_id,
                role=Role.LEARNER,
            )
        )
        session.add(
            ExternalIdentity(
                id=identity_id,
                organization_id=organization_id,
                user_id=principal_id,
                provider="FEISHU",
                subject="ou_migrated_" + uuid.uuid4().hex,
                revision=3,
                verified_at=now,
            )
        )
        session.flush()
        session.add(
            IdentitySession(
                id=session_id,
                organization_id=organization_id,
                user_id=principal_id,
                external_identity_id=identity_id,
                external_identity_revision=3,
                role=Role.LEARNER,
                token_hash=credential_hash(get_settings().session_secret, "session", token),
                csrf_token_hash=credential_hash(get_settings().session_secret, "csrf", csrf),
                expires_at=now + timedelta(hours=1),
            )
        )
        session.add(
            CompletionCode(
                id=code_id,
                organization_id=organization_id,
                user_id=source_id,
                code_hash=credential_hash(
                    get_settings().session_secret, "completion-code", raw_code
                ),
                code_ciphertext=encrypt_completion_code(raw_code),
                code_hint=raw_code[-4:],
                expires_at=now + timedelta(days=1),
            )
        )

    client = client_for("migrated-ai-" + principal_id.hex)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    corporate = client, csrf
    result = assert_ok(
        post(corporate, "me/completion-code/migrate", dict(code=raw_code))
    )
    assert result["status"] == "MIGRATED" and result["migrated_tasks"] == 1
    assert assert_ok(client.get("/api/v1/session"))["user_id"] == str(principal_id)
    assert phone[0].get("/api/v1/session").status_code == 401
    with SessionLocal.begin() as session:
        source = session.get(User, source_id)
        principal = session.get(User, principal_id)
        mapping = session.get(CompletionCode, code_id)
        assert source.status == UserStatus.DISABLED
        assert principal.status == UserStatus.ACTIVE
        assert mapping.user_id == source_id and mapping.migrated_to_user_id == principal_id
        assert mapping.used_at is not None
        assert session.get(ExternalIdentity, phone_identity_id).revoked_at is not None
        assert session.get(ExternalIdentity, identity_id).revoked_at is None
        # Used codes remain durable ownership mappings after their original
        # claim deadline passes. They are no longer being used as credentials.
        mapping.used_at = now - timedelta(days=2)
        mapping.expires_at = now - timedelta(days=1)
    task = read(corporate, task_id)
    assert task["assignmentId"] == original["assignmentId"]
    assert task["versionId"] == original["versionId"]
    return SimpleNamespace(
        learner=corporate,
        task=task,
        content=content,
        source_id=source_id,
        principal_id=principal_id,
        identity_id=identity_id,
        session_id=session_id,
        code_id=code_id,
        organization_id=organization_id,
    )


def assert_record_owner(case, record):
    """Immutable work belongs to the retired record, never the login principal."""
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(case.task["assignmentId"]))
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        attempt = session.get(ExplorationSelfCheck, uuid.UUID(record["id"]))
        assert enrollment.learner_id == case.source_id
        assert attempt.user_id == case.source_id
        assert attempt.organization_id == case.organization_id
        assert session.get(User, case.source_id).status == UserStatus.DISABLED
        assert session.get(User, case.principal_id).status == UserStatus.ACTIVE
        if attempt.details.get("aiSelfCheckId"):
            source = session.get(AISelfCheck, uuid.UUID(attempt.details["aiSelfCheckId"]))
            assert source.learner_id == case.source_id
            assert source.assignment_id == assignment.id


def test_migrated_feishu_document_comments_and_completes_for_retired_phone_record(
    migrated_exploration, ai
):
    case = migrated_exploration
    documents, reviewer = ai
    documents.owner = dict(
        id="ou_actual_document_owner_" + uuid.uuid4().hex,
        name="答题文档的实际所有者",
    )
    assert documents.owner["id"] not in {
        str(case.source_id), str(case.principal_id)
    }
    reviewer.score_factor = .4
    below = assert_ok(check(case.learner, case.task, ANSWER))
    record = below["record"]
    assert record["score"] == 40 and record["status"] == "COMPLETED"
    assert record["commentStatus"] == "SENT"
    assert record["commentId"] == "one-title-comment"
    assert not record["errorMessage"]
    assert_uncompleted(below["task"], record)
    assert documents.comments == [("actual-title-block", record["result"])]
    assert documents.mentions == [(documents.owner,)]
    assert documents.owner_checks == documents.revision_checks == 1
    assert_record_owner(case, record)

    documents.body += " 已按反馈补充自己的执行步骤和验证方法。"
    documents.revision = "2"
    reviewer.score_factor = .6
    passed = assert_ok(check(case.learner, below["task"], "已修改答案。\n" + ANSWER))
    assert passed["record"]["score"] == 60
    assert passed["record"]["commentStatus"] == "SENT"
    assert passed["record"]["commentId"] == record["commentId"]
    assert_ai_completion(passed["task"], passed["record"], case.content, 60)
    assert len(documents.comments) == 1 and len(documents.updates) == 1
    assert documents.updates[0][0] == record["commentId"]
    assert documents.updates[0][2] == passed["record"]["result"]
    assert documents.owner_checks == documents.revision_checks == 2
    assert len(reviewer.calls) == 2
    assert [row["score"] for row in history(case.learner, case.task)] == [60, 40]
    assert_record_owner(case, passed["record"])
    assert assert_ok(case.learner[0].get("/api/v1/session"))["user_id"] == str(
        case.principal_id
    )


def test_migrated_feishu_text_score_completes_without_document_or_human_review(
    migrated_exploration, ai
):
    case = migrated_exploration
    documents, reviewer = ai
    reviewer.score_factor = .6
    result = assert_ok(check(case.learner, case.task, TEXT_ANSWER))
    record = result["record"]
    assert record["score"] == 60 and record["inputKind"] == "text"
    assert record["commentStatus"] == "NOT_REQUIRED"
    assert not record["errorMessage"]
    assert_ai_completion(result["task"], record, case.content, 60)
    assert_record_owner(case, record)
    assert len(reviewer.calls) == 1
    assert not documents.reads and not documents.comments and not documents.updates


@pytest.mark.parametrize("session_kind", ["password", "internal"])
@pytest.mark.parametrize("document", [True, False], ids=["document", "text"])
def test_other_valid_sessions_of_migrated_principal_keep_inherited_ai_access(
    migrated_exploration, ai, session_kind, document
):
    case = migrated_exploration
    documents, reviewer = ai
    token, csrf = uuid.uuid4().hex + uuid.uuid4().hex, uuid.uuid4().hex
    identity_id = uuid.uuid4() if session_kind == "password" else None
    session_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        if identity_id:
            session.add(
                ExternalIdentity(
                    id=identity_id,
                    organization_id=case.organization_id,
                    user_id=case.principal_id,
                    provider="PHONE_PASSWORD",
                    subject="phone-password-" + uuid.uuid4().hex,
                    revision=7,
                    verified_at=datetime.now(UTC),
                )
            )
            session.flush()
        session.add(
            IdentitySession(
                id=session_id,
                organization_id=case.organization_id,
                user_id=case.principal_id,
                external_identity_id=identity_id,
                external_identity_revision=7 if identity_id else None,
                role=Role.LEARNER,
                token_hash=credential_hash(get_settings().session_secret, "session", token),
                csrf_token_hash=credential_hash(get_settings().session_secret, "csrf", csrf),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    client = client_for("migrated-other-session-" + session_id.hex)
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    learner = client, csrf
    assert assert_ok(client.get("/api/v1/session"))["user_id"] == str(case.principal_id)
    current = read(learner, case.task["id"])
    assert current["assignmentId"] == case.task["assignmentId"]
    reviewer.score_factor = .6
    documents.owner = dict(
        id="ou_actual_document_owner_" + uuid.uuid4().hex,
        name="任务文档的实际所有者",
    )
    result = assert_ok(check(learner, current, ANSWER if document else TEXT_ANSWER))
    record = result["record"]
    assert record["score"] == 60 and not record["errorMessage"]
    assert_ai_completion(result["task"], record, case.content, 60)
    assert_record_owner(case, record)
    assert len(reviewer.calls) == 1
    if document:
        assert record["commentStatus"] == "SENT"
        assert documents.comments == [("actual-title-block", record["result"])]
        assert documents.mentions == [(documents.owner,)]
        assert documents.owner_checks == documents.revision_checks == 1
    else:
        assert record["commentStatus"] == "NOT_REQUIRED"
        assert not documents.reads and not documents.comments and not documents.updates


def revoke_during_scoring(case, boundary):
    """Mutate durable permission rows after auth, while the model is running."""
    with SessionLocal.begin() as session:
        if boundary == "session_revoked":
            session.get(IdentitySession, case.session_id).revoked_at = datetime.now(UTC)
        elif boundary == "session_expired":
            session.get(IdentitySession, case.session_id).expires_at = (
                datetime.now(UTC) - timedelta(seconds=1)
            )
        elif boundary == "principal_disabled":
            session.get(User, case.principal_id).status = UserStatus.DISABLED
        elif boundary in {"principal_role_removed", "record_owner_role_removed"}:
            owner = (
                case.principal_id if boundary == "principal_role_removed"
                else case.source_id
            )
            session.execute(
                delete(RoleAssignment).where(
                    RoleAssignment.user_id == owner,
                    RoleAssignment.organization_id == case.organization_id,
                    RoleAssignment.role == Role.LEARNER,
                )
            )
        elif boundary == "mapping_unused":
            session.get(CompletionCode, case.code_id).used_at = None
        elif boundary == "mapping_removed":
            session.get(CompletionCode, case.code_id).migrated_to_user_id = None
        elif boundary == "identity_revoked":
            session.get(ExternalIdentity, case.identity_id).revoked_at = datetime.now(UTC)
        elif boundary == "identity_revision_changed":
            session.get(ExternalIdentity, case.identity_id).revision += 1
        elif boundary == "identity_user_changed":
            # Both users belong to the same organization, so this is valid FK
            # data while breaking the session's authenticated identity binding.
            session.get(ExternalIdentity, case.identity_id).user_id = case.source_id
        else:
            raise AssertionError("Unexpected permission boundary: " + boundary)


@pytest.mark.parametrize("document", [True, False], ids=["document", "text"])
@pytest.mark.parametrize(
    "boundary",
    [
        "session_revoked",
        "session_expired",
        "principal_disabled",
        "principal_role_removed",
        "record_owner_role_removed",
        "mapping_unused",
        "mapping_removed",
        "identity_revoked",
        "identity_revision_changed",
        "identity_user_changed",
    ],
)
def test_migrated_authority_revoked_during_scoring_cannot_comment_or_complete(
    migrated_exploration, ai, boundary, document
):
    case = migrated_exploration
    documents, reviewer = ai
    reviewer.score_factor = .6
    reviewer.on_review = lambda: revoke_during_scoring(case, boundary)
    result = assert_ok(
        check(case.learner, case.task, ANSWER if document else TEXT_ANSWER)
    )
    record = result["record"]
    assert record["status"] == "COMPLETED" and record["score"] == 60
    assert record["passed"] is True and record["taskCompleted"] is False
    assert record["commentStatus"] == ("FAILED" if document else "NOT_REQUIRED")
    assert record["errorMessage"], "The late permission failure must remain visible"
    assert not documents.comments and not documents.updates and not documents.mentions
    assert len(reviewer.calls) == 1
    # The revoked login may no longer access GET endpoints. Inspect the durable
    # outcome directly instead of accidentally testing with fixture auth.
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(case.task["assignmentId"]))
        attempt = session.get(ExplorationSelfCheck, uuid.UUID(record["id"]))
        work = session.scalar(
            select(ExplorationWork).where(
                ExplorationWork.assignment_id == assignment.id,
                ExplorationWork.user_id == case.source_id,
            )
        )
        assert assignment.status == AssignmentStatus.IN_PROGRESS
        assert assignment.revision == case.task["revision"]
        assert work.completed_at is None
        assert attempt.user_id == case.source_id
        assert not attempt.details.get("completion")
        for model in (Submission, Review, Evaluation):
            assert session.scalar(
                select(model.id).where(model.assignment_id == assignment.id)
            ) is None


@pytest.mark.parametrize("locked_row", ["organization", "principal"])
def test_completion_lock_contention_preserves_sent_feedback_and_replays_without_ai(
    migrated_exploration, ai, monkeypatch, locked_row
):
    """Completion retries only its transaction, never document/model side effects."""
    if engine.dialect.name != "postgresql":
        pytest.skip("This regression needs real PostgreSQL row locks.")
    from journey_api import exploration_ai_completion

    case = migrated_exploration
    documents, reviewer = ai
    reviewer.score_factor = .6
    real_complete = exploration_ai_completion.complete
    # Stage the durable boundary immediately after real HTTP grading and title
    # comment delivery. The completion service under test is fully restored
    # before either competing connection is opened.
    with monkeypatch.context() as staging:
        staging.setattr(exploration_ai_completion, "complete", lambda *args, **kwargs: None)
        result = assert_ok(check(case.learner, case.task, ANSWER))
    record = result["record"]
    assert record["score"] == 60 and record["passed"] is True
    assert record["commentStatus"] == "SENT" and record["taskCompleted"] is False
    assert result["task"]["status"] == "active"
    assert result["task"]["submissionHistory"] == []
    assert len(reviewer.calls) == len(documents.comments) == 1
    assert documents.mentions == [(documents.owner,)]
    with SessionLocal() as session:
        attempt = session.get(ExplorationSelfCheck, uuid.UUID(record["id"]))
        assignment = session.get(Assignment, attempt.assignment_id)
        work = session.scalar(
            select(ExplorationWork).where(
                ExplorationWork.assignment_id == assignment.id,
                ExplorationWork.user_id == case.source_id,
            )
        )
        assert assignment.status == AssignmentStatus.IN_PROGRESS
        assert assignment.revision == case.task["revision"]
        assert work.completed_at is None
        assert session.scalar(
            select(Submission.id).where(Submission.assignment_id == assignment.id)
        ) is None
        assert not attempt.details.get("completion")
        values = dict(
            attempt_id=attempt.id,
            expected_request_hash=attempt.details["requestHash"],
            expected_answer=attempt.answer,
            validated_result=copy.deepcopy(attempt.details["grading"]),
            request_id="completion-lock-replay-" + uuid.uuid4().hex,
            expected_assignment_revision=attempt.details["assignmentRevision"],
        )
        original_result = attempt.result
        source_id = uuid.UUID(attempt.details["aiSelfCheckId"])
    actor = Actor(
        id=case.source_id,
        organization_id=case.organization_id,
        roles=frozenset({Role.LEARNER}),
        display_name="迁入记录的飞书学员",
        session_id=case.session_id,
        entry_role=Role.LEARNER,
        external_identity_verified=True,
        inherited_learner_id=case.source_id,
    )
    target = Organization if locked_row == "organization" else User
    target_id = case.organization_id if locked_row == "organization" else case.principal_id
    with engine.connect() as blocker:
        with blocker.begin():
            assert blocker.scalar(
                select(target.id).where(target.id == target_id).with_for_update()
            ) == target_id
            with SessionLocal.begin() as contender:
                # A broken timeout implementation fails this test within four
                # seconds instead of leaving the test runner hung on our lock.
                contender.execute(text("SET LOCAL statement_timeout = '4s'"))
                previous_lock_timeout = contender.scalar(text("SHOW lock_timeout"))
                started = monotonic()
                assert real_complete(contender, actor, **values) is None
                assert monotonic() - started < 4
                # A lock timeout must roll back its savepoint without poisoning
                # the request transaction or leaking its timeout setting.
                assert contender.scalar(text("SELECT 1")) == 1
                assert contender.scalar(text("SHOW lock_timeout")) == previous_lock_timeout
        # Release the blocking connection before any HTTP/catalog reads.

    with SessionLocal() as session:
        attempt = session.get(ExplorationSelfCheck, values["attempt_id"])
        source = session.get(AISelfCheck, source_id)
        assignment = session.get(Assignment, uuid.UUID(case.task["assignmentId"]))
        assert attempt.result == original_result and attempt.status == "COMPLETED"
        assert attempt.details["grading"] == values["validated_result"]
        assert attempt.details["commentStatus"] == "SENT"
        assert not attempt.details.get("completion")
        assert source.status == "COMPLETED" and source.comment_id == record["commentId"]
        assert assignment.status == AssignmentStatus.IN_PROGRESS
        assert assignment.revision == case.task["revision"]
        assert session.scalar(
            select(Submission.id).where(Submission.assignment_id == assignment.id)
        ) is None
        assert session.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.aggregate_id == assignment.id,
                OutboxEvent.event_type == "exploration.ai_completed.v1",
            )
        ) is None
        assert session.scalar(
            select(AuditEntry.id).where(
                AuditEntry.organization_id == case.organization_id,
                AuditEntry.action == "exploration.ai_completed",
            )
        ) is None

    with SessionLocal.begin() as session:
        completed = real_complete(session, actor, **values)
        assert completed["source"] == "AI" and completed["score"] == 60
    # The exact persisted attempt can settle after the unrelated writer exits.
    # Replaying completion must not call the model or resend the title comment.
    assert len(reviewer.calls) == len(documents.comments) == 1
    assert not documents.updates and documents.mentions == [(documents.owner,)]
    current = read(case.learner, case.task["id"])
    saved_record = history(case.learner, case.task)[0]
    assert saved_record["id"] == record["id"]
    assert saved_record["result"] == original_result
    assert saved_record["commentStatus"] == "SENT"
    assert_ai_completion(current, saved_record, case.content, 60)
