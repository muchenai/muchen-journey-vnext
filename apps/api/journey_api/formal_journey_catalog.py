"""Version-controlled pilot catalog for the formal Muchen Journey.

The archived product was used only to recover intent. These concise task
contracts are new vNext content and remain internal-only until WP-23 human UAT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from journey_api.models import JourneyCompletionPolicy, JourneyStageKind


FORMAL_JOURNEY_KEY = "EXPLORATION-CAMP"
FORMAL_JOURNEY_TITLE = "Muchen Journey 探索营"
FORMAL_JOURNEY_PURPOSE = "通过四段认知探索和三项实操评测，形成可追溯的学习与判断证据。"
CONTENT_SOURCE_NOTE = "DEC-024 与 34 号正式产品真相；旧归档仅用于需求发现，本正文为 vNext 重写。"
CONTENT_REVIEW_NOTE = (
    "受控内测 V1：Product/Content Owner 已授权最小纵向切片；"
    "三类 Reviewer 真人校准仍由 WP-23 内测完成，不用于自动人事判断。"
)


@dataclass(frozen=True)
class FormalStageCatalogItem:
    stable_key: str
    title: str
    short_description: str
    stage_kind: JourneyStageKind
    completion_policy: JourneyCompletionPolicy
    purpose: str
    learner_outcome: str
    instructions: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    required_deliverables: tuple[str, ...]
    estimated_duration_minutes: int
    rubric: dict[str, Any]


def task_version_values(item: FormalStageCatalogItem) -> dict[str, Any]:
    """Return the exact immutable TaskVersion content published for one stage."""

    return {
        "title": item.title,
        "purpose": item.purpose,
        "learner_outcome": item.learner_outcome,
        "instructions": list(item.instructions),
        "completion_criteria": list(item.completion_criteria),
        "required_deliverables": list(item.required_deliverables),
        "content_source_notes": [CONTENT_SOURCE_NOTE],
        "change_summary": "发布正式探索营受控内测 V1 的固定内容版本。",
        "reviewer_calibration_note": (
            "Learner 认知证据阶段不产生能力评分。"
            if item.completion_policy == JourneyCompletionPolicy.LEARNER_EVIDENCE
            else "明显通过、明显需修订、边界样本已编码；真人独立校准在 WP-23 内测记录。"
        ),
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": [],
        "estimated_duration_minutes": item.estimated_duration_minutes,
        "rubric": item.rubric,
        "rubric_version": 1,
        "reviewer_role": "REVIEWER",
        "feedback_sla_business_days": 2,
        "sensitivity": "INTERNAL",
        "audience": "LEARNER",
    }


def _dimension(
    key: str,
    title: str,
    purpose: str,
    evidence: str,
    meets: str,
    needs_work: str,
) -> dict[str, Any]:
    return {
        "dimension_key": key,
        "title": title,
        "purpose": purpose,
        "evidence_expected": evidence,
        "levels": {"MEETS": meets, "NEEDS_WORK": needs_work},
        "required": True,
        "feedback_prompt": "指出一处具体证据和下一步可执行修改。",
        "blocking_rule": "REQUIRE_FEEDBACK",
    }


def _rubric(*dimensions: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "dimensions": list(dimensions)}


NO_REVIEW_RUBRIC: dict[str, Any] = {"version": 1, "dimensions": []}


FORMAL_STAGE_CATALOG: tuple[FormalStageCatalogItem, ...] = (
    FormalStageCatalogItem(
        stable_key="DAY-0",
        title="启程",
        short_description="看清路线，写下你带着什么问题出发。",
        stage_kind=JourneyStageKind.DAY_0,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="确认你理解这段旅程的结构、人工评审边界和自己的当前行动。",
        learner_outcome="能说清四个认知宝藏、三项能力评测，以及遇到不确定时如何求助。",
        instructions=(
            "用自己的话写下：你将经历什么、哪一部分由 Reviewer 判断。",
            "写下一个你想在这段旅程中验证的问题。",
        ),
        completion_criteria=("说明四宝藏与三评测", "写下一个真实问题"),
        required_deliverables=("80–300 字启程记录",),
        estimated_duration_minutes=10,
        rubric=NO_REVIEW_RUBRIC,
    ),
    FormalStageCatalogItem(
        stable_key="TRE-001-COMPANY-VALUES",
        title="公司与 Muchener 价值",
        short_description="从真实业务出发，判断你愿意成为什么样的同行者。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解沐晨解决的真实问题，以及学习、规则、反馈和责任为什么重要。",
        learner_outcome="能用自己的话说明公司在解决什么问题，并选择一项愿意践行的 Muchener 品质。",
        instructions=(
            "用一句话说明你理解的公司业务问题。",
            "选择一项最重要的 Muchener 品质，并写一个你会如何实践的例子。",
        ),
        completion_criteria=("不是泛泛描述 AI", "品质与具体行动相连"),
        required_deliverables=("100–300 字价值理解记录",),
        estimated_duration_minutes=20,
        rubric=NO_REVIEW_RUBRIC,
    ),
    FormalStageCatalogItem(
        stable_key="TRE-002-AI-DATA-BASICS",
        title="AI 数据与模型基础",
        short_description="模型会犯错；关键是你能否留下可复核的判断。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解模型输出的不确定性，以及数据、人工反馈和证据链之间的关系。",
        learner_outcome="能解释模型为何可能出错，并说明人的判断为什么必须引用规则和证据。",
        instructions=(
            "列出一个模型回答可能出错的原因。",
            "说明人工判断如何通过规则、证据和反馈改善数据质量。",
        ),
        completion_criteria=("指出具体错误来源", "连接人工反馈与数据质量"),
        required_deliverables=("100–300 字模型认知记录",),
        estimated_duration_minutes=25,
        rubric=NO_REVIEW_RUBRIC,
    ),
    FormalStageCatalogItem(
        stable_key="TRE-003-PROJECT-AWARENESS",
        title="项目认知",
        short_description="你交付的不只是答案，而是质量链条中的一段证据。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解 AI 数据项目如何把客户场景转化为可执行标准和可验证结果。",
        learner_outcome="能说清一个项目从客户问题到规则、作业、质检和反馈的价值链。",
        instructions=(
            "按顺序写出客户问题、规则、作业、质检、反馈五个环节。",
            "指出新人在哪个环节最容易因为误解规则造成质量风险。",
        ),
        completion_criteria=("五个环节顺序清楚", "指出一个具体质量风险"),
        required_deliverables=("项目价值链与风险记录",),
        estimated_duration_minutes=20,
        rubric=NO_REVIEW_RUBRIC,
    ),
    FormalStageCatalogItem(
        stable_key="TRE-004-DELIVERY-FIT",
        title="项目交付与组织适配",
        short_description="先判断，再提报；不硬猜，也不把问题原样丢给别人。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解角色分工、责任边界和有效提报的最小结构。",
        learner_outcome="能区分自己应先判断的问题与必须向 QA、PM 提报的边界问题。",
        instructions=(
            "写一个你会先自行判断的场景，并说明依据。",
            "写一个必须提报的场景，包含已知事实、不确定点和具体问题。",
        ),
        completion_criteria=("自行判断有依据", "提报问题具体可回答"),
        required_deliverables=("一组判断与提报对照记录",),
        estimated_duration_minutes=20,
        rubric=NO_REVIEW_RUBRIC,
    ),
    FormalStageCatalogItem(
        stable_key="ASM-001-RULE-BREAKDOWN",
        title="能力评测一：规则拆解",
        short_description="把规则拆成目标、维度、红线和提报点。",
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        purpose="证明你能把一段任务规则转化为可执行、可复核的判断框架。",
        learner_outcome="能独立拆出任务目标、判断维度、红线和需提报的不确定点。",
        instructions=(
            "阅读题面中的规则，先用一句话写任务目标。",
            "列出判断维度、红线和至少一个需要提报的边界点。",
        ),
        completion_criteria=("目标准确", "维度可执行", "红线明确", "边界可提报"),
        required_deliverables=("结构化规则拆解答案",),
        estimated_duration_minutes=30,
        rubric=_rubric(
            _dimension("task_goal", "任务目标", "确认目标没有被原文噪声淹没。", "一句可执行目标。", "目标准确且可执行", "目标含糊或偏离规则"),
            _dimension("judgement_dimensions", "判断维度", "确认能拆成独立判断维度。", "至少三个维度及判断含义。", "维度完整且不重叠", "维度缺失或无法执行"),
            _dimension("red_lines", "红线识别", "确认禁止项和不可提交条件明确。", "红线及触发条件。", "红线具体可识别", "红线缺失或泛化"),
            _dimension("escalation_points", "提报点", "确认不确定时不会强行判断。", "至少一个边界和具体问题。", "提报点具体可回复", "未识别边界或问题不可回复"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="ASM-002-MODEL-JUDGEMENT",
        title="能力评测二：模型回答判断",
        short_description="比较两个回答，用证据说明为什么。",
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        purpose="证明你能按规则比较模型回答，而不是只凭感觉选择。",
        learner_outcome="能给出选择、判断维度、具体引用和风险说明。",
        instructions=(
            "比较题面中的回答 A 与 B，明确选择或说明都不合格。",
            "从完整性、准确性、约束遵循和风险四个角度引用具体证据。",
        ),
        completion_criteria=("结论明确", "证据可定位", "理由可复核", "风险被识别"),
        required_deliverables=("A/B 判断与证据链",),
        estimated_duration_minutes=30,
        rubric=_rubric(
            _dimension("criteria_application", "维度应用", "确认判断维度来自规则。", "逐维度比较。", "维度正确且覆盖关键约束", "维度随意或遗漏关键约束"),
            _dimension("evidence_reference", "证据定位", "确认理由引用回答中的事实。", "A/B 具体文本或缺口。", "证据具体可定位", "只有感受没有证据"),
            _dimension("tradeoff_reasoning", "权衡理由", "确认能解释取舍。", "结论与权衡。", "取舍清楚且与目标一致", "结论与理由脱节"),
            _dimension("risk_detection", "风险识别", "确认能发现遗漏和错误风险。", "至少一项风险。", "风险具体且影响明确", "风险缺失或泛化"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="ASM-003-BOUNDARY-ESCALATION",
        title="能力评测三：边界识别与提报",
        short_description="遇到规则没覆盖的情况，给出谨慎初判和有效问题。",
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        purpose="证明你能识别不确定边界，保留事实并提出可回答的提报问题。",
        learner_outcome="能说明已知、不确定、初判、风险与需要谁回答的具体问题。",
        instructions=(
            "写清题面中已知事实和规则没有覆盖的部分。",
            "给出谨慎初判、风险控制动作，以及一个可直接回复的提报问题。",
        ),
        completion_criteria=("边界明确", "初判有依据", "问题可回答", "风险动作具体"),
        required_deliverables=("边界分析与提报记录",),
        estimated_duration_minutes=30,
        rubric=_rubric(
            _dimension("uncertainty_boundary", "边界识别", "确认能指出规则覆盖缺口。", "已知与未知的边界。", "边界具体且有事实依据", "把一般困难误当边界"),
            _dimension("preliminary_judgement", "谨慎初判", "确认不会因不确定而放弃思考。", "初判与依据。", "初判可追溯且保留不确定性", "强行下结论或完全无判断"),
            _dimension("escalation_question", "有效提问", "确认问题可被直接回答。", "对象、事实和一个具体问题。", "问题清楚且可回复", "原样转交困惑或缺少上下文"),
            _dimension("risk_control", "风险控制", "确认等待期间不会扩散错误。", "暂停、标记或隔离动作。", "动作具体且与风险匹配", "没有控制动作或动作过度"),
        ),
    ),
)


def validate_catalog() -> None:
    if len(FORMAL_STAGE_CATALOG) != 8:
        raise ValueError("formal journey must contain Day 0, four treasures, and three assessments")
    if [item.stage_kind for item in FORMAL_STAGE_CATALOG].count(JourneyStageKind.DAY_0) != 1:
        raise ValueError("formal journey must contain exactly one Day 0")
    if [item.stage_kind for item in FORMAL_STAGE_CATALOG].count(JourneyStageKind.TREASURE) != 4:
        raise ValueError("formal journey must contain exactly four treasures")
    if [item.stage_kind for item in FORMAL_STAGE_CATALOG].count(JourneyStageKind.ASSESSMENT) != 3:
        raise ValueError("formal journey must contain exactly three assessments")
    if len({item.stable_key for item in FORMAL_STAGE_CATALOG}) != len(FORMAL_STAGE_CATALOG):
        raise ValueError("formal journey stage keys must be unique")


validate_catalog()
