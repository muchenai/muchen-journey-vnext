from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.models import (
    JourneyCompletionPolicy,
    JourneyDefinition,
    JourneyDefinitionStatus,
    JourneyKind,
    JourneyStageKind,
    JourneyStageVersion,
    JourneyVersion,
    TaskVersion,
)


def ensure_single_stage_alpha_journey(
    session: Session,
    *,
    organization_id: uuid.UUID,
    stable_key: str,
    title: str,
    task: TaskVersion,
    owner_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> tuple[JourneyVersion, JourneyStageVersion]:
    """Create or return a local/controlled one-stage Alpha composition for a fixed task."""
    definition = session.scalar(
        select(JourneyDefinition).where(
            JourneyDefinition.organization_id == organization_id,
            JourneyDefinition.stable_key == stable_key,
        )
    )
    if definition is not None:
        existing = session.execute(
            select(JourneyVersion, JourneyStageVersion)
            .join(
                JourneyStageVersion,
                JourneyStageVersion.journey_version_id == JourneyVersion.id,
            )
            .where(
                JourneyVersion.journey_definition_id == definition.id,
                JourneyVersion.organization_id == organization_id,
                JourneyStageVersion.task_version_id == task.id,
            )
        ).first()
        if existing is not None:
            return existing[0], existing[1]
    else:
        definition = JourneyDefinition(
            id=uuid.uuid4(),
            organization_id=organization_id,
            stable_key=stable_key,
            kind=JourneyKind.ALPHA_VALIDATION,
            status=JourneyDefinitionStatus.DRAFT,
            revision=1,
            created_by=owner_id,
        )
        session.add(definition)
        session.flush()

    next_version = (
        session.scalar(
            select(func.max(JourneyVersion.version)).where(
                JourneyVersion.journey_definition_id == definition.id
            )
        )
        or 0
    ) + 1
    version = JourneyVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        journey_definition_id=definition.id,
        version=next_version,
        title=title,
        change_summary="Controlled compatibility composition for one fixed Alpha task.",
        published_by=owner_id,
        reviewed_by=reviewer_id,
    )
    session.add(version)
    session.flush()
    stage = JourneyStageVersion(
        id=uuid.uuid4(),
        organization_id=organization_id,
        journey_version_id=version.id,
        stable_key=f"{stable_key}-STAGE",
        position=1,
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        task_definition_id=task.task_definition_id,
        task_version_id=task.id,
    )
    session.add(stage)
    definition.status = JourneyDefinitionStatus.PUBLISHED
    definition.revision += 1
    session.flush()
    return version, stage
