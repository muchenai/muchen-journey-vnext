export type ModuleName = "village" | "academy" | "guild"
export const moduleTitles: Record<ModuleName, string> = {
  village: "新手村",
  academy: "AI 学院",
  guild: "交付线工会",
}
export type PracticeTask = {
  id: string
  category: string
  title: string
  description: string
  level: string
  minutes: number
  review: string
  experience: number
  points: number
  mentor: string
  badges: [string, number][]
  requirements: string[]
}
export const practiceTasks: PracticeTask[] = [
  {
    id: "interview",
    category: "产品开发",
    title: "用户访谈：找到真正的问题",
    description: "从访谈记录中提炼需求，区分用户描述与真实问题，完成洞察卡片。",
    level: "入门",
    minutes: 30,
    review: "人工审核",
    experience: 50,
    points: 5,
    mentor: "林若晴",
    badges: [
      ["产品开发", 70],
      ["数据交付", 30],
    ],
    requirements: [
      "设计 5 个开放式访谈问题，说明每个问题的目的。",
      "整理 3 条用户洞察，区分事实、假设与真实需求。",
      "提交一张洞察卡片，附上建议的下一步验证行动。",
    ],
  },
  {
    id: "api",
    category: "技术开发",
    title: "搭建你的第一个 REST API",
    description: "实现一个任务列表接口，完成参数校验、错误处理与接口文档。",
    level: "进阶",
    minutes: 60,
    review: "人工审核",
    experience: 100,
    points: 10,
    mentor: "陈知远",
    badges: [
      ["技术开发", 80],
      ["质量检测", 20],
    ],
    requirements: [
      "定义任务查询、创建和更新接口。",
      "列出参数校验规则与统一错误码。",
      "提交可运行的代码仓库链接和接口说明。",
    ],
  },
  {
    id: "clean",
    category: "数据交付",
    title: "数据清洗与交付检查",
    description: "清洗一份销售数据，输出质量报告，并按照交付清单完成验收。",
    level: "入门",
    minutes: 30,
    review: "AI 自测",
    experience: 50,
    points: 5,
    mentor: "周予安",
    badges: [
      ["数据交付", 60],
      ["质量检测", 40],
    ],
    requirements: [
      "列出缺失、重复和异常数据的判断规则。",
      "用示例数据演示清洗过程，记录前后数量。",
      "提交质量报告与交付检查清单。",
    ],
  },
  {
    id: "risk",
    category: "PMO",
    title: "为项目制定一份风险清单",
    description: "识别项目中的关键风险，为风险设定责任人、触发条件和应对措施。",
    level: "进阶",
    minutes: 60,
    review: "人工审核",
    experience: 100,
    points: 10,
    mentor: "许嘉宁",
    badges: [
      ["PMO", 60],
      ["项目管理", 40],
    ],
    requirements: [
      "识别至少 5 项项目风险并标注优先级。",
      "为每项风险设置责任人、触发条件与应对措施。",
      "给出风险升级的判断标准和沟通路径。",
    ],
  },
  {
    id: "grounding",
    category: "AI 评测",
    title: "让 AI 回答有据可依",
    description: "改写提示词，设计对照测试，并用评测标准验证回答质量的提升。",
    level: "进阶",
    minutes: 60,
    review: "AI 自测",
    experience: 100,
    points: 10,
    mentor: "宋一禾",
    badges: [
      ["AI 评测", 60],
      ["AI 能力", 40],
    ],
    requirements: [
      "提供原始提示词与优化后的提示词。",
      "准备 5 组对照问题，记录回答差异。",
      "从准确性、可追溯性和完整性三个维度评分。",
    ],
  },
  {
    id: "test",
    category: "质量检测",
    title: "从需求到测试用例",
    description: "从产品需求提取测试点，覆盖主流程、边界条件与异常路径。",
    level: "入门",
    minutes: 30,
    review: "AI 自测",
    experience: 50,
    points: 5,
    mentor: "陈知远",
    badges: [["质量检测", 100]],
    requirements: [
      "选取一个熟悉的产品功能，列出测试点。",
      "至少编写 8 条测试用例，覆盖正常、边界和异常场景。",
      "标明前置条件、操作步骤与预期结果。",
    ],
  },
]
export type AcademyCourse = {
  id: string
  category: string
  title: string
  description: string
  level: string
  domain: string
  minutes: number
  learners: number
  author: string
  unavailable?: boolean
}
export const academyCourses: AcademyCourse[] = [
  {
    id: "prompt",
    category: "管理员外链",
    title: "提示词炼金术：把想法变成好答案",
    description:
      "从一个模糊的想法出发，学会用角色、任务、背景和输出格式，调配一条真正好用的提示词。附可直接复用的工作模板。",
    level: "入门",
    domain: "通用能力",
    minutes: 18,
    learners: 328,
    author: "沐晨学院",
  },
  {
    id: "workflow",
    category: "平台视频",
    title: "搭建你的第一个 AI 工作流",
    description:
      "把重复的小事交给 AI。从整理信息到生成初稿，跟随演示拆解一条工作流，找到属于你的效率加速器。",
    level: "进阶",
    domain: "效率工具",
    minutes: 26,
    learners: 216,
    author: "沐晨学院",
  },
  {
    id: "design",
    category: "员工共建",
    title: "我的 AI 设计搭子，一周省下 5 小时",
    description:
      "分享我在需求分析、灵感收集和设计说明里使用 AI 的真实流程。里面有踩过的坑，也有可以带走的小技巧。",
    level: "入门",
    domain: "岗位实践",
    minutes: 12,
    learners: 189,
    author: "陈可可",
  },
  {
    id: "report",
    category: "管理员外链",
    title: "AI 办公锦囊：让周报不再熬夜",
    description:
      "学习用 AI 提炼工作重点、组织周报结构，把零散的工作记录变成清晰有重点的成果表达。",
    level: "入门",
    domain: "效率工具",
    minutes: 15,
    learners: 142,
    author: "沐晨学院",
    unavailable: true,
  },
  {
    id: "meeting",
    category: "平台视频",
    title: "10 分钟解锁 AI 会议纪要",
    description:
      "从会议录音到行动清单，掌握整理会议纪要的关键步骤，让每一次讨论都落到下一步行动。",
    level: "入门",
    domain: "效率工具",
    minutes: 10,
    learners: 274,
    author: "沐晨学院",
  },
  {
    id: "research",
    category: "员工共建",
    title: "从 0 到 1，用 AI 做一份调研报告",
    description:
      "一位产品同学的实战复盘：怎样提问、交叉核对资料，再把信息整理成有结论的调研报告。欢迎带着你的问题一起探索。",
    level: "进阶",
    domain: "岗位实践",
    minutes: 20,
    learners: 96,
    author: "周屿",
  },
]
