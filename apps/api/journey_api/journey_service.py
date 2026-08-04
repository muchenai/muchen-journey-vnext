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
    Outcome,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
)


@dataclass(frozen=True)
class FormalEvaluationEvidence:
    stage: JourneyStageVersion
    evaluation: Evaluation


FORMAL_V3_STAGE_KEYS = (
    "DAY-0",
    "TRE-001-COMPANY-VALUES",
    "TRE-002-AI-DATA-BASICS",
    "TRE-003-PROJECT-AWARENESS",
    "TRE-004-DELIVERY-FIT",
    "ASM-001-RULE-BREAKDOWN",
    "ASM-002-MODEL-JUDGEMENT",
    "ASM-003-DATA-CONSTRUCTION",
)


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
    expected_current_version: int,
) -> JourneyVersion:
    definition = session.scalar(
        select(JourneyDefinition)
        .where(
            JourneyDefinition.organization_id == organization_id,
            JourneyDefinition.stable_key == FORMAL_JOURNEY_KEY,
        )
        .with_for_update()
    )
    if definition is None:
        if expected_current_version != 0:
            raise ApiError(409, "VERSION_CONFLICT", "正式探索营当前版本已变化，请刷新后重试。")
        definition = JourneyDefinition(
            id=uuid.uuid4(),
            organization_id=organization_id,
            stable_key=FORMAL_JOURNEY_KEY,
            status=JourneyDefinitionStatus.PUBLISHED,
            revision=1,
            created_by=operator_id,
        )
        session.add(definition)
        session.flush()
        current_version = 0
    else:
        current_version = session.scalar(
            select(func.max(JourneyVersion.version)).where(
                JourneyVersion.journey_definition_id == definition.id,
                JourneyVersion.organization_id == organization_id,
            )
        ) or 0
        if current_version != expected_current_version:
            raise ApiError(409, "VERSION_CONFLICT", "正式探索营当前版本已变化，请刷新后重试。")
        current_journey_version = session.scalar(
            select(JourneyVersion).where(
                JourneyVersion.journey_definition_id == definition.id,
                JourneyVersion.organization_id == organization_id,
                JourneyVersion.version == current_version,
            )
        )
        if current_journey_version is not None and session.scalar(
            select(JourneyStageVersion.id).where(
                JourneyStageVersion.journey_version_id == current_journey_version.id,
                JourneyStageVersion.organization_id == organization_id,
                JourneyStageVersion.stable_key == "ASM-003-DATA-CONSTRUCTION",
            )
        ):
            raise ApiError(409, "VERSION_CONFLICT", "WP-24 正式探索营 V2 已发布，不得重复生成相同版本。")

    version = JourneyVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        journey_definition_id=definition.id,
        version=current_version + 1,
        title=FORMAL_JOURNEY_TITLE,
        purpose=FORMAL_JOURNEY_PURPOSE,
        change_summary="WP-24：重建一天学习内容、三项真实题面、量化评分证据与人工准入路径。",
        content_review_note=CONTENT_REVIEW_NOTE,
        published_by=operator_id,
        reviewed_by=reviewer_id,
    )
    session.add(version)
    session.flush()

    stage_rows: list[JourneyStageVersion] = []
    for position, item in enumerate(FORMAL_STAGE_CATALOG):
        task_definition = session.scalar(
            select(TaskDefinition)
            .where(
                TaskDefinition.organization_id == organization_id,
                TaskDefinition.stable_key == item.stable_key,
            )
            .with_for_update()
        )
        if task_definition is None:
            task_definition = TaskDefinition(
                id=uuid.uuid4(),
                organization_id=organization_id,
                stable_key=item.stable_key,
                status=TaskDefinitionStatus.PUBLISHED,
                revision=1,
                created_by=operator_id,
            )
            session.add(task_definition)
            session.flush()
            task_version_number = 1
        else:
            task_version_number = (
                session.scalar(
                    select(func.max(TaskVersion.version)).where(
                        TaskVersion.task_definition_id == task_definition.id,
                        TaskVersion.organization_id == organization_id,
                    )
                )
                or 0
            ) + 1
        task_version = TaskVersion(
            id=uuid.uuid4(),
            organization_id=organization_id,
            task_definition_id=task_definition.id,
            version=task_version_number,
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
        session.add(task_version)
        stage_rows.append(stage)
    session.flush()
    session.add_all(stage_rows)
    session.flush()
    validate_published_structure(journey_stages(session, version.id, organization_id))
    return version


def publish_composed_v3_journey(
    session: Session,
    *,
    operator_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    organization_id: uuid.UUID,
    expected_current_version: int,
    task_version_ids: list[uuid.UUID],
    content_review_note: str,
) -> JourneyVersion:
    """Publish a V3 composition from eight already immutable, approved task versions."""

    definition = session.scalar(
        select(JourneyDefinition)
        .where(
            JourneyDefinition.organization_id == organization_id,
            JourneyDefinition.stable_key == FORMAL_JOURNEY_KEY,
            JourneyDefinition.status == JourneyDefinitionStatus.PUBLISHED,
        )
        .with_for_update()
    )
    if definition is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "请先保留既有正式旅程定义。")
    current_version = session.scalar(
        select(func.max(JourneyVersion.version)).where(
            JourneyVersion.journey_definition_id == definition.id,
            JourneyVersion.organization_id == organization_id,
        )
    ) or 0
    if current_version != expected_current_version:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "正式探索营当前版本已变化，请刷新后重试。",
            details={"current_version": current_version},
        )
    if len(task_version_ids) != 8 or len(set(task_version_ids)) != 8:
        raise ApiError(422, "VALIDATION_FAILED", "Journey V3 必须绑定八个唯一版本。")

    task_rows: list[tuple[TaskVersion, TaskDefinition]] = []
    for expected_key, task_version_id in zip(
        FORMAL_V3_STAGE_KEYS, task_version_ids, strict=True
    ):
        row = session.execute(
            select(TaskVersion, TaskDefinition)
            .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
            .where(
                TaskVersion.id == task_version_id,
                TaskVersion.organization_id == organization_id,
                TaskDefinition.organization_id == organization_id,
                TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
            )
        ).first()
        if row is None:
            raise ApiError(422, "VALIDATION_FAILED", "Journey V3 包含不可用的任务版本。")
        task, task_definition = row
        if task_definition.stable_key != expected_key:
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                f"Journey V3 阶段顺序错误：需要 {expected_key}。",
            )
        required_materials = [
            item
            for item in task.learning_materials
            if isinstance(item, dict) and item.get("required") is True
        ]
        if not required_materials:
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                f"{expected_key} 缺少已固定的 required material。",
            )
        task_rows.append((task, task_definition))

    version = JourneyVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        journey_definition_id=definition.id,
        version=current_version + 1,
        title=f"{FORMAL_JOURNEY_TITLE} · V3",
        purpose=FORMAL_JOURNEY_PURPOSE,
        change_summary=(
            "WP-27/28：组合经 Content Editor 提交、Reviewer 复核并由 Operator "
            "发布的 Day 0、四宝藏与三项评测固定版本。"
        ),
        content_review_note=content_review_note,
        published_by=operator_id,
        reviewed_by=reviewer_id,
    )
    session.add(version)
    session.flush()
    stages: list[JourneyStageVersion] = []
    for position, (task, definition_row) in enumerate(task_rows):
        stage_kind = (
            JourneyStageKind.DAY_0
            if position == 0
            else JourneyStageKind.TREASURE
            if position < 5
            else JourneyStageKind.ASSESSMENT
        )
        completion_policy = (
            JourneyCompletionPolicy.REVIEW_REQUIRED
            if stage_kind == JourneyStageKind.ASSESSMENT
            else JourneyCompletionPolicy.LEARNER_EVIDENCE
        )
        stages.append(
            JourneyStageVersion(
                id=uuid.uuid4(),
                organization_id=organization_id,
                journey_version_id=version.id,
                stable_key=definition_row.stable_key,
                position=position,
                stage_kind=stage_kind,
                completion_policy=completion_policy,
                task_version_id=task.id,
                title=task.title,
                short_description=task.learner_outcome[:240],
            )
        )
    session.add_all(stages)
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


def formal_admission_scorecard(
    session: Session,
    enrollment: Enrollment,
    *,
    human_scores: dict[str, int],
    score_evidence: str,
) -> tuple[Outcome, dict[str, object], list[uuid.UUID], str]:
    """Build evidence for a human decision without making that decision."""

    if enrollment.status != EnrollmentStatus.COMPLETED or not formal_journey_is_complete(
        session, enrollment
    ):
        raise ApiError(422, "JOURNEY_INCOMPLETE", "只有完成正式探索营后才能进入人工准入。")
    if enrollment.journey_version_id is None:
        raise ApiError(422, "VALIDATION_FAILED", "Enrollment 未绑定正式探索营版本。")
    stages = journey_stages(
        session, enrollment.journey_version_id, enrollment.organization_id
    )
    if "ASM-003-DATA-CONSTRUCTION" not in {stage.stable_key for stage in stages}:
        raise ApiError(422, "VALIDATION_FAILED", "旧版探索营不具备 WP-24 正式评分合同。")
    outcome = session.scalar(
        select(Outcome).where(
            Outcome.enrollment_id == enrollment.id,
            Outcome.organization_id == enrollment.organization_id,
        )
    )
    if outcome is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "完整旅程缺少权威 Outcome。")

    category_scores = {
        "rule_decomposition": 0,
        "model_judgement": 0,
        "rationale_writing": 0,
        "data_construction": 0,
    }
    evaluation_ids: list[uuid.UUID] = []
    for evidence in formal_evaluation_evidence(session, enrollment):
        task = session.scalar(
            select(TaskVersion).where(
                TaskVersion.id == evidence.stage.task_version_id,
                TaskVersion.organization_id == enrollment.organization_id,
            )
        )
        if task is None:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "评测证据缺少固定任务版本。")
        dimensions = {
            str(item.get("dimension_key")): item
            for item in task.rubric.get("dimensions", [])
            if isinstance(item, dict) and item.get("dimension_key")
        }
        structured = evidence.evaluation.structured_feedback
        if not isinstance(structured, list):
            raise ApiError(422, "SCORE_INCOMPLETE", "评测缺少 WP-24 数值评分证据。")
        for item in structured:
            dimension = dimensions.get(str(item.get("dimension_key")))
            score = item.get("score")
            if dimension is None or not isinstance(score, int):
                raise ApiError(422, "SCORE_INCOMPLETE", "评测数值评分不完整。")
            category = dimension.get("score_category")
            if category not in category_scores:
                raise ApiError(409, "INVALID_STATE_TRANSITION", "评测评分分类无效。")
            category_scores[str(category)] += score
        evaluation_ids.append(evidence.evaluation.id)

    expected_category_totals = {
        "rule_decomposition": 15,
        "model_judgement": 15,
        "rationale_writing": 10,
        "data_construction": 10,
    }
    if any(
        category_scores[key] > maximum
        for key, maximum in expected_category_totals.items()
    ):
        raise ApiError(409, "INVALID_STATE_TRANSITION", "评测评分超过固定权重。")

    scorecard: dict[str, object] = {
        "attendance_discipline": {
            "score": human_scores["attendance_discipline"],
            "max": 10,
            "source": "HUMAN_OPERATOR",
        },
        "learning_completion": {
            "score": 10,
            "max": 10,
            "source": "SYSTEM_EIGHT_STAGES_COMPLETED",
        },
        "muchener_understanding": {
            "score": human_scores["muchener_understanding"],
            "max": 10,
            "source": "HUMAN_OPERATOR",
        },
        "ai_data_fundamentals": {
            "score": human_scores["ai_data_fundamentals"],
            "max": 10,
            "source": "HUMAN_OPERATOR",
        },
        "project_organization_fit": {
            "score": human_scores["project_organization_fit"],
            "max": 10,
            "source": "HUMAN_OPERATOR",
        },
        **{
            key: {"score": value, "max": expected_category_totals[key], "source": "REVIEWER_EVALUATIONS"}
            for key, value in category_scores.items()
        },
        "human_score_evidence": score_evidence,
    }
    total_score = sum(
        int(value["score"])
        for value in scorecard.values()
        if isinstance(value, dict) and "score" in value
    )
    tier = "A" if total_score >= 85 else "B" if total_score >= 75 else "C" if total_score >= 65 else "D"
    scorecard["total"] = {"score": total_score, "max": 100, "source": "SYSTEM_SUM"}
    scorecard["recommendation"] = {
        "tier": tier,
        "advisory_only": True,
        "meaning": {
            "A": "优先继续",
            "B": "继续并关注差距",
            "C": "人工复核后决定",
            "D": "建议暂不进入下一阶段",
        }[tier],
    }
    return outcome, scorecard, evaluation_ids, tier
