import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from journey_api.data_lifecycle import (
    DataLifecycleError,
    load_policy,
    retention_plan,
)
from journey_api.db import SessionLocal
from journey_api.models import (
    AuditEntry,
    DataRightsRequest,
    DataRightsRequestStatus,
    DataRightsRequestType,
    IdempotencyRecord,
    Role,
    RoleAssignment,
    User,
)


def user_for_role(role: Role) -> User:
    with SessionLocal() as session:
        user = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(RoleAssignment.role == role)
            .order_by(User.id)
        )
        assert user is not None
        session.expunge(user)
        return user


def test_policy_matches_dec_008_and_rejects_drift(tmp_path: Path):
    policy = load_policy()
    assert policy.data_rights_due_days == 30
    assert policy.retention_days == {
        "identity": 1095,
        "submissions": 1095,
        "evaluations": 1095,
        "outcomes": 1095,
        "audit": 1095,
        "attachments": 365,
        "notifications": 180,
        "idempotency": 30,
    }

    raw = json.loads(Path("config/wp12_data_lifecycle.json").read_text())
    raw["retention_days"]["idempotency"] = 31
    drifted = tmp_path / "policy.json"
    drifted.write_text(json.dumps(raw))
    with pytest.raises(DataLifecycleError, match="DEC-008"):
        load_policy(drifted)


def test_plan_is_read_only_bounded_and_reports_overdue_rights_requests():
    as_of = datetime(2026, 7, 28, 12, tzinfo=UTC)
    old = as_of - timedelta(days=1200)
    recent = as_of - timedelta(days=5)
    operator = user_for_role(Role.OPERATOR)
    learner = user_for_role(Role.LEARNER)
    old_key = f"wp12-old-{uuid.uuid4()}"
    recent_key = f"wp12-recent-{uuid.uuid4()}"

    with SessionLocal.begin() as session:
        session.add_all(
            [
                IdempotencyRecord(
                    id=uuid.uuid4(),
                    actor_id=operator.id,
                    command="wp12.retention.test",
                    key=old_key,
                    request_hash="a" * 64,
                    response_body={"status": "OLD"},
                    created_at=old,
                ),
                IdempotencyRecord(
                    id=uuid.uuid4(),
                    actor_id=operator.id,
                    command="wp12.retention.test",
                    key=recent_key,
                    request_hash="b" * 64,
                    response_body={"status": "RECENT"},
                    created_at=recent,
                ),
                AuditEntry(
                    id=uuid.uuid4(),
                    organization_id=operator.organization_id,
                    actor_id=operator.id,
                    action="wp12.retention.test",
                    resource_type="data_lifecycle",
                    resource_id=None,
                    result="PASS",
                    request_id=f"req_{uuid.uuid4().hex}",
                    details={"contains_pii": False},
                    occurred_at=old,
                ),
                DataRightsRequest(
                    id=uuid.uuid4(),
                    organization_id=learner.organization_id,
                    subject_user_id=learner.id,
                    request_type=DataRightsRequestType.DELETE,
                    status=DataRightsRequestStatus.OPEN,
                    requested_by=operator.id,
                    requested_at=as_of - timedelta(days=31),
                    due_at=as_of - timedelta(days=1),
                    legal_hold=False,
                    legal_hold_reason=None,
                    revision=1,
                ),
                DataRightsRequest(
                    id=uuid.uuid4(),
                    organization_id=learner.organization_id,
                    subject_user_id=learner.id,
                    request_type=DataRightsRequestType.CORRECT,
                    status=DataRightsRequestStatus.OPEN,
                    requested_by=operator.id,
                    requested_at=as_of - timedelta(days=40),
                    due_at=as_of - timedelta(days=10),
                    legal_hold=True,
                    legal_hold_reason="LEGAL_HOLD",
                    revision=1,
                ),
            ]
        )

    with SessionLocal() as session:
        before = session.scalar(select(func.count()).select_from(IdempotencyRecord))
        plan = retention_plan(session, load_policy(), as_of=as_of)
        after = session.scalar(select(func.count()).select_from(IdempotencyRecord))

    assert before == after
    assert plan["mode"] == "PLAN_ONLY"
    assert plan["mutations_executed"] is False
    assert plan["contains_record_identifiers"] is False
    assert plan["eligible_counts"]["idempotency"] >= 1
    assert plan["eligible_counts"]["audit"] >= 1
    assert plan["overdue_data_rights_requests"] >= 1
    assert plan["active_legal_holds"] >= 1
    assert plan["cutoffs"]["idempotency"] == (
        as_of - timedelta(days=30)
    ).isoformat()


def test_plan_rejects_naive_as_of():
    with SessionLocal() as session, pytest.raises(
        DataLifecycleError, match="timezone-aware"
    ):
        retention_plan(session, load_policy(), as_of=datetime(2026, 7, 28))
