import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.domain import AssignmentActionState, assignment_action, resolve_current_action
from journey_api.errors import ApiError
from journey_api.formal_assignment_workflow import (
    FormalAssignmentEvent,
    FormalAssignmentTransitionError,
    WorkflowActorKind,
    public_assignment_status,
    transition_formal_assignment,
)
from journey_api.idempotency import find_replay, store_result
from journey_api.learning_materials import (
    completed_materials,
    ensure_required_materials_completed,
    material_by_key,
)
from journey_api.journey_service import (
    formal_admission_scorecard,
    journey_stages,
    lock_active_learner_assignment,
    publish_catalog_journey,
    publish_composed_v3_journey,
)
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    AuditEntry,
    Enrollment,
    EnrollmentStatus,
    JourneyCompletionPolicy,
    JourneyAdmissionDecision,
    JourneyDefinition,
    JourneyDefinitionStatus,
    JourneyStageVersion,
    JourneyVersion,
    LearningMaterialCompletion,
    FormalAdmissionDecisionType,
    OutboxEvent,
    OutboxStatus,
    Role,
    RoleAssignment,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)
from journey_api.schemas import (
    AssignmentJourneyStageOut,
    AssignmentOut,
    AssignmentResponse,
    AssembleFormalJourneyV3Command,
    CompleteLearningMaterialCommand,
    CommandOut,
    CommandResponse,
    CreateFormalAdmissionDecisionCommand,
    CreateTaskDefinitionCommand,
    CurrentActionOut,
    CurrentActionResponse,
    HealthOut,
    FormalJourneyStageOut,
    FormalJourneyVersionListOut,
    FormalJourneyVersionListResponse,
    FormalJourneyVersionOut,
    FormalJourneyVersionResponse,
    FormalAdmissionDecisionOut,
    FormalAdmissionPreviewOut,
    JourneyProgressNodeOut,
    JourneyProgressOut,
    LearnerEnrollmentListOut,
    LearnerEnrollmentListResponse,
    LearnerEnrollmentOut,
    LearningMaterialCompletionOut,
    LearningMaterialCompletionResponse,
    LearningMaterialOut,
    PublishFormalJourneyCommand,
    PreviewFormalAdmissionCommand,
    RevisionCommand,
    PublishTaskVersionCommand,
    TaskDefinitionListOut,
    TaskDefinitionListResponse,
    TaskDefinitionOut,
    TaskDefinitionResponse,
    TaskVersionOut,
    TaskVersionResponse,
    TaskVersionSummaryOut,
)
from journey_api.submission_service import assignment_workspace

router = APIRouter()
api = APIRouter(prefix="/api/v1")

def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def lock_learner_assignment(session: Session, actor: Actor, assignment_id: uuid.UUID) -> Assignment:
    assignment, _enrollment = lock_active_learner_assignment(
        session, actor, assignment_id
    )
    return assignment


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def add_event(session: Session, event_type: str, aggregate_type: str, aggregate_id: uuid.UUID) -> None:
    session.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload={"aggregate_id": str(aggregate_id)},
            status=OutboxStatus.PENDING,
        )
    )


def add_audit(
    session: Session,
    *,
    request: Request,
    actor: Actor,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    details: dict[str, object],
) -> None:
    session.add(
        AuditEntry(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result="SUCCESS",
            request_id=request.state.request_id,
            details=details,
        )
    )


def task_definition_out(
    session: Session, definition: TaskDefinition, *, replay: bool = False
) -> TaskDefinitionOut:
    versions = session.scalars(
        select(TaskVersion)
        .where(TaskVersion.task_definition_id == definition.id)
        .order_by(TaskVersion.version)
    ).all()
    return TaskDefinitionOut(
        id=definition.id,
        stable_key=definition.stable_key,
        status=definition.status.value,
        revision=definition.revision,
        content_owner_id=definition.created_by,
        versions=[
            TaskVersionSummaryOut(
                id=version.id,
                version=version.version,
                title=version.title,
                published_at=version.published_at,
            )
            for version in versions
        ],
        idempotency_replay=replay,
    )


def task_version_out(
    version: TaskVersion, stable_key: str, *, replay: bool = False
) -> TaskVersionOut:
    return TaskVersionOut(
        id=version.id,
        task_definition_id=version.task_definition_id,
        stable_key=stable_key,
        version=version.version,
        title=version.title,
        purpose=version.purpose,
        learner_outcome=version.learner_outcome,
        instructions=version.instructions,
        completion_criteria=version.completion_criteria,
        required_deliverables=version.required_deliverables,
        content_source_notes=version.content_source_notes,
        change_summary=version.change_summary,
        reviewer_calibration_note=version.reviewer_calibration_note,
        allowed_attachment_types=version.allowed_attachment_types,
        max_attachment_size_bytes=version.max_attachment_size_bytes,
        reference_materials=version.reference_materials,
        learning_materials=version.learning_materials,
        learning_experience=version.learning_experience,
        estimated_duration_minutes=version.estimated_duration_minutes,
        rubric=version.rubric,
        rubric_version=version.rubric_version,
        reviewer_role=version.reviewer_role,
        feedback_sla_business_days=version.feedback_sla_business_days,
        sensitivity=version.sensitivity,
        audience=version.audience,
        published_by=version.published_by,
        reviewed_by=version.reviewed_by,
        published_at=version.published_at,
        idempotency_replay=replay,
    )


def formal_journey_out(
    session: Session, version: JourneyVersion, *, replay: bool = False
) -> FormalJourneyVersionOut:
    definition = session.scalar(
        select(JourneyDefinition).where(
            JourneyDefinition.id == version.journey_definition_id,
            JourneyDefinition.organization_id == version.organization_id,
        )
    )
    if definition is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "旅程版本缺少稳定定义。")
    stages = journey_stages(session, version.id, version.organization_id)
    return FormalJourneyVersionOut(
        id=version.id,
        stable_key=definition.stable_key,
        version=version.version,
        title=version.title,
        purpose=version.purpose,
        change_summary=version.change_summary,
        content_review_note=version.content_review_note,
        published_at=version.published_at,
        stages=[
            FormalJourneyStageOut(
                id=stage.id,
                stable_key=stage.stable_key,
                position=stage.position,
                stage_kind=stage.stage_kind.value,
                completion_policy=stage.completion_policy.value,
                task_version_id=stage.task_version_id,
                title=stage.title,
                short_description=stage.short_description,
            )
            for stage in stages
        ],
        idempotency_replay=replay,
    )


def formal_admission_out(
    decision: JourneyAdmissionDecision, *, replay: bool = False
) -> FormalAdmissionDecisionOut:
    return FormalAdmissionDecisionOut(
        id=decision.id,
        enrollment_id=decision.enrollment_id,
        journey_version_id=decision.journey_version_id,
        outcome_id=decision.outcome_id,
        total_score=decision.total_score,
        recommendation_tier=decision.recommendation_tier,
        scorecard=decision.scorecard,
        source_evaluation_ids=decision.source_evaluation_ids,
        decision=decision.decision.value,
        decision_reason=decision.decision_reason,
        override_reason=decision.override_reason,
        decided_by=decision.decided_by,
        created_at=decision.created_at,
        idempotency_replay=replay,
    )


@router.get("/health/live", response_model=HealthOut)
def live() -> HealthOut:
    return HealthOut(status="ok", release=get_settings().app_release)


@router.get("/health/ready", response_model=HealthOut)
def ready(session: Session = Depends(get_db)) -> HealthOut:
    session.execute(select(1))
    return HealthOut(status="ok", release=get_settings().app_release)


@api.post("/ops/task-definitions", response_model=TaskDefinitionResponse)
def create_task_definition(
    command: CreateTaskDefinitionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="task_definition.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        definition = session.get(TaskDefinition, uuid.UUID(str(replay["id"])))
        if definition is None or definition.organization_id != actor.organization_id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的任务定义已不可用。")
        return envelope(request, task_definition_out(session, definition, replay=True))
    existing = session.scalar(
        select(TaskDefinition).where(
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.stable_key == command.stable_key,
        )
    )
    if existing is not None:
        raise ApiError(409, "VERSION_CONFLICT", "同一组织内已存在这个稳定任务编号。")
    definition = TaskDefinition(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        stable_key=command.stable_key,
        status=TaskDefinitionStatus.DRAFT,
        revision=1,
        created_by=actor.id,
    )
    session.add(definition)
    result = {
        "id": str(definition.id),
        "stable_key": definition.stable_key,
        "status": definition.status.value,
        "revision": definition.revision,
    }
    store_result(
        session,
        actor_id=actor.id,
        command="task_definition.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request=request,
        actor=actor,
        action="task_definition.created",
        resource_type="task_definition",
        resource_id=definition.id,
        details={"stable_key": definition.stable_key},
    )
    session.commit()
    return envelope(request, task_definition_out(session, definition))


@api.get("/ops/task-definitions", response_model=TaskDefinitionListResponse)
def list_task_definitions(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    definitions = session.scalars(
        select(TaskDefinition)
        .where(TaskDefinition.organization_id == actor.organization_id)
        .order_by(TaskDefinition.stable_key)
    ).all()
    return envelope(
        request,
        TaskDefinitionListOut(
            items=[task_definition_out(session, definition) for definition in definitions]
        ),
    )


@api.post(
    "/ops/task-definitions/{task_definition_id}/publish",
    response_model=TaskVersionResponse,
)
def publish_task_version(
    task_definition_id: uuid.UUID,
    command: PublishTaskVersionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {
        **command.model_dump(mode="json"),
        "task_definition_id": str(task_definition_id),
    }
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="task_version.publish",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        version = session.get(TaskVersion, uuid.UUID(str(replay["id"])))
        definition = session.get(TaskDefinition, task_definition_id)
        if (
            version is None
            or definition is None
            or version.organization_id != actor.organization_id
            or definition.organization_id != actor.organization_id
        ):
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的任务版本已不可用。")
        return envelope(request, task_version_out(version, definition.stable_key, replay=True))

    definition = session.scalar(
        select(TaskDefinition)
        .where(
            TaskDefinition.id == task_definition_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.created_by == actor.id,
        )
        .with_for_update()
    )
    if definition is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可发布的任务定义。")
    ensure_revision(definition.revision, command.expected_revision)
    if definition.status == TaskDefinitionStatus.WITHDRAWN:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已撤销的任务定义不能发布新版本。")
    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.reviewed_by,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "内容复核人必须是同组织的有效 Reviewer。")
    next_version = (
        session.scalar(
            select(func.max(TaskVersion.version)).where(
                TaskVersion.task_definition_id == definition.id
            )
        )
        or 0
    ) + 1
    version = TaskVersion(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        task_definition_id=definition.id,
        version=next_version,
        title=command.title.strip(),
        purpose=command.purpose.strip(),
        learner_outcome=command.learner_outcome.strip(),
        instructions=command.instructions,
        completion_criteria=command.completion_criteria,
        required_deliverables=command.required_deliverables,
        content_source_notes=command.content_source_notes,
        change_summary=command.change_summary.strip(),
        reviewer_calibration_note=command.reviewer_calibration_note.strip(),
        allowed_attachment_types=command.allowed_attachment_types,
        max_attachment_size_bytes=command.max_attachment_size_bytes,
        reference_materials=command.reference_materials,
        learning_materials=[
            material.model_dump(mode="json") for material in command.learning_materials
        ],
        learning_experience={},
        estimated_duration_minutes=command.estimated_duration_minutes,
        rubric=command.rubric.model_dump(mode="json"),
        rubric_version=command.rubric.version,
        reviewer_role=command.reviewer_role,
        feedback_sla_business_days=command.feedback_sla_business_days,
        sensitivity=command.sensitivity,
        audience=command.audience,
        published_by=actor.id,
        reviewed_by=command.reviewed_by,
    )
    session.add(version)
    session.flush()
    definition.status = TaskDefinitionStatus.PUBLISHED
    definition.revision += 1
    result = {"id": str(version.id), "task_definition_id": str(definition.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="task_version.publish",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "task_version.published.v1", "task_definition", definition.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="task_version.published",
        resource_type="task_version",
        resource_id=version.id,
        details={
            "stable_key": definition.stable_key,
            "version": next_version,
            "drafted_by": str(definition.created_by),
            "reviewed_by": str(command.reviewed_by),
            "rubric_version": command.rubric.version,
            "sensitivity": command.sensitivity,
            "audience": command.audience,
            "reference_material_count": len(command.reference_materials),
            "content_source_count": len(command.content_source_notes),
            "change_summary": command.change_summary.strip(),
            "reviewer_calibration_note": command.reviewer_calibration_note.strip(),
        },
    )
    session.commit()
    return envelope(request, task_version_out(version, definition.stable_key))


@api.get(
    "/ops/formal-journeys",
    response_model=FormalJourneyVersionListResponse,
)
def list_formal_journeys(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    versions = session.scalars(
        select(JourneyVersion)
        .join(
            JourneyDefinition,
            JourneyDefinition.id == JourneyVersion.journey_definition_id,
        )
        .where(
            JourneyVersion.organization_id == actor.organization_id,
            JourneyDefinition.organization_id == actor.organization_id,
            JourneyDefinition.status == JourneyDefinitionStatus.PUBLISHED,
        )
        .order_by(JourneyVersion.published_at.desc())
    ).all()
    return envelope(
        request,
        FormalJourneyVersionListOut(
            items=[formal_journey_out(session, version) for version in versions]
        ),
    )


@api.post(
    "/ops/formal-journeys/publish",
    response_model=FormalJourneyVersionResponse,
)
def publish_formal_journey(
    command: PublishFormalJourneyCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="formal_journey.publish",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        version = session.get(JourneyVersion, uuid.UUID(str(replay["id"])))
        if version is None or version.organization_id != actor.organization_id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的旅程版本已不可用。")
        return envelope(request, formal_journey_out(session, version, replay=True))

    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.reviewed_by,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "内容复核人必须是同组织的有效 Reviewer。")
    version = publish_catalog_journey(
        session,
        operator_id=actor.id,
        reviewer_id=reviewer.id,
        organization_id=actor.organization_id,
        expected_current_version=command.expected_current_version,
    )
    result = {"id": str(version.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="formal_journey.publish",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "formal_journey.published.v2", "journey_version", version.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="formal_journey.published",
        resource_type="journey_version",
        resource_id=version.id,
        details={
            "reviewed_by": str(reviewer.id),
            "review_acknowledged": command.review_acknowledged,
            "stage_count": 8,
            "audience": "FORMAL_CAMP_V2",
            "catalog_version": command.catalog_version,
            "previous_version": command.expected_current_version,
        },
    )
    session.commit()
    return envelope(request, formal_journey_out(session, version))


@api.post(
    "/ops/formal-journeys/assemble-v3",
    response_model=FormalJourneyVersionResponse,
)
def assemble_formal_journey_v3(
    command: AssembleFormalJourneyV3Command,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="formal_journey.assemble_v3",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        version = session.get(JourneyVersion, uuid.UUID(str(replay["id"])))
        if version is None or version.organization_id != actor.organization_id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的旅程版本已不可用。")
        return envelope(request, formal_journey_out(session, version, replay=True))
    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.reviewed_by,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "内容复核人必须是同组织的有效 Reviewer。")
    version = publish_composed_v3_journey(
        session,
        operator_id=actor.id,
        reviewer_id=reviewer.id,
        organization_id=actor.organization_id,
        expected_current_version=command.expected_current_version,
        task_version_ids=command.task_version_ids,
        content_review_note=command.content_review_note,
    )
    result = {"id": str(version.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="formal_journey.assemble_v3",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "formal_journey.published.v3", "journey_version", version.id)
    add_audit(
        session,
        request=request,
        actor=actor,
        action="formal_journey.v3_published",
        resource_type="journey_version",
        resource_id=version.id,
        details={
            "reviewed_by": str(reviewer.id),
            "review_acknowledged": True,
            "stage_count": 8,
            "audience": "FORMAL_CAMP_V3",
            "previous_version": command.expected_current_version,
            "task_version_ids": [str(item) for item in command.task_version_ids],
        },
    )
    session.commit()
    return envelope(request, formal_journey_out(session, version))


def preview_formal_admission(
    enrollment_id: uuid.UUID,
    command: PreviewFormalAdmissionCommand,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    enrollment = session.scalar(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == actor.organization_id,
        )
    )
    if enrollment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可评分的 Enrollment。")
    _outcome, scorecard, evaluation_ids, tier = formal_admission_scorecard(
        session,
        enrollment,
        human_scores=command.scores.model_dump(),
        score_evidence="PREVIEW_ONLY",
    )
    recommended_decision = "ADMIT" if tier in {"A", "B"} else "DEFER" if tier == "C" else "NOT_ADMIT"
    return envelope(
        request,
        FormalAdmissionPreviewOut(
            enrollment_id=enrollment.id,
            total_score=int(dict(scorecard["total"])["score"]),
            recommendation_tier=tier,
            recommended_decision=recommended_decision,
            scorecard=scorecard,
            source_evaluation_ids=evaluation_ids,
        ),
    )


def create_formal_admission_decision(
    enrollment_id: uuid.UUID,
    command: CreateFormalAdmissionDecisionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {**command.model_dump(mode="json"), "enrollment_id": str(enrollment_id)}
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="formal_admission.decide",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        decision = session.get(JourneyAdmissionDecision, uuid.UUID(str(replay["id"])))
        if decision is None or decision.organization_id != actor.organization_id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等结果引用的准入结论已不可用。")
        return envelope(request, formal_admission_out(decision, replay=True))

    enrollment = session.scalar(
        select(Enrollment)
        .where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if enrollment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可处置的 Enrollment。")
    existing = session.scalar(
        select(JourneyAdmissionDecision).where(
            JourneyAdmissionDecision.enrollment_id == enrollment.id,
            JourneyAdmissionDecision.organization_id == actor.organization_id,
        )
    )
    if existing is not None:
        raise ApiError(409, "VERSION_CONFLICT", "该 Enrollment 已有不可变人工准入结论。")
    if enrollment.journey_version_id is None:
        raise ApiError(422, "VALIDATION_FAILED", "Enrollment 未绑定正式探索营版本。")

    outcome, scorecard, evaluation_ids, tier = formal_admission_scorecard(
        session,
        enrollment,
        human_scores=command.scores.model_dump(),
        score_evidence=command.score_evidence,
    )
    recommended_decision = "ADMIT" if tier in {"A", "B"} else "DEFER" if tier == "C" else "NOT_ADMIT"
    if command.decision != recommended_decision and not command.override_reason:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "人工结论与分档建议不一致时必须记录覆盖理由。",
        )
    decision = JourneyAdmissionDecision(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        enrollment_id=enrollment.id,
        journey_version_id=enrollment.journey_version_id,
        outcome_id=outcome.id,
        total_score=int(dict(scorecard["total"])["score"]),
        recommendation_tier=tier,
        scorecard=scorecard,
        source_evaluation_ids=[str(item) for item in evaluation_ids],
        decision=FormalAdmissionDecisionType(command.decision),
        decision_reason=command.decision_reason,
        override_reason=command.override_reason,
        decided_by=actor.id,
    )
    session.add(decision)
    session.flush()
    store_result(
        session,
        actor_id=actor.id,
        command="formal_admission.decide",
        key=idempotency_key,
        payload=payload,
        response={"id": str(decision.id)},
    )
    add_audit(
        session,
        request=request,
        actor=actor,
        action="formal_admission.decided",
        resource_type="journey_admission_decision",
        resource_id=decision.id,
        details={
            "enrollment_id": str(enrollment.id),
            "journey_version_id": str(enrollment.journey_version_id),
            "total_score": decision.total_score,
            "recommendation_tier": tier,
            "decision": decision.decision.value,
            "override_recorded": bool(command.override_reason),
            "score_evidence_characters": len(command.score_evidence),
            "decision_reason_characters": len(command.decision_reason),
            "human_judgement_acknowledged": command.human_judgement_acknowledged,
        },
    )
    session.commit()
    return envelope(request, formal_admission_out(decision))


@api.get("/me/current-action", response_model=CurrentActionResponse)
def current_action(
    request: Request,
    enrollment_id: uuid.UUID | None = None,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    enrollment_query = select(Enrollment).where(
        Enrollment.organization_id == actor.organization_id,
        Enrollment.learner_id == actor.id,
    )
    if enrollment_id is not None:
        enrollment_query = enrollment_query.where(Enrollment.id == enrollment_id)
    else:
        enrollment_query = enrollment_query.order_by(
            case(
                (Enrollment.status == EnrollmentStatus.ACTIVE, 0),
                (Enrollment.status == EnrollmentStatus.PENDING_IDENTITY, 1),
                (Enrollment.status == EnrollmentStatus.COMPLETED, 2),
                else_=3,
            ),
            Enrollment.revision.desc(),
        )
    enrollment = session.scalar(enrollment_query)
    if enrollment_id is not None and enrollment is None:
        raise ApiError(404, "NOT_FOUND", "找不到当前账号可访问的模块加入记录。")
    assignment_rows: list[
        tuple[Assignment, TaskVersion, JourneyStageVersion | None]
    ] = []
    reviewer: User | None = None
    if enrollment is not None:
        assignment_rows = list(
            session.execute(
                select(Assignment, TaskVersion, JourneyStageVersion)
                .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
                .outerjoin(
                    JourneyStageVersion,
                    JourneyStageVersion.id == Assignment.journey_stage_version_id,
                )
                .where(
                    Assignment.enrollment_id == enrollment.id,
                    Assignment.organization_id == actor.organization_id,
                    TaskVersion.organization_id == actor.organization_id,
                )
                .order_by(Assignment.position, Assignment.id)
            ).all()
        )
        reviewer = session.scalar(
            select(User).where(
                User.id == enrollment.reviewer_id,
                User.organization_id == actor.organization_id,
            )
        )
    action = resolve_current_action(
        fallback_resource_id=enrollment.id if enrollment is not None else actor.id,
        fallback_revision=enrollment.revision if enrollment is not None else 1,
        enrollment_status=enrollment.status if enrollment is not None else None,
        assignments=tuple(
            AssignmentActionState(
                id=assignment.id,
                status=assignment.status,
                revision=assignment.revision,
                position=assignment.position,
                stage_key=stage.stable_key if stage is not None else None,
                stage_title=stage.title if stage is not None else None,
                stage_kind=stage.stage_kind if stage is not None else None,
                completion_policy=(
                    stage.completion_policy.value if stage is not None else None
                ),
            )
            for assignment, _, stage in assignment_rows
        ),
        journey_version_bound=enrollment.journey_version_id is not None
        if enrollment is not None
        else False,
    )
    selected_task = next(
        (
            task
            for assignment, task, _stage in assignment_rows
            if assignment.id == action.resource_id
        ),
        None,
    )
    selected_stage = next(
        (
            stage
            for assignment, _task, stage in assignment_rows
            if assignment.id == action.resource_id
        ),
        None,
    )
    journey_progress: JourneyProgressOut | None = None
    if enrollment is not None and enrollment.journey_version_id is not None:
        journey_version = session.scalar(
            select(JourneyVersion).where(
                JourneyVersion.id == enrollment.journey_version_id,
                JourneyVersion.organization_id == actor.organization_id,
            )
        )
        journey_definition = (
            session.scalar(
                select(JourneyDefinition).where(
                    JourneyDefinition.id == journey_version.journey_definition_id,
                    JourneyDefinition.organization_id == actor.organization_id,
                )
            )
            if journey_version is not None
            else None
        )
        if journey_version is None or journey_definition is None:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "当前旅程版本不可用。")
        completed_stages = sum(
            assignment.status == AssignmentStatus.COMPLETED
            for assignment, _task, stage in assignment_rows
            if stage is not None
        )
        current_stage_key = next(
            (
                stage.stable_key
                for assignment, _task, stage in assignment_rows
                if stage is not None and assignment.id == action.resource_id
            ),
            None,
        )
        journey_progress = JourneyProgressOut(
            journey_version_id=journey_version.id,
            stable_key=journey_definition.stable_key,
            version=journey_version.version,
            title=journey_version.title,
            completed_stages=completed_stages,
            total_stages=sum(stage is not None for _, _, stage in assignment_rows),
            current_stage_key=current_stage_key,
            nodes=[
                JourneyProgressNodeOut(
                    stable_key=stage.stable_key,
                    position=stage.position,
                    stage_kind=stage.stage_kind.value,
                    completion_policy=stage.completion_policy.value,
                    title=stage.title,
                    short_description=stage.short_description,
                    status=(
                        "COMPLETED"
                        if assignment.status == AssignmentStatus.COMPLETED
                        else "CURRENT"
                        if assignment.id == action.resource_id
                        else "LOCKED"
                    ),
                    assignment_id=assignment.id,
                )
                for assignment, _task, stage in assignment_rows
                if stage is not None
            ],
        )
    data = CurrentActionOut(
        action_type=action.action_type,
        stage=action.stage,
        resource_id=action.resource_id,
        title=action.title,
        reason=action.reason,
        allowed_commands=list(action.allowed_commands),
        revision=action.revision,
        responsible_party=(
            "由你完成证据"
            if selected_stage is not None
            and selected_stage.completion_policy
            == JourneyCompletionPolicy.LEARNER_EVIDENCE
            else reviewer.display_name
            if reviewer is not None
            else "运营支持"
        ),
        feedback_expectation=(
            "提交后进入下一站"
            if selected_stage is not None
            and selected_stage.completion_policy
            == JourneyCompletionPolicy.LEARNER_EVIDENCE
            else f"{selected_task.feedback_sla_business_days} 个工作日内"
            if selected_task is not None
            else "按当前加入状态处理"
        ),
        journey=journey_progress,
    )
    return envelope(request, data)


@api.get("/me/enrollments", response_model=LearnerEnrollmentListResponse)
def learner_enrollments(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    rows = session.execute(
        select(Enrollment, JourneyVersion, JourneyDefinition, User)
        .outerjoin(
            JourneyVersion,
            (JourneyVersion.id == Enrollment.journey_version_id)
            & (JourneyVersion.organization_id == Enrollment.organization_id),
        )
        .outerjoin(
            JourneyDefinition,
            (JourneyDefinition.id == JourneyVersion.journey_definition_id)
            & (JourneyDefinition.organization_id == Enrollment.organization_id),
        )
        .join(
            User,
            (User.id == Enrollment.reviewer_id)
            & (User.organization_id == Enrollment.organization_id),
        )
        .where(
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
        )
        .order_by(
            case(
                (Enrollment.status == EnrollmentStatus.ACTIVE, 0),
                (Enrollment.status == EnrollmentStatus.PENDING_IDENTITY, 1),
                (Enrollment.status == EnrollmentStatus.COMPLETED, 2),
                else_=3,
            ),
            JourneyDefinition.stable_key,
            Enrollment.id,
        )
    ).all()
    return envelope(
        request,
        LearnerEnrollmentListOut(
            items=[
                LearnerEnrollmentOut(
                    id=enrollment.id,
                    status=enrollment.status.value,
                    revision=enrollment.revision,
                    journey_version_id=enrollment.journey_version_id,
                    journey_stable_key=(
                        definition.stable_key if definition is not None else None
                    ),
                    journey_title=version.title if version is not None else None,
                    journey_version=version.version if version is not None else None,
                    reviewer_display_name=reviewer.display_name,
                )
                for enrollment, version, definition, reviewer in rows
            ]
        ),
    )


@api.get("/me/assignments/{assignment_id}", response_model=AssignmentResponse)
def assignment_detail(
    assignment_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    row = session.execute(
        select(Assignment, TaskVersion, TaskDefinition, JourneyStageVersion)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(TaskVersion, TaskVersion.id == Assignment.task_version_id)
        .join(TaskDefinition, TaskDefinition.id == Assignment.task_definition_id)
        .outerjoin(
            JourneyStageVersion,
            JourneyStageVersion.id == Assignment.journey_stage_version_id,
        )
        .where(
            Assignment.id == assignment_id,
            Assignment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
            TaskVersion.organization_id == actor.organization_id,
            TaskDefinition.organization_id == actor.organization_id,
        )
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    assignment, task, definition, journey_stage = row
    commands = () if assignment.status == AssignmentStatus.CANCELLED else assignment_action(assignment.status)[4]
    submission, draft, available_attachments, latest_feedback = assignment_workspace(
        session, actor, assignment.id
    )
    material_completions = completed_materials(session, assignment)
    data = AssignmentOut(
        id=assignment.id,
        status=public_assignment_status(
            assignment.status,
            formal=(
                journey_stage is None
                or journey_stage.completion_policy
                is JourneyCompletionPolicy.REVIEW_REQUIRED
            ),
        ),
        revision=assignment.revision,
        allowed_commands=list(commands),
        stable_task_key=definition.stable_key,
        task_version=task.version,
        task_title=task.title,
        task_purpose=task.purpose,
        learner_outcome=task.learner_outcome,
        instructions=task.instructions,
        completion_criteria=task.completion_criteria,
        required_deliverables=task.required_deliverables,
        allowed_attachment_types=(
            task.allowed_attachment_types if get_settings().attachments_enabled else []
        ),
        max_attachment_size_bytes=(
            task.max_attachment_size_bytes if get_settings().attachments_enabled else 0
        ),
        reference_materials=task.reference_materials,
        learning_materials=[
            LearningMaterialOut(
                **material,
                completed_at=(
                    material_completions[str(material["key"])].completed_at
                    if str(material.get("key")) in material_completions
                    else None
                ),
            )
            for material in task.learning_materials
            if isinstance(material, dict) and material.get("key")
        ],
        learning_experience=task.learning_experience,
        estimated_duration_minutes=task.estimated_duration_minutes,
        feedback_sla_business_days=task.feedback_sla_business_days,
        rubric=task.rubric,
        submission=submission,
        draft=draft,
        available_attachments=available_attachments,
        latest_revision_feedback=latest_feedback,
        journey_stage=(
            AssignmentJourneyStageOut(
                stable_key=journey_stage.stable_key,
                position=journey_stage.position,
                stage_kind=journey_stage.stage_kind.value,
                completion_policy=journey_stage.completion_policy.value,
                title=journey_stage.title,
                short_description=journey_stage.short_description,
            )
            if journey_stage is not None
            else None
        ),
    )
    return envelope(request, data)


@api.post(
    "/me/assignments/{assignment_id}/materials/{material_key}/complete",
    response_model=LearningMaterialCompletionResponse,
)
def complete_learning_material(
    assignment_id: uuid.UUID,
    material_key: str,
    command: CompleteLearningMaterialCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = {
        **command.model_dump(mode="json"),
        "assignment_id": str(assignment_id),
        "material_key": material_key,
    }
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="learning_material.complete",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(
            request,
            LearningMaterialCompletionOut(
                **{**replay, "idempotency_replay": True}
            ),
        )
    assignment, enrollment = lock_active_learner_assignment(
        session, actor, assignment_id
    )
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="learning_material.complete",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return envelope(
            request,
            LearningMaterialCompletionOut(
                **{**replay, "idempotency_replay": True}
            ),
        )
    task = session.get(TaskVersion, assignment.task_version_id)
    if task is None or task.organization_id != actor.organization_id:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少固定内容版本。")
    if task.version != command.task_version:
        raise ApiError(409, "VERSION_CONFLICT", "学习材料版本已变化，请刷新后重试。")
    material_by_key(task, material_key)
    existing = session.scalar(
        select(LearningMaterialCompletion).where(
            LearningMaterialCompletion.organization_id == actor.organization_id,
            LearningMaterialCompletion.assignment_id == assignment.id,
            LearningMaterialCompletion.task_version_id == task.id,
            LearningMaterialCompletion.material_key == material_key,
        )
    )
    if existing is not None:
        result = LearningMaterialCompletionOut(
            assignment_id=assignment.id,
            task_version=task.version,
            material_key=existing.material_key,
            completed_at=existing.completed_at,
        )
    else:
        if assignment.status not in {
            AssignmentStatus.AVAILABLE,
            AssignmentStatus.IN_PROGRESS,
            AssignmentStatus.NEEDS_REVISION,
        }:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "当前任务不能记录材料完成。")
        completion = LearningMaterialCompletion(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            enrollment_id=enrollment.id,
            assignment_id=assignment.id,
            task_version_id=task.id,
            learner_id=actor.id,
            material_key=material_key,
        )
        session.add(completion)
        session.flush()
        result = LearningMaterialCompletionOut(
            assignment_id=assignment.id,
            task_version=task.version,
            material_key=completion.material_key,
            completed_at=completion.completed_at,
        )
        add_event(
            session,
            "learning_material.completed.v1",
            "learning_material_completion",
            completion.id,
        )
        add_audit(
            session,
            request=request,
            actor=actor,
            action="learning_material.completed",
            resource_type="learning_material_completion",
            resource_id=completion.id,
            details={
                "assignment_id": str(assignment.id),
                "task_version_id": str(task.id),
                "material_key": material_key,
            },
        )
    serialized = result.model_dump(mode="json")
    store_result(
        session,
        actor_id=actor.id,
        command="learning_material.complete",
        key=idempotency_key,
        payload=payload,
        response=serialized,
    )
    session.commit()
    return envelope(request, result)


@api.post("/me/assignments/{assignment_id}/start", response_model=CommandResponse)
def start_assignment(
    assignment_id: uuid.UUID,
    command: RevisionCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.LEARNER)
    payload = command.model_dump(mode="json")
    replay = find_replay(
        session, actor_id=actor.id, command="assignment.start", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    assignment = lock_learner_assignment(session, actor, assignment_id)
    replay = find_replay(
        session, actor_id=actor.id, command="assignment.start", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return envelope(request, CommandOut(**replay))
    ensure_revision(assignment.revision, command.expected_revision)
    enrollment = session.get(Enrollment, assignment.enrollment_id)
    if enrollment is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少有效 Enrollment。")
    try:
        target_status = transition_formal_assignment(
            current=assignment.status,
            event=FormalAssignmentEvent.START,
            actor_kind=WorkflowActorKind.LEARNER,
            actor_id=actor.id,
            learner_id=enrollment.learner_id,
            assigned_reviewer_id=enrollment.reviewer_id,
        )
    except FormalAssignmentTransitionError as exc:
        raise ApiError(
            409, "INVALID_STATE_TRANSITION", "当前任务不能执行开始操作。"
        ) from exc
    ensure_required_materials_completed(session, assignment)
    assignment.status = target_status
    assignment.revision += 1
    result = {"resource_id": str(assignment.id), "status": assignment.status.value, "revision": assignment.revision}
    store_result(
        session,
        actor_id=actor.id,
        command="assignment.start",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_event(session, "assignment.started.v1", "assignment", assignment.id)
    session.commit()
    return envelope(request, CommandOut(**result))


router.include_router(api)
