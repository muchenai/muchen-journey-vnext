# Muchen Journey 产品—代码继承映射表 V0.1

> 状态：`WORKING_DRAFT`  
> 创建日期：2026-08-23  
> 使用者：产品 Owner、探索营业务 Owner、新手村运营 Owner、Tech Lead、Data Owner、QA/UAT Owner  
> 使用限制：本表用于确定“产品真相如何装入2.0技术底座”；在批准前，不得把表内候选映射直接转成开发需求。

## 1. 已批准的继承公式

> 沐晨新手村已验证的任务闭环  
> ＋探索营 V1.0 的真实业务方案  
> ＋V0.7 中经过批准的治理升级  
> ＝Muchen Journey 下一版

补充决策：现阶段允许受控真实项目任务，但 Journey 不直接执行生产作业；成熟任务系统和运营闭环不得丢弃。第一发布纳入 AI学院、公会、认证竞技场和 Career Map，但各模块必须独立定界和验收。

2.0 的定位：**技术运行底座，不是产品权威源。**

## 2. 来源权威顺序

| 来源 | 权威角色 | 下一版如何使用 |
| --- | --- | --- |
| [Muchen Quest｜沐晨新手村](https://zx6w57w0j34.feishu.cn/wiki/PPbfwhQq2ibIW5kC6FGcK5lpnbd) PRD＋MVP | 已验证产品行为与运营闭环 | 继承任务、角色、提交、审核、返工、积分/NPC运营和分流机制 |
| [MUCHEN新人启航探索营 V1.0](https://zx6w57w0j34.feishu.cn/docx/Wuz5dtk8GoXpdvxrH7BcQlaVnZe) | 探索营阶段业务 SSOT | 继承 Day 0/Day 1、材料、人工节点、输出、测评和准入口径 |
| [Muchen Journey 产品设计融合文档 V0.7](https://zx6w57w0j34.feishu.cn/wiki/K7NdwxtC6iMpWek9lM2cV5CLnid) | 治理升级候选集 | 只吸收明确批准的证据、权限、人工签署、申诉、版本和跨系统治理 |
| Mac mini `Muchen Journey2.0` | 技术能力与运行资产 | 承载页面、API、数据库、身份、审计、发布、恢复和监控 |
| 当前探索营 Web | 待审实施稿 | 可保留视觉资产和通用组件；无权反向定义产品结构 |

## 3. 判定词

| 判定 | 含义 | 谁批准 |
| --- | --- | --- |
| `原样继承` | 用户行为和业务目的不变，只允许换技术实现或视觉 | 产品 Owner＋业务 Owner |
| `治理升级` | 保留原行为，增加权限、证据、人工签署、审计等控制 | 产品 Owner＋治理 Owner |
| `暂缓` | 技术资产保留，但不进入第一发布范围 | 产品 Owner |
| `正式废弃` | 明确不再使用，必须记录原因、影响和替代方案 | 业务 Decider |
| `待确认` | 证据不足，不得进入开发 | 对应 Owner |

## 4. 第一发布范围（已裁决）

第一发布恢复并升级：

1. 探索营 V1.0；
2. 新手村真实任务闭环；
3. 真实项目任务安全 Gate；
4. V0.7 中批准的证据与人工治理；
5. AI学院；
6. 首批公会；
7. 认证竞技场；
8. Career Map。

AI学院、公会、认证竞技场和 Career Map 纳入范围不等于直接发布既有候选页面；每个模块必须分别建立权威来源、Owner、最小闭环、Build Contract和真人验收 Gate。BOSS 副本暂不进入第一发布。

## 5. 核心继承映射

状态只允许使用：`MAPPED`、`PARTIAL`、`GAP`、`CONFLICT`、`PENDING_EVIDENCE`。

### A. 角色、入口与身份

| ID | 来源能力 | 学员/运营必须能完成什么 | 2.0 技术载体 | 当前判断 | 缺口或待决策 | Owner | 验收 Gate | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MAP-001 | 学员／NPC／管理员三角色 | 学员做任务；NPC发布/审核；管理员处理人员、权限和异常 | `User`、`RoleAssignment`、`IdentitySession`；`/app`、`/review`、`/ops` | 原样继承 | 需要把 Reviewer 与新手村 NPC 业务责任对齐，不能只做技术角色改名 | 产品 Owner＋Tech Lead | 三角色各完成一次真实端到端演练 | `PARTIAL` |
| MAP-002 | 受控邀请与首次进入 | 新人收到邀请、确认身份并进入正确旅程 | `Invite`、`InvitationControl`、`JoinContext`；`/join`、飞书 OAuth | 治理升级 | 明确探索营邀请人、有效期、撤销和重复进入规则 | 探索营业务 Owner＋Security Owner | 新人无口头提示完成首次进入，旧链接和越权访问失败 | `PARTIAL` |
| MAP-003 | 学员档案与旅程分配 | 学员看见属于自己的当前任务和进度 | `Enrollment`、`Assignment`、`JourneyVersion`、`/app` | 原样继承 | 确认旧MVP学员档案迁移、封存或不导入 | 产品 Owner＋Data Owner | 学员身份、旅程、当前任务和历史一致 | `PARTIAL` |

### B. 任务与学习闭环

| ID | 来源能力 | 学员/运营必须能完成什么 | 2.0 技术载体 | 当前判断 | 缺口或待决策 | Owner | 验收 Gate | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MAP-004 | 主线／支线／隐藏任务 | 不同任务有触发条件、输入、交付和奖励 | `TaskDefinition`、`TaskVersion`、`Assignment` | 原样继承 | 2.0是否显式支持三类任务尚未形成已核验证据；不得用“八站”替代 | 新手村运营 Owner＋Tech Lead | 每类至少一个真实任务可领取、交付和审核 | `PENDING_EVIDENCE` |
| MAP-005 | 标准任务卡 | 看清为什么做、输入、目标、交付物、时限、审核人、评分和求助方式 | `TaskContentInput`、`TaskVersion`；`/app/tasks/[assignmentId]` | 原样继承 | 当前学员页需逐字段核对，不得展示后台元数据代替任务说明 | 产品 Owner＋Design Owner | 新学员能复述任务目的、交付物、截止时间和求助人 | `PARTIAL` |
| MAP-006 | 领取／开始任务 | 学员主动开始任务，系统记录状态和版本 | Current Action、Assignment状态、start command | 原样继承 | “点击找到线索”不能作为任务完成 | 产品 Owner＋Tech Lead | 开始动作幂等、可追溯，未提交不得伪完成 | `MAPPED` |
| MAP-007 | 学习材料 | 学员打开材料、带着问题阅读并形成可观察输出 | `LearningMaterialCompletion`、TaskVersion material；任务页 | 治理升级 | 阅读完成和任务完成必须分开；材料完成不能直接证明能力 | 探索营业务 Owner＋产品 Owner | 阅读、输出、证据和审核四个状态可区分 | `PARTIAL` |
| MAP-008 | 提交／修订／附件 | 学员提交真实产物，保留版本并只修改问题部分 | `Submission`、`SubmissionVersion`、`SubmissionDraft`、`Attachment`；任务页 | 原样继承 | 真实项目附件需补数据等级和外链规则 | Tech Lead＋Data Owner | 初交、返工、再提交均保留历史和原始证据 | `MAPPED` |
| MAP-009 | NPC审核／Rubric／返工 | NPC看见任务要求与提交，给出理由明确的通过或返工 | `Review`、`ReviewDelegation`、`Evaluation`；`/review` | 原样继承 | 补NPC容量、SLA、升级与替补责任 | 新手村运营 Owner＋QA Owner | Reviewer能完成领取、反馈、返工和通过；操作留痕 | `MAPPED` |
| MAP-010 | 结果与下一步 | 学员看见结论、依据、反馈和下一行动 | `Outcome`、`Handoff`、`JourneyOutcomeEvidence`；`/app/result`、timeline | 治理升级 | 结果必须拆分学习事实、Reviewer结论、系统建议和人工准入 | 产品 Owner＋QA Owner | 学员能解释“我完成了什么、谁判断、依据是什么、下一步是什么” | `PARTIAL` |

### C. 激励、运营和阶段分流

| ID | 来源能力 | 学员/运营必须能完成什么 | 2.0 技术载体 | 当前判断 | 缺口或待决策 | Owner | 验收 Gate | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MAP-011 | 积分、徽章和排行榜 | 完成真实贡献后获得反馈和可见成长 | 未发现明确 `Points`／`Badge` 独立模型 | 第一发布恢复积分；与能力证据隔离 | 积分只用于激励与参考，不得单独决定准入、淘汰、晋升或岗位结论 | 产品 Owner＋新手村运营 Owner | 奖励来源可追溯，不能篡改能力证据 | `GAP` |
| MAP-012 | NPC任务发布与负载管理 | NPC发布任务、看审核队列、处理超载和逾期 | Content Draft、TaskVersion、Review Queue、RuntimeStatus | 治理升级 | 需要负载、SLA、逾期和升级看板 | 新手村运营 Owner＋Release/Ops | 超载和逾期能被发现并升级到明确人员 | `PARTIAL` |
| MAP-013 | 自动提醒和运营看板 | 状态变化触发通知；运营看见参与、提交、审核和异常 | `OutboxEvent`、Worker、NotificationDelivery、Audit、`/ops` | 原样继承 | 历史 backlog 与接收人启用前必须隔离；看板指标需重新对齐业务 | Release/Ops＋业务 Owner | 不误发历史消息；关键状态可对账 | `PARTIAL` |
| MAP-014 | T+30／60／90阶段分流 | 基于任务、反馈和证据形成阶段结论与下一安排 | Outcome、Handoff、JourneyAdmissionDecision | 治理升级 | 时间触发、评审人、证据窗口和申诉路径尚待确认 | 产品 Owner＋人才发展 Owner | 结论有人签署、有证据、有复核和下一步 | `PARTIAL` |

### D. 探索营 V1.0

| ID | 来源能力 | 学员/运营必须能完成什么 | 2.0 技术载体 | 当前判断 | 缺口或待决策 | Owner | 验收 Gate | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MAP-015 | Day 0预读 | 新人完成指定材料预读，形成进入Day 1的问题和基础认知 | Journey/TaskVersion/LearningMaterial | 原样继承 | 逐项核对探索营V1.0材料、顺序、时长和产出 | 探索营业务 Owner＋Content Owner | Day 0每项内容都能追溯到V1.0正式来源 | `CONFLICT` |
| MAP-016 | Day 1 业务流程 | 完成异步学习、实操、证据提交并通过人工Gate | 2.0可承载任务和证据；人工环节未形成完整映射 | V1.0业务逻辑原样继承；学习内容允许异步 | 异步学习不能替代实操、证据和人工Gate | 探索营业务 Owner | 学习、实操、证据、人工结论和下一行动逐项验收 | `PARTIAL` |
| MAP-017 | 四个宝藏与三项核心能力测评 | 通过真实材料和任务形成能力准入证据 | TaskVersion、Evaluation、JourneyAdmissionDecision | 四宝藏原样继承＋治理升级；个人成长基线作为结果包 | 补齐四宝藏材料、Rubric、结果包和人工签署 | 探索营业务 Owner＋产品 Owner | 名称、材料、数量、Rubric和准入结果全部统一 | `PARTIAL` |
| MAP-018 | 探索营之后进入项目规则训练 | 测评结果决定后续训练安排，不由点击数或积分决定 | Outcome、Handoff、AdmissionDecision | 原样继承 | 明确准入Decider、最低证据和未通过路径 | 探索营业务 Owner＋人才发展 Owner | 每种结果都有人工签署和下一行动 | `PARTIAL` |

### E. 真实项目任务与治理升级

| ID | 来源能力 | 学员/运营必须能完成什么 | 2.0 技术载体 | 当前判断 | 缺口或待决策 | Owner | 验收 Gate | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MAP-019 | 真实项目任务 | 在授权范围内完成对项目可使用的真实产出 | Task/Submission/Review/Audit/Attachment | 原样继承＋安全Gate | 补授权、客户数据等级、脱敏、最小权限、AI使用和保留期 | 项目 Owner＋Data/Security Owner | 任一任务可回答谁授权、谁可见、谁审核、如何追溯 | `PARTIAL` |
| MAP-020 | 游戏账本与能力证据隔离 | 既保留激励，又不让XP/排名直接改写能力判断 | JourneyOutcomeEvidence、Evaluation；积分模型待补 | 治理升级 | 明确两类账本字段、Owner和单向/禁止关系 | 产品 Owner＋Data Owner | 积分变化不能改变人工结论或原始证据 | `GAP` |
| MAP-021 | AI辅助、真人签署 | AI可帮助自查和初评，高影响判断由真人负责 | AI summary、Review、Evaluation、AdmissionDecision | 治理升级 | 明确哪些字段是AI建议、谁签署、如何覆盖和申诉 | 产品 Owner＋业务 Reviewer | AI不可直接产生准入、淘汰、晋升终判 | `PARTIAL` |
| MAP-022 | 证据来源、可信度、有效期和可见范围 | 每条能力证据可追溯且只对授权角色可见 | Audit、JourneyOutcomeEvidence、SubmissionVersion、RBAC | 治理升级 | 需要统一 EvidenceRef 规则和有效期 | Data Owner＋Security Owner | 抽查证据能回到原始提交、Reviewer和版本 | `PARTIAL` |
| MAP-023 | 申诉、纠错与版本追溯 | 学员对关键判断提出复核，系统保留原结论与修订 | 已有版本、审计和Data Rights；未发现明确申诉流程 | 治理升级 | 申诉对象、SLA、复核人和结论状态待设计 | 产品 Owner＋治理 Owner | 一次模拟申诉完整走通且不覆盖原记录 | `GAP` |
| MAP-024 | 历史新手村资产 | 保留已验证任务、学员记录、审核、积分和运营证据 | Offline Import、ImportBatch、ImportRecord | 待确认 | 先分类迁移、封存或不导入；禁止在线直连旧库和静默修正 | 产品 Owner＋Data Owner | 数据数量、含义、Owner和差异均可核对 | `PENDING_EVIDENCE` |

### F. 当前实现与后续空间

| ID | 当前资产 | 判定 | 处理要求 | Owner | 恢复开发条件 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| MAP-025 | 当前“八站＋线索＋自证完成”页面逻辑 | 暂停并重映射 | 每一站必须找到正式来源；无来源内容删除或提交决策 | 产品 Owner＋Design Owner | MAP-015—018通过 | `CONFLICT` |
| MAP-026 | 当前视觉系统与通用组件 | 保留候选资产 | 只保留不携带错误业务逻辑的样式、布局和组件 | Design Owner＋Tech Lead | 组件与业务状态解耦 | `PARTIAL` |
| MAP-027 | AI学院候选 | 纳入第一发布，独立定界 | 不直接发布候选页面；先定义学习—产出—点评—证据闭环 | AI学院 Owner＋产品 Owner | 独立业务来源、内容Owner、最小闭环和真人Gate批准 | `PENDING_EVIDENCE` |
| MAP-028 | 公会候选 | 纳入第一发布，按公会插件独立定界 | 明确首批公会，不复制平台能力，不并入探索营主路径 | 公会 Owner＋产品 Owner | 公会名单、能力模型、任务、Rubric、考官和版本批准 | `PENDING_EVIDENCE` |
| MAP-029 | BOSS副本候选 | 暂缓第一发布 | 保留代码、证据和候选，不并入探索营主路径 | 产品 Owner | 独立业务方案和真人Gate批准 | `PENDING_EVIDENCE` |
| MAP-030 | 认证竞技场候选 | 纳入第一发布，独立定界 | 建立报名、提交、评审、Panel、申诉和凭证闭环 | 认证治理 Owner＋产品 Owner | 认证对象、Rubric、考官、申诉和凭证规则批准 | `PENDING_EVIDENCE` |
| MAP-031 | Career Map候选 | 纳入第一发布，独立定界 | 只提供可解释的成长导航与参考，不自动产生人事结论 | 人才发展 Owner＋产品 Owner | 目标角色、证据输入、可见范围和人工确认规则批准 | `PENDING_EVIDENCE` |

## 6. 冲突决议台账

只有业务 Decider 或其明确授权人可以关闭“来源冲突”。

| 冲突ID | 冲突 | 推荐主口径 | 决议 | Decider | 日期 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| CON-001 | 探索营V1.0四个宝藏 vs V0.7五个宝藏 | 四宝藏；个人成长基线作为结果包 | `DECIDED` | 刘默文 | 2026-08-23 | 本轮裁决 |
| CON-002 | V1.0人工Day 1 vs 当前自助八站 | 异步学习＋实操/证据/人工Gate | `DECIDED` | 刘默文 | 2026-08-23 | 本轮裁决 |
| CON-003 | 新手村真实项目任务 vs V0.7一律禁止真实项目 | 允许受控真实任务；Journey不直接执行生产作业 | `IMPLEMENTATION_PENDING` | 刘默文 | 2026-08-23 | 产品已裁决；安全Gate待施工 |
| CON-004 | 新手村成熟任务闭环 vs 当前点击自证完成 | 正式任务提交—审核—返工/通过；自证无正式状态 | `IMPLEMENTATION_PENDING` | 刘默文 | 2026-08-23 | 产品已裁决；状态机与验收待完成 |
| CON-005 | 2.0 Greenfield Replacement ADR vs 产品继承决策 | 保留技术独立，废止产品“从零定义” | `IMPLEMENTATION_PENDING` | 刘默文 | 2026-08-23 | 产品已裁决；代码基线与ADR待收口 |
| CON-006 | 积分参与分流 vs 双账本隔离 | 积分用于激励与参考，不能单独产生人才结论 | `DECIDED` | 刘默文 | 2026-08-23 | 本轮裁决 |
| CON-007 | Day 1能力准入 vs 低压力不淘汰 | 只决定下一训练阶段，不作录用、淘汰或项目准入终判 | `DECIDED` | 刘默文 | 2026-08-23 | 本轮裁决 |
| CON-008 | 历史数据迁移 vs 重新开始 | 先审计，再分类迁移、封存或不导入 | `IMPLEMENTATION_PENDING` | 刘默文 | 2026-08-23 | 产品已裁决；数据盘点待完成 |
| CON-009 | 第一发布是否扩展全生命周期模块 | 纳入AI学院、公会、认证竞技场和Career Map，各自独立定界 | `DECIDED` | 刘默文 | 2026-08-23 | 产品范围已裁决；四模块分别受Build Contract与Gate约束 |
| CON-010 | AI自动评分 vs 真人责任 | AI自查/初评/摘要；高影响结论真人签署且可申诉 | `DECIDED` | 刘默文 | 2026-08-23 | 产品治理已裁决；实现状态见对应MAP-ID |

## 7. 恢复开发 Gate

| Gate | 必须交付物 | 通过标准 | 当前状态 |
| --- | --- | --- | --- |
| P0｜来源冻结 | 来源角色表、冲突台账 | 所有产品能力有唯一权威来源 | `IN_PROGRESS` |
| P1｜能力映射 | MAP-001—031逐项证据 | 第一发布项没有 `CONFLICT` 或无Owner的 `GAP` | `NO_GO` |
| P2｜技术基线 | 《技术运行基线冻结清单》V1.0 | 唯一代码、schema、备份与发布基线通过 | `NO_GO` |
| P3｜Build Contract | 只含已批准映射编号的开发合同 | 每个需求引用MAP-ID、Owner和验收Gate | `IN_PROGRESS`：BC-001—006已起草，均待签署 |
| P4｜真人闭环 | 学员、NPC、管理员真实演练 | 领取—提交—审核—返工—通过—证据—下一步全部成立 | `NO_GO` |
| P5｜发布批准 | 产品、技术、数据、QA、Release共同签署 | 机器与真人证据齐备，回滚可执行 | `NO_GO` |

## 8. Build Contract 登记与输入模板

| Contract | 模块 | 来源 MAP-ID | 文件 | 当前状态 |
| --- | --- | --- | --- | --- |
| BC-001 | 探索营V1.0 | MAP-002、007、015—018、021—023 | `build-contracts/BC-001_探索营_V1.0_V0.1.md` | `DRAFT_FOR_OWNER_SIGNOFF` |
| BC-002 | 新手村受控任务闭环 | MAP-001、003—014、019—024 | `build-contracts/BC-002_新手村受控任务闭环_V0.1.md` | `DRAFT_FOR_OWNER_SIGNOFF` |
| BC-003 | AI学院 | MAP-007—010、021—023、027 | `build-contracts/BC-003_AI学院_V0.1.md` | `DRAFT_FOR_OWNER_SIGNOFF` |
| BC-004 | 公会 | MAP-004—014、019—023、028 | `build-contracts/BC-004_公会_V0.1.md` | `BLOCKED_BY_EVIDENCE` |
| BC-005 | 认证竞技场 | MAP-008—010、021—023、030 | `build-contracts/BC-005_认证竞技场_V0.1.md` | `DRAFT_FOR_OWNER_SIGNOFF` |
| BC-006 | Career Map | MAP-010、014、020—023、031 | `build-contracts/BC-006_Career_Map_V0.1.md` | `DRAFT_FOR_OWNER_SIGNOFF` |

BOSS副本 MAP-029 没有第一发布 Build Contract，状态保持 `DEFERRED_FIRST_RELEASE`。

恢复开发后，每个开发项必须填写：

| 字段 | 内容 |
| --- | --- |
| 需求名称 |  |
| 来源 MAP-ID |  |
| 产品权威来源 |  |
| 用户必须完成的行为 |  |
| 允许复用的2.0技术资产 |  |
| 明确禁止改变的业务逻辑 |  |
| 数据与权限要求 |  |
| Owner |  |
| 验收Gate |  |
| 真人证据 |  |
| 发布与回滚条件 |  |

没有 MAP-ID 的需求不得进入开发。

## 9. 批准记录

| 角色 | 姓名 | 结论 | 日期 | 备注 |
| --- | --- | --- | --- | --- |
| 产品 Owner | `待确认` | `PENDING` |  |  |
| 探索营业务 Owner | `待确认` | `PENDING` |  |  |
| 新手村运营 Owner | `待确认` | `PENDING` |  |  |
| Tech Lead | `待确认` | `PENDING` |  |  |
| Data Owner | `待确认` | `PENDING` |  |  |
| QA/UAT Owner | `待确认` | `PENDING` |  |  |
| 业务 Decider | 刘默文 | `SCOPE_DECISIONS_RECORDED` | 2026-08-23 | 九项产品裁决已记录；映射表整体批准仍待其余Owner和Gate |
