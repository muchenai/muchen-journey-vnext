"""Exercise the one-off operation against a disposable PostgreSQL test database."""
import importlib.util
from pathlib import Path
import uuid

import pytest
from sqlalchemy import select, text

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID
from journey_api.journey_service import published_formal_journey
from journey_api.models import Enrollment, User
from test_learner_feishu_login import learner_provider, login
from test_shared_learner_reviews import new_submission
from test_wp09_feishu_identity import assert_ok, oauth_provider

spec = importlib.util.spec_from_file_location("owner_retest", Path(__file__).parents[1] / "deploy/owner_retest.py")
operation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operation)


@pytest.fixture
def target(learner_provider, monkeypatch):
    monkeypatch.setenv("FEISHU_LEARNER_SHARED_REVIEWER_IDS", str(REVIEWER_ID))
    get_settings.cache_clear()
    review_id = new_submission(learner_provider)
    # The submitted learner is identified by the new review's assignment lineage.
    with SessionLocal() as session:
        owner_id = session.scalar(text("select e.learner_id from reviews r join assignments a on a.id=r.assignment_id join enrollments e on e.id=a.enrollment_id where r.id=:id"), {"id": review_id})
        owner = session.get(User, owner_id)
        journey = published_formal_journey(session, ORGANIZATION_ID)
        monkeypatch.setattr(operation, "ORG", ORGANIZATION_ID)
        monkeypatch.setattr(operation, "OWNER", owner.id)
        monkeypatch.setattr(operation, "NAME", owner.display_name)
        monkeypatch.setattr(operation, "JOURNEY", journey.id)
        monkeypatch.setattr(operation, "OPERATION", "test-retest-" + uuid.uuid4().hex)
    yield learner_provider, owner_id
    get_settings.cache_clear()


def snapshot():
    # Compare complete existing rows, not just counts; no output of contents.
    with SessionLocal() as session:
        return {table: session.execute(text("select row_to_json(t)::text from " + table + " t order by id")).scalars().all()
            for table in ("users", "role_assignments", "external_identities", "assignments",
                          "submissions", "submission_versions", "reviews", "evaluations")}


def apply():
    with SessionLocal.begin() as session:
        return operation.restart(session)


def test_restart_preserves_history_and_is_idempotent(target):
    provider, owner_id = target
    with SessionLocal() as session:
        old = session.scalar(select(Enrollment).where(Enrollment.learner_id == owner_id))
        old_id = old.id
        other = session.execute(text("select row_to_json(e)::text from enrollments e where learner_id != :id order by id"), {"id": owner_id}).scalars().all()
    before = snapshot()
    result = apply()
    assert result["result"] == "APPLIED"
    after = snapshot()
    for table, rows in before.items():
        if table == "assignments":
            assert set(rows) <= set(after[table])
            assert len(after[table]) == len(rows) + 8
        else:
            assert rows == after[table], table
    with SessionLocal() as session:
        assert session.get(Enrollment, old_id).status.value == "CANCELLED"
        fresh = session.get(Enrollment, uuid.UUID(result["new_enrollment_id"]))
        assert fresh.status.value == "ACTIVE" and fresh.review_assignment_mode == "SHARED"
        assert other == session.execute(text("select row_to_json(e)::text from enrollments e where learner_id != :id order by id"), {"id": owner_id}).scalars().all()
    assert apply()["result"] == "ALREADY_APPLIED"
    assert snapshot() == after
    # Resolve the same real OAuth test identity again: default page chooses fresh round.
    subject = next(iter(provider.subjects.values()))
    client, response = login(provider, "owner-after-retest", subject)
    assert_ok(response)
    action = assert_ok(client.get('/api/v1/me/current-action'))
    assert action["journey"]["nodes"][0]["status"] == "CURRENT"
    assert all(node["status"] == "LOCKED" for node in action["journey"]["nodes"][1:])


def test_identity_mismatch_makes_no_changes(target, monkeypatch):
    before = snapshot()
    monkeypatch.setattr(operation, "NAME", "wrong name")
    with pytest.raises(RuntimeError, match="OWNER_IDENTITY_MISMATCH"):
        apply()
    assert snapshot() == before


def test_creation_failure_rolls_back_old_round(target, monkeypatch):
    _, owner_id = target
    before = snapshot()
    monkeypatch.setattr(operation, "create_journey_assignments", lambda *a, **kw: [])
    with pytest.raises(RuntimeError, match="EXPECTED_EIGHT_FRESH_ASSIGNMENTS"):
        apply()
    assert snapshot() == before
    with SessionLocal() as session:
        rounds = list(session.scalars(select(Enrollment).where(Enrollment.learner_id == owner_id)))
        assert len(rounds) == 1 and rounds[0].status.value == "ACTIVE"
