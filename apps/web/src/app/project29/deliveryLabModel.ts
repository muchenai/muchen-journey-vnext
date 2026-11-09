import type { BadgePointCost } from "./badgeEconomy";

export const deliveryStageIds = ["brief", "plan", "prepare", "pilot", "staff", "produce", "quality", "deliver", "retrospect"] as const;
export type DeliveryStageId = typeof deliveryStageIds[number];
export type Handling = "keep" | "redact" | "drop" | "hold";
export type Intent = "order" | "refund" | "account" | "unclear";

export const handlingOptions: { value: Handling; label: string }[] = [
  { value: "keep", label: "保留" }, { value: "redact", label: "脱敏后保留" },
  { value: "drop", label: "去重剔除" }, { value: "hold", label: "隔离待确认" },
];
export const intentOptions: { value: Intent; label: string }[] = [
  { value: "order", label: "订单物流" }, { value: "refund", label: "退款售后" },
  { value: "account", label: "账户安全" }, { value: "unclear", label: "待澄清" },
];
export const deliveryLabRewards: BadgePointCost[] = [{ type: "数据交付", amount: 12 }, { type: "质量检测", amount: 3 }];

export type DeliveryEvent = {
  title: string;
  message: string;
  options: { id: string; label: string; feedback: string }[];
};
export type DeliveryStage = {
  id: DeliveryStageId;
  title: string;
  subtitle: string;
  role: string;
  deliverable: string;
  brief: string;
  materials: { title: string; content: string }[];
  prompts: string[];
  checks: string[];
  event?: DeliveryEvent;
};

// Synthetic training case, not the inaccessible Feishu SOP or a real customer project.
export const deliveryLabStages: DeliveryStage[] = [
  {
    id: "brief", title: "需求澄清", subtitle: "先对齐什么是“交付成功”", role: "客户对接 / 交付负责人", deliverable: "需求确认单",
    brief: "星港客服中心希望用一批对话数据训练意图识别模型。你是交付负责人，需要把含糊的客户需求变成可执行、可验收的约定。",
    materials: [
      { title: "客户需求初稿", content: "交付 1,000 条中文客服对话的意图分类结果，初始类别为订单物流、退款售后、账户安全。演练交期为需求确认后 5 个工作日。" },
      { title: "待澄清事项", content: "一条对话同时出现两种意图时如何处理？信息不足的数据是否计入有效条数？新增分类、验收样本与返修轮次需要谁确认？" },
      { title: "演练验收基线", content: "本案例暂定分类正确率不低于 95%，格式合规率 100%，不允许明文敏感信息。阈值、授权范围与验收方法仍须写入客户确认单；这些不是公司正式 SOP。" },
    ],
    prompts: ["明确交付用途、范围、条数、格式、交期与责任人。", "列出至少 3 个需要客户确认的问题及其影响。", "说明数据授权、敏感信息处理和验收口径如何留痕。"],
    checks: ["已区分已知需求与待确认问题", "已写明验收口径和范围边界", "已确认授权与敏感信息处理要求"],
  },
  {
    id: "plan", title: "评估与计划", subtitle: "把交期拆成产能、成本和风险", role: "交付负责人 / 项目管理", deliverable: "实施计划与风险清单",
    brief: "在承诺交期前，先用试估算检验项目是否可交付。成本、产能与质量要一起考虑，不能只看生产速度。",
    materials: [
      { title: "资源条件", content: "可安排 3 名生产人员和 1 名质检人员。初始估算为每人每天 120 条，演练预算上限为 4,800 元；培训、返修和复检也要计入计划。" },
      { title: "排期约束", content: "客户要求 T+5 验收。T+1 完成规范和试生产，T+2 至 T+4 生产与滚动质检，T+5 完成终检、交付及验收沟通。请检验而不是直接照抄这个初稿。" },
      { title: "风险提示", content: "原始数据可能存在重复和信息不足；分类边界尚未统一；人员缺勤或需求变更都会影响有效产能。预算数字仅用于本次演练。" },
    ],
    prompts: ["给出工作分解、各阶段负责人和时间缓冲。", "用明确假设估算产能与成本，说明是否满足 T+5。", "列出至少 3 项风险、触发信号、应对措施和升级对象。"],
    checks: ["已包含培训、质检和返修工时", "已说明产能与成本的计算假设", "已为关键风险设置触发条件与负责人"],
  },
  {
    id: "prepare", title: "数据准备", subtitle: "让每条数据都有去向", role: "数据准备 / 合规检查", deliverable: "数据准备清单与异常记录",
    brief: "在练习台逐条处理 20 条虚构样本。决定保留、脱敏后保留、去重剔除或隔离待确认，再汇总处理依据。",
    materials: [
      { title: "样本说明", content: "练习台共有 20 条合成对话，包含重复、占位敏感信息、多意图和信息不足样本。占位符不含真实个人信息，请勿录入真实客户资料。" },
      { title: "处理规则", content: "保留原始样本 ID 和处理记录；未确认授权或无法判断的数据先隔离。去重、脱敏不能静默改变数量，原始数与各类去向要能对账。" },
      { title: "后续依赖", content: "选择“保留”或“脱敏后保留”的样本会进入试生产与生产练习。为完成本案例，至少保留 5 条；这是练习完整性检查，不是质量判分。" },
    ],
    prompts: ["汇总各类处理数量并说明去重、脱敏和隔离的依据。", "记录异常样本的 ID、问题、负责人及下一步动作。", "说明如何校验数据授权、格式、版本和数量一致性。"],
    checks: ["已为 20 条样本选择处理方式", "已记录数量变化与异常去向", "已说明授权、脱敏和版本检查方法"],
  },
  {
    id: "pilot", title: "规范与试生产", subtitle: "小批量验证，再扩大生产", role: "规范负责人 / 试标人员", deliverable: "加工规范与试生产结论",
    brief: "为保留样本中的前 5 条选择意图分类。用试标暴露规范中的歧义，补齐正例、反例和升级机制。",
    materials: [
      { title: "初始分类规范", content: "订单物流：发货、配送、订单状态；退款售后：退货、退款、售后处理；账户安全：登录、验证、账号保护。无法确定主诉的样本选择“待澄清”，不可编造意图。" },
      { title: "试生产要求", content: "先处理 5 条样本，记录边界案例。试标结果用于验证规范、培训和工时假设，不应直接把歧义扩散到整批生产。" },
      { title: "规范版本", content: "提交规范 v1.0 的适用范围、规则、例外、问题升级路径与生效时间。发生规则修订时，要评估已生产数据是否需要回溯。" },
    ],
    prompts: ["写出分类规则、边界案例及无法判断时的处理方式。", "汇总试生产发现、规范修订与工时调整建议。", "说明如何确认新规范并同步到所有生产和质检人员。"],
    checks: ["已完成 5 条试生产样本", "已补充歧义处理和正反例", "已明确规范版本及变更同步机制"],
    event: {
      title: "同一条对话，出现了两种分类", message: "两位试标人员分别把“包裹没到，我想退款”标为订单物流和退款售后。两人都认为自己符合初稿规则。你如何处理？",
      options: [
        { id: "align", label: "汇总争议，确认主诉规则并补充正反例", feedback: "方向提示：还要写明谁确认规则、生效版本，以及已完成数据是否需要回溯。" },
        { id: "vote", label: "按多数意见决定，继续生产", feedback: "风险提示：投票不能代替统一规则，生产与质检仍可能采用不同口径。请说明你的修正方案。" },
        { id: "ignore", label: "保留两种结果，不调整规范", feedback: "风险提示：同类样本可能持续不一致。请说明歧义如何升级、留痕和闭环。" },
      ],
    },
  },
  {
    id: "staff", title: "团队与派单", subtitle: "把标准落实到人和批次", role: "交付负责人 / 培训负责人", deliverable: "人员分工与派单计划",
    brief: "根据试生产结果安排人员准入、培训、派单和复核。保证生产者与质检者使用同一套规范。",
    materials: [
      { title: "团队情况", content: "生产人员 A 熟悉业务但新接触工具；B 有标注经验但未学习本项目规范；C 只能在 T+2 至 T+4 参与。质检人员 Q 不直接承担同一批次的自检验收。" },
      { title: "派单要求", content: "每批需要批次 ID、规范版本、样本范围、负责人、截止时间和质检人。权限按工作需要分配，禁止使用私人渠道传输数据。" },
      { title: "培训材料", content: "使用已确认的规范与试标案例开展培训。请定义试标准入条件、不合格人员的补训安排，以及异常反馈渠道。" },
    ],
    prompts: ["列出角色分工、培训准入与权限安排。", "给出批次拆分、派单节奏、截止时间和质检衔接。", "说明人员缺勤或返修增加时如何重新分配工作。"],
    checks: ["已区分生产、自检和质检职责", "已明确准入条件及数据权限", "已给出可追踪的批次派单方案"],
  },
  {
    id: "produce", title: "生产与过程管理", subtitle: "持续看见进度，也看见偏差", role: "交付负责人 / 生产团队", deliverable: "生产跟踪表与变更记录",
    brief: "继续完成保留样本的意图分类，再结合模拟批次报表判断是否需要调整计划。试生产标签会沿用到生产练习中。",
    materials: [
      { title: "T+3 模拟报表", content: "全量项目已加工 620 / 1,000 条，其中 40 条待返修、30 条待澄清；另有 380 条尚未加工。已加工不等于可验收，三类状态不能重复计数。" },
      { title: "进度异常", content: "生产人员 C 在 T+4 请假。按原排期存在延期风险，请结合返修、质检与待澄清工作量，重新评估剩余有效产能。" },
      { title: "练习台说明", content: "当前保留样本需要逐条选择意图。练习台是小样本操作；1,000 条项目报表是另行提供的合成情境，不会由你的点击自动变成真实生产数据。" },
    ],
    prompts: ["汇总各批次的已加工、可交付、返修、待澄清与未加工状态。", "说明缺勤对排期、成本和质量的影响及调整措施。", "记录本次客户变更的评估、确认人及版本生效条件。"],
    checks: ["已完成全部保留样本的分类", "已区分加工进度与可验收进度", "已记录异常升级与客户变更处理"],
    event: {
      title: "客户临时要求新增“投诉升级”类别", message: "客户希望在原交期内增加一个分类，并回溯已经完成的数据，但尚未确认新增成本和验收口径。",
      options: [
        { id: "assess", label: "评估回溯量、成本与交期，确认变更后执行", feedback: "方向提示：补齐新增类别的定义、确认人、版本切换及在制数据处理方案。" },
        { id: "promise", label: "先承诺原交期，团队加班消化", feedback: "风险提示：未经评估的承诺可能同时损害交期、预算与质量。请写出重新评估和沟通方案。" },
        { id: "refuse", label: "直接拒绝，不再沟通", feedback: "风险提示：可以守住范围边界，但仍需要提供影响评估和可选方案，不能让变更悬而未决。" },
      ],
    },
  },
  {
    id: "quality", title: "质检与返修", subtitle: "找出原因，再验证问题已关闭", role: "质量负责人 / 返修人员", deliverable: "质检报告与返修复检记录",
    brief: "模拟全量批次的抽检未达到演练基线。你需要区分个别错误和系统性规范问题，决定返修范围与复检方式。",
    materials: [
      { title: "全量批次模拟抽检", content: "抽检 20 条，其中 18 条分类正确、2 条为多意图争议，正确率 90%，低于本案例暂定的 95% 验收基线。这是给定的模拟报表，不是系统对你的答案评分。" },
      { title: "错误线索", content: "两条错误分别出现在批次 B02、B03，均使用旧版主诉规则。仅修改被抽到的两条数据，不能证明同类错误已被清除。" },
      { title: "闭环要求", content: "记录错误类型、影响范围、根因、返修负责人、规范版本和复检证据。返修后的验收仍以客户约定的方法为准。" },
    ],
    prompts: ["解释为什么当前批次不能直接按合格交付。", "制定抽检扩展、回溯返修、培训纠偏与复检方案。", "列出返修闭环证据，以及仍不达标时的升级和沟通方式。"],
    checks: ["已区分抽样错误与潜在系统性问题", "已明确返修范围、责任人及版本", "已定义复检方式和放行条件"],
    event: {
      title: "离交期只剩一天，是否直接交付？", message: "生产团队建议只修正抽检发现的两条错误后立即打包。客户尚未同意降低验收要求。",
      options: [
        { id: "recheck", label: "评估同类错误范围，返修并复检后再判断放行", feedback: "方向提示：同时说明对交期的影响、客户沟通和未解决风险，不要只写“重新质检”。" },
        { id: "sample-only", label: "只修正抽检样本，按原计划放行", feedback: "风险提示：样本修正不代表整批问题闭环。请说明如何验证其他批次没有同类问题。" },
        { id: "lower", label: "自行把验收线改为 90%", feedback: "风险提示：团队不能单方面更改客户验收标准。任何变更都需要明确确认和留痕。" },
      ],
    },
  },
  {
    id: "deliver", title: "交付与验收", subtitle: "交付的不只是一个文件", role: "交付负责人 / 客户验收", deliverable: "交付清单与验收闭环记录",
    brief: "在正式打包前核对文件、版本、条数和质量证据。把交付包交给客户，并对验收反馈进行分类处理。",
    materials: [
      { title: "交付包约定", content: "本案例使用 UTF-8 JSONL，每条至少包含 sample_id、intent、spec_version、batch_id。数据文件、数量对账、规范版本、质检报告与异常处理说明需要一起核对。" },
      { title: "版本与传输", content: "交付命名示例 SG-intent-v1.0；使用客户确认的传输渠道和授权范围。交付时保留接收确认，不用未授权的公开网盘代替正式交付。" },
      { title: "验收反馈", content: "客户反馈可能是约定内的质量缺陷，也可能是新类别或新增范围。分别记录处理方式、责任人和截止时间，不能把新增需求默认为原范围返修。" },
    ],
    prompts: ["列出交付文件、字段、条数、版本和质量证据的核对清单。", "说明传输权限、接收确认与客户验收的记录方式。", "给出缺陷返修与新增需求的区分和闭环方法。"],
    checks: ["已核对数量、格式、规范和交付版本", "已写明授权渠道及接收确认", "已区分验收缺陷和新增范围"],
  },
  {
    id: "retrospect", title: "结算与复盘", subtitle: "让这一次交付，成为下一次的经验", role: "交付负责人 / 经营复盘", deliverable: "项目复盘与归档清单",
    brief: "汇总验收结论与成本偏差，沉淀可复用的改进措施。按授权约定归档或删除数据，形成完整的交付档案。",
    materials: [
      { title: "经营复盘材料", content: "对比原预算、实际投入、有效产量、返修成本与交期偏差。请说明统计口径和证据来源，不能凭空补出实际成本或客户验收结论。" },
      { title: "结算依据", content: "核对需求及变更确认、有效交付量、验收确认、约定计价方式。此处仅拟定结算核对项，不创建真实付款或合同记录。" },
      { title: "归档与删除", content: "归档规范、培训、批次、质检、变更和验收记录。原始数据与中间文件的留存期限、访问权限和删除凭证以授权协议为准。" },
    ],
    prompts: ["复盘本次需求、规范、人员和质量管理中的主要偏差。", "提出至少 3 项可执行改进，写明负责人和验证指标。", "列出结算依据、归档目录、访问权限与数据删除安排。"],
    checks: ["已说明成本与交期偏差的证据口径", "已形成可执行的改进措施", "已列清验收、结算和数据归档事项"],
  },
];

export const deliveryLabSamples = [
  { id: "SG-001", text: "订单 A001 已经付款，什么时候发货？" },
  { id: "SG-002", text: "退货已经签收，退款什么时候到账？" },
  { id: "SG-003", text: "登录时一直收不到验证码，怎么处理？" },
  { id: "SG-004", text: "订单 A001 已经付款，什么时候发货？" },
  { id: "SG-005", text: "包裹还没到，我想申请退款。" },
  { id: "SG-006", text: "请用[待脱敏联系方式]联系我，我想查订单。" },
  { id: "SG-007", text: "就是上次那个事情，帮我处理一下。" },
  { id: "SG-008", text: "物流三天没有更新了，能查一下吗？" },
  { id: "SG-009", text: "收到的商品破损，如何办理退货？" },
  { id: "SG-010", text: "我怀疑账号被其他人登录了。" },
  { id: "SG-011", text: "退货已经签收，退款什么时候到账？" },
  { id: "SG-012", text: "换货需要寄回哪些配件？" },
  { id: "SG-013", text: "我忘记密码了，想重新设置。" },
  { id: "SG-014", text: "快递显示签收，但我没有收到包裹。" },
  { id: "SG-015", text: "资料里有[待脱敏联系地址]，请帮我确认退货进度。" },
  { id: "SG-016", text: "怎么解除以前绑定的登录设备？" },
  { id: "SG-017", text: "退款金额与订单支付金额不一致。" },
  { id: "SG-018", text: "这个订单能修改配送时间吗？" },
  { id: "SG-019", text: "新的手机号如何更换账号绑定？" },
  { id: "SG-020", text: "我想取消，应该怎么办？" },
];

export type LabAnswer = { artifact: string; checks: string[]; decision: string; rationale: string };
export type DeliveryLabSession = {
  status: "available" | "active" | "submitted";
  activeStage: DeliveryStageId;
  answers: Record<DeliveryStageId, LabAnswer>;
  handling: Partial<Record<string, Handling>>;
  labels: Partial<Record<string, Intent>>;
  completed: DeliveryStageId[];
  submittedAt: string | null;
  submissionCount: number;
};

export function createDeliveryLabSession(): DeliveryLabSession {
  return {
    status: "available", activeStage: "brief", handling: {}, labels: {}, completed: [], submittedAt: null, submissionCount: 0,
    answers: Object.fromEntries<LabAnswer>(deliveryStageIds.map(id => [id, { artifact: "", checks: [], decision: "", rationale: "" }])) as Record<DeliveryStageId, LabAnswer>,
  };
}
export function beginDeliveryLab(session: DeliveryLabSession): DeliveryLabSession {
  return session.status === "available" ? { ...session, status: "active", activeStage: "brief" } : session;
}
function invalidateFrom(session: DeliveryLabSession, stageId: DeliveryStageId): DeliveryLabSession {
  const index = deliveryStageIds.indexOf(stageId);
  return { ...session, completed: session.completed.filter(id => deliveryStageIds.indexOf(id) < index) };
}
export function updateLabAnswer(session: DeliveryLabSession, id: DeliveryStageId, patch: Partial<LabAnswer>): DeliveryLabSession {
  if (session.status !== "active") return session;
  const previous = session.answers[id];
  const answer = { ...previous, ...patch };
  if (answer.artifact === previous.artifact && answer.decision === previous.decision && answer.rationale === previous.rationale &&
    answer.checks.length === previous.checks.length && answer.checks.every((check, index) => check === previous.checks[index])) return session;
  return invalidateFrom({ ...session, answers: { ...session.answers, [id]: answer } }, id);
}
export function updateLabHandling(session: DeliveryLabSession, sampleId: string, value: string): DeliveryLabSession {
  const option = handlingOptions.find(item => item.value === value);
  if (session.status !== "active" || !option || !deliveryLabSamples.some(item => item.id === sampleId) || session.handling[sampleId] === option.value) return session;
  return invalidateFrom({ ...session, handling: { ...session.handling, [sampleId]: option.value } }, "prepare");
}
export function productionSamples(session: DeliveryLabSession) {
  return deliveryLabSamples.filter(sample => session.handling[sample.id] === "keep" || session.handling[sample.id] === "redact");
}
export function updateLabLabel(session: DeliveryLabSession, sampleId: string, value: string): DeliveryLabSession {
  const option = intentOptions.find(item => item.value === value);
  const samples = productionSamples(session);
  if (session.status !== "active" || !option || !samples.some(item => item.id === sampleId) || session.labels[sampleId] === option.value) return session;
  const firstStage = samples.slice(0, 5).some(sample => sample.id === sampleId) ? "pilot" : "produce";
  return invalidateFrom({ ...session, labels: { ...session.labels, [sampleId]: option.value } }, firstStage);
}
export function validateLabStage(session: DeliveryLabSession, id: DeliveryStageId): string[] {
  if (session.status === "available") return ["请先领取模拟任务，再填写阶段成果。"];
  if (session.status === "submitted") return ["请先撤回模拟提交，再修改成果。"];
  const stage = deliveryLabStages.find(item => item.id === id)!;
  const answer = session.answers[id];
  const errors: string[] = [];
  if (deliveryStageIds.slice(0, deliveryStageIds.indexOf(id)).some(previous => !session.completed.includes(previous))) errors.push("请先完成前面阶段的自查；所有阶段材料仍可自由预览。");
  if (answer.artifact.trim().length < 60 || answer.artifact.length > 6000) errors.push("请填写 60～6,000 字的阶段成果，说明判断、依据和下一步动作。");
  if (!stage.checks.every(check => answer.checks.includes(check))) errors.push("请逐项核对并勾选本阶段的 3 项自查。");
  if (stage.event && (!stage.event.options.some(option => option.id === answer.decision) || answer.rationale.trim().length < 30 || answer.rationale.length > 2000)) errors.push("本阶段有异常事件：请选择处理方案，并填写 30～2,000 字的判断依据。");
  if (id === "prepare") {
    if (!deliveryLabSamples.every(sample => handlingOptions.some(option => option.value === session.handling[sample.id]))) errors.push("请在样本练习台为全部 20 条样本选择处理方式。");
    if (productionSamples(session).length < 5) errors.push("本次演练至少需要 5 条保留样本用于试生产。");
  }
  if (id === "pilot" || id === "produce") {
    const samples = id === "pilot" ? productionSamples(session).slice(0, 5) : productionSamples(session);
    if (samples.length < 5 || !samples.every(sample => intentOptions.some(option => option.value === session.labels[sample.id]))) errors.push(id === "pilot" ? "请完成前 5 条保留样本的试生产分类。" : "请完成全部保留样本的生产分类。");
  }
  return errors;
}
export function completeLabStage(session: DeliveryLabSession, id: DeliveryStageId) {
  const errors = validateLabStage(session, id);
  if (errors.length) return { session, errors };
  const completed = deliveryStageIds.filter(stageId => stageId === id || session.completed.includes(stageId));
  return {
    session: { ...session, completed, activeStage: deliveryStageIds[Math.min(deliveryStageIds.indexOf(id) + 1, deliveryStageIds.length - 1)] },
    errors,
  };
}
export function canSubmitDeliveryLab(session: DeliveryLabSession) {
  return session.status === "active" && deliveryStageIds.every(id => session.completed.includes(id) && validateLabStage(session, id).length === 0);
}
export function submitDeliveryLab(session: DeliveryLabSession, submittedAt: string): DeliveryLabSession {
  if (!canSubmitDeliveryLab(session) || !Number.isFinite(Date.parse(submittedAt))) return session;
  return { ...session, status: "submitted", submittedAt, submissionCount: session.submissionCount + 1 };
}
export function withdrawDeliveryLab(session: DeliveryLabSession): DeliveryLabSession {
  return session.status === "submitted" ? { ...session, status: "active", submittedAt: null } : session;
}
export function buildDeliveryArchive(session: DeliveryLabSession, identity: string) {
  const lines = [
    "# 数据交付全流程 · 模拟交付档案", "",
    "> 仅为前端练习导出。未发送到 NPC 管理端，不代表审核通过，不发放经验或徽章点。",
    "> 所有客户、样本、预算及质量报表均为虚构；本案例不是公司正式 SOP。", "",
    `练习身份：${identity}`, `阶段自查：${session.completed.length} / 9`,
    `模拟提交次数：${session.submissionCount}`, `模拟提交时间：${session.submittedAt || "尚未提交"}`, "",
  ];
  for (const [index, stage] of deliveryLabStages.entries()) {
    const answer = session.answers[stage.id];
    lines.push(`## ${String(index + 1).padStart(2, "0")} ${stage.title} · ${stage.deliverable}`, "", answer.artifact || "尚未填写", "", ...stage.checks.map(check => `- [${answer.checks.includes(check) ? "x" : " "}] ${check}`), "");
    if (stage.event) lines.push(`### 异常事件：${stage.event.title}`, stage.event.options.find(option => option.id === answer.decision)?.label || "尚未选择", answer.rationale || "尚未填写判断依据", "");
  }
  lines.push("## 20 条样本练习记录", "", "| 样本 ID | 原始合成文本 | 处理方式 | 意图分类 |", "| --- | --- | --- | --- |");
  for (const sample of deliveryLabSamples) lines.push(`| ${sample.id} | ${sample.text} | ${handlingOptions.find(option => option.value === session.handling[sample.id])?.label || "未处理"} | ${session.handling[sample.id] === "drop" || session.handling[sample.id] === "hold" ? "不进入生产" : intentOptions.find(option => option.value === session.labels[sample.id])?.label || "未分类"} |`);
  return lines.join("\n");
}
