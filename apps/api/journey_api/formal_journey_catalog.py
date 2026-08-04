"""Version-controlled catalogs for the formal Muchen Journey.

V1 remains frozen for existing enrollments. V2 restores the approved full-day
learning and assessment intent as new immutable task and journey versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from journey_api.models import JourneyCompletionPolicy, JourneyStageKind


FORMAL_JOURNEY_KEY = "EXPLORATION-CAMP"
FORMAL_JOURNEY_TITLE = "Muchen Journey 新人启航探索营"
FORMAL_JOURNEY_PURPOSE = "用一天完成公司与项目认知学习、三项真实能力评测，并形成可追溯的人工准入证据。"
CONTENT_SOURCE_NOTE = (
    "WP-24 基于《MUCHEN新人启航探索营 V1.0》与《给 Muchener 的一封信》重写；"
    "客户、项目和经营数字未获复核时不得补写或推测。"
)
CONTENT_REVIEW_NOTE = (
    "Formal Exploration Camp V2：内容按 WP-24 正式方案重建；"
    "评分只形成建议，准入结论必须由授权人工给出并记录理由。"
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
    learning_experience: dict[str, Any] = field(default_factory=dict)


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
        "change_summary": "WP-24：发布正式探索营 V2 的一天学习与真实评测固定内容。",
        "reviewer_calibration_note": (
            "Learner 认知证据阶段不产生能力评分。"
            if item.completion_policy == JourneyCompletionPolicy.LEARNER_EVIDENCE
            else "Reviewer 必须按固定分值、阈值与证据评分；准入仍由授权人工独立决定。"
        ),
        "allowed_attachment_types": [],
        "max_attachment_size_bytes": 0,
        "reference_materials": [],
        "learning_materials": [],
        "learning_experience": item.learning_experience,
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


FORMAL_STAGE_CATALOG_V1: tuple[FormalStageCatalogItem, ...] = (
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


def _block(kind: str, title: str, body: str) -> dict[str, str]:
    return {"kind": kind, "title": title, "body": body}


def _experience(
    *,
    start: str,
    end: str,
    mode: str,
    blocks: tuple[dict[str, str], ...],
    checks: tuple[str, ...],
    response_sections: tuple[str, ...],
    break_after: str | None = None,
) -> dict[str, Any]:
    return {
        "version": 2,
        "schedule": {
            "start": start,
            "end": end,
            "break_after": break_after,
        },
        "mode": mode,
        "learning_blocks": list(blocks),
        "knowledge_checks": list(checks),
        "response_sections": list(response_sections),
    }


def _scored_dimension(
    key: str,
    title: str,
    purpose: str,
    evidence: str,
    meets: str,
    needs_work: str,
    *,
    max_points: int,
    meets_threshold: int,
    score_category: str,
) -> dict[str, Any]:
    value = _dimension(key, title, purpose, evidence, meets, needs_work)
    value.update(
        {
            "max_points": max_points,
            "meets_threshold": meets_threshold,
            "score_category": score_category,
        }
    )
    return value


FORMAL_STAGE_CATALOG_V2: tuple[FormalStageCatalogItem, ...] = (
    FormalStageCatalogItem(
        stable_key="DAY-0",
        title="Day 0：看见整段旅程",
        short_description="先理解一天会发生什么，再写下你真正想验证的问题。",
        stage_kind=JourneyStageKind.DAY_0,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="完成开营导入、学习边界与一天路线确认，避免在没有输入时被迫作答。",
        learner_outcome="能说清今天的四段认知学习、三项能力评测、人工评审与求助路径。",
        instructions=(
            "先阅读页面中的开营信摘要与全天路线，再完成三个自检问题。",
            "最后写下一个你今天最想验证的问题，以及你会如何验证它。",
        ),
        completion_criteria=("先完成学习输入", "问题具体", "验证方式可执行"),
        required_deliverables=("120–300 字启程记录",),
        estimated_duration_minutes=25,
        rubric=NO_REVIEW_RUBRIC,
        learning_experience=_experience(
            start="10:00",
            end="10:25",
            mode="ORIENTATION",
            blocks=(
                _block("OPENING", "It's a long game", "这里不是知识竞赛。你会在一天里阅读、判断、动手构建，再由真实 Reviewer 看你的证据和思考过程。"),
                _block("ROUTE", "四个宝藏 + 三项评测", "10:25 前完成开营与路线确认；上午进入公司与 Muchener、AI 数据与模型基础；午休后学习项目认知、交付与组织适配；15:00 起依次完成规则拆解、模型回答比较与通用数据构建，18:40 起确认提交和后续流程。"),
                _block("BOUNDARY", "评审与求助", "系统保存事实但不替人作录用决定。遇到规则没有覆盖的情况，先保留事实、写出初判，再提出一个可回答的问题。"),
                _block("RESULT", "结果怎样产生", "四个宝藏用于形成认知证据；三项评测由独立 Reviewer 按固定 Rubric 评分；出勤、学习和组织适配由 Operator 记录，最终是否进入下一阶段必须由人工决定并写明理由。"),
            ),
            checks=("我知道今天先学习后输出。", "我知道三项评测均由人工 Reviewer 复核。", "我知道不确定时应保留证据并提问。"),
            response_sections=("我今天想验证的问题", "我准备用什么证据验证", "需要帮助时我会怎么做"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="TRE-001-COMPANY-VALUES",
        title="宝藏一：公司与 Muchener",
        short_description="理解公司为什么存在，以及长期主义如何落到每天的动作。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解沐晨从低端重复劳动转向高质量 AI 数据工程的经营命题。",
        learner_outcome="能用自己的话说明公司提供的价值，并用可观察行动解释一项 Muchener 品质。",
        instructions=("阅读三段公司命题与反例。", "选择一项你认可或质疑的命题，用事实和行动说明。"),
        completion_criteria=("不是复述口号", "包含一个可观察行动", "允许提出有依据的质疑"),
        required_deliverables=("3–5 句话的公司认知与行动承诺",),
        estimated_duration_minutes=45,
        rubric=NO_REVIEW_RUBRIC,
        learning_experience=_experience(
            start="10:25",
            end="11:10",
            mode="LEARN_AND_REFLECT",
            break_after="10 分钟",
            blocks=(
                _block("THESIS", "客户购买的是确定性交付", "真正的价值不是堆人力，而是把复杂需求转成可定义、可生产、可质检、可复盘的交付系统。"),
                _block("THESIS", "变化不是例外", "低端标注会继续自动化；公司要靠真实需求识别、质量体系、人才培养、系统沉淀和学习速度持续升级。"),
                _block("MODEL", "持续成功的五种能力", "真实需求识别决定做什么；复杂项目交付把需求变成结果；质量体系让结果可验收；人才培养扩大能力密度；组织系统把一次经验变成下一次可复用的方法。任何一项长期为零，口号都不能替代结果。"),
                _block("PRACTICE", "长期主义要能被观察", "不抱怨起点、研究系统；不只完成任务、还要沉淀方法；不确定时不硬猜，而是留下证据和清晰问题。"),
                _block("COUNTERPOINT", "不要求盲目信任", "判断公司是否真正进步，要看客户是否复购、项目是否按期验收、质量问题是否复盘、新人是否成长、经验是否进入系统，以及组织是否越来越不依赖少数能人。"),
            ),
            checks=("公司不把低价人力视为长期壁垒。", "一次项目是否形成可复用方法，是长期价值的证据。", "质疑可以被提出，但要附事实和验证方法。"),
            response_sections=("我理解公司在解决什么问题", "我选择或质疑的命题", "未来一周可被观察的行动"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="TRE-002-AI-DATA-BASICS",
        title="宝藏二：AI 数据与模型基础",
        short_description="模型会给出流畅答案；你的工作是判断它是否可靠。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="建立模型输出、数据质量、规则、人工反馈和证据链之间的基础认知。",
        learner_outcome="能识别模型常见失败方式，并说明人工评测如何改善训练与交付质量。",
        instructions=("阅读模型错误链路和两个短例子。", "回答三个理解问题，再写一个你会如何核验模型回答的例子。"),
        completion_criteria=("区分流畅与正确", "指出具体核验方法", "连接反馈与数据质量"),
        required_deliverables=("三个理解答案 + 一个核验示例",),
        estimated_duration_minutes=40,
        rubric=NO_REVIEW_RUBRIC,
        learning_experience=_experience(
            start="11:20",
            end="12:00",
            mode="LEARN_AND_CHECK",
            break_after="午休至 13:00",
            blocks=(
                _block("FOUNDATION", "Prompt、Context、Token 与 LLM", "Prompt 是你给模型的任务与要求；Context 是回答时可用的上下文；Token 是模型处理文本的基本片段；LLM 根据上下文预测后续 token，因此能生成流畅内容，却不会自动保证事实正确。"),
                _block("CONCEPT", "输出不是事实", "模型可能编造来源、遗漏限制、混淆时间、误解上下文，也可能用非常确定的语气表达错误。所谓幻觉，是输出看起来合理但缺少事实依据或与事实冲突。"),
                _block("CONCEPT", "偏好、对齐与人的角色", "有些任务不是简单的对错题，而是要在帮助性、安全性、准确性和表达之间取舍。偏好数据记录人更认可哪种回答及原因；对齐让模型更符合人的目标与边界。"),
                _block("QUALITY", "数据质量怎样影响模型", "规则含糊会制造互相矛盾的标签；样本单一会让模型只会熟悉场景；错误反馈会放大错误模式。高质量数据需要明确目标、代表性覆盖、稳定规则、边界样例和可追溯质检。"),
                _block("CONCEPT", "高质量反馈是什么", "有效反馈包含固定规则、可定位证据、明确结论和可执行修改，而不是一句“感觉不好”。不同 Reviewer 对同一规则分歧时，应先校准规则而不是简单投票。"),
                _block("EXAMPLE", "一个最小核验链", "先确认任务目标，再逐项检查关键约束；随后定位答案中的原句或缺口；最后记录风险、结论和需要提报的边界。结论可以暂时不确定，但证据不能消失。"),
            ),
            checks=("为什么模型回答流畅也可能不可靠？", "什么样的人工反馈能被复核？", "规则没有覆盖时，为什么不能强行给确定结论？"),
            response_sections=("三个理解答案", "我的模型核验示例", "我会保留的证据"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="TRE-003-PROJECT-AWARENESS",
        title="宝藏三：项目认知",
        short_description="从客户问题到验收结果，看见一条完整质量链。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解 AI 数据项目如何把模糊业务目标转为规则、样例、生产、质检和反馈。",
        learner_outcome="能复原项目价值链，并识别新人最容易制造的质量风险。",
        instructions=("阅读虚构的客服意图数据项目案例。", "完成 3 道选择/判断题与 2 道短答题。"),
        completion_criteria=("价值链顺序正确", "风险可定位", "改善动作对应风险"),
        required_deliverables=("五题项目认知答案",),
        estimated_duration_minutes=45,
        rubric=NO_REVIEW_RUBRIC,
        learning_experience=_experience(
            start="13:00",
            end="13:45",
            mode="CASE_STUDY",
            break_after="10 分钟",
            blocks=(
                _block("SCOPE", "公司项目方向的事实边界", "已批准材料只确认方向包含高质量数据、模型评测、多模态理解、Agent 行为数据、模型出海数据与工程化交付；本页不展示客户名单、项目规模或经营数字，也不把未经复核的信息写成公司事实。"),
                _block("CASE", "合成案例：售后意图识别", "下面案例专门用于学习，不代表真实客户。目标是让模型区分退款、换货、物流查询和其他咨询。团队要先澄清业务目标，再定义标签边界、制作样例、培训作业、质检并回传错误模式。"),
                _block("CHAIN", "质量链", "客户目标 → 规则与样例 → 人员校准 → 数据生产 → 质检验收 → 错误复盘与规则更新。任何一段信息丢失，都会在后续被放大。"),
                _block("VALUE", "客户真正验收什么", "客户不是只看交了多少条，而是看需求是否被正确理解、结构是否符合约定、数据是否覆盖目标场景、质量是否达到阈值、异常是否可追溯，以及返修能否回到规则和流程。"),
                _block("RISK", "最常见的早期风险", "把未理解的规则直接投入大批生产、只看结果不保留证据、把边界问题原样丢给上级，都会制造不可复核的返工。"),
                _block("CONTROL", "把风险前移", "先用少量样本校准，再扩大生产；对高风险样本单独标记；抽检发现系统性偏差时暂停扩散；把错误模式写入问题库，并明确由谁修改规则、谁重新校准。"),
            ),
            checks=("规则与样例应在大批生产前完成校准。", "客户目标变化后，旧规则仍可直接使用。（判断并说明）", "列出一个最早可以发现质量偏差的检查点。", "为什么返工记录要回到规则库？", "新人在哪个环节最需要主动提问？"),
            response_sections=("第 1–3 题", "第 4–5 题", "我识别的一个质量风险"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="TRE-004-DELIVERY-FIT",
        title="宝藏四：交付与组织适配",
        short_description="知道谁负责什么，也知道问题怎样被有效升级。",
        stage_kind=JourneyStageKind.TREASURE,
        completion_policy=JourneyCompletionPolicy.LEARNER_EVIDENCE,
        purpose="理解 Learner、作业者、QA、PM 与客户接口之间的责任边界和升级结构。",
        learner_outcome="能在自己先判断与必须升级之间作出有依据的选择。",
        instructions=("阅读角色卡与三个异常场景。", "完成四道选择题和一道结构化升级短答。"),
        completion_criteria=("角色边界清楚", "升级包含已知/未知/初判/问题", "不泄露无关信息"),
        required_deliverables=("五题组织适配答案",),
        estimated_duration_minutes=45,
        rubric=NO_REVIEW_RUBRIC,
        learning_experience=_experience(
            start="13:55",
            end="14:40",
            mode="ROLE_PRACTICE",
            break_after="20 分钟",
            blocks=(
                _block("ROLE", "作业者 / Learner", "按固定版本执行、保留证据、标记边界；不得自行改写规则。"),
                _block("ROLE", "QA / Reviewer", "按同一 Rubric 校准判断、给可执行反馈；不得替 Learner 伪造提交。"),
                _block("ROLE", "PM / Operator", "管理范围、版本、分配和异常；不得直接修改历史业务事实。"),
                _block("RESPONSIBILITY", "为什么不能等 QA 全检", "QA 是风险控制点，不是作业者的替代品。每个人都要对自己提交的准确性、证据和边界标记负责；把所有判断外包给 QA 会让质量问题在规模化时迅速放大。"),
                _block("TOOL", "一次有效升级", "已知事实 + 未覆盖点 + 谨慎初判 + 风险控制 + 一个可直接回答的问题。"),
                _block("ANTI_PATTERN", "三种不适配信号", "不读规则直接做、遇到反馈只辩解不修正、发现边界后既不保留证据也不提报，都会破坏交付。可以不会，但必须先学习、先判断、再清晰求助。"),
            ),
            checks=("规则明确且证据充分时，先完成自己的判断。", "同一边界反复出现时，应推动规则更新而非持续口头询问。", "升级时只说“我不会”是否足够？", "发现疑似隐私数据时应先隔离并提报。", "为一个边界场景写出有效升级。"),
            response_sections=("第 1–4 题", "第 5 题：结构化升级", "我的风险控制动作"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="ASM-001-RULE-BREAKDOWN",
        title="评测一：把规则变成检查清单",
        short_description="真实工作从拆清规则开始，而不是立刻写答案。",
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        purpose="评估 Learner 是否能把一段客服意图规则转成可执行、可复核的判断框架。",
        learner_outcome="能独立拆出任务目标、判断维度、红线和需要升级的不确定点。",
        instructions=("阅读完整题面，先不要作答。", "按目标、维度、红线、升级点四段结构提交。"),
        completion_criteria=("目标准确", "维度可执行", "红线明确", "升级问题可直接回答"),
        required_deliverables=("结构化规则拆解答案",),
        estimated_duration_minutes=60,
        rubric=_rubric(
            _scored_dimension("task_goal", "任务目标", "确认抓住业务目标。", "一句可执行目标。", "目标准确且可执行", "目标含糊或偏离规则", max_points=3, meets_threshold=2, score_category="rule_decomposition"),
            _scored_dimension("judgement_dimensions", "判断维度", "确认规则能变成检查项。", "至少四个维度及判断条件。", "维度完整且互不混淆", "维度缺失或无法执行", max_points=5, meets_threshold=4, score_category="rule_decomposition"),
            _scored_dimension("red_lines", "红线识别", "确认禁止项明确。", "红线及触发条件。", "红线具体可识别", "红线缺失或泛化", max_points=4, meets_threshold=3, score_category="rule_decomposition"),
            _scored_dimension("escalation_points", "边界与升级", "确认不会强行判断。", "至少一个边界和具体问题。", "问题可被直接回复", "未识别边界或问题不可回复", max_points=3, meets_threshold=2, score_category="rule_decomposition"),
        ),
        learning_experience=_experience(
            start="15:00",
            end="16:00",
            mode="ASSESSMENT",
            break_after="10 分钟",
            blocks=(
                _block("METHOD", "四遍拆解法", "第一遍只找业务目标；第二遍圈出标签、条件与优先级；第三遍列出禁止项、隐私与不可提交条件；第四遍寻找规则没有覆盖或彼此冲突的边界，并把它改写成一个可回答的问题。"),
                _block("BRIEF", "任务背景", "你在为售后客服意图模型制作评测集。每条用户消息只能标一个主意图：REFUND（明确要求退款）、EXCHANGE（明确要求换货）、LOGISTICS（只询问物流）、OTHER（以上均不满足）。"),
                _block("RULE", "固定规则", "出现多个诉求时，以用户最后一个明确请求为主；只有抱怨但没有提出处理要求时不能标退款或换货；包含订单号、手机号等个人信息时必须标记并隔离，不进入普通评测集；规则未覆盖的组合诉求不得自行新增标签。"),
                _block("SAMPLES", "边界样例", "“一直没到，帮我查物流”=LOGISTICS；“太慢了，我不要了，退款”=REFUND；“能不能换蓝色，顺便查下到哪了”以最后一个明确请求 LOGISTICS 为主，但需记录组合诉求风险。"),
            ),
            checks=("先确认唯一主标签目标。", "红线必须包含隐私隔离。", "组合诉求是需要记录的边界。"),
            response_sections=("1. 一句话任务目标", "2. 判断维度与条件", "3. 红线与不可提交条件", "4. 边界、谨慎初判与升级问题"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="ASM-002-MODEL-JUDGEMENT",
        title="评测二：比较两份模型答案",
        short_description="选择只是结果，证据链才是能力。",
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        purpose="评估 Learner 是否能按固定标准比较两个模型回答并写出可复核理由。",
        learner_outcome="能给出明确结论、逐维证据、风险与结构化书面理由。",
        instructions=("阅读用户问题、约束和回答 A/B。", "选择更可靠的回答或判定都不合格，并逐项引用证据。"),
        completion_criteria=("结论明确", "证据可定位", "理由可复核", "风险与边界被识别"),
        required_deliverables=("A/B 判断与证据链",),
        estimated_duration_minutes=60,
        rubric=_rubric(
            _scored_dimension("criteria_application", "标准应用", "确认判断来自固定约束。", "逐项比较关键约束。", "覆盖关键约束", "遗漏关键约束", max_points=5, meets_threshold=4, score_category="model_judgement"),
            _scored_dimension("tradeoff_reasoning", "结论与权衡", "确认能解释取舍。", "结论、优点与缺口。", "权衡清楚且与目标一致", "结论与理由脱节", max_points=5, meets_threshold=4, score_category="model_judgement"),
            _scored_dimension("risk_detection", "风险识别", "确认能发现错误影响。", "至少两项风险。", "风险具体且影响明确", "风险缺失或泛化", max_points=5, meets_threshold=4, score_category="model_judgement"),
            _scored_dimension("evidence_reference", "证据定位", "确认理由引用具体文本。", "A/B 的原句或明确缺口。", "证据具体可定位", "只有感受没有证据", max_points=5, meets_threshold=3, score_category="rationale_writing"),
            _scored_dimension("written_rationale", "书面理由", "确认别人能复核你的判断。", "结构化、无矛盾的说明。", "结构清晰且结论一致", "跳步、矛盾或无法复核", max_points=5, meets_threshold=3, score_category="rationale_writing"),
        ),
        learning_experience=_experience(
            start="16:10",
            end="17:10",
            mode="ASSESSMENT",
            break_after="20 分钟答疑",
            blocks=(
                _block("METHOD", "先做约束矩阵", "把每条回答分别按事实准确、约束遵循、帮助程度和风险四列检查。每个判断都要指向回答中的原句或明确缺口；如果两份回答都触碰红线，应判定都不合格，而不是强行二选一。"),
                _block("USER", "用户问题", "我买的耳机左边没有声音，订单还在七天无理由期内。我今晚出差，想知道最快怎样处理。"),
                _block("CONSTRAINT", "回答约束", "必须先说明无法确认库存和即时到店结果；给出换货与退款两条路径；不得承诺具体到账或送达时间；提醒备份订单信息但不要索取完整订单号；控制在 180 字内。"),
                _block("ANSWER_A", "回答 A", "建议直接申请换货，门店今晚一定能给你一副新的。把完整订单号发来，我可以替你加急；如果退款，款项 24 小时内肯定到账。"),
                _block("ANSWER_B", "回答 B", "我无法确认门店库存或今晚能否完成换货。你可以在订单页发起换货并联系门店确认库存；若行程不便，也可在七天无理由期内申请退款，到账与物流时间以平台页面为准。请只在官方订单页核对订单信息。"),
            ),
            checks=("不能把无法验证的库存写成承诺。", "不得索取完整订单号。", "结论必须引用 A/B 的具体内容。"),
            response_sections=("1. 结论", "2. 按四项约束逐项比较", "3. 可定位证据", "4. 风险与改进建议"),
        ),
    ),
    FormalStageCatalogItem(
        stable_key="ASM-003-DATA-CONSTRUCTION",
        title="评测三：构建一组可用数据",
        short_description="把目标、约束和边界真正落到一组可验收的数据里。",
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        purpose="评估 Learner 是否能按固定标签和约束构建小型数据集并完成自检。",
        learner_outcome="能设计数据结构、覆盖约束与边界、记录问题并迭代修正。",
        instructions=("阅读构建任务与固定约束。", "提交 6 条结构化样本、覆盖说明、自检清单和问题记录。"),
        completion_criteria=("结构一致", "标签合法", "覆盖正常与边界样本", "自检可复核"),
        required_deliverables=("6 条数据样本 + 覆盖说明 + 自检与问题记录",),
        estimated_duration_minutes=90,
        rubric=_rubric(
            _scored_dimension("data_schema", "数据结构", "确认数据能被稳定读取。", "六条相同字段的样本。", "结构一致且字段完整", "结构不一致或字段缺失", max_points=3, meets_threshold=2, score_category="data_construction"),
            _scored_dimension("constraint_coverage", "约束覆盖", "确认固定标签与边界被覆盖。", "正常、组合、抱怨和隐私样本。", "覆盖完整且标签合法", "遗漏关键约束", max_points=3, meets_threshold=2, score_category="data_construction"),
            _scored_dimension("sample_quality", "样本质量", "确认样本真实且不泄露信息。", "自然文本、无真实个人信息。", "样本自然且可用", "模板化、矛盾或含敏感信息", max_points=2, meets_threshold=1, score_category="data_construction"),
            _scored_dimension("self_check", "自检与问题记录", "确认能发现并记录缺口。", "逐项自检和至少一个问题。", "自检可复核且问题具体", "没有自检或问题含糊", max_points=2, meets_threshold=1, score_category="data_construction"),
        ),
        learning_experience=_experience(
            start="17:30",
            end="19:00",
            mode="ASSESSMENT",
            break_after="18:40–19:00：提交确认、当日复盘与人工评审说明",
            blocks=(
                _block("METHOD", "构建—覆盖—自检—修正", "先固定字段和合法值，再按覆盖矩阵逐条构造；完成后检查结构一致、标签与理由一致、边界是否覆盖、是否含真实个人信息；发现问题必须修改样本，并在问题记录里说明改了什么。"),
                _block("BRIEF", "构建目标", "为售后意图模型构建 6 条中文评测样本，字段固定为 sample_id、user_text、expected_label、reason、risk_flag。标签只能使用 REFUND、EXCHANGE、LOGISTICS、OTHER。"),
                _block("COVERAGE", "覆盖要求", "至少包含：1 条明确退款、1 条明确换货、1 条只查物流、1 条只有抱怨没有处理要求、1 条多个诉求且最后请求决定标签、1 条含虚构个人信息占位符并标记风险。"),
                _block("SAFETY", "安全与质量", "不得使用真实姓名、手机号、订单号；含隐私的样本用 [PHONE]、[ORDER_ID] 占位并将 risk_flag 标为 PII_REVIEW；每条 reason 必须引用规则。"),
                _block("FORMAT", "提交格式", "可用 Markdown 表格或逐条 JSON-like 文本。结构必须一致；完成后附覆盖矩阵、自检清单和仍需确认的问题。"),
                _block("CLOSE", "18:40 前完成，随后确认", "18:40 前提交六条样本、自检与一次修正；最后 20 分钟用于确认无漏项、写下是否愿意进入后续项目规则培训、当前能力差距和需要的支持。提交结果只进入人工评审，不自动录用或淘汰。"),
            ),
            checks=("只有抱怨没有请求时不能标退款。", "多诉求按最后一个明确请求确定主标签。", "虚构占位符也要标记 PII_REVIEW。"),
            response_sections=("1. 六条结构化样本", "2. 覆盖矩阵", "3. 自检清单", "4. 问题记录与一次修正", "5. 入项意愿、能力差距与所需支持"),
        ),
    ),
)


FORMAL_STAGE_CATALOG = FORMAL_STAGE_CATALOG_V2


def validate_catalog(catalog: tuple[FormalStageCatalogItem, ...]) -> None:
    if len(catalog) != 8:
        raise ValueError("formal journey must contain Day 0, four treasures, and three assessments")
    if [item.stage_kind for item in catalog].count(JourneyStageKind.DAY_0) != 1:
        raise ValueError("formal journey must contain exactly one Day 0")
    if [item.stage_kind for item in catalog].count(JourneyStageKind.TREASURE) != 4:
        raise ValueError("formal journey must contain exactly four treasures")
    if [item.stage_kind for item in catalog].count(JourneyStageKind.ASSESSMENT) != 3:
        raise ValueError("formal journey must contain exactly three assessments")
    if len({item.stable_key for item in catalog}) != len(catalog):
        raise ValueError("formal journey stage keys must be unique")


def validate_v2_catalog(catalog: tuple[FormalStageCatalogItem, ...]) -> None:
    """Fail closed if the one-day content or fixed 50-point review contract drifts."""

    experiences = [item.learning_experience for item in catalog]
    if experiences[0].get("schedule", {}).get("start") != "10:00":
        raise ValueError("formal journey V2 must start at 10:00")
    if experiences[-1].get("schedule", {}).get("end") != "19:00":
        raise ValueError("formal journey V2 must end at 19:00")
    for experience in experiences:
        if experience.get("version") != 2:
            raise ValueError("formal journey V2 learning experiences must be version 2")
        blocks = experience.get("learning_blocks")
        checks = experience.get("knowledge_checks")
        response_sections = experience.get("response_sections")
        if not isinstance(blocks, list) or len(blocks) < 3:
            raise ValueError("formal journey V2 stages require at least three learning blocks")
        if sum(len(str(block.get("body", ""))) for block in blocks) < 180:
            raise ValueError("formal journey V2 stage learning input is too thin")
        if not isinstance(checks, list) or len(checks) < 3:
            raise ValueError("formal journey V2 stages require at least three knowledge checks")
        if not isinstance(response_sections, list) or len(response_sections) < 3:
            raise ValueError("formal journey V2 stages require at least three response sections")

    category_totals: dict[str, int] = {}
    for item in catalog:
        for dimension in item.rubric.get("dimensions", []):
            category = dimension.get("score_category")
            maximum = dimension.get("max_points")
            threshold = dimension.get("meets_threshold")
            if category is None:
                continue
            if not isinstance(maximum, int) or not isinstance(threshold, int):
                raise ValueError("formal journey V2 scored dimensions require integer bounds")
            if not 0 <= threshold <= maximum:
                raise ValueError("formal journey V2 score threshold exceeds its maximum")
            category_totals[str(category)] = category_totals.get(str(category), 0) + maximum
    if category_totals != {
        "rule_decomposition": 15,
        "model_judgement": 15,
        "rationale_writing": 10,
        "data_construction": 10,
    }:
        raise ValueError("formal journey V2 reviewer score weights must total fixed 50 points")


validate_catalog(FORMAL_STAGE_CATALOG_V1)
validate_catalog(FORMAL_STAGE_CATALOG_V2)
validate_v2_catalog(FORMAL_STAGE_CATALOG_V2)
