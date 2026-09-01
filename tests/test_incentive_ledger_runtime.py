import uuid

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID
from journey_api.incentive_ledger import (
    IncentiveLedgerError,
    append_incentive_entry,
)
from journey_api.models import Evaluation, IncentiveLedgerEntry, IncentiveType, Outcome
from journey_api.shared_domain import JourneyModuleKey
from test_reviewer_workbench import (
    REVIEWER_HEADERS,
    assert_ok,
    client_for,
    create_submission,
    finalize_payload,
)


RULE_REF = "governance/incentives/owner-approved-rule-v1"
RULE_SHA256 = "a" * 64


def passed_flow(label: str):
    flow = create_submission(label)
    reviewer = client_for(f"reviewer-{label}")
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"incentive-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    finalized = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"incentive-finalize-{uuid.uuid4()}",
            },
            json=finalize_payload(
                started["review_revision"],
                decision="APPROVE",
            ),
        )
    )
    person_id = uuid.UUID(assert_ok(flow["learner"].get("/api/v1/session"))["user_id"])
    return flow, uuid.UUID(finalized["evaluation_id"]), person_id


def test_immutable_approved_outcome_supports_append_only_award_and_correction():
    flow, evaluation_id, person_id = passed_flow("incentive-ledger")
    with SessionLocal.begin() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        outcome_id = session.scalar(
            select(Outcome.id).where(Outcome.source_evaluation_id == evaluation.id)
        )
        assert outcome_id is not None
        original = append_incentive_entry(
            session,
            organization_id=evaluation.organization_id,
            person_id=person_id,
            module_key=JourneyModuleKey.EXPLORATION_CAMP,
            incentive_type=IncentiveType.POINTS,
            amount=5,
            source_outcome_id=outcome_id,
            rule_ref=RULE_REF,
            rule_sha256=RULE_SHA256,
            created_by=REVIEWER_ID,
        )
        correction = append_incentive_entry(
            session,
            organization_id=evaluation.organization_id,
            person_id=person_id,
            module_key=JourneyModuleKey.EXPLORATION_CAMP,
            incentive_type=IncentiveType.POINTS,
            amount=-2,
            source_outcome_id=outcome_id,
            rule_ref=RULE_REF,
            rule_sha256=RULE_SHA256,
            created_by=REVIEWER_ID,
            correction_of_entry_id=original.id,
            correction_reason="Reviewer corrected the manually recorded delta.",
        )
        original_id = original.id
        correction_id = correction.id

    projection = assert_ok(flow["learner"].get("/api/v1/me/incentives"))
    assert projection["points_total"] == 3
    assert projection["xp_total"] == 0
    assert projection["formal_effect"] == "NONE"
    assert projection["can_unlock_human_gate"] is False
    projected_by_id = {item["id"]: item for item in projection["entries"]}
    assert set(projected_by_id) == {str(original_id), str(correction_id)}
    assert projected_by_id[str(correction_id)]["correction_of_entry_id"] == str(
        original_id
    )

    for statement in (
        update(IncentiveLedgerEntry)
        .where(IncentiveLedgerEntry.id == original_id)
        .values(amount=99),
        delete(IncentiveLedgerEntry).where(IncentiveLedgerEntry.id == original_id),
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            with SessionLocal.begin() as session:
                session.execute(statement)


def test_non_pass_or_cross_person_source_and_unsigned_rule_fail_closed():
    _flow, evaluation_id, person_id = passed_flow("incentive-negative")
    with SessionLocal.begin() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        outcome_id = session.scalar(
            select(Outcome.id).where(Outcome.source_evaluation_id == evaluation.id)
        )
        assert outcome_id is not None
        with pytest.raises(IncentiveLedgerError, match="SHA-256"):
            append_incentive_entry(
                session,
                organization_id=evaluation.organization_id,
                person_id=person_id,
                module_key=JourneyModuleKey.EXPLORATION_CAMP,
                incentive_type=IncentiveType.POINTS,
                amount=1,
                source_outcome_id=outcome_id,
                rule_ref=RULE_REF,
                rule_sha256="not-a-hash",
                created_by=REVIEWER_ID,
            )
        with pytest.raises(IncentiveLedgerError, match="same Person"):
            append_incentive_entry(
                session,
                organization_id=evaluation.organization_id,
                person_id=uuid.uuid4(),
                module_key=JourneyModuleKey.EXPLORATION_CAMP,
                incentive_type=IncentiveType.POINTS,
                amount=1,
                source_outcome_id=outcome_id,
                rule_ref=RULE_REF,
                rule_sha256=RULE_SHA256,
                created_by=REVIEWER_ID,
            )
        organization_id = evaluation.organization_id

    with pytest.raises(DBAPIError):
        with SessionLocal.begin() as session:
            session.add(
                IncentiveLedgerEntry(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    person_id=REVIEWER_ID,
                    module_key=JourneyModuleKey.EXPLORATION_CAMP.value,
                    incentive_type=IncentiveType.POINTS,
                    amount=1,
                    label=None,
                    source_outcome_id=outcome_id,
                    rule_ref=RULE_REF,
                    rule_sha256=RULE_SHA256,
                    correction_of_entry_id=None,
                    correction_reason=None,
                    created_by=REVIEWER_ID,
                )
            )
            session.flush()


def test_rank_remains_a_ledger_fact_and_creates_no_people_conclusion():
    flow, evaluation_id, person_id = passed_flow("incentive-rank")
    with SessionLocal.begin() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        outcome_id = session.scalar(
            select(Outcome.id).where(Outcome.source_evaluation_id == evaluation.id)
        )
        assert outcome_id is not None
        append_incentive_entry(
            session,
            organization_id=evaluation.organization_id,
            person_id=person_id,
            module_key=JourneyModuleKey.NEWCOMER_VILLAGE,
            incentive_type=IncentiveType.RANK,
            label="Synthetic test rank",
            source_outcome_id=outcome_id,
            rule_ref=RULE_REF,
            rule_sha256=RULE_SHA256,
            created_by=REVIEWER_ID,
        )

    projection = assert_ok(flow["learner"].get("/api/v1/me/incentives"))
    assert projection["formal_effect"] == "NONE"
    assert projection["can_unlock_human_gate"] is False
    assert projection["entries"][0]["incentive_type"] == "RANK"
    result = assert_ok(flow["learner"].get("/api/v1/me/result"))
    assert "rank" not in result
    assert "talent" not in result


def test_no_incentive_mutation_route_is_exposed():
    from journey_api.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/me/incentives" in paths
    assert set(paths["/api/v1/me/incentives"]) == {"get"}
    assert all("incentive" not in path or "ops" not in path for path in paths)
