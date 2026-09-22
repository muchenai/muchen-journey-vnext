import time
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from journey_api import learner_write_limits as limits
from journey_api.auth import Actor
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.config import get_settings
from journey_api.identity import credential_hash
from journey_api.models import AuthRateLimit, IdempotencyRecord, Role, Submission, SubmissionDraft, SubmissionVersion
from test_submission_attachments import assert_ok, client_for, new_attachment_learner

pytestmark = pytest.mark.write_rate_limits


@pytest.fixture
def clock(monkeypatch):
    value = [datetime(2030, 1, 1, tzinfo=UTC)]
    monkeypatch.setattr(limits, "database_now", lambda _session: value[0])
    return value


def actor():
    return Actor(uuid.uuid4(), uuid.uuid4(), frozenset({Role.LEARNER}), "synthetic")


def check(subject, kind="draft"):
    try:
        limits.enforce_learner_write_limit(subject, kind)
        return 200
    except ApiError as exc:
        return exc.status_code


def process_check(identity):
    actor_id, organization_id = identity
    limits.database_now = lambda _session: datetime(2030, 2, 1, tzinfo=UTC)
    return check(Actor(actor_id, organization_id, frozenset({Role.LEARNER}), "separate process"))


def test_independent_processes_share_database_counter():
    identity = (uuid.uuid4(), uuid.uuid4())
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as workers:
        statuses = list(workers.map(process_check, [identity] * 50))
    assert statuses.count(200) == 20
    assert statuses.count(429) == 30


def test_atomic_shared_counter_and_independent_user_org_scopes(clock):
    subject = actor()
    with ThreadPoolExecutor(max_workers=20) as workers:
        statuses = list(workers.map(lambda _: check(subject), range(50)))
    assert statuses.count(200) == 20
    assert statuses.count(429) == 30
    subject_hash = credential_hash(get_settings().session_secret, "learner-write-limit", f"{subject.organization_id}:{subject.id}")
    with SessionLocal() as session:
        buckets = session.scalars(select(AuthRateLimit).where(AuthRateLimit.subject_hash == subject_hash)).all()
        assert len(buckets) == 2
        assert sorted(bucket.attempts for bucket in buckets) == [21, 50]
    assert check(actor()) == 200
    assert check(Actor(subject.id, uuid.uuid4(), subject.roles, "other org")) == 200
    assert check(subject, "submit") == 200
    clock[0] += timedelta(seconds=10)
    assert check(subject) == 200


def test_minute_limit_retry_after_cleanup_and_normal_autosave(clock):
    subject = actor()
    for batch in range(4):
        clock[0] = clock[0].replace(second=batch * 10)
        assert [check(subject) for _ in range(20)] == [200] * 20
    clock[0] = clock[0].replace(second=40)
    assert [check(subject) for _ in range(10)] == [200] * 10
    with pytest.raises(ApiError) as error:
        limits.enforce_learner_write_limit(subject, "draft")
    assert error.value.details["retry_after_seconds"] == 20
    clock[0] += timedelta(minutes=11)
    assert check(subject) == 200
    subject_hash = credential_hash(get_settings().session_secret, "learner-write-limit", f"{subject.organization_id}:{subject.id}")
    with SessionLocal() as session:
        buckets = session.scalars(select(AuthRateLimit).where(AuthRateLimit.subject_hash == subject_hash)).all()
        assert len(buckets) == 2
        assert all(bucket.attempts == 1 for bucket in buckets)
    normal = actor()
    for _ in range(100):
        assert check(normal) == 200
        clock[0] += timedelta(seconds=1.2)


def test_storage_failure_fails_closed(monkeypatch):
    def fail():
        raise OperationalError("counter unavailable", None, None)
    monkeypatch.setattr(limits.CounterSession, "begin", fail)
    with pytest.raises(ApiError) as error:
        limits.enforce_learner_write_limit(actor(), "draft")
    assert error.value.status_code == 503
    assert error.value.retryable


def test_fifty_draft_requests_only_write_accepted_commands(clock):
    learner, csrf, assignment, started = new_attachment_learner(f"limit-{uuid.uuid4()}")
    payload = {"expected_revision": started["revision"], "body": "短文本"}
    before = time.monotonic()
    replies = [learner.put(
        f"/api/v1/me/assignments/{assignment}/draft", json=payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"limit-save-{uuid.uuid4()}"},
    ) for _ in range(50)]
    assert time.monotonic() - before < 10
    assert [r.status_code for r in replies] == [200] * 20 + [429] * 30
    assert replies[-1].headers["Retry-After"] == "10"
    other_connection = client_for(f"another-browser-{uuid.uuid4()}")
    other_connection.cookies.update(learner.cookies)
    # Another connection and another assignment URL cannot reset actor scope.
    changed_task = other_connection.put(
        f"/api/v1/me/assignments/{uuid.uuid4()}/draft", json=payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert changed_task.status_code == 429
    with SessionLocal() as session:
        draft = session.scalar(select(SubmissionDraft).where(SubmissionDraft.assignment_id == uuid.UUID(assignment)))
        assert draft.revision == 20
        assert session.scalar(select(func.count()).select_from(Submission).where(Submission.assignment_id == uuid.UUID(assignment))) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == draft.owner_id,
            IdempotencyRecord.command == "submission.draft.save",
        )) == 20
    # Draft cooldown does not consume the independent submit allowance.
    submitted = assert_ok(learner.post(
        f"/api/v1/me/assignments/{assignment}/submissions",
        json={**payload, "body": "有效内容" * 20},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"limit-submit-{uuid.uuid4()}"},
    ))
    assert submitted["version_no"] == 1


def test_submit_replay_is_limited_then_recovers_without_new_version(clock):
    learner, csrf, assignment, started = new_attachment_learner(f"replay-{uuid.uuid4()}")
    path = f"/api/v1/me/assignments/{assignment}/submissions"
    payload = {"expected_revision": started["revision"], "body": "有效内容" * 20}
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": f"limited-replay-{uuid.uuid4()}"}
    first = assert_ok(learner.post(path, json=payload, headers=headers))
    for _ in range(4):
        assert assert_ok(learner.post(path, json=payload, headers=headers))["submission_version_id"] == first["submission_version_id"]
    limited = learner.post(path, json=payload, headers=headers)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "10"
    clock[0] += timedelta(seconds=10)
    assert assert_ok(learner.post(path, json=payload, headers=headers))["submission_version_id"] == first["submission_version_id"]
    stale = learner.post(path, json=payload, headers={**headers, "Idempotency-Key": f"new-{uuid.uuid4()}"})
    assert stale.status_code == 409
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(SubmissionVersion).where(
            SubmissionVersion.submission_id == uuid.UUID(first["submission_id"]),
        )) == 1


def test_submit_minute_limit_and_fixed_window_boundary(clock):
    subject = actor()
    for second in (0, 10, 20, 30):
        clock[0] = clock[0].replace(second=second)
        assert [check(subject, "submit") for _ in range(5)] == [200] * 5
    clock[0] = clock[0].replace(second=40)
    with pytest.raises(ApiError) as error:
        limits.enforce_learner_write_limit(subject, "submit")
    assert error.value.details["retry_after_seconds"] == 20
    clock[0] += timedelta(seconds=20)
    assert check(subject, "submit") == 200
    boundary = actor()
    clock[0] = clock[0].replace(second=9, microsecond=999999)
    assert [check(boundary) for _ in range(20)] == [200] * 20
    assert check(boundary) == 429
    clock[0] += timedelta(microseconds=1)
    assert [check(boundary) for _ in range(20)] == [200] * 20


def test_auth_checks_precede_counter_and_counter_failure_blocks_business(monkeypatch):
    learner, csrf, assignment, started = new_attachment_learner(f"closed-{uuid.uuid4()}")
    calls = []
    def fail():
        calls.append(True)
        raise OperationalError("counter unavailable", None, None)
    monkeypatch.setattr(limits.CounterSession, "begin", fail)
    payload = {"expected_revision": started["revision"], "body": "有效正文" * 20}
    for suffix, method in (("draft", learner.put), ("submissions", learner.post)):
        path = f"/api/v1/me/assignments/{assignment}/{suffix}"
        bad = method(path, json=payload, headers={"Idempotency-Key": str(uuid.uuid4())})
        assert bad.status_code == 403
        before = len(calls)
        response = method(path, json=payload, headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())})
        assert len(calls) == before + 1
        assert response.status_code == 503
        assert response.json()["error"]["retryable"] is True
    assert len(calls) == 2
    with SessionLocal() as session:
        for model in (SubmissionDraft, Submission):
            assert session.scalar(select(func.count()).select_from(model).where(model.assignment_id == uuid.UUID(assignment))) == 0
