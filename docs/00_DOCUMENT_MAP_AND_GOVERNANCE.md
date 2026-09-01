# 00｜文档地图与治理规则

状态：`APPROVED_FOR_BUILD`
版本：V1.0
日期：2026-08-13
适用阶段：产品重置、P0 关闭、P1/P2 规划
权威性：本目录是 vNext 的文档事实源。42/43 获批后是 2026-08-13 之后的最高产品与施工基线；00–15 是受其约束的规范合同；16–41 是当时构建/运行/决策证据，不因新基线而被追溯改写。

## 1. 为什么不再以“8 份文档”为目标

上一轮的问题不是文档数量不足，而是文档没有把“全新系统”转化为可机器验证的物理边界，也没有阻止实现继续依赖旧仓库、旧路由、旧数据库迁移和旧发布链路。

本轮按决策问题组织文档。每份文档必须回答一个明确问题、拥有责任人和批准状态，并能在需求、设计、代码与测试之间追溯。Word/PDF 可以作为评审导出物，但 Markdown 才是版本控制中的权威原文。

## 2. 文档清单

| 编号 | 文档 | 回答的问题 | G0 要求 |
| --- | --- | --- | --- |
| 01 | [重构失败深度复盘](01_REFACTOR_POSTMORTEM.md) | 上一轮为什么必然演化为新旧混合？ | 复盘事实无争议；纠正措施进入其他文档 |
| 02 | [Greenfield 项目章程与隔离合同](02_GREENFIELD_CHARTER_AND_ISOLATION_CONTRACT.md) | 什么叫“从零独立开发”，如何证明？ | 全部红线批准；隔离验收可执行 |
| 03 | [产品简报与 PRD](03_PRODUCT_BRIEF_AND_PRD.md) | 为谁解决什么问题，首版做什么、不做什么？ | P0 范围、角色、成功指标批准 |
| 04 | [用户旅程、信息架构与体验合同](04_USER_JOURNEYS_IA_AND_UX_CONTRACT.md) | 用户如何完成闭环，页面与状态如何组织？ | 核心旅程、路由、页面状态批准 |
| 05 | [领域模型、状态机与数据合同](05_DOMAIN_MODEL_STATE_MACHINE_AND_DATA.md) | 业务事实如何建模，谁拥有状态？ | 实体、状态迁移、数据所有权批准 |
| 06 | [系统架构与 ADR](06_SYSTEM_ARCHITECTURE_AND_ADRS.md) | 系统如何独立构建、运行和演进？ | 架构、栈、边界 ADR 批准 |
| 07 | [API、事件与集成合同](07_API_EVENT_AND_INTEGRATION_CONTRACT.md) | 前后端及外部系统如何交互？ | P0 端点、错误、幂等、集成边界批准 |
| 08 | [安全、隐私与权限模型](08_SECURITY_PRIVACY_AND_PERMISSION_MODEL.md) | 谁能看/改什么，数据如何受保护？ | 权限矩阵、敏感数据、保留规则批准 |
| 09 | [测试、UAT 与质量策略](09_TEST_UAT_AND_QUALITY_STRATEGY.md) | 如何在开发前定义“真的可用”？ | 验收场景、门禁、证据标准批准 |
| 10 | [交付计划与工程规则](10_DELIVERY_PLAN_AND_ENGINEERING_RULES.md) | 如何开发而不重演分支、补丁和并行失控？ | 里程碑、WIP、合并与 DoD 批准 |
| 11 | [发布、数据导入与运行计划](11_RELEASE_MIGRATION_AND_OPERATIONS_PLAN.md) | 如何上线、导入、观测和恢复？ | 环境、导入、切换、回滚批准 |
| 12 | [决策、风险与开放问题台账](12_DECISION_RISK_AND_OPEN_QUESTIONS.md) | 哪些决定已锁定，哪些仍阻塞开工？ | 所有 `BLOCKS_G0` 项关闭；DEC-017 锁定无附件；DEC-018/019 延期外部观测与独立故障域；DEC-020 保留 WP-12B 原 FAIL；DEC-022/023 允许精确候选以正式域名进入单组织受控 Alpha，但不等同完整 production GO |
| 13 | [需求追溯矩阵](13_REQUIREMENTS_TRACEABILITY_MATRIX.md) | 每条需求由什么设计、接口、数据和测试证明？ | P0 行无空白引用 |
| 14 | [UI Foundations 与组件合同](14_UI_FOUNDATIONS_AND_COMPONENT_CONTRACT.md) | 视觉、交互和组件如何保持一套正式语言？ | Token、组件状态、无障碍基线批准 |
| 15 | [P0 内容、Rubric 与运营规范](15_P0_CONTENT_RUBRIC_AND_OPERATIONS_SPEC.md) | 实际交付什么任务内容，主管按什么标准评？ | 任务/Rubric/SLA/Owner 批准 |
| 16 | [WP-00 与 Walking Skeleton 构建证据](16_WP00_AND_WALKING_SKELETON_EVIDENCE.md) | 本次实际实现、验证了什么，哪些门禁仍未运行？ | 本地基座与标准路径证据可复现；不混同发布 GO |
| 17 | [WP-01 邀请、身份与会话构建证据](17_WP01_INVITE_IDENTITY_SESSION_EVIDENCE.md) | WP-01 实际实现和自动化证明了什么，哪些真人/物理门禁仍未运行？ | 邀请、内部身份、独立会话证据可复现；不混同 UAT/发布 GO |
| 18 | [WP-02 Current Action 与任务版本构建证据](18_WP02_CURRENT_ACTION_TASK_VERSION_EVIDENCE.md) | WP-02 的 Resolver、任务版本、Learner 页面和迁移实际证明了什么？ | Current Action/TaskVersion 证据可复现；真人理解率与发布门禁仍独立 |
| 19 | [WP-03 提交、附件与修订构建证据](19_WP03_SUBMISSION_ATTACHMENT_REVISION_EVIDENCE.md) | WP-03 的不可变提交历史、受控附件、草稿恢复与首次/修订路径实际证明了什么？ | REQ-BR-004/006 本地证据可复现；真人 UAT、真实存储/扫描和发布门禁仍独立 |
| 20 | [WP-04 Reviewer 工作台与结论构建证据](20_WP04_REVIEWER_WORKBENCH_EVALUATION_EVIDENCE.md) | WP-04 的授权队列、固定材料、结构化结论、不可变历史与 Learner 状态闭环实际证明了什么？ | REQ-BR-005 本地证据可复现；真人 Reviewer/UAT、校准、物理环境和发布门禁仍独立 |
| 21 | [WP-05 结果、交接、通知与历史构建证据](21_WP05_OUTCOME_HANDOFF_NOTIFICATION_TIMELINE_EVIDENCE.md) | WP-05 的不可变 Outcome/Handoff、可重试通知 worker、完整结果页与跨域时间线实际证明了什么？ | REQ-BR-007/009/010 本地证据可复现；真实通知/AI、真人 UAT、物理环境和发布门禁仍独立 |
| 22 | [WP-06 受控运营、离线导入、恢复与发布门禁构建证据](22_WP06_CONTROLLED_OPERATIONS_IMPORT_RECOVERY_RELEASE_EVIDENCE.md) | WP-06 的有意图运营命令、签名导入、安全审计、运行状态、本地灾备及 fail-closed 发布判断实际证明了什么？ | REQ-BR-008、ISO-MUST-009/010/011 与 NFR-009/010/011 本地证据可复现；真实导入、真人 UAT、真实通知、物理环境、异机恢复和发布签署仍 `NOT_RUN`/`NO_GO` |
| 23 | [G4–G6 下一批工作包定义](23_G4_G6_NEXT_WORK_PACKAGES.md) | WP-07～WP-15 如何按单一 WIP 推进候选、试点与正式切换？ | WP-07/WP-08/WP-09 已关闭；WP-10 按 Alpha/RC 无附件边界关闭；WP-11 三项外部证据按 DEC-018 仅在 Alpha 延期；WP-12 独立灾备故障域按 DEC-019 延期但基础硬化继续，production 保持 `NO_GO` |
| 24 | [WP-07 候选基线与软件供应链构建证据](24_WP07_CANDIDATE_BASELINE_SUPPLY_CHAIN_EVIDENCE.md) | 本地候选、分层 CI、扫描、SBOM 与 release manifest 实际证明了什么？ | 候选、远端 CI、GHCR digest 与受保护 main 已复验；staging/production 仍不在该证据范围 |
| 25 | [WP-08 Definition of Ready 构建证据](25_WP08_DEFINITION_OF_READY_EVIDENCE.md) | 物理 staging 写入前的 Git、浏览器、迁移、fixture、冷启动、Ops 与证据边界是否真实可重复？ | 本地 DoR 证据可复现；不等同于物理 staging 已创建、部署或通过隔离验收 |
| 26 | [WP-08 火山引擎 Staging 实施路径证据](26_WP08_VOLCENGINE_STAGING_PATH_EVIDENCE.md) | 已锁定 provider/region/budget 后，唯一 IaC/CI/secret/回滚路径是什么，云端是否已经写入？ | 冻结基础设施上的候选 `14c9ba0…` 已完成 migration、seed、完整服务健康、TLS 与浏览器 smoke；控制台、冻结 state 与真实数据面组合证据关闭物理 ACL，WP-08 为 `STAGING_ISOLATION_VERIFIED` |
| 27 | [WP-09 真实身份与会话构建证据](27_WP09_REAL_IDENTITY_SESSION_EVIDENCE.md) | 飞书身份绑定、真实会话和撤销边界在代码与物理环境分别证明了什么？ | 修复候选已部署；指定真实 Reviewer 在撤销后原会话看到明确 `SESSION_EXPIRED`/重新登录提示，WP-09 为 `IDENTITY_AND_ACCESS_VERIFIED` |
| 28 | [WP-10 真实附件与文件安全构建证据](28_WP10_FILE_SECURITY_EVIDENCE.md) | 私有对象存储、短时授权、隔离扫描与停用边界实际证明了什么？ | 当前 Alpha/RC 固定无附件的 TSK-001 V1 并 fail closed，结论为 `SECURELY_DISABLED_FOR_ALPHA`；未来启用前重开五项物理门禁 |
| 29 | [WP-11 真实通知与外部可观测构建证据](29_WP11_NOTIFICATION_OBSERVABILITY_EVIDENCE.md) | 加密接收人、真实飞书适配器、回执、重驱、结构化日志和外部观测合同分别证明了什么？ | 候选 `172c9f6…` 已部署，独立通知应用/secrets 与主机观测通过；DEC-018 将 TLS topic、真实通知和告警演练仅在 Alpha 延期，三项仍 `NOT_RUN`，production 与完整 WP-11 结论仍 `NO_GO` |
| 30 | [WP-12 候选硬化与灾备构建证据](30_WP12_CANDIDATE_HARDENING_DR_EVIDENCE.md) | RC 的安全、性能、保留删除、异机恢复和回滚门禁实际关闭到什么程度？ | 第一批代码级安全硬化已验证；DEC-019 仅延期独立灾备故障域选型，基础恢复、威胁模型、性能、保留删除和回滚仍未关闭，WP-12 为 `IN_PROGRESS`，production 为 `NO_GO` |
| 31 | [WP-13～WP-15 真人、时间与生产门禁执行包](31_WP13_WP15_EXECUTION_GATE_KIT.md) | 如何确保真人 UAT、14 天试点和生产批准不被自动化假证据替代？ | 候选 `8f77ceec…` 已完成一条真人修订闭环并以 `journey.muchenai.com` 开放单组织受控 Alpha；完整 WP-13/14/15 仍未通过，不伪造完整 production GO |
| 32 | [WP-12B 多租户容量与隔离门禁证据](32_WP12B_MULTI_TENANT_LOAD_AND_ISOLATION_EVIDENCE.md) | 十几个真实组织上线前如何证明多租户并发容量、隔离和事实唯一性？ | run `30525165474` 的隔离/正确性/退役 PASS、原 1 秒性能 FAIL 均已固化；DEC-020 仅允许同一候选按 ≤1.2 秒进入 WP-13，不记 `WP12B_CLOSED` |
| 33 | [WP-17 Learner Experience 高保真原型合同](33_WP17_LEARNER_EXPERIENCE_PROTOTYPE.md) | 如何让 Learner 在首次进入、任务执行和结果反馈中形成清晰而克制的旅程感？ | 视觉方向已关闭；三个路线点只验证交互语言，不代表正式阶段数量。正式路由实现等待 WP-18/19，`/review` 与 `/ops` 保持专业工具界面 |
| 34 | [WP-18 正式产品真相恢复与 vNext 重接合同](34_WP18_FORMAL_PRODUCT_TRUTH_RECOVERY.md) | 旧正式探索营与单任务 Alpha 为什么不一致，四宝藏＋三评测如何接回 vNext？ | `DEC-024` 锁定 Day 0＋四宝藏＋三能力评测＋结果；TSK-001 保留为 Alpha 验证任务；后续只在现有 vNext 基座上补多阶段 Journey 编排，不复用旧运行时 |
| 35 | [WP-19～WP-22 正式探索营最小纵向切片证据](35_WP19_WP22_FORMAL_JOURNEY_VERTICAL_SLICE_EVIDENCE.md) | 多阶段 Journey、四宝藏、三评测和正式 Learner 页面是否已在同一条真实路径上接通？ | 代码、migration、API、Web、staging、Journey V1 发布与绑定邀请读回已形成 `MINIMAL_VERTICAL_SLICE_COMPLETE / MACHINE_READBACK_VERIFIED`；内容真人有效性、Reviewer 校准、WP-23 和 production GO 仍独立 |
| 36 | [WP-24 Formal Exploration Camp V2](36_WP24_FORMAL_EXPLORATION_CAMP_V2.md) | 如何把最小技术切片重建为完整一天学习、三项真实评测和人工准入产品？ | V1/既有事实不可变；V2 内容、评分和人工准入本地实现并通过门禁后方可由 Reviewer/Operator 发布；不自动部署或迁移 |
| 37 | [WP-25～WP-30 探索营 P0 真人体验与受控上线工作包](37_WP25_WP30_LEARNING_PRODUCTIZATION_WORK_PACKAGES.md) | 如何把真实内容、完整体验、单宝藏纵向切片和每包真人验证接成可受控上线的探索营？ | `DEC-026` 已批准并启动 WP-25 内容/原型/真人验证；产品代码、WP-26 及全部外部动作仍未授权 |
| 38 | [WP-25 P0 Experience & Content Freeze 执行包](38_WP25_P0_EXPERIENCE_CONTENT_FREEZE.md) | WP-25 已核对哪些正式内容、页面状态和真人验收，哪些材料仍需负责人提供？ | 原型三视口/路线/完整点击路径机器通过；当前 `PROTOTYPE_MACHINE_VERIFIED / HUMAN_GATES_NOT_RUN / CONTENT_INPUT_REQUIRED`，不得以原型或工程草稿冒充已批准内容 |
| 39 | [WP-26～WP-30 本地构建记录与待授权账本](39_WP26_WP30_AUTONOMOUS_BUILD_RECORD.md) | 夜间自主开发完成了哪些机器合同，哪些真人/外部动作仍必须另行授权？ | WP-26～30 本地机器能力已实现；真人内容/UAT、V3 发布、部署、正式域名和 cohort 仍 `NOT_RUN`/`NO_GO`，按顺序授权 |
| 40 | [WP-15 上线战时模式生产切换证据](40_WP15_WARTIME_PRODUCTION_CUTOVER_EVIDENCE.md) | 如何把已验收 staging 候选用新鲜恢复库切到正式域名，同时保留旧应用＋旧库的一键回退？ | 候选、staging 与当前生产基线已只读核验；生产 preflight、备份恢复、部署、真人飞书登录和维护/回退演练必须按单次工作流补齐，完整 production GO 继续延期 |
| 41 | [P0 产品闭环修复与真实反馈计划](41_P0_PRODUCT_CLOSURE_AND_FEEDBACK_PLAN.md) | 为什么简单业务仍反复出现小问题，如何从模块完成切换为真实旅程完成？ | 一步邀请、24 小时会话、邀请三态、八站链接渲染和新浏览器续接已完成 API/Web 与隔离合成浏览器回归；正式 Journey V3 材料访问与真人 UAT 仍未证明 |
| 42 | [第一性原理产品与工程总基线](42_FIRST_PRINCIPLES_PRODUCT_AND_ENGINEERING_BASELINE.md) | 什么才算产品进度，身份、体验、事实和复杂度遵循什么公理？ | Owner 批准后成为所有后续需求、设计、实现和验收的最高基线 |
| 43 | [P0、P1、P2 总施工计划](43_P0_P1_P2_EXECUTION_MASTER_PLAN.md) | 基于当前真实差距，先修什么、如何验收、什么明确延后？ | Owner 批准 P0 顺序、真人名册、受控上线目标和 P1/P2 延后边界 |
| 44 | [P0-1 身份中心化与多角色访问施工证据](44_P0_1_IDENTITY_CAPABILITY_BUILD_EVIDENCE.md) | 单角色会话根因如何被模型级修复，哪些机器与真人证据已通过？ | staging 机器验证与同一飞书身份 `/content`、`/review` 真人复验均通过；P0-1 已关闭 |
| 45 | [P0-2 Learner 一站式任务页施工合同](45_P0_2_LEARNER_ONE_PAGE_BUILD_CONTRACT.md) | 新人如何在 5 秒内看懂当前站、输入、要求与唯一动作？ | P0-1 关闭后唯一产品 WIP；机器/浏览器与真人证据分层记录 |
| RB-15 | [受控 Alpha 正式域名切换手册](runbooks/WP15_ALPHA_PRODUCTION_CUTOVER.md) | 如何在不丢失 staging 和新业务事实的前提下备份恢复、切换正式域名并一键止血？ | 受保护主线唯一入口；锁定候选、空库恢复、加密异机备份、双 host、OAuth/TLS、维护页与旧站入口回退边界 |
| RB-15W | [上线战时模式受控生产切换手册](runbooks/WP15_WARTIME_PRODUCTION_CUTOVER.md) | 如何用最短可恢复路径完成新鲜备份、隔离恢复、冻结候选验收和小范围正式使用？ | 不改 DNS/基础设施；只接受 `ff530528…`，任一步失败即停；旧应用＋旧库保持可执行回退，成功也只记 `CONTROLLED_ALPHA_LIVE` |
| TM | [仓库级 Threat Model](../muchen-journey-vnext-threat-model.md) | 公网、身份、组织隔离、业务事实、Worker、供应链和恢复边界的主要攻击路径是什么？ | 已完成仓库证据绑定和风险排序；DEC-018/019 延期项保留为显式风险，不能替代物理演练或发布 GO |

## 3. 权威顺序

发生冲突时按以下顺序处理：

1. 已批准的 42 号第一性原理基线；
2. 与 42 一致的已批准 `DEC-*` 决策；
3. Greenfield 隔离合同；
4. 已批准的 PRD 与体验合同；
5. 领域、架构、API、安全合同；
6. 43 号总施工计划及测试、交付和运行计划；
7. 需求追溯矩阵；
8. As-Built、原型、任务单和历史实现说明。

任何人不能通过代码、临时脚本、环境变量或发布操作悄悄改变上位合同。需要改变时，先更新决策及受影响文档，再改实现。

## 4. 文档状态

| 状态 | 含义 |
| --- | --- |
| `DRAFT_FOR_APPROVAL` | 内容已准备，尚未获得责任人批准 |
| `BLOCKED_BY_DECISION` | 存在会改变实现方向的未决事项 |
| `APPROVED_FOR_BUILD` | 已批准，可作为开发输入 |
| `SUPERSEDED` | 已被明确的新版本替代，保留追溯 |
| `AS_BUILT` | 记录已实现事实；必须注明验证环境和发布状态，不得覆盖原设计版本 |

设计文档和 As-Built 记录必须分版保存。禁止像上一轮一样把生产补遗继续追加到原始设计稿并让两者共用同一版本身份。

### 4.1 2026-08-13 分类结论

| 文档范围 | 分类 | 后续处理 |
| --- | --- | --- |
| 00–15 | `NORMATIVE_UNDER_42` | 保留有效合同；所有冲突按 42/43 和新增 DEC 解释 |
| 16–32、35–36、38–40 | `HISTORICAL_EVIDENCE` | 保留当时 SHA、run、PASS/FAIL/NOT_RUN；不作为新需求顺序 |
| 33–34 | `PRODUCT_DISCOVERY_INPUT` | 保留视觉与产品真相结论；不得代替真人体验验收 |
| 37、41 | `SUPERSEDED_EXECUTION_ORDER` | 根因和证据仍有效；未完成施工顺序由 43 替代 |
| 42 | `FIRST_PRINCIPLES_AUTHORITY` | 批准后最高产品/工程基线 |
| 43 | `CURRENT_EXECUTION_AUTHORITY` | 批准后唯一 P0/P1/P2 施工顺序 |

“历史证据”不是“无效”：它继续证明当时做过什么、没做什么。它只是不再有权因为模块已完成而推动错误的下一步。

## 5. 变更规则

- 每个 P0 需求使用永久 `REQ-*` 编号；每个决策使用永久 `DEC-*` 编号；每个验收使用永久 `AT-*` 编号。
- 变更必须说明原因、影响的需求/状态/API/数据/测试、批准人和生效版本。
- 一个需求若无法映射到验收场景，不得进入开发。
- 一个实现若无法映射到批准需求，不得合并。
- 口头决定、聊天内容和代码注释只有被登记后才生效。
- 文档与代码在未来独立仓库内一起评审；本预备包获批后整体迁入该仓库。

## 6. G0 开工门禁

以下条件全部满足后，才允许初始化产品脚手架：

- [x] `DEC-001` 至 `DEC-016` 中所有适用的构建方向已批准；需真人或物理环境证明的项目转为 G4/G5 门禁，不得伪造证据。
- [x] P0 只有一个明确垂直闭环，范围和非目标已批准。
- [x] 新仓库及全部独立资源命名和初始 Owner 已确定；物理 staging/prod 资源在 G4 验证。
- [x] 旧仓库依赖禁令、旧数据库网络禁令和离线导入边界已写成可执行验收。
- [x] P0 状态机不存在同义状态或“兼容状态映射”。
- [x] API、权限、错误、幂等和审计合同已冻结。
- [x] `REQ-* → AT-*` 追溯完整；真实角色 UAT 规模和角色已安排，具体名册在 G4 受控登记。
- [x] P0 不导入旧业务数据；未来导入必须离线、隔离、可拒绝且零写回。
- [x] 发布、回滚、备份恢复和观测初始责任人已确认；真人/物理演练仍是 G4 门禁。
- [x] 本轮批准明确接受：进度压力不能豁免隔离红线。

## 7. G0 签署角色

| 角色 | 责任 |
| --- | --- |
| Product Owner | 产品问题、P0 范围、角色、内容和成功指标 |
| Tech Lead | Greenfield 边界、架构、API、工程门禁 |
| Data Owner | 新数据模型、导入范围、核对与保留 |
| Design Owner | 用户旅程、IA、页面状态和可访问性 |
| Security/Privacy Owner | 身份、权限、敏感数据、审计与数据权利 |
| QA/UAT Owner | 验收场景、真实角色、证据和退出标准 |
| Release/Ops Owner | 环境、部署、观测、恢复和切换 |

同一人可以承担多个角色，但每项责任必须明确写出姓名，不能只写“产品团队”或“研发团队”。
