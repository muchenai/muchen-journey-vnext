from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from journey_api.shared_domain import (
    AiUseDisclosure,
    AppealContract,
    AppealStatus,
    DataClassification,
    EvidenceAuthority,
    EvidenceContract,
    EvidenceVisibility,
    GrowthPlanActionContract,
    GrowthPlanActionStatus,
    GrowthPlanContract,
    GrowthPlanStatus,
    HumanGateContract,
    HumanGateDecision,
    HumanGateKind,
    JourneyModuleKey,
    PersonContract,
    SharedDomainAction,
    SharedDomainRole,
    require_formal_result_basis,
    require_shared_domain_permission,
)


NOW = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
ORGANIZATION_ID = UUID("10000000-0000-4000-8000-000000000001")
PERSON_ID = UUID("20000000-0000-4000-8000-000000000001")
REVIEWER_ID = UUID("30000000-0000-4000-8000-000000000001")


def no_ai() -> AiUseDisclosure:
    return AiUseDisclosure(used=False)


def person() -> PersonContract:
    return PersonContract(
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
    )


def practice_evidence(**overrides) -> EvidenceContract:
    values = {
        "evidence_id": uuid4(),
        "organization_id": ORGANIZATION_ID,
        "person_id": PERSON_ID,
        "module_key": JourneyModuleKey.NEWCOMER_VILLAGE,
        "authority": EvidenceAuthority.PRACTICE,
        "authorized_source_ref": "BC-002/task/newcomer-first-controlled-task.v1",
        "task_version_id": uuid4(),
        "assignment_id": uuid4(),
        "submission_version_id": uuid4(),
        "created_by": PERSON_ID,
        "occurred_at": NOW,
        "revision": 1,
        "ai_use": no_ai(),
        "visibility": (
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        "data_classification": DataClassification.CONFIDENTIAL_PEOPLE,
        "retention_policy": "people-growth-evidence-v1",
    }
    values.update(overrides)
    return EvidenceContract(**values)


def human_evaluation_evidence(**overrides) -> EvidenceContract:
    values = {
        "evidence_id": uuid4(),
        "organization_id": ORGANIZATION_ID,
        "person_id": PERSON_ID,
        "module_key": JourneyModuleKey.NEWCOMER_VILLAGE,
        "authority": EvidenceAuthority.HUMAN_EVALUATION,
        "authorized_source_ref": "BC-002/review/fixed-evaluation.v1",
        "evaluation_id": uuid4(),
        "created_by": REVIEWER_ID,
        "occurred_at": NOW + timedelta(hours=1),
        "revision": 1,
        "ai_use": no_ai(),
        "visibility": (
            EvidenceVisibility.PERSON,
            EvidenceVisibility.ASSIGNED_REVIEWERS,
        ),
        "data_classification": DataClassification.CONFIDENTIAL_PEOPLE,
        "retention_policy": "people-growth-evidence-v1",
    }
    values.update(overrides)
    return EvidenceContract(**values)


def human_gate(evidence_ids: tuple[UUID, ...], **overrides) -> HumanGateContract:
    values = {
        "gate_id": uuid4(),
        "organization_id": ORGANIZATION_ID,
        "person_id": PERSON_ID,
        "module_key": JourneyModuleKey.NEWCOMER_VILLAGE,
        "gate_kind": HumanGateKind.TASK_PASS,
        "evidence_ids": evidence_ids,
        "rubric_version": "newcomer-task-rubric.v1",
        "decision": HumanGateDecision.PASS,
        "reason": "Reviewer verified the fixed practice submission against the rubric.",
        "signed_by_person_ids": (REVIEWER_ID,),
        "signed_at": NOW + timedelta(hours=1),
    }
    values.update(overrides)
    return HumanGateContract(**values)


def growth_action(evidence_id: UUID) -> GrowthPlanActionContract:
    return GrowthPlanActionContract(
        action_id=uuid4(),
        capability_key="controlled_delivery",
        action="Complete the next controlled delivery task with reviewer feedback.",
        evidence_ids=(evidence_id,),
        status=GrowthPlanActionStatus.PLANNED,
        target_at=NOW + timedelta(days=30),
    )


def test_contracts_are_strict_machine_readable_schemas():
    for contract in (
        PersonContract,
        EvidenceContract,
        HumanGateContract,
        AppealContract,
        GrowthPlanContract,
    ):
        schema = contract.model_json_schema()
        assert schema["additionalProperties"] is False
        assert schema["type"] == "object"


def test_person_contract_reuses_user_as_the_only_person_source():
    assert person().source == "users.id"
    with pytest.raises(ValidationError, match="source"):
        PersonContract(
            organization_id=ORGANIZATION_ID,
            person_id=PERSON_ID,
            source="module_local_people.id",
        )


def test_practice_evidence_requires_fixed_task_assignment_and_submission_versions():
    with pytest.raises(ValidationError, match="practice evidence requires"):
        practice_evidence(submission_version_id=None)


def test_ai_evidence_requires_full_provenance_and_remains_advisory():
    with pytest.raises(ValidationError, match="requires purpose"):
        AiUseDisclosure(used=True)
    with pytest.raises(ValidationError, match="advisory only"):
        AiUseDisclosure(
            used=True,
            purpose="initial feedback",
            model_version="model-v1",
            prompt_version="prompt-v1",
            output_is_advisory_only=False,
        )


def test_formal_result_accepts_practice_human_evaluation_and_a_human_signature():
    practice = practice_evidence()
    evaluation = human_evaluation_evidence()
    gate = human_gate((practice.evidence_id, evaluation.evidence_id))

    require_formal_result_basis(
        person=person(), evidence=(practice, evaluation), gate=gate
    )


def test_practice_without_human_evaluation_cannot_create_formal_result():
    practice = practice_evidence()
    gate = human_gate((practice.evidence_id,))

    with pytest.raises(ValueError, match="human evaluation evidence"):
        require_formal_result_basis(
            person=person(), evidence=(practice,), gate=gate
        )


def test_needs_revision_gate_cannot_create_a_formal_result():
    evidence = practice_evidence()
    evaluation = human_evaluation_evidence()
    gate = human_gate(
        (evidence.evidence_id, evaluation.evidence_id),
        decision=HumanGateDecision.NEEDS_REVISION,
    )

    with pytest.raises(ValueError, match="requires a PASS human gate"):
        require_formal_result_basis(
            person=person(), evidence=(evidence, evaluation), gate=gate
        )


@pytest.mark.parametrize(
    "authority",
    [
        EvidenceAuthority.AI_ADVISORY,
        EvidenceAuthority.SELF_ATTESTATION,
        EvidenceAuthority.INCENTIVE_LEDGER,
    ],
)
def test_ai_self_attestation_and_points_cannot_create_formal_results(authority):
    ai_use = (
        AiUseDisclosure(
            used=True,
            purpose="initial feedback",
            model_version="model-v1",
            prompt_version="prompt-v1",
        )
        if authority is EvidenceAuthority.AI_ADVISORY
        else no_ai()
    )
    evidence = EvidenceContract(
        evidence_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        module_key=JourneyModuleKey.AI_ACADEMY,
        authority=authority,
        authorized_source_ref="BC-003/advisory-source.v1",
        created_by=PERSON_ID,
        occurred_at=NOW,
        revision=1,
        ai_use=ai_use,
        visibility=(EvidenceVisibility.PERSON,),
        data_classification=DataClassification.INTERNAL,
        retention_policy="advisory-v1",
    )
    gate = human_gate(
        (evidence.evidence_id,), module_key=JourneyModuleKey.AI_ACADEMY
    )

    with pytest.raises(ValueError, match="requires practice evidence"):
        require_formal_result_basis(person=person(), evidence=(evidence,), gate=gate)


def test_learning_completion_system_fact_cannot_create_formal_result():
    completion = EvidenceContract(
        evidence_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        module_key=JourneyModuleKey.EXPLORATION_CAMP,
        authority=EvidenceAuthority.SYSTEM_FACT,
        authorized_source_ref="learning-material-completion:test-only",
        created_by=PERSON_ID,
        occurred_at=NOW,
        revision=1,
        ai_use=no_ai(),
        visibility=(EvidenceVisibility.PERSON,),
        data_classification=DataClassification.INTERNAL,
        retention_policy="learning-facts-v1",
    )
    gate = human_gate(
        (completion.evidence_id,),
        module_key=JourneyModuleKey.EXPLORATION_CAMP,
    )

    with pytest.raises(ValueError, match="requires practice evidence"):
        require_formal_result_basis(
            person=person(), evidence=(completion,), gate=gate
        )


def test_formal_result_rejects_cross_person_or_organization_evidence():
    evidence = practice_evidence(person_id=uuid4())
    evaluation = human_evaluation_evidence()
    gate = human_gate((evidence.evidence_id, evaluation.evidence_id))

    with pytest.raises(ValueError, match="cannot cross person"):
        require_formal_result_basis(
            person=person(), evidence=(evidence, evaluation), gate=gate
        )


def test_human_gate_cannot_be_self_signed():
    evidence = practice_evidence()
    with pytest.raises(ValidationError, match="own formal gate"):
        human_gate(
            (evidence.evidence_id,), signed_by_person_ids=(PERSON_ID,)
        )


def test_high_impact_gate_is_appealable_by_contract():
    evidence = practice_evidence()
    with pytest.raises(ValidationError, match="appeal policy"):
        human_gate(
            (evidence.evidence_id,),
            gate_kind=HumanGateKind.HIGH_IMPACT_PEOPLE_RESULT,
        )

    gate = human_gate(
        (evidence.evidence_id,),
        gate_kind=HumanGateKind.HIGH_IMPACT_PEOPLE_RESULT,
        appeal_policy_ref="people-high-impact-appeal.v1",
        appeal_window_ends_at=NOW + timedelta(days=10),
    )
    assert gate.appeal_window_ends_at > gate.signed_at


def test_original_gate_signer_cannot_resolve_their_own_appeal():
    with pytest.raises(ValidationError, match="cannot review their own appeal"):
        AppealContract(
            appeal_id=uuid4(),
            organization_id=ORGANIZATION_ID,
            person_id=PERSON_ID,
            gate_id=uuid4(),
            appellant_id=PERSON_ID,
            reason="The fixed evidence was interpreted without the submitted revision.",
            submitted_at=NOW,
            status=AppealStatus.IN_REVIEW,
            original_signer_ids=(REVIEWER_ID,),
            independent_reviewer_ids=(REVIEWER_ID,),
        )


def test_resolved_appeal_requires_independent_signed_reason():
    independent_reviewer = uuid4()
    appeal = AppealContract(
        appeal_id=uuid4(),
        organization_id=ORGANIZATION_ID,
        person_id=PERSON_ID,
        gate_id=uuid4(),
        appellant_id=PERSON_ID,
        reason="The fixed evidence was interpreted without the submitted revision.",
        submitted_at=NOW,
        status=AppealStatus.RETURNED_FOR_REVIEW,
        original_signer_ids=(REVIEWER_ID,),
        independent_reviewer_ids=(independent_reviewer,),
        resolution_reason="Independent review found that a fixed revision was omitted.",
        resolved_at=NOW + timedelta(days=1),
    )
    assert appeal.independent_reviewer_ids == (independent_reviewer,)


def test_confirmed_growth_plan_requires_person_confirmation_and_lineage():
    evidence = practice_evidence()
    with pytest.raises(ValidationError, match="person confirmation"):
        GrowthPlanContract(
            growth_plan_id=uuid4(),
            organization_id=ORGANIZATION_ID,
            person_id=PERSON_ID,
            version=1,
            status=GrowthPlanStatus.CONFIRMED,
            based_on_evidence_ids=(evidence.evidence_id,),
            based_on_gate_ids=(uuid4(),),
            actions=(growth_action(evidence.evidence_id),),
            created_by=REVIEWER_ID,
            created_at=NOW,
            ai_use=no_ai(),
        )


def test_growth_plan_contract_forbids_automatic_employment_fields():
    evidence = practice_evidence()
    with pytest.raises(ValidationError, match="automatic_employment_decision"):
        GrowthPlanContract(
            growth_plan_id=uuid4(),
            organization_id=ORGANIZATION_ID,
            person_id=PERSON_ID,
            version=1,
            status=GrowthPlanStatus.DRAFT,
            based_on_evidence_ids=(evidence.evidence_id,),
            based_on_gate_ids=(uuid4(),),
            actions=(growth_action(evidence.evidence_id),),
            created_by=REVIEWER_ID,
            created_at=NOW,
            ai_use=no_ai(),
            automatic_employment_decision="PROMOTE",
        )


def test_permissions_keep_person_confirmation_and_appeal_resolution_separate():
    require_shared_domain_permission(
        action=SharedDomainAction.CONFIRM_GROWTH_PLAN,
        actor_id=PERSON_ID,
        actor_roles=frozenset({SharedDomainRole.PERSON}),
        person_id=PERSON_ID,
    )
    with pytest.raises(PermissionError):
        require_shared_domain_permission(
            action=SharedDomainAction.CONFIRM_GROWTH_PLAN,
            actor_id=REVIEWER_ID,
            actor_roles=frozenset({SharedDomainRole.REVIEWER}),
            person_id=PERSON_ID,
            assigned_reviewer_ids=frozenset({REVIEWER_ID}),
        )

    with pytest.raises(PermissionError):
        require_shared_domain_permission(
            action=SharedDomainAction.RESOLVE_APPEAL,
            actor_id=REVIEWER_ID,
            actor_roles=frozenset({SharedDomainRole.APPEAL_REVIEWER}),
            person_id=PERSON_ID,
            assigned_reviewer_ids=frozenset({REVIEWER_ID}),
            original_gate_signer_ids=frozenset({REVIEWER_ID}),
        )


def test_only_an_assigned_coach_can_sign_growth_plan_confirmation_gate():
    coach_id = uuid4()
    require_shared_domain_permission(
        action=SharedDomainAction.SIGN_GROWTH_PLAN_GATE,
        actor_id=coach_id,
        actor_roles=frozenset({SharedDomainRole.COACH}),
        person_id=PERSON_ID,
        assigned_reviewer_ids=frozenset({coach_id}),
    )
    with pytest.raises(PermissionError):
        require_shared_domain_permission(
            action=SharedDomainAction.SIGN_GROWTH_PLAN_GATE,
            actor_id=REVIEWER_ID,
            actor_roles=frozenset({SharedDomainRole.REVIEWER}),
            person_id=PERSON_ID,
            assigned_reviewer_ids=frozenset({REVIEWER_ID}),
        )
    with pytest.raises(PermissionError):
        require_shared_domain_permission(
            action=SharedDomainAction.SIGN_GROWTH_PLAN_GATE,
            actor_id=PERSON_ID,
            actor_roles=frozenset({SharedDomainRole.COACH}),
            person_id=PERSON_ID,
            assigned_reviewer_ids=frozenset({PERSON_ID}),
        )


def test_assigned_human_reviewer_can_sign_but_person_cannot_self_sign():
    require_shared_domain_permission(
        action=SharedDomainAction.SIGN_HUMAN_GATE,
        actor_id=REVIEWER_ID,
        actor_roles=frozenset({SharedDomainRole.REVIEWER}),
        person_id=PERSON_ID,
        assigned_reviewer_ids=frozenset({REVIEWER_ID}),
    )
    with pytest.raises(PermissionError):
        require_shared_domain_permission(
            action=SharedDomainAction.SIGN_HUMAN_GATE,
            actor_id=PERSON_ID,
            actor_roles=frozenset(
                {SharedDomainRole.PERSON, SharedDomainRole.REVIEWER}
            ),
            person_id=PERSON_ID,
            assigned_reviewer_ids=frozenset({PERSON_ID}),
        )
