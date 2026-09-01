import journeyProduct from "./muchen-journey-product.generated.json";
import controlledRelease from "./muchen-journey-controlled-release.generated.json";
import moduleBindings from "./muchen-journey-module-bindings.generated.json";

export type JourneyModuleKey =
  | "exploration-camp"
  | "newcomer-village"
  | "ai-academy"
  | "delivery-guild"
  | "certification-arena"
  | "career-map";

export type JourneyModule = {
  key: JourneyModuleKey;
  runtimeKey: string;
  order: number;
  name: string;
  shortName: string;
  owner: string;
  role: "STAGE" | "CROSS_CUTTING_RESULT";
  promise: string;
  question: string;
  nextAction: string;
  output: string;
  source: string;
  steps: readonly string[];
  evidence: readonly string[];
  humanGate: string;
  prohibited: string;
  contentBinding: ModuleContentBinding;
};

export type ModuleContentBinding = {
  packageId: string;
  packageSha256: string;
  version: string;
  effectiveAt: string;
  ownerName: string;
  ownerDecision: "APPROVED";
  contentEstimatedMinutes: number;
  contentItemCount: number;
  taskVersionCount: number;
  rubricCount: number;
  reviewerPoolRef: string;
  primaryReviewers: readonly string[];
  backupReviewers: readonly string[];
  dataPolicy: {
    productionWriteAllowed: boolean;
    rawCustomerDataAllowed: boolean;
    aiHighImpactDecisionAllowed: boolean;
    visibility: readonly string[];
    retentionPolicy: string;
  };
};

type JourneyModuleContract = {
  key: JourneyModuleKey;
  runtime_key: string;
  order: number;
  name: string;
  owner: string;
  role: JourneyModule["role"];
  output: string;
};

type JourneyModuleExperience = Omit<
  JourneyModule,
  "key" | "runtimeKey" | "order" | "name" | "owner" | "role" | "output" | "contentBinding"
>;

const MODULE_EXPERIENCE: Record<JourneyModuleKey, JourneyModuleExperience> = {
  "exploration-camp": {
    shortName: "找到方向",
    promise: "用四个真实业务宝藏建立方向感，再用实操形成第一份个人成长基线。",
    question: "我适合从哪里开始，下一阶段应该练什么？",
    nextAction: "继续当前探索任务",
    source: "探索营 V1.0 四宝藏",
    steps: ["选择一个真实问题", "从四宝藏中寻找线索", "完成能力实操", "由真人确认结果"],
    evidence: ["学习与问题线索", "三项能力实操", "Reviewer 反馈", "Day 1 结果包"],
    humanGate: "Day 1 只决定下一训练阶段，不直接作录用、淘汰或项目准入终判。",
    prohibited: "不能只凭阅读完成度、积分或 AI 评价生成正式人才结论。",
  },
  "newcomer-village": {
    shortName: "学会做事",
    promise: "继承已验证的任务闭环，在受控真实项目任务中完成提交、审核、返工或通过。",
    question: "在真实工作里，我能不能按规则把事情交付出来？",
    nextAction: "领取一项受控任务",
    source: "沐晨新手村已验证任务闭环",
    steps: ["理解任务与边界", "在训练环境完成实操", "提交证据", "接受独立审核", "返工或通过"],
    evidence: ["固定任务版本", "提交版本历史", "独立 Reviewer 结论", "返工记录"],
    humanGate: "运营者不能成为自己任务的唯一 Reviewer；正式状态必须由独立 Reviewer 签署。",
    prohibited: "Journey 内不直接执行生产作业，自证也不能产生正式通过状态。",
  },
  "ai-academy": {
    shortName: "练成能力",
    promise: "允许异步学习，但把正式能力结果建立在练习、作品证据和人工 Gate 上。",
    question: "我学到的 AI 方法，能不能在任务里稳定用出来？",
    nextAction: "开始一个能力单元",
    source: "《AI学院主管_2026下半年执行计划_V0.2》",
    steps: ["选择能力目标", "异步学习", "完成练习", "提交作品证据", "真人评定"],
    evidence: ["课程完成记录", "练习与作品", "测评结果", "人工反馈"],
    humanGate: "学习完成不等于能力通过；正式能力等级必须有实操证据和真人签署。",
    prohibited: "不能用观看、签到或 AI 初评分替代能力认证。",
  },
  "delivery-guild": {
    shortName: "在协作中成长",
    promise: "围绕真实业务问题组织导师、同伴和受控任务，沉淀可复核的协作与交付证据。",
    question: "我能不能和真实团队协作，并在边界内完成交付？",
    nextAction: "查看适合我的公会任务",
    source: "真实业务线任务包＋公会导师机制",
    steps: ["加入业务公会", "接受导师说明", "选择受控任务", "协作交付", "复盘并收证据"],
    evidence: ["任务授权边界", "协作过程记录", "交付证据", "导师评价", "项目复盘"],
    humanGate: "任务必须由真实业务 Owner 授权，结论由导师与独立 Reviewer 按证据确认。",
    prohibited: "不能把训练任务伪装成生产权限，也不能把导师印象当正式能力结论。",
  },
  "certification-arena": {
    shortName: "证明自己",
    promise: "通过模拟真实大型项目的综合挑战，验证判断、协作、交付和复盘能力。",
    question: "面对复杂任务，我能否拿出经得起复核的综合能力证据？",
    nextAction: "查看认证挑战与门槛",
    source: "认证治理规则＋模拟真实项目挑战",
    steps: ["确认认证目标", "接受固定挑战", "完成综合实操", "Panel 评审", "签署或申诉"],
    evidence: ["固定挑战版本", "过程与交付证据", "Panel 评分", "签署记录", "申诉记录"],
    humanGate: "AI 只做自查、初评和摘要；正式认证由真人 Panel 签署，并保留独立申诉。",
    prohibited: "不能自动认证，不能让原评审者单独裁决针对自身结论的申诉。",
  },
  "career-map": {
    shortName: "看见下一步",
    promise: "把五个阶段的事实、人工判断和发展建议分层呈现，形成可解释的成长路线。",
    question: "我现在有哪些已证明能力，下一步最值得练什么？",
    nextAction: "查看我的成长结果",
    source: "五阶段 Evidence Ledger＋人工签署结果",
    steps: ["汇总可核对事实", "区分人工判断与 AI 建议", "识别能力差距", "确认 Growth Plan", "持续更新证据"],
    evidence: ["来源可追溯的能力证据", "人工签署结论", "AI 建议标识", "Growth Plan 版本"],
    humanGate: "积分仅作激励与参考；高影响结论由真人签署，个人可查看来源并提出申诉。",
    prohibited: "不能把积分、AI 建议或 Day 1 结果直接转换为录用、晋升、淘汰或绩效结论。",
  },
};

const CONTROLLED_RELEASE_MODULE_KEYS = new Set<string>(controlledRelease.modules);
const APPROVED_MODULES = (journeyProduct.approved_product_modules.modules as JourneyModuleContract[])
  .filter((contract) => CONTROLLED_RELEASE_MODULE_KEYS.has(contract.key));
const CONTENT_BINDINGS = new Map(
  moduleBindings.modules.map((binding) => [binding.module_key, binding]),
);

if (
  APPROVED_MODULES.length !== controlledRelease.modules.length
  || CONTENT_BINDINGS.size !== controlledRelease.modules.length
) {
  throw new Error("Controlled release module or content binding projection is incomplete");
}

export const JOURNEY_MODULES: readonly JourneyModule[] = APPROVED_MODULES.map((contract) => {
  const binding = CONTENT_BINDINGS.get(contract.key);
  if (!binding || binding.owner_decision !== "APPROVED") {
    throw new Error(`Missing approved content binding for ${contract.key}`);
  }
  return {
    key: contract.key,
    runtimeKey: contract.runtime_key,
    order: contract.order,
    name: contract.name,
    owner: contract.owner,
    role: contract.role,
    output: contract.output,
    ...MODULE_EXPERIENCE[contract.key],
    contentBinding: {
      packageId: binding.package_id,
      packageSha256: binding.package_sha256,
      version: binding.version,
      effectiveAt: binding.effective_at,
      ownerName: binding.owner_name,
      ownerDecision: binding.owner_decision,
      contentEstimatedMinutes: binding.content_estimated_minutes,
      contentItemCount: binding.content_item_count,
      taskVersionCount: binding.task_version_count,
      rubricCount: binding.rubric_count,
      reviewerPoolRef: binding.reviewer_pool_ref,
      primaryReviewers: binding.primary_reviewers,
      backupReviewers: binding.backup_reviewers,
      dataPolicy: {
        productionWriteAllowed: binding.data_policy.production_write_allowed,
        rawCustomerDataAllowed: binding.data_policy.raw_customer_data_allowed,
        aiHighImpactDecisionAllowed: binding.data_policy.ai_high_impact_decision_allowed,
        visibility: binding.data_policy.visibility,
        retentionPolicy: binding.data_policy.retention_policy,
      },
    },
  };
});

export function getJourneyModule(key: string): JourneyModule | undefined {
  return JOURNEY_MODULES.find((module) => module.key === key);
}
