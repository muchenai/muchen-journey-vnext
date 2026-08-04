# 36｜WP-24 Formal Exploration Camp V2

状态：`AS_BUILT`

产品状态：`STAGING_DEPLOYED / V2_PUBLICATION_OWNER_REPORTED / HUMAN_UX_DEFECTS_OPEN / CONTROLLED_INVITE_PAUSED`

日期：2026-08-04
前置：`DEC-024`、REQ-BR-011..014、WP-19～WP-22 最小纵向切片

## 1. 为什么启动 WP-24

WP-19～WP-22 证明了八阶段 Journey 能发布、邀请、提交、修订和形成结果，但受控 V1 的正文仍是技术切片：Learner 进入任务后缺少足够学习输入，第三项评测也偏离正式方案。WP-23 的首位真人明确暴露了这个问题：系统能够工作，不等于探索营能够完成一天学习、判断与筛选。

WP-24 不重做 vNext 基座，也不修改 Journey V1、既有 Enrollment、Submission、Evaluation 或 WP-23 现场。它以新 JourneyVersion 和新 TaskVersion 发布正式 V2。

## 2. 产品合同

### 2.1 一天路线

| 时间 | 阶段 | 学习/评测目标 | 完成方式 |
| --- | --- | --- | --- |
| 10:00–10:25 | Day 0 | 路线、人工评审和求助边界 | Learner 学习证据 |
| 10:25–11:10 | 宝藏一 | 公司、Muchener 与确定性交付 | Learner 学习证据 |
| 11:20–12:00 | 宝藏二 | 模型输出、AI 数据与证据链 | Learner 学习证据 |
| 12:00–13:00 | 午休 | 不计任务 | — |
| 13:00–13:45 | 宝藏三 | 客户目标到质检验收的项目质量链 | Learner 学习证据 |
| 13:55–14:40 | 宝藏四 | 角色、责任边界和有效升级 | Learner 学习证据 |
| 15:00–16:00 | 评测一 | 规则拆解 | Reviewer 评分与反馈 |
| 16:10–17:10 | 评测二 | 模型回答比较与理由写作 | Reviewer 评分与反馈 |
| 17:10–17:30 | 答疑/休息 | 不替 Learner 作答 | — |
| 17:30–19:00 | 评测三与收束 | 通用数据构建、自检、提交确认和复盘 | Reviewer 评分与反馈 |

每一站必须先展示输入材料、固定约束和自检问题，再开放作答。禁止回到“什么都没学就面对空白输入框”的 V1 体验。

### 2.2 三项真实题面

1. `ASM-001-RULE-BREAKDOWN`：把售后意图识别规则拆成目标、判断维度、红线和升级问题；包含多诉求、隐私隔离和未覆盖边界。
2. `ASM-002-MODEL-JUDGEMENT`：按固定约束比较耳机售后回答 A/B，引用可定位证据，识别承诺、隐私和遗漏风险。
3. `ASM-003-DATA-CONSTRUCTION`：按固定 schema 构建 6 条售后意图评测样本，覆盖正常、抱怨、多诉求和 PII 占位场景，并提交覆盖矩阵与自检。

所有题面均为 PII-free 合成场景，不使用客户材料、真实订单、真实姓名或联系方式。边界与升级能力作为三项评测的横向维度，不再冒充第三项独立能力。

## 3. 评分与人工准入

### 3.1 固定 100 分证据

| 维度 | 分值 | 事实来源 |
| --- | ---: | --- |
| 出勤与纪律 | 10 | Operator 人工观察 |
| 八阶段学习完成 | 10 | 系统完成事实 |
| Muchener 理解 | 10 | Operator 人工观察 |
| AI 数据基础 | 10 | Operator 人工观察 |
| 项目与组织适配 | 10 | Operator 人工观察 |
| 规则拆解 | 15 | Reviewer 固定 Rubric |
| 模型判断 | 15 | Reviewer 固定 Rubric |
| 理由写作 | 10 | Reviewer 固定 Rubric |
| 通用数据构建 | 10 | Reviewer 固定 Rubric |

分档：A ≥ 85；B = 75–84；C = 65–74；D < 65。分档只提供建议：A/B 建议准入，C 建议暂缓人工复核，D 建议本次不准入。

### 3.2 人工责任边界

- 系统不得根据分数自动录用、淘汰、撤销身份或发送通知。
- Operator 必须先以只读预览看到总分、分档和建议，再选择 `ADMIT`、`DEFER` 或 `NOT_ADMIT`。
- 人工结论必须记录事实依据和决定理由；若覆盖系统建议，必须另写覆盖理由。
- 最终 `JourneyAdmissionDecision` 绑定 organization、Enrollment、JourneyVersion、Outcome、源 Evaluation 和 Operator，创建后禁止更新或删除。
- 准入权限不等同招聘录用权限；系统只记录探索营下一阶段准入事实。

## 4. 数据与兼容性

- migration `0016_wp24_formal_camp_v2` 只新增 `TaskVersion.learning_experience` 和不可变 `journey_admission_decisions`。
- 旧 TaskVersion 的学习内容默认 `{}`；旧页面继续走原 instructions，不伪造 V2 内容。
- V2 发布复用稳定 JourneyDefinition/TaskDefinition，但为八站各建新 TaskVersion，并创建新的 JourneyVersion。
- Journey V1、现有邀请、Enrollment 和历史提交不迁移、不改写；V1 Learner 可继续原固定版本。
- 相同 V2 不允许重复发布；发布必须提供当前 Journey version、独立 Reviewer 和明确复核确认。

## 5. 页面合同

### Learner

任务页依次呈现时间/模式、学习材料卡、自检、完成边界、分段输出结构和作答区。Assessment 在题面之前不出现孤立大输入框；草稿、修订历史和 Reviewer 反馈继续保留。

### Reviewer

每个能力维度同时提交 `rating`、0–固定上限整数分和具体反馈。`MEETS` 不得低于阈值，`NEEDS_WORK` 必须低于阈值；通过仍要求所有维度达标。

### Operator

只在已完成 V2 且尚无准入结论的 Enrollment 展示准入面板。先输入四项人工观察分，调用无写入 preview；确认证据和责任声明后才创建不可变决定。

## 6. 验收与门禁

- `AT-WP24-001`：八站覆盖 10:00–19:00，午休、短休和答疑明确；每站先有输入再有输出。
- `AT-WP24-002`：三项题面身份、题面、交付物和 Rubric 固定，第三项为通用数据构建。
- `AT-WP24-003`：Reviewer 数值评分、阈值、PASS/REVISION 状态机和不可变 Evaluation 一致。
- `AT-WP24-004`：完整八站和三项 PASS 才能预览准入；总分精确为 100 分权重。
- `AT-WP24-005`：系统建议不能自动产生准入；人工覆盖必须有理由；最终决定不可变。
- `AT-WP24-006`：V1 与既有事实不变，V2 为新版本且不得重复发布。
- `AT-WP24-007`：匿名、Learner、Reviewer、Operator 和跨组织权限负测保持通过。
- `AT-WP24-008`：390/768/1280 视口、键盘、阅读顺序和真实 Learner/Reviewer 内容校准通过。

## 7. 当前证据与下一步

已完成：领域模型、migration、V2 catalog、API、Learner/Reviewer/Operator Web 路径；空库 `0001→0016` 迁移与 290 项 API 回归通过；Web lint、typecheck、13 项合同测试和 production build 通过；OpenAPI、isolation、traceability、secret scan 通过；隔离 production-mode 浏览器已验证 390/1280 视口中的“学习输入先于作答”。本地 Python 依赖审计重试遇到 PyPI TLS EOF，但 PR Fast Gate 的完整 `make ci-fast`（run `30902143844`，含依赖审计）已通过。768 视口、完整键盘顺序和真人内容校准仍属于发布前人工门禁，不以构建结果代替。

2026-08-04 运行事实：候选 `0589fc825e41dc0c536b3bf87ac284c9a50013fd` 由 run `30913941412` 在冻结 staging 完成 migration `0015→0016_wp24_formal_camp_v2`、API/Web/Worker 部署、外部 TLS/readiness、匿名 `/ops`/`/review` 拒绝和 SSH 关闭；production 候选保持不变。Owner 随后报告已在 `/ops` 发布 Formal Exploration Camp V2 / Journey V2。该业务发布目前是合格的 Owner 操作陈述，尚未以新绑定邀请完成本轮机器读回。

发布后人工检查发现 `UAT-WP24-001` 路线节点错位、`UAT-WP24-002` 多页面重复文案，以及 `UAT-WP24-003` 宝藏缺少 Content Editor 导入材料与“学习后解锁小任务”的完整路径。受控邀请因此暂停；V2 保持不可变，后续提案见 37 号 WP-25～WP-30 工作包，不在 WP-24 原地修正文或既有事实。

## 8. 内容事实边界

- 课程结构、时间、三项能力和 100 分权重来自《MUCHEN新人启航探索营 V1.0》；公司长期命题来自《给 Muchener 的一封信》。Learner 页面使用重新组织的短课正文，不直接复制原文。
- 当前可用材料没有正式公司介绍 PPT、脱敏项目清单、客户结构或经复核经营数据；V2 因此只陈述“高质量数据、模型评测、多模态、Agent、出海数据与工程化交付”等已出现于批准材料的方向。
- 宝藏三和三项评测使用明确标注的 PII-free 合成售后案例，不冒充公司真实客户项目。若内容 Reviewer 未来补入真实项目材料，必须另建 TaskVersion/JourneyVersion，不得原地修改 V2。
- 发布前内容 Reviewer 必须逐项确认：公司定位没有夸大、项目方向没有泄密或虚构、三项题面与当前能力准入标准一致。没有该人工确认，状态继续保持 `CONTENT_REVIEW_REQUIRED`。
