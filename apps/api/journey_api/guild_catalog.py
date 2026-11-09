"""Versioned project39 practice templates, not actual instructor publications."""

HALLS = [
    dict(id="multilingual", title="多语种数据交付线", type="交付线工会", description="让术语、语义与格式跨越语言准确对齐。", icon="ce04e"),
    dict(id="agent-trajectories", title="Agent 交付与行为轨迹交付线", type="交付线工会", description="还原决策路径，交付可复核的行为轨迹。", icon="9aa97"),
    dict(id="code-reasoning", title="代码推理交付线", type="交付线工会", description="验证推理、代码与测试证据的一致性。", icon="a6862"),
    dict(id="quality-data", title="高质量数据构建交付线", type="交付线工会", description="从样本标准到质量闭环，夯实数据根基。", icon="a03b5"),
    dict(id="multimodal", title="多模态数据交付线", type="交付线工会", description="连接图像、文本与标注，让信息彼此对齐。", icon="42cb2"),
    dict(id="model-evaluation", title="通用模型测评交付线", type="交付线工会", description="以基准与证据，识别模型能力边界。", icon="d7bdc"),
    dict(id="dialect-speech", title="方言语音交付线", type="交付线工会", description="守护乡音细节，完成可信的语音交付。", icon="eec40"),
    dict(id="functional", title="综合职能工会", type="职能工会", description="面向运营、人才、财法、组织与项目协同的综合实践。", icon="8c48a"),
]
HALL_BY_ID = {hall["id"]: hall for hall in HALLS}
TASKS = [
    dict(id="guild-l1-brief", level=1, title="需求澄清与验收边界", difficulty="进阶", minutes=60,
         referenceMentor="陈远 · 交付线负责人",
         brief="客户提出 5 天内交付 1,000 条数据，但没有明确有效数据、歧义样本和验收方法。请在承诺交期前完成需求确认。",
         deliverable="一份需求确认单，写明交付范围、至少 3 项待澄清问题、验收口径和确认责任人。",
         checks=["明确有效条数与范围边界", "列出待澄清问题及责任人", "写明质量、格式与验收方法"]),
    dict(id="guild-l2-quality", level=2, title="质检返修与进度调整", difficulty="挑战", minutes=90,
         referenceMentor="周予安 · 数据质量导师",
         brief="抽检 20 条仅 18 条正确，低于客户约定的 95% 合格线，且一名生产人员临时缺勤。请重新安排返修、复检和剩余交付计划。",
         deliverable="一份质检与调整方案，包含错误根因、返修范围、复检方法、人员排期与风险升级。",
         checks=["区分个别错误与系统性问题", "明确返修范围、负责人和复检条件", "评估缺勤对交期和成本的影响"]),
    dict(id="guild-l3-change", level=3, title="复杂交付变更与验收复盘", difficulty="挑战", minutes=90,
         referenceMentor="许嘉宁 · 风险管理导师",
         brief="客户临时新增分类并要求回溯历史批次，原交期不变，部分数据还有授权范围疑问。请制定变更、风险控制、验收和复盘的完整方案。",
         deliverable="一份综合交付方案，包含变更影响评估、数据授权处理、备选方案、客户确认、版本切换与复盘改进。",
         checks=["评估变更的成本、交期及回溯影响", "明确授权边界、客户确认和版本生效", "提出可验证的验收与复盘改进措施"]),
]
for task in TASKS:
    task.update(version=1, source="project39-template", publicationStatus="published", mentor="内置任务模板")

# Keep existing versions addressable when a later catalog revision is introduced.
TASK_VERSIONS = {(task["id"], task["version"]): task for task in TASKS}
