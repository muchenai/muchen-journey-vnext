from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor
from journey_api.errors import ApiError
from journey_api.formal_journey_catalog import (
    CONTENT_REVIEW_NOTE,
    FORMAL_JOURNEY_KEY,
    FORMAL_JOURNEY_PURPOSE,
    FORMAL_JOURNEY_TITLE,
    FORMAL_STAGE_CATALOG,
    task_version_values,
)
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    JourneyCompletionPolicy,
    JourneyDefinition,
    JourneyDefinitionStatus,
    JourneyStageKind,
    JourneyStageVersion,
    JourneyVersion,
    Review,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
)


@dataclass(frozen=True)
class FormalEvaluationEvidence:
    stage: JourneyStageVersion
    evaluation: Evaluation


def published_formal_journey(
    session: Session, organization_id: uuid.UUID
) -> JourneyVersion | None:
    return session.scalar(
        select(JourneyVersion)
        .join(
            JourneyDefinition,
            JourneyDefinition.id == JourneyVersion.journey_definition_id,
        )
        .where(
            JourneyVersion.organization_id == organization_id,
            JourneyDefinition.organization_id == organization_id,
            JourneyDefinition.stable_key == FORMAL_JOURNEY_KEY,
            JourneyDefinition.status == JourneyDefinitionStatus.PUBLISHED,
        )
        .order_by(JourneyVersion.version.desc())
    )


def journey_stages(
    session: Session, journey_version_id: uuid.UUID, organization_id: uuid.UUID
) -> list[JourneyStageVersion]:
    return list(
        session.scalars(
            select(JourneyStageVersion)
            .where(
                JourneyStageVersion.journey_version_id == journey_version_id,
                JourneyStageVersion.organization_id == organization_id,
            )
            .order_by(JourneyStageVersion.position, JourneyStageVersion.id)
        ).all()
    )


def validate_published_structure(stages: list[JourneyStageVersion]) -> None:
    if len(stages) != 8 or [stage.position for stage in stages] != list(range(8)):
        raise ApiError(
            409,
            "INVALID_STATE_TRANSITION",
            "正式探索营版本必须包含连续的 Day 0、四个宝藏和三个能力评测。",
        )
    expected_kinds = [
        JourneyStageKind.DAY_0,
        *([JourneyStageKind.TREASURE] * 4),
        *([JourneyStageKind.ASSESSMENT] * 3),
    ]
    if [stage.stage_kind for stage in stages] != expected_kinds:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "正式探索营阶段类型或顺序无效。")
    for stage in stages:
        expected_policy = (
            JourneyCompletionPolicy.REVIEW_REQUIRED
            if stage.stage_kind == JourneyStageKind.ASSESSMENT
            else JourneyCompletionPolicy.LEARNER_EVIDENCE
        )
        if stage.completion_policy != expected_policy:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "正式探索营阶段完成策略无效。")


def publish_catalog_journey(
    session: Session,
    *,
    operator_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> JourneyVersion:
    existing = published_formal_journey(session, organization_id)
    if existing is not None:
        raise ApiError(409, "VERSION_CONFLICT", "当前组织已发布正式探索营版本。")

    definition = JourneyDefinition(
        id=uuid.uuid4(),
        organization_id=organization_id,
        stable_key=FORMAL_JOURNEY_KEY,
        status=JourneyDefinitionStatus.PUBLISHED,
        revision=1,
        created_by=operator_id,
    )
    version = JourneyVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        journey_definition_id=definition.id,
        version=1,
        title=FORMAL_JOURNEY_TITLE,
        purpose=FORMAL_JOURNEY_PURPOSE,
        change_summary="建立 Day 0、四宝藏、三评测和完整结果的首个 vNext 受控内测版本。",
        content_review_note=CONTENT_REVIEW_NOTE,
        published_by=operator_id,
        reviewed_by=reviewer_id,
    )
    session.add_all([definition, version])
    session.flush()

    stage_rows: list[JourneyStageVersion] = []
    for position, item in enumerate(FORMAL_STAGE_CATALOG):
        task_definition = TaskDefinition(
            id=uuid.uuid4(),
            organization_id=organization_id,
            stable_key=item.stable_key,
            status=TaskDefinitionStatus.PUBLISHED,
            revision=1,
            created_by=operator_id,
        )
        task_version = TaskVersion(
            id=uuid.uuid4(),
            organization_id=organization_id,
            task_definition_id=task_definition.id,
            version=1,
            **task_version_values(item),
            published_by=operator_id,
            reviewed_by=reviewer_id,
        )
        stage = JourneyStageVersion(
            id=uuid.uuid4(),
            organization_id=organization_id,
            journey_version_id=version.id,
            stable_key=item.stable_key,
            position=position,
            stage_kind=item.stage_kind,
            completion_policy=item.completion_policy,
            task_version_id=task_version.id,
            title=item.title,
            short_description=item.short_description,
        )
        session.add_all([task_definition, task_version])
        stage_rows.append(stage)
    session.flush()
    session.add_all(stage_rows)
    session.flush()
    validate_published_structure(journey_stages(session, version.id, organization_id))
    return version


def create_formal_assignments(
    session: Session,
    *,
    enrollment: Enrollment,
) -> list[Assignment]:
    if enrollment.journey_version_id is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Enrollment 未绑定正式旅程版本。")
    stages = journey_stages(
        session, enrollment.journey_version_id, enrollment.organization_id
    )
    validate_published_structure(stages)
    assignments = [
        Assignment(
            id=uuid.uuid4(),
            organization_id=enrollment.organization_id,
            enrollment_id=enrollment.id,
            task_definition_id=session.scalar(
                select(TaskVersion.task_definition_id).where(
                    TaskVersion.id == stage.task_version_id,
                    TaskVersion.organization_id == enrollment.organization_id,
                )
            ),
            task_version_id=stage.task_version_id,
            journey_stage_version_id=stage.id,
            position=stage.position + 1,
            status=AssignmentStatus.AVAILABLE,
            revision=1,
        )
        for stage in stages
    ]
    if any(assignment.task_definition_id is None for assignment in assignments):
        raise ApiError(409, "INVALID_STATE_TRANSITION", "旅程阶段缺少固定任务版本。")
    session.add_all(assignments)
    return assignments


def lock_active_learner_assignment(
    session: Session, actor: Actor, assignment_id: uuid.UUID
) -> tuple[Assignment, Enrollment]:
    enrollment = session.scalar(
        select(Enrollment)
        .join(Assignment, Assignment.enrollment_id == Enrollment.id)
        .where(
            Assignment.id == assignment_id,
            Assignment.organization_id == actor.organization_id,
            Enrollment.organization_id == actor.organization_id,
            Enrollment.learner_id == actor.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
        .with_for_update(of=Enrollment)
    )
    if enrollment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    assignment = session.scalar(
        select(Assignment)
        .where(
            Assignment.id == assignment_id,
            Assignment.organization_id == actor.organization_id,
            Assignment.enrollment_id == enrollment.id,
        )
        .with_for_update()
    )
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    ensure_formal_assignment_is_current(session, enrollment, assignment)
    return assignment, enrollment


def ensure_formal_assignment_is_current(
    session: Session, enrollment: Enrollment, assignment: Assignment
) -> None:
    if enrollment.journey_version_id is None:
        return
    current_id = session.scalar(
        select(Assignment.id)
        .join(
            JourneyStageVersion,
            JourneyStageVersion.id == Assignment.journey_stage_version_id,
        )
        .where(
            Assignment.enrollment_id == enrollment.id,
            Assignment.organization_id == enrollment.organization_id,
            JourneyStageVersion.journey_version_id == enrollment.journey_version_id,
            JourneyStageVersion.organization_id == enrollment.organization_id,
            Assignment.status.not_in(
                [AssignmentStatus.COMPLETED, AssignmentStatus.CANCELLED]
            ),
        )
        .order_by(JourneyStageVersion.position, Assignment.id)
        .limit(1)
    )
    if current_id != assignment.id:
        raise ApiError(
            409,
            "JOURNEY_STAGE_LOCKED",
            "请先完成当前阶段，后续节点尚未开放。",
        )


def assignment_stage(
    session: Session, assignment: Assignment
) -> JourneyStageVersion | None:
    if assignment.journey_stage_version_id is None:
        return None
    return session.scalar(
        select(JourneyStageVersion).where(
            JourneyStageVersion.id == assignment.journey_stage_version_id,
            JourneyStageVersion.organization_id == assignment.organization_id,
        )
    )


def formal_evaluation_evidence(
    session: Session, enrollment: Enrollment
) -> list[FormalEvaluationEvidence]:
    if enrollment.journey_version_id is None:
        return []
    rows = session.execute(
        select(JourneyStageVersion, Evaluation)
        .join(Assignment, Assignment.journey_stage_version_id == JourneyStageVersion.id)
        .join(Review, Review.assignment_id == Assignment.id)
        .join(Evaluation, Evaluation.review_id == Review.id)
        .where(
            Assignment.enrollment_id == enrollment.id,
            Assignment.organization_id == enrollment.organization_id,
            Assignment.status == AssignmentStatus.COMPLETED,
            JourneyStageVersion.journey_version_id == enrollment.journey_version_id,
            JourneyStageVersion.organization_id == enrollment.organization_id,
            JourneyStageVersion.stage_kind == JourneyStageKind.ASSESSMENT,
            JourneyStageVersion.completion_policy
            == JourneyCompletionPolicy.REVIEW_REQUIRED,
            Evaluation.organization_id == enrollment.organization_id,
            Evaluation.decision == Decision.PASS,
        )
        .order_by(JourneyStageVersion.position)
    ).all()
    return [FormalEvaluationEvidence(stage, evaluation) for stage, evaluation in rows]


def formal_journey_is_complete(session: Session, enrollment: Enrollment) -> bool:
    if enrollment.journey_version_id is None:
        return False
    expected = session.scalar(
        select(func.count(JourneyStageVersion.id)).where(
            JourneyStageVersion.journey_version_id == enrollment.journey_version_id,
            JourneyStageVersion.organization_id == enrollment.organization_id,
        )
    )
    completed = session.scalar(
        select(func.count(Assignment.id))
        .join(
            JourneyStageVersion,
            JourneyStageVersion.id == Assignment.journey_stage_version_id,
        )
        .where(
            Assignment.enrollment_id == enrollment.id,
            Assignment.organization_id == enrollment.organization_id,
            JourneyStageVersion.journey_version_id == enrollment.journey_version_id,
            Assignment.status == AssignmentStatus.COMPLETED,
        )
    )
    return expected == 8 and completed == expected and len(
        formal_evaluation_evidence(session, enrollment)
    ) == 3
