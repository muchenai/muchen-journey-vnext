from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.errors import ApiError
from journey_api.models import Assignment, LearningMaterialCompletion, TaskVersion


def material_by_key(task: TaskVersion, material_key: str) -> dict[str, Any]:
    material = next(
        (
            item
            for item in task.learning_materials
            if isinstance(item, dict) and item.get("key") == material_key
        ),
        None,
    )
    if material is None:
        raise ApiError(404, "NOT_FOUND", "没有找到当前固定版本中的学习材料。")
    return material


def completed_materials(
    session: Session, assignment: Assignment
) -> dict[str, LearningMaterialCompletion]:
    return {
        item.material_key: item
        for item in session.scalars(
            select(LearningMaterialCompletion).where(
                LearningMaterialCompletion.organization_id
                == assignment.organization_id,
                LearningMaterialCompletion.assignment_id == assignment.id,
                LearningMaterialCompletion.task_version_id
                == assignment.task_version_id,
            )
        ).all()
    }


def missing_required_material_keys(
    session: Session, assignment: Assignment, task: TaskVersion | None = None
) -> list[str]:
    fixed_task = task or session.get(TaskVersion, assignment.task_version_id)
    if fixed_task is None or fixed_task.organization_id != assignment.organization_id:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "任务缺少固定内容版本。")
    required = {
        str(item["key"])
        for item in fixed_task.learning_materials
        if isinstance(item, dict) and item.get("required") is True and item.get("key")
    }
    return sorted(required - set(completed_materials(session, assignment)))


def ensure_required_materials_completed(
    session: Session, assignment: Assignment, task: TaskVersion | None = None
) -> None:
    missing = missing_required_material_keys(session, assignment, task)
    if missing:
        raise ApiError(
            409,
            "LEARNING_MATERIALS_INCOMPLETE",
            "请先显式完成所有必读材料，再开始小任务。",
            details={"missing_material_keys": missing},
        )
