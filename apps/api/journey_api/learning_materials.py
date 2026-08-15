from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.errors import ApiError
from journey_api.models import Assignment, LearningMaterialCompletion, TaskVersion


HTTPS_URL = re.compile(r"https://[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+")
TRAILING_URL_PUNCTUATION = re.compile(r"[),.;!?，。；！？、）】》]+$")
NON_MATERIAL_SENTINEL = "无，自行观看"


def is_publishable_learning_material(material: object) -> bool:
    """Exclude a source-table placeholder that was never a learner material.

    The formal content source uses ``无，自行观看`` to record that no second
    video exists.  It has no URL and must not become a required learner step.
    Real TEXT materials remain valid; this only recognizes the explicit source
    sentinel and only when the record contains no HTTPS material link.
    """
    if not isinstance(material, dict) or not material.get("key"):
        return False
    title = str(material.get("title") or "")
    body = str(material.get("body") or "")
    return not (
        material.get("kind") == "TEXT"
        and NON_MATERIAL_SENTINEL in f"{title}\n{body}"
        and HTTPS_URL.search(body) is None
    )


def learner_learning_materials(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only materials that are real learner inputs."""
    return [material for material in materials if is_publishable_learning_material(material)]


def reviewable_material_links(materials: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return the exact, de-duplicated URLs an operator must open before publish."""
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for material in learner_learning_materials(materials):
        title = str(material.get("title") or "学习材料")
        candidates: list[tuple[str, str]] = []
        if material.get("kind") == "HTTPS_LINK" and material.get("url"):
            candidates.append((title, str(material["url"])))
        elif material.get("kind") == "TEXT" and material.get("body"):
            for index, match in enumerate(
                HTTPS_URL.findall(str(material["body"])), start=1
            ):
                candidates.append(
                    (f"{title} · 链接 {index}", TRAILING_URL_PUNCTUATION.sub("", match))
                )
        for link_title, url in candidates:
            if url in seen:
                continue
            seen.add(url)
            links.append({"title": link_title, "url": url})
    return links


def material_by_key(task: TaskVersion, material_key: str) -> dict[str, Any]:
    material = next(
        (
            item
            for item in learner_learning_materials(task.learning_materials)
            if item.get("key") == material_key
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
        for item in learner_learning_materials(fixed_task.learning_materials)
        if item.get("required") is True and item.get("key")
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
