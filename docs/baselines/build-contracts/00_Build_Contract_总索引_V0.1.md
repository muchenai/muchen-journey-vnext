# Muchen Journey 第一发布 Build Contract 总索引 V0.1

> 状态：`ALL_ROLES_APPOINTED / TEAM_ACCEPTANCE_PENDING / ZERO_CONTRACTS_SIGNED / DEVELOPMENT_ACTIVE_BY_DECIDER_OVERRIDE / RELEASE_BLOCKED`  
> 创建日期：2026-08-23  
> 业务裁决人：刘默文  
> 技术候选基线：`main@a1ec7e30e1e6321b5af7585eec63091c1afdca24`  
> 规则：合同批准的是“谁能因此做成什么，以及如何验收”，不是页面数量、代码量或机器测试数量。

统一签署入口：`../Muchen_Journey_Build_Contract签署包_V0.1.md`。权威任命及接受表见 `../Muchen_Journey_Owner任命与接受记录_V0.1.md`，逐合同签署状态见 `../Muchen_Journey_Build_Contract签署决议单_V0.1.md`。本索引和六份模块合同继续作为产品与验收合同正文。

开发解锁入口：`../Muchen_Journey_全模块开发解锁决议_V0.1.md`。六模块已获直接开发授权，未签署事项转为发布前Gate；正式发布仍未授权。

## 1. 第一发布模块

| Contract | 模块 | MAP-ID | 使用者结果 | 当前状态 | 开发条件 |
| --- | --- | --- | --- | --- | --- |
| BC-001 | 探索营 V1.0 | MAP-002、007、015—018、021—023 | 学员形成四宝藏认知、三项实操证据和个人成长基线结果包；真人决定下一训练阶段 | `OWNERS_APPOINTED / CONTENT_PENDING` | 郑田源、屠元琦接受；材料、Rubric和真人Gate批准 |
| BC-002 | 新手村受控任务闭环 | MAP-001、003—014、019—024 | 学员完成一项受控真实任务的提交—审核—返工/通过闭环 | `OWNERS_APPOINTED / DATA_AND_SOD_BLOCKED` | 屠元琦接受；独立Reviewer/UAT、真实任务安全合同和历史数据审计批准 |
| BC-003 | AI学院 | MAP-007—010、021—023、027 | 学员把异步学习转成可复核练习产出和能力证据 | `OWNERS_APPOINTED / FIRST_UNIT_PENDING` | 段超群、屠元琦接受；首批学习单元、内容Owner与Reviewer批准 |
| BC-004 | 公会 | MAP-004—014、019—023、028 | 成员通过短周期共同实践形成项目/专业证据和导师反馈 | `OWNERS_APPOINTED / EVIDENCE_BLOCKED` | 段超群、屠元琦接受；第一公会业务线Owner、导师和插件包批准 |
| BC-005 | 认证竞技场 | MAP-008—010、021—023、030 | 参与者完成认证挑战并获得真人Panel签署、可申诉的认证结论 | `OWNERS_APPOINTED / GOVERNANCE_BLOCKED` | 段超群、屠元琦接受；认证对象、实际Panel、有效期与申诉批准 |
| BC-006 | Career Map | MAP-010、014、020—023、031 | 个人看见证据来源、能力差距和下一行动，但系统不替代人才决定 | `OWNERS_APPOINTED / MODEL_BLOCKED` | 段超群、屠元琦接受；角色内容子Owner、能力模型和可见范围批准 |

BOSS副本对应 MAP-029，状态为 `DEFERRED_FIRST_RELEASE`，只保留候选代码和证据，不进入第一发布导航、数据库迁移和发布包。

## 2. 统一业务不变量

以下规则对 BC-001—006 全部生效，模块合同不得覆盖：

1. 探索营采用 V1.0 四宝藏；个人成长基线是结果包。
2. 学习可异步；正式能力结果必须来自实操、证据和人工 Gate。
3. Journey 可以编排受控真实任务、接收证据和审核结果，但不直接执行生产作业。
4. 正式任务必须提交、审核并进入返工或通过；自证只允许保存草稿或自查，不产生正式状态。
5. 积分只用于激励与参考；不能单独产生录用、淘汰、准入、晋升、绩效或岗位结论。
6. Day 1 只决定下一训练阶段。
7. 历史数据先审计，再迁移、只读封存或不导入。
8. AI只做自查、初评、风险提示和摘要；高影响结论由真人签署并允许申诉。
9. 机器测试、AI评分、点击完成和页面上线均不能替代真人验收。

## 3. 共享状态与证据语义

正式任务最小状态链：

`DRAFT → AVAILABLE → IN_PROGRESS → SUBMITTED → IN_REVIEW → NEEDS_REVISION → SUBMITTED → PASSED`

允许的终止状态：`CANCELLED`、`WITHDRAWN`。任何跳过 `SUBMITTED / IN_REVIEW` 直接进入 `PASSED` 的实现都不合格。

每条正式证据至少包含：

- 人、组织、模块和任务版本；
- 权威来源与任务授权；
- 原始提交和修订历史；
- Reviewer、Rubric、结论、理由和时间；
- AI使用说明、模型/Prompt版本（若使用）；
- 可见范围、数据等级、保留期；
- 申诉、复核和修订记录。

积分、徽章、排行榜属于单独的激励账本，只能引用“已发生的贡献事实”，不得改写 Evidence、Evaluation、Outcome 或人工签署结论。

## 4. 技术复用边界

统一复用2.0的身份、邀请、权限、版本化Journey/Task、Assignment、提交版本、附件、Review/Evaluation、Outcome/Handoff、Outbox、通知、审计、离线导入、数据权利、发布和恢复能力。

以下内容不得作为权威产品源：

- `codex/wp15-live-evidence@b7597ed` 中的五地图/BOSS总产品结构；
- 当前八站自助浏览、自证完成和点击即进度；
- 任何机器 `READY_FOR_HUMAN`、AI建议或候选页面；
- 没有正式来源、Owner、MAP-ID和本合同编号的新增状态或页面。

## 5. 开发顺序

| Wave | 工作 | 允许写入 | 退出Gate |
| --- | --- | --- | --- |
| W0 | 代码基线收口 | 文档、测试保护、PR Gate、无业务语义的安全修复 | 唯一tag、分叉处置、数据/运行Gate |
| W1 | BC-001＋BC-002 | 探索营和新手村最小纵向闭环 | 两条黄金路径均通过机器、真人、运营、安全验收 |
| W2 | BC-003＋BC-004 | AI学院和首批公会插件 | 每个模块有真实内容、产出、Reviewer和证据闭环 |
| W3 | BC-005＋BC-006 | 竞技场和Career Map | Panel/申诉及非自动人才决策边界走通 |
| R1 | 第一发布候选 | 仅经总控集成的已签署合同范围 | 六份合同、跨模块回归、恢复演练和Release签署通过 |

Wave表示内部依赖顺序，不改变六个模块均属于第一发布范围。

## 6. 合同签署 Gate

每份合同至少需要：产品 Owner、模块业务 Owner、Tech Lead、Data/Security Owner、QA/UAT Owner签署；涉及正式高影响结论的合同还需要对应Reviewer/Panel Owner签署。

签署前状态只能是：`DRAFT_FOR_SIGNOFF`、`BLOCKED_BY_EVIDENCE`、`BLOCKED_BY_OWNER`。签署后才可标为 `APPROVED_FOR_BUILD`。机器通过后只能标为 `READY_FOR_HUMAN`；真人和运营Gate通过后才可标为 `READY_FOR_RELEASE_REVIEW`。

## 7. 重签触发

出现任一情况必须重签：第一发布范围变化；正式来源版本变化；新数据等级或生产连接；Reviewer/Panel责任变化；AI从辅助变成影响结论；任务状态机变化；积分与人才结论关系变化；历史数据迁移范围变化。

## 8. 总控集成阶段合同

模块合同之外的总控集成、机器复核和发布准备度工作，以编号阶段合同记录；它们不能替代 BC-001—006 签署或真人 UAT。

| Gate | 合同 | 当前机器状态 | 下一 Gate |
| --- | --- | --- | --- |
| G7 | `07_G7_当前Golden_Path机器复核与语义校正_V0.1.md` | `READY_FOR_HUMAN / UNCOMMITTED_CANDIDATE` | 3/3 首次学员真人验证；未通过前禁止合并、候选晋级和发布 |
| G8 | `08_G8_受控任务授权强绑定接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_TASK_AND_SIGNATURES_PENDING` | Pro 复核后，由任务所需 Owner 对同一 TaskVersion 摘要完成真人签署 |
| G9 | `09_G9_AI学院与公会模块包强绑定接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_CONTENT_MENTOR_AND_SIGNATURES_PENDING` | Pro 复核后，AI 学院与公会所需 Owner 对精确模块包签署并完成 Reviewer/导师校准 |
| G10 | `10_G10_正式结果申诉与Growth_Plan连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_APPEAL_POLICY_REVIEWERS_AND_EVIDENCE_PENDING` | Pro 复核后，各模块所需 Owner 对申诉政策签署，并完成独立 Reviewer 分配与替代 Gate 演练 |
| G11 | `11_G11_正式结果包与跨地图Handoff连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_OUTCOME_RECONCILIATION_AND_HANDOFF_SIGNOFF_PENDING` | Pro 复核后，在非生产脱敏副本完成 Outcome/Handoff 只读对账，并由模块与 Handoff Owner 对双签和重发语义签署 |
| G12 | `12_G12_认证终局结果与Career_Growth_Plan连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_APPEAL_REGISTER_ROLE_MODEL_AND_GROWTH_CONFIRMATION_PENDING` | Pro 复核后，由认证、Appeal Register、Career Model、Data/Security 与 Growth Plan Owner 对终局结果和跨切面连续性签署 |
| G13 | `13_G13_跨地图受控入站与Appeal新鲜度连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_INTAKE_POLICY_APPEAL_REGISTER_AND_HUMAN_ENTRY_PENDING` | Pro 复核后，由各目的站、Intake Reviewer、Data/Security 与 Appeal Register Owner 对五阶段入站政策和真人决定签署 |
| G14 | `14_G14_跨地图Enrollment命令与原子前置条件接线_V0.1.md` | `MACHINE_CANDIDATE / SCHEMA_TRANSACTION_ADAPTER_AND_RUNTIME_AUTHORIZATION_PENDING` | Pro 复核 schema、四 scope 原子锁和重放/恢复后，由 Tech、Platform、Data/Security、目的站与 Intake Owner 对精确事务适配器签署；未授权前禁止迁移和运行时写入 |
| G15 | `15_G15_入站决定申诉与Recovery_Growth_Plan连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_ENTRY_APPEAL_POLICY_REVIEWERS_AND_RECOVERY_CONFIRMATION_PENDING` | Pro 复核 adverse Gate、独立复核、推翻后重新决定和 Recovery Growth Plan 后，由目的站、Intake、Appeal、Data/Security、Coach 与 Person 代表签署 |
| G16 | `16_G16_入站申诉后独立重审连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_REPLACEMENT_READINESS_CONSENT_AND_REDECISION_PENDING` | Pro 复核 G15 resolution→替代 readiness→新 Person consent→独立 Intake 决定的完整谱系；随后由目的站、原/新 Intake、Appeal、Data/Security 与 Person 代表对真实重审脚本签署 |
| G17 | `17_G17_独立重审后Enrollment谱系连续性接线_V0.1.md` | `MACHINE_CANDIDATE / REAL_STAGE_ENTRY_APPEAL_REGISTER_AND_LINEAGE_PERSISTENCE_PENDING` | Pro 复核 G16 `ACCEPT` 到 G14 command 的 Appeal resolution snapshot、八 scope 原子锁与 lineage fact；随后由 Appeal Register、Platform、Data/Security、Intake 与 Person 代表签署脱敏事务演练 |
| G18 | `18_G18_Person入站解释与单一下一动作Projection_V0.1.md` | `MACHINE_CANDIDATE / REAL_PERSON_EXPLANATION_UAT_AND_RUNTIME_PROJECTION_PENDING` | Pro 复核 Person-safe 状态、最小时间线、单一下一动作和敏感信息剥离；随后由 Person 代表、UX、Intake、Appeal 与 Data/Security Owner 对脱敏视图完成理解度与隐私 UAT |
| G19 | `19_G19_直接ACCEPT_Person入站连续性Projection_V0.1.md` | `MACHINE_CANDIDATE / REAL_DIRECT_ACCEPT_EXPLANATION_UAT_AND_RUNTIME_PROJECTION_PENDING` | Pro 复核 G13 direct `ACCEPT` 到可选 G14 plan 的 Person-safe 状态、唯一团队动作和“尚未入站”语义；随后由 Person 代表、UX、Intake 与 Data/Security Owner 完成四条顺序入站路径的理解度与隐私 UAT |
| G20 | `20_G20_统一Person入站View与来源Selector_V0.1.md` | `MACHINE_CANDIDATE / REAL_UNIFIED_VIEW_UAT_AND_RUNTIME_SOURCE_SELECTOR_PENDING` | Pro 复核 G18/G19 exactly-one source selector、十二状态统一映射、safe/full 边界和 source snapshot 新鲜度；随后由 Person 代表、UX、Intake、Appeal 与 Data/Security Owner 对 direct/adverse/无来源/stale 脚本完成理解度、隐私与错误态 UAT |
| G21 | `21_G21_只读Person入站来源Index与Fail_Closed_Resolver_V0.1.md` | `MACHINE_CANDIDATE / REAL_READ_ONLY_REPOSITORY_ADAPTER_AND_FALLBACK_UAT_PENDING` | Pro 复核非权威只读 index、snapshot digest、唯一 active source、supersession/new-fact stale 判定与 Person-safe fallback；随后由 Tech、Platform、Data/Security、Intake、Appeal、UX 与 Person 代表在非生产脱敏副本完成 unavailable/missing/ambiguous/stale/恢复脚本 UAT |
| G22 | `22_G22_Career_Map_Person证据解释与单一成长动作View_V0.1.md` | `MACHINE_CANDIDATE / REAL_PERSON_EXPLANATION_AND_GROWTH_ACTION_UAT_PENDING` | Pro 复核 G4/G12 双来源、证据/真人/AI 分层、focus capability、Appeal 优先级、AI 采纳披露、exact-source Growth Plan 与单一动作；随后由 Career Model、Data/Security、UX、Coach 与 Person 代表完成模型待批/有效/无证据/申诉/无计划/AI 计划脚本 UAT |
| G23 | `23_G23_Person自主Career_Focus与最新Source_Fail_Closed_Resolver_V0.1.md` | `MACHINE_CANDIDATE / REAL_READ_ONLY_REPOSITORY_FOCUS_AND_FALLBACK_UAT_PENDING` | Pro 复核 Person-only focus、换版重选、非权威 source index、exactly-one、source/plan digest、水位和 supersession；随后由 Career Model、Platform、Data/Security、UX、Coach 与 Person 代表完成 focus/模型换版/Appeal/过期/撤权/plan 替代/unavailable/恢复脚本 UAT |
| G24 | `24_G24_Career_Growth_Action受控任务路由与Person开始意图_V0.1.md` | `MACHINE_CANDIDATE / REAL_ROUTE_APPROVAL_PERSON_INTENT_AND_ASSIGNMENT_COMMAND_UAT_PENDING` | Pro 复核 G23 当前计划到 G8/G9 精确任务、三方真人路由签署、Person-only start intent、AI 披露和 Assignment 命令资格边界；随后由 Career Model、目的模块、Data/Security、UX、Coach、Platform 与 Person 代表完成任务换版/撤权/过期/恢复脚本 UAT |
| G25 | `25_G25_Career_Growth_Assignment原子命令与谱系计划_V0.1.md` | `MACHINE_CANDIDATE / REAL_RUNTIME_BINDING_SCHEMA_TRANSACTION_AND_ASSIGNMENT_UAT_PENDING` | Pro 复核 G24 Person intent 到 active Enrollment、JourneyStage、TaskVersion、Reviewer、六 scope 锁、幂等键、Audit/Outbox 与 Growth lineage 的确定性计划；随后由 Tech、Platform、Data/Security、Career、目的模块与 Reviewer 对 schema、事务适配器和脱敏重放/冲突/恢复演练签署，未通过前禁止 migration、API 与 Assignment 写入 |
| G26 | `26_G26_认证挑战版本包与五角色真人授权_V0.1.md` | `MACHINE_CANDIDATE / REAL_CHALLENGE_ARTIFACTS_FIVE_OWNER_SIGNOFF_PANEL_CALIBRATION_AND_CATALOG_UAT_PENDING` | Pro 复核 BC-005 专用 TaskVersion、十二项版本治理材料、五角色真人授权、Panel/Appeal/审批三层职责隔离、AI/防舞弊与 Person-safe catalog；随后由 Certification Governance、Challenge、Panel、Appeal、Data/Security Owner 对首个真实挑战包签署，并完成 Panel 校准和 3/3 Person 理解度 UAT |
| G27 | `27_G27_认证申请资格快照与可申诉真人准入_V0.1.md` | `MACHINE_CANDIDATE / REAL_APPLICATION_REGISTER_ELIGIBILITY_REVIEWER_APPEAL_AND_PERSON_UAT_PENDING` | Pro 复核 Person 显式申请、权威 register 去重、完整资格/容量快照、AI/积分/自证禁用、Eligibility Reviewer 与治理/内容/Panel/Appeal 全隔离、可申诉 Human Gate 和四态 Person-safe 投影；随后完成脱敏重复申请、过期事实、waitlist、拒绝、申诉和恢复 UAT |
| G28 | `28_G28_认证准入申诉独立复核与重新决策_V0.1.md` | `MACHINE_CANDIDATE / REAL_APPEAL_REGISTER_REVIEWERS_RESOLUTION_REDECISION_AND_PERSON_UAT_PENDING` | Pro 复核 G27 adverse Gate 到权威 Appeal Register、G26 policy 内容快照、pool 内独立 Reviewer 分配、全员签署 resolution Evidence、最终 register、替代资格/容量快照与新 Eligibility Reviewer 重审的完整谱系；随后完成 UPHELD/OVERTURNED/RETURNED、SLA 超期、再次 adverse 申诉和 Person-safe 七态脱敏 UAT |
| G29 | `29_G29_认证Registration_Attempt_Assignment原子命令与谱系计划_V0.1.md` | `MACHINE_CANDIDATE / REAL_RUNTIME_BINDING_SCHEMA_TRANSACTION_PANEL_ACCESS_AND_ASSIGNMENT_UAT_PENDING` | Pro 复核 G27 direct ACCEPT 或 G28 independent redecision ACCEPT 到最新 Application Register、active Certification Enrollment、published assessment stage、Registration/first Attempt/Assignment 三行计划、十 scope 原子锁、幂等、Audit/Outbox 和 Appeal lineage；随后由 Tech、Platform、Certification Governance、Data/Security 与 Panel Owner 对 schema、Panel access/quorum、事务适配器及脱敏并发/重放/恢复演练签署，未通过前禁止 migration、API 与任何写入 |
| G30 | `30_G30_认证首次Attempt_Submission与Practice_Evidence原子命令_V0.1.md` | `MACHINE_CANDIDATE / REAL_G29_RUNTIME_RECEIPT_SUBMISSION_SCHEMA_EVIDENCE_LEDGER_AND_PERSON_UAT_PENDING` | Pro 复核未来 G29 authorized runtime receipt 到 active first Attempt、Person-only explicit submit、固定 deliverable、READY+CLEAN Attachment、AI disclosure、SubmissionVersion、PRACTICE Evidence、八加附件 scope 锁与 Audit/Outbox；随后由 Tech、Platform、Certification Governance、Data/Security、Panel Owner 与 Person 代表验证真实 storage/scan、事务、幂等和通用单 Reviewer route 隔离，未通过前禁止 submission API、Review/Panel 创建或写入 |
| G31 | `31_G31_认证Panel分配_全员接受与最小Evidence访问_V0.1.md` | `MACHINE_CANDIDATE / REAL_G30_RUNTIME_RECEIPT_PANEL_AUTHORIZATION_MULTI_REVIEWER_SCHEMA_ACCESS_AND_UAT_PENDING` | Pro 复核未来 G30 authorized runtime receipt 到 Panel Owner 人工选人、G26 精确 policy/pool/quorum、全员冲突与真人接受、逐人 PRACTICE Evidence 最小访问、十四加 Panelist scope 锁及 Audit/Outbox；随后由 Tech、Platform、Certification Governance、Data/Security、Panel Owner 与全体 Panelist 验证多人 schema、授权/改派、访问撤销、事务与并发恢复，未通过前禁止 Panel API、Review、投票、Human Gate 或 Credential 创建 |
| G32 | `32_G32_认证Panel逐人Review_Vote与Human_Gate原子命令_V0.1.md` | `MACHINE_CANDIDATE / REAL_G31_RUNTIME_RECEIPT_RUBRIC_PANEL_REVIEW_GATE_APPEAL_AND_UAT_PENDING` | Pro 复核未来 G31 authorized runtime receipt 到权威 Rubric、每名 Panelist 完整评分与独立真人签署、逐人 HUMAN_EVALUATION Evidence、全员 quorum/严重票优先聚合、Certification Human Gate、Attempt/Assignment 状态、access 回收与 Appeal/Appeal Register handoff；随后由 Tech、Platform、Certification Governance、Data/Security、Panel Owner、全体 Panelist 与 Appeal Owner 验证真实多人事务、结论登记、申诉入口及恢复，未通过前禁止 Panel Review API、Gate、Appeal、Terminal Result 或 Credential 写入 |
| G33 | `33_G33_认证Panel_Gate申诉登记与独立Reviewer分配_V0.1.md` | `MACHINE_CANDIDATE / REAL_G32_ADVERSE_GATE_APPEAL_REGISTER_REVIEWER_ASSIGNMENT_AND_UAT_PENDING` | Pro 复核未来 G32 adverse Certification Gate receipt 到 Person 显式申诉、完整空 Appeal Register、G26 Appeal policy/独立 pool、Appeal Owner 人工选人、全员真人接受、冲突隔离、原 Gate Evidence 最小访问及 SUBMITTED→IN_REVIEW 原子计划；随后由 Tech、Platform、Certification Governance、Data/Security、Appeal Owner、独立 Reviewers 与 Person 代表验证真实登记、授权、并发/重放/撤权/超时/恢复，未通过前禁止 Appeal API、Resolution、replacement Panel/Gate、Terminal Result 或 Credential 写入 |
| G34 | `34_G34_认证Panel_Gate申诉独立复核_Resolution_Evidence与Replacement_Panel_Handoff_V0.1.md` | `MACHINE_CANDIDATE / REAL_G33_RUNTIME_RECEIPT_REVIEWER_RESOLUTION_EVIDENCE_REPLACEMENT_PANEL_POOL_AND_UAT_PENDING` | Pro 复核未来 G33 authorized runtime receipt 到全体独立 Reviewer 逐人完整复核、真人 finding 签署、全员一致终局、逐人 HUMAN_OBSERVATION Evidence、全体最终 Resolution 签署、Appeal/Register 终局更新、access 回收和 replacement Panel handoff；当前 G26 pool 排除原 Panel 后容量不足，必须扩池重批，未通过前禁止 Resolution API、复用原 Panel、降低 quorum、创建 replacement Panel/Gate、Terminal Result 或 Credential |
