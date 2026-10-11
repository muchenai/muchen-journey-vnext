from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.errors import ApiError
from journey_api.models import Assignment, LearningMaterialCompletion, TaskVersion


HTTPS_URL = re.compile(r"https://[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+")
TRAILING_URL_PUNCTUATION = re.compile(r"[),.;!?，。；！？、）】》]+$")
NON_MATERIAL_SENTINEL = "无，自行观看"
TREASURE_ONE_QUIZ_URL = "https://zx6w57w0j34.feishu.cn/docx/N1CmdNwvtoF6ubxGGK6cztvnnpg"
TREASURE_TWO_DOCUMENT_URL = "https://zx6w57w0j34.feishu.cn/docx/EDm2dFzmco58SJx10Xeceo0WnIc"
TREASURE_TWO_QUIZ_URL = "https://zx6w57w0j34.feishu.cn/docx/B9uhdkLwUoqqIYxeh9TcWErbnHd?from=from_parent_sheet"
LEGACY_STAGE_LINKS = {
    "TRE-002-AI-DATA-BASICS": (
        "宝藏二", "AI与数据基础文档", "AI基础学习小测",
        TREASURE_TWO_DOCUMENT_URL, TREASURE_TWO_QUIZ_URL,
    ),
    "TRE-003-PROJECT-AWARENESS": (
        "宝藏三", "MDOS 项目经理全流程操作指引", "宝藏三材料二",
        "https://zx6w57w0j34.feishu.cn/docx/HDoidinI9oTlmzxw5H7cqQbqnCF",
        "https://zx6w57w0j34.feishu.cn/file/QcEqbZ3NlolbaTxvmc0cZNeYnvc",
    ),
    "TRE-004-DELIVERY-FIT": (
        "宝藏四", "项目中的关键角色与新人责任边界", "项目交付与责任边界视频",
        "https://zx6w57w0j34.feishu.cn/wiki/Lu9ZwEM9kij7fdk7eOMcInNenld",
        "https://zx6w57w0j34.feishu.cn/minutes/obcnk5wa15l826747rlb55rr",
    ),
    "ASM-001-RULE-BREAKDOWN": (
        "评测一", "项目规则文档拆解作业 SOP", "项目规则文档拆解教学视频",
        "https://zx6w57w0j34.feishu.cn/wiki/Fxccw68nAipuM3kK8gJcqiyDnRJ",
        "https://zx6w57w0j34.feishu.cn/minutes/obcnk68g8j32fn4f8af53752",
    ),
    "ASM-002-MODEL-JUDGEMENT": (
        "评测二", "模型回答判断与理由书写", "模型回答质量判断教学视频",
        "https://zx6w57w0j34.feishu.cn/docx/NbGRdVd6aolCDRxkmodcHoMLnlg",
        "https://zx6w57w0j34.feishu.cn/minutes/obcnj65w46z681x365gyo3wu",
    ),
    "ASM-003-DATA-CONSTRUCTION": (
        "评测三", "通用数据构造讲义", "通用数据构造教学视频",
        "https://zx6w57w0j34.feishu.cn/docx/Hx8HdBHYmoSFOexbyoxc9A3dn0c",
        "https://lcnf4xe7p1h6.feishu.cn/minutes/obcnk1s9uh3y25xle6723aq3",
    ),
}


def published_exploration_materials(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve the exact legacy pairs verified in the production preflight.

    The old video records are TEXT, which the link-only exploration UI cannot
    open. Only recognized two-record signatures receive the owner's supplied
    links. Stored versions and historical completion facts are never rewritten.
    A replacement resource gets a new key; an unchanged document keeps its key.
    """
    if len(materials) != 2 or materials[0].get("kind") != "TEXT" or materials[1].get("kind") != "HTTPS_LINK":
        return materials
    first, second = materials
    if (first.get("key") == "day0-company-intro" and second.get("key") == "day0-letter"
            and str(second.get("url", "")).split("?", 1)[0] == "https://zx6w57w0j34.feishu.cn/wiki/MpxDwemUwiOY0fk9jM5cqRYRn3b"):
        return [dict(second), {
            "key": "day0-company-intro-linked", "title": "公司基础介绍材料", "kind": "HTTPS_LINK",
            "url": "https://zx6w57w0j34.feishu.cn/docx/B9f2d0P0ior6UBxTeFRc2ELmnlg",
            "source_label": "Day 1 材料二", "estimated_duration_minutes": 1, "required": bool(first.get("required")),
        }]
    stage_by_prefix = {
        "tre002": "TRE-002-AI-DATA-BASICS", "tre003": "TRE-003-PROJECT-AWARENESS",
        "tre004": "TRE-004-DELIVERY-FIT", "asm001": "ASM-001-RULE-BREAKDOWN",
        "asm002": "ASM-002-MODEL-JUDGEMENT", "asm003": "ASM-003-DATA-CONSTRUCTION",
    }
    prefix = str(second.get("key", "")).removesuffix("-document")
    video_key = "tre002-video-note" if prefix == "tre002" else prefix + "-video"
    if first.get("key") != video_key or second.get("key") != prefix + "-document":
        return materials
    if prefix == "tre001":
        label, title1, title2 = "宝藏一", "使命愿景价值观", "公司价值体现视频"
        old_url = "https://zx6w57w0j34.feishu.cn/docx/Av3pdq3lhoQlfbxcep1cG8gtn4e"
        url1 = "https://zx6w57w0j34.feishu.cn/wiki/TUV1wbptdiXmapkfDsOcRrvknme"
        url2 = "https://zx6w57w0j34.feishu.cn/file/PewIbRCP3oDKAIx7MS9cSqUMnod"
    elif prefix in stage_by_prefix:
        label, title1, title2, url1, url2 = LEGACY_STAGE_LINKS[stage_by_prefix[prefix]]
        old_url = url1
    else:
        return materials
    if urlsplit(str(second.get("url", "")))._replace(query="", fragment="").geturl() != old_url:
        return materials
    document_key = str(second["key"]) if old_url == url1 else prefix + "-document-linked"
    return [
        {**second, "key": document_key, "title": title1, "url": url1, "source_label": label + "材料一"},
        {"key": prefix + "-video-linked", "title": title2, "kind": "HTTPS_LINK", "url": url2,
         "source_label": label + "材料二", "estimated_duration_minutes": 1, "required": bool(first.get("required"))},
    ]


def task_learning_materials(task: TaskVersion) -> list[dict[str, Any]]:
    """Resolve supplied materials for legacy local journey versions.

    Keep immutable versions and existing completion facts intact. Match only
    known placeholder records; explicit published materials remain authoritative.
    """
    materials = learner_learning_materials(task.learning_materials)
    for stable_key, (label, first_title, second_title, first_url, second_url) in LEGACY_STAGE_LINKS.items():
        material_key = f"material-{stable_key.lower()}"
        if not (
            len(materials) == 1
            and materials[0].get("key") == material_key
            and str(materials[0].get("url", "")).startswith(
                f"https://example.feishu.cn/wiki/P0LearnerExperienceMaterial{stable_key.replace('-', '')}?"
            )
        ):
            continue
        # New keys prevent clicks on the old placeholder from completing the
        # newly supplied documents. Never mutate the published source version.
        # Treasure 3/4 videos moved from slot 1 to slot 2: keep their old keys,
        # while the newly supplied documents receive separate completion keys.
        moved_video = stable_key in {"TRE-003-PROJECT-AWARENESS", "TRE-004-DELIVERY-FIT"}
        materials = [
            {
                **materials[0],
                "key": f"{material_key}-reference" if moved_video else f"{material_key}-document",
                "title": first_title,
                "source_label": f"{label}材料一",
                "url": first_url,
            },
            {
                "key": (f"{material_key}-document" if moved_video
                        else f"{material_key}-video" if stable_key.startswith("ASM-")
                        else f"{material_key}-quiz"),
                "title": second_title,
                "kind": "HTTPS_LINK",
                "source_label": f"{label}材料二",
                "url": second_url,
                "estimated_duration_minutes": 1,
                "required": False,
            },
        ]
    if (
        len(materials) in {1, 2}
        and materials[0].get("key") == "material-tre-001-company-values"
        and materials[0].get("url") == "https://zx6w57w0j34.feishu.cn/file/PewIbRCP3oDKAIx7MS9cSqUMnod"
        and (len(materials) == 1 or materials[1].get("url") == TREASURE_ONE_QUIZ_URL)
    ):
        video = materials[0]
        materials = [{
            "key": "material-tre-001-company-values-document",
            "title": "使命愿景价值观",
            "kind": "HTTPS_LINK",
            "source_label": "宝藏一材料一",
            "url": "https://zx6w57w0j34.feishu.cn/wiki/TUV1wbptdiXmapkfDsOcRrvknme",
            "estimated_duration_minutes": 1,
            "required": True,
        }, {**video, "source_label": "宝藏一材料二"}]
    return published_exploration_materials(materials)


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
            for item in task_learning_materials(task)
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
        for item in task_learning_materials(fixed_task)
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
