from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from journey_api.appeal_continuity import (
    AppealReplacementGateContract,
    ResolvedAppealCaseContract,
)
from journey_api.formal_result_handoff import (
    ControlledHandoffScopeContract,
    ControlledHandoffStatus,
    FormalResultStatus,
    HandoffSignatureContract,
    HandoffSignatureDecision,
    HandoffSignatureRole,
    bind_formal_result_package,
    project_controlled_handoff,
)
from journey_api.models import Handoff, HandoffStatus, Outcome
from journey_api.shared_domain import (
    AiUseDisclosure,
    AppealContract,
    AppealStatus,
    DataClassification,
    EvidenceAuthority,
    EvidenceContract,
    EvidenceVisibility,
    HumanGateContract,
    HumanGateDecision,
    HumanGateKind,
    JourneyModuleKey,
    PersonContract,
)
from journey_api.shared_domain_projection import ReviewCycleProjection, ReviewCycleStatus


NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("80000000-0000-4000-8000-000000000001")
PERSON_ID = UUID("80000000-0000-4000-8000-000000000002")
REVIEWER_ID = UUID("80000000-0000-4000-8000-000000000003")
APPEAL_REVIEWER_ID = UUID("80000000-0000-4000-8000-000000000004")


def review_cycle(
    *, module_key: JourneyModuleKey = JourneyModuleKey.NEWCOMER_VILLAGE
) -> ReviewCycleProjection:
    assignment_id = uuid4()
    practice = EvidenceContract(
        evidence_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        module_key=module_key,
        authority=EvidenceAuthority.PRACTICE,
        authorized_source_ref="task-auth:fixed-task-version-sha256",
        task_version_id=uuid4(),
        assignment_id=assignment_id,
        submission_version_id=uuid4(),
        created_by=PERSON_ID,
        occurred_at=NOW,
        revision=1,
        ai_use=AiUseDisclosure(used=False),
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
        retention_policy="controlled-evidence-v1",
    )
    evaluation = EvidenceContract(
        evidence_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        module_key=module_key,
        authority=EvidenceAuthority.HUMAN_EVALUATION,
        authorized_source_ref="task-auth:fixed-task-version-sha256",
        evaluation_id=uuid4(),
        created_by=REVIEWER_ID,
        occurred_at=NOW + timedelta(minutes=10),
        revision=1,
        ai_use=AiUseDisclosure(used=False),
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
        retention_policy="controlled-evidence-v1",
    )
    gate = HumanGateContract(
        gate_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        module_key=module_key,
        gate_kind=(
            HumanGateKind.TASK_PASS
            if module_key is JourneyModuleKey.NEWCOMER_VILLAGE
            else HumanGateKind.CAPABILITY
        ),
        evidence_ids=(practice.evidence_id, evaluation.evidence_id),
        rubric_version="fixed-task-version:rubric-v1",
        decision=HumanGateDecision.PASS,
        reason="The reviewer verified the complete practice evidence against the rubric.",
        signed_by_person_ids=(REVIEWER_ID,),
        signed_at=NOW + timedelta(minutes=10),
        appeal_policy_ref="appeal-policy:newcomer:v1:sha256:fixed",
        appeal_window_ends_at=NOW + timedelta(days=14),
    )
    return ReviewCycleProjection(
        person=PersonContract(
            organization_id=ORGANIZATION_ID,
            person_id=PERSON_ID,
        ),
        practice_evidence=practice,
        human_evaluation_evidence=evaluation,
        human_gate=gate,
        status=ReviewCycleStatus.FORMAL_RESULT_ELIGIBLE,
        blockers=(),
    )


def outcome_for(cycle: ReviewCycleProjection) -> Outcome:
    return Outcome(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        learner_id=PERSON_ID,
        assignment_id=cycle.practice_evidence.assignment_id,
        enrollment_id=uuid4(),
        source_evaluation_id=cycle.human_evaluation_evidence.evaluation_id,
        status="HANDOFF_READY",
        summary="Human review passed and a developmental next-step result is ready.",
        created_at=NOW + timedelta(minutes=11),
    )


def handoff_for(outcome: Outcome, *, owner_id: UUID = REVIEWER_ID) -> Handoff:
    return Handoff(
        id=uuid4(),
        organization_id=outcome.organization_id,
        enrollment_id=outcome.enrollment_id,
        outcome_id=outcome.id,
        source_evaluation_id=outcome.source_evaluation_id,
        owner_user_id=owner_id,
        status=HandoffStatus.READY,
        title="Developmental handoff is ready",
        next_step_code="CONFIRM_HANDOFF",
        next_step_title="Confirm the next learning stage with the owner",
        instructions="Review the evidence and jointly confirm whether to continue.",
        created_at=outcome.created_at,
    )


def appeal_for(
    cycle: ReviewCycleProjection,
    *, status: AppealStatus,
) -> AppealContract:
    resolved = status in {
        AppealStatus.UPHELD,
        AppealStatus.OVERTURNED,
        AppealStatus.RETURNED_FOR_REVIEW,
    }
    return AppealContract(
        appeal_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        gate_id=cycle.human_gate.gate_id,
        appellant_id=PERSON_ID,
        reason="The submitted fixed evidence was not interpreted under the stated rubric.",
        submitted_at=NOW + timedelta(hours=1),
        status=status,
        original_signer_ids=(REVIEWER_ID,),
        independent_reviewer_ids=(APPEAL_REVIEWER_ID,) if resolved else (),
        resolution_reason=(
            "Independent review completed and documented the corrected conclusion."
            if resolved
            else None
        ),
        resolved_at=NOW + timedelta(hours=2) if resolved else None,
        evidence_ids=cycle.human_gate.evidence_ids,
    )


def handoff_signatures(scope) -> tuple[HandoffSignatureContract, ...]:
    return (
        HandoffSignatureContract(
            signer_person_id=PERSON_ID,
            role=HandoffSignatureRole.PERSON,
            decision=HandoffSignatureDecision.CONFIRM,
            subject_sha256=scope.subject_sha256(),
            signed_at=scope.created_at + timedelta(minutes=1),
            evidence_ref="evidence/handoff/person-confirmation",
        ),
        HandoffSignatureContract(
            signer_person_id=REVIEWER_ID,
            role=HandoffSignatureRole.HANDOFF_OWNER,
            decision=HandoffSignatureDecision.CONFIRM,
            subject_sha256=scope.subject_sha256(),
            signed_at=scope.created_at + timedelta(minutes=2),
            evidence_ref="evidence/handoff/owner-confirmation",
        ),
    )


def test_effective_outcome_requires_person_and_owner_before_next_stage_confirmation():
    cycle = review_cycle()
    outcome = outcome_for(cycle)
    package = bind_formal_result_package(outcome=outcome, review_cycle=cycle)

    assert package.status is FormalResultStatus.EFFECTIVE
    assert package.automatic_talent_status_change_allowed is False
    handoff = handoff_for(outcome)
    pending = project_controlled_handoff(
        handoff=handoff,
        formal_result=package,
    )
    assert pending.status is ControlledHandoffStatus.PENDING_HUMAN_CONFIRMATION
    assert pending.scope.from_module_key is JourneyModuleKey.NEWCOMER_VILLAGE
    assert pending.scope.to_module_key is JourneyModuleKey.AI_ACADEMY
    assert pending.scope.automatic_enrollment_allowed is False

    confirmed = project_controlled_handoff(
        handoff=handoff,
        formal_result=package,
        signatures=handoff_signatures(pending.scope),
    )
    assert confirmed.status is ControlledHandoffStatus.CONFIRMED
    assert confirmed.blockers == ()
    assert confirmed.scope.production_action_executed is False


def test_outcome_binding_fails_closed_on_caller_or_scope_drift():
    cycle = review_cycle()
    outcome = outcome_for(cycle)
    outcome.source_evaluation_id = uuid4()
    with pytest.raises(ValueError, match="fixed shared review-cycle scope"):
        bind_formal_result_package(outcome=outcome, review_cycle=cycle)

    with pytest.raises(ValidationError, match="cannot automate enrollment"):
        ControlledHandoffScopeContract(
            organization_id=ORGANIZATION_ID,
            person_id=PERSON_ID,
            handoff_id=uuid4(),
            outcome_id=uuid4(),
            formal_result_package_id=uuid4(),
            formal_result_package_sha256="a" * 64,
            from_module_key=JourneyModuleKey.NEWCOMER_VILLAGE,
            to_module_key=JourneyModuleKey.AI_ACADEMY,
            owner_person_id=REVIEWER_ID,
            title="Developmental handoff is ready",
            next_step_code="CONFIRM_HANDOFF",
            next_step_title="Confirm the next controlled learning stage",
            instructions="Review evidence and confirm the developmental next action.",
            created_at=NOW,
            production_action_executed=True,
        )


def test_open_appeal_blocks_existing_ready_handoff_and_rejects_signatures():
    cycle = review_cycle()
    outcome = outcome_for(cycle)
    appeal = appeal_for(cycle, status=AppealStatus.SUBMITTED)
    package = bind_formal_result_package(
        outcome=outcome,
        review_cycle=cycle,
        appeals=(appeal,),
    )
    assert package.status is FormalResultStatus.DISPUTED

    handoff = handoff_for(outcome)
    blocked = project_controlled_handoff(
        handoff=handoff,
        formal_result=package,
    )
    assert blocked.status is ControlledHandoffStatus.BLOCKED_BY_APPEAL
    with pytest.raises(ValueError, match="appeal-blocked"):
        project_controlled_handoff(
            handoff=handoff,
            formal_result=package,
            signatures=handoff_signatures(blocked.scope),
        )


def test_overturned_appeal_invalidates_old_result_until_replacement_gate_exists():
    cycle = review_cycle()
    outcome = outcome_for(cycle)
    appeal = appeal_for(cycle, status=AppealStatus.OVERTURNED)
    invalidated = bind_formal_result_package(
        outcome=outcome,
        review_cycle=cycle,
        appeals=(appeal,),
    )
    assert invalidated.status is FormalResultStatus.INVALIDATED_BY_APPEAL

    resolution = EvidenceContract(
        evidence_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        module_key=cycle.human_gate.module_key,
        authority=EvidenceAuthority.HUMAN_OBSERVATION,
        authorized_source_ref=f"appeal:{appeal.appeal_id}:resolution",
        created_by=APPEAL_REVIEWER_ID,
        occurred_at=appeal.resolved_at,
        revision=1,
        ai_use=AiUseDisclosure(used=False),
        visibility=(
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        data_classification=DataClassification.CONFIDENTIAL_PEOPLE,
        retention_policy="controlled-evidence-v1",
    )
    replacement_gate = HumanGateContract(
        **{
            **cycle.human_gate.model_dump(),
            "gate_id": uuid4(),
            "evidence_ids": (*cycle.human_gate.evidence_ids, resolution.evidence_id),
            "signed_by_person_ids": (APPEAL_REVIEWER_ID,),
            "signed_at": NOW + timedelta(hours=3),
            "appeal_window_ends_at": NOW + timedelta(days=15),
            "revision": 2,
            "supersedes_gate_id": cycle.human_gate.gate_id,
            "source_appeal_id": appeal.appeal_id,
        }
    )
    # G10 owns construction and validation of the resolved case; this isolated G11
    # fixture supplies that already-validated upstream artifact without duplicating
    # the policy/assignment builder exercised in test_appeal_continuity_contract.py.
    resolved_case = ResolvedAppealCaseContract.model_construct(appeal=appeal)
    replacement = AppealReplacementGateContract.model_construct(
        original_gate=cycle.human_gate,
        appeal_case=resolved_case,
        resolution_evidence=resolution,
        replacement_gate=replacement_gate,
    )
    corrected = bind_formal_result_package(
        outcome=outcome,
        review_cycle=cycle,
        appeals=(appeal,),
        replacement=replacement,
    )
    assert corrected.status is FormalResultStatus.EFFECTIVE_AFTER_APPEAL
    assert corrected.human_gate.revision == 2

    stale = project_controlled_handoff(
        handoff=handoff_for(outcome),
        formal_result=corrected,
    )
    assert stale.status is ControlledHandoffStatus.REISSUE_REQUIRED
    assert stale.scope.to_module_key is JourneyModuleKey.AI_ACADEMY


def test_career_map_and_terminal_certification_are_not_sequential_handoffs():
    career_cycle = review_cycle(module_key=JourneyModuleKey.CAREER_MAP)
    career_package = bind_formal_result_package(
        outcome=outcome_for(career_cycle),
        review_cycle=career_cycle,
    )
    with pytest.raises(ValueError, match="no sequential v1 handoff target"):
        project_controlled_handoff(
            handoff=handoff_for(outcome_for(career_cycle)),
            formal_result=career_package,
        )

    certification_cycle = review_cycle(module_key=JourneyModuleKey.CERTIFICATION_ARENA)
    certification_package = bind_formal_result_package(
        outcome=outcome_for(certification_cycle),
        review_cycle=certification_cycle,
    )
    with pytest.raises(ValueError, match="no sequential v1 handoff target"):
        project_controlled_handoff(
            handoff=handoff_for(outcome_for(certification_cycle)),
            formal_result=certification_package,
        )
