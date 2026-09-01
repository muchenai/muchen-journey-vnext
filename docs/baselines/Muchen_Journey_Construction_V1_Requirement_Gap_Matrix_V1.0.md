# Muchen Journey Construction V1 Requirement Gap Matrix V1.0

> 状态：`SHARED_P0_IN_PROGRESS / OWNER_CONTENT_BLOCKED / REAL_UAT_NOT_RUN / NO_RELEASE`  
> 基线：`codex/full-module-development@b7597edfdf7d5bd2fdbda99cd1141590ab3d5859`  
> 机器矩阵：`outputs/controller-integration/construction-v1.0/requirement-gap-matrix.v1.json`

## Owner 校正后的 Requirement 统计

- P0：`READY_FOR_HUMAN=9 / IN_PROGRESS=8 / BLOCKED_OR_GATED=7 / TOTAL=24`；
- P1：`TOTAL=2`，其中 `NV-003=PARTIAL_RUNTIME`、`AIA-003=GAP_P1`；
- P1 与 `POST_RELEASE_DEFERRED` 范围停止继续开发，不进入 Construction V1 technical checkpoint；
- 本统计不把 technical checkpoint、机器测试或 dirty overlay 记为候选冻结或真人通过。

## 2026-08-26 EXP-003 独立复核与替换决定谱系

- 新增 `0027_next_stage_review`，只扩展已批准的“探索营结果包 → 下一训练阶段决定”纵切：`NextTrainingStageReviewRequest` 继续作为不可变本人申请事实；新增不可变独立 Reviewer 分配和终局复核事实，不建立第二套 Person、Evidence、Review/Evaluation、Outcome 或 Human Gate 表。
- 原 `NextTrainingStageDecision` 不可更新、不可删除。`OVERTURNED` 必须在同一事务追加 revision+1 的替换决定，并引用原决定和复核请求；延期约束触发器在事务结束前验证替换事实存在。`UPHELD` 和 `RETURNED_FOR_REVIEW` 不会静默覆盖原决定，也不会自动创建 Enrollment 或 Assignment。
- API 现在提供本人提交/回读、Operator 分配独立 Reviewer、指定 Reviewer 队列/终局处理。数据库和 API 同时拒绝本人、原签署人、分配人或无 Reviewer 角色人员充当独立复核人；Assignment、Resolution 和新旧 Decision 全部不可变，写命令具备幂等、审计和 Outbox。
- 结果页并行回读复核谱系，显示 `RECEIVED / IN_REVIEW / UPHELD / OVERTURNED / RETURNED_FOR_REVIEW`，明确原决定保留及替换决定为新增版本。页面仍只使用“下一训练阶段”语义，不产生录用、淘汰、项目准入、晋升或其他正式人才状态。
- 空合成库 `0001→0027` 以及无新复核事实时的 `0027→0026→0027` 回滚/重升级通过；有追加复核事实时 downgrade 明确失败关闭并要求 forward-fix。定向 API 为 `22 passed`，Runtime 范围为 `1518 passed, 3 skipped, 4 subtests passed`，Web 为 `47 passed` 且 TypeScript、ESLint、production build 通过，OpenAPI 等价。
- 最新受控 inventory 为 614 个 pre-evidence 状态条目：`344 RELEASE_REQUIRED / 270 POST_RELEASE_DEFERRED / 0 UNKNOWN`；仓库外隔离树 445 个源文件，source hash 为 `3dd5639f…`。Python 43 项完整解析图及 3 项构建后端现已逐版本/全部 PyPI artifact SHA-256 锁定；篡改 hash 失败关闭、真实 API/Worker 构建、`pip check`、1518 项 Runtime、三镜像 SBOM 与 Gitleaks 通过。当前镜像 OS CVE scan 因 Scout 要求登录、Docker Hub timeout、官方 Trivy GHCR 拉取停滞而保持 `NOT_RUN_EXTERNAL_SCANNER_UNAVAILABLE`，没有复用旧镜像 0C/0H 结论；该 hash 仍是 dirty overlay，不是候选提交。
- `EXP-003` 因此上调到 `MACHINE_READY_FOR_HUMAN`。`GOV-005` 仍保持 `PARTIAL_RUNTIME`：本纵切不是通用高影响人才 Gate，也不替代尚未绑定的真实 appeal policy/window、具名独立 Reviewer、Owner 签署和真人 UAT。

## 2026-08-26 CORE-001/002 身份与唯一行动校正

- `0026_identity_organization_scope` 将既有 User、RoleAssignment、ExternalIdentity、Invite、JoinContext、IdentitySession、ExternalIdentityLink 和 InvitationControl 通过组织复合 FK 闭合；迁移前置扫描发现任何跨组织旧行即整体失败关闭，不改写或删除事实。没有新增第二 Person 表。
- 新测试在 `0025` 真实复现数据库接受跨组织 RoleAssignment 的红灯；实现后身份/邀请定向测试为 `13 passed`。另一个合成库证明不合规旧行阻断 `0026` 升级且 revision 保持 `0025`；相邻 `0026→0025→0026` 回滚/重升级通过。
- 邀请明文 token 不进入 Audit、Outbox 或幂等重放载荷；local/test 之外 fixture identity 继续配置失败关闭。真实身份、撤销与跨 Person UAT 仍为 `NOT_RUN`，所以 `CORE-001` 只上调到 `MACHINE_READY_FOR_HUMAN`。
- CORE-002 的当前浏览器重跑发现：无 Journey 图谱投影的新 Enrollment 只有“开始当前任务”文字、没有可点击行动。新增合同测试先得到 `8 passed / 1 failed`，最小修正后该分支提供唯一“进入当前任务”或“查看当前结果”，不增加客户端状态或第二导航模型。
- Web 合同 `47 passed`，TypeScript、ESLint 和 production build 通过；本地合成邀请在 Chromium 的 `390x844 / 768x1024 / 1280x900` 三种视口都先显示可执行当前行动、再显示准确四模块目录，无横向溢出，CTA 可进入任务页，控制台 0 error/0 warning。3/3 首次真人理解 UAT 仍为 `NOT_RUN`，所以 `CORE-002` 只上调到 `MACHINE_READY_FOR_HUMAN`。
- 最新 `0026` 空合成库 Runtime 范围为 `1513 passed, 3 skipped, 4 subtests passed`；OpenAPI 等价。宿主 inventory 为 `4 tests OK`，只读挂载证据容器中的 Legacy reference-only/config 为 `21 passed`。Docker 上下文有意排除 `outputs/`，相关证据测试没有被冒充为 Runtime 测试。

## 2026-08-26 GOV-001 与供应链校正

- `0025_formal_result_gate` 已将正式结果资格落实为数据库 Gate：只复用既有 `User / Enrollment / Assignment / SubmissionVersion / Review / Evaluation / Outcome`，要求同组织、本人当前固定实操版本、指定真人 Reviewer 的 finalized PASS、签署理由及完成状态；没有建立第二套 Person、Evidence 或 Human Gate 事实源。
- 全新合成库定向 Gate 为 `43 passed`；候选 Runtime 范围为 `1525 passed, 1 skipped, 4 subtests passed`，单一 migration head 为 `0025`。不合规历史合成行阻断升级的负向测试通过，但这不是历史数据库审计或真人 UAT。
- 镜像构建快照的独占 inventory 为 560 个状态条目：`290 RELEASE_REQUIRED / 270 POST_RELEASE_DEFERRED / 0 UNKNOWN`；仓库外隔离树 440 个源文件，source hash 为 `888897a5c3cb5bd65e9e1ccb8c5bd58cf4eb6e466f807b4abb7708c62743f09f`，candidate SHA 仍为空。随后写入本节机器证据会改变文档层源码摘要，因此不得把该镜像快照冒充最终工作树候选。
- 本轮首次供应链扫描真实发现三个旧镜像各 `7 High`（Alpine OpenSSL 3.5.7），因此旧零高危结论作废。三个 Dockerfile 随后以官方 URL、版本和 SHA-256 固定 OpenSSL 3.5.8 三项 APK；重建后的 API/Worker/Web 均为 `0 Critical / 0 High`，运行时版本、非 root、OpenAPI 等价、Web 无 npm/npx、SPDX SBOM 与 Gitleaks 均有机器证据。
- 以上仍只是 dirty overlay 的机器候选。干净 full-SHA candidate、独立 QA、同一候选恢复/回滚、真人 UAT、告警真人回执和 Release GO 均未完成。

## 2026-08-26 四模块内容包运行载体进展

- 新增 `0024_module_content_binding`：`ModuleContentPackageBinding` 将施工包规定的 Owner 已签名内容包一对一绑定到既有不可变 `JourneyVersion` 与 `TaskVersion`，保存内容包、任务、Rubric 三项 hash、来源、Owner、有效期、主备 Reviewer、SLA、可见范围和数据等级。数据库拒绝更新/删除，并用复合 FK、CHECK 和 JSON/hash 谱系约束防止跨组织或安全边界漂移。
- 新增 `POST /api/v1/ops/module-content-packages/publish`，首发仅承载 AI学院和交付线公会的一个签署单元/任务包。未生效、已过期、hash 漂移、Owner/Reviewer 不匹配、非具名替补、生产写入或试图从此入口绕过 `ControlledTaskAuthorization` 均失败关闭。
- AI学院与交付线公会复用同一 `JourneyDefinition/Version → JourneyStageVersion → Enrollment → Assignment → SubmissionVersion → Review/Evaluation` 内核；没有新增第二套任务、提交、评审或证据状态机。合成测试已证明发布、邀请、本人确认和唯一 Assignment 创建；不把合成内容计为 Owner 内容或真人 UAT。
- AI学院与交付线公会现已各自完成一轮合成的“固定材料 Gate → v1 → 指定真人 Reviewer 退回 → v2 → 指定真人 Reviewer 通过”，且数据库逐模块只形成两个不可变 `SubmissionVersion/Review/Evaluation`。未经过评审的覆盖提交和无法驱动真人评审的不完整 Rubric 都失败关闭，因此共享 `GOV-002` 机器状态上调为 `MACHINE_READY_FOR_HUMAN`；这不改变模块 Owner 内容与真人 UAT 的阻塞状态。
- 模块 Enrollment 的 Reviewer 更换仅允许在签署包具名的主/备 Reviewer 间进行，且继续复用现有 CAS、Audit 与 Outbox。容量值、超时聚合、真实升级接收人和真人接受仍未就位，因此 `CORE-005` 保持 `PARTIAL_RUNTIME`。
- AI学院页面来源已校正为《AI学院主管_2026下半年执行计划_V0.2》。真实首单元、示例/反例、Rubric、Reviewer 校准和公会使命/成员规则/导师池仍全部 `PENDING_OWNER_SIGNATURE`，所以 `AIA-001` 与 `DLG-001` 仍为 `BLOCKED_OWNER_CONTENT`。
- 本次在新建合成库 `journey_next_c1_20260826_07` 完成 `0001 → 0024` 升级与播种，候选 Runtime 范围回归为 `1509 passed / 6 skipped / 4 subtests passed`，定向模块闭环为 `7 passed`，Runtime OpenAPI 与固定合同一致且 migration 仍为单一 `0024` head。两项宿主 Git 工具测试和两项已废止 Legacy 路线测试未在该容器命令运行，不计为 PASS；此前回归记录保留，不被本次结果覆盖。
- 当前仍是 dirty worktree，`candidate_sha=null`；上述仅为机器候选证据，不是 Owner 签署、真人 UAT、独立发布复核或 Release GO。官方 Trivy 0.73.0 扫描器已固定 digest，但漏洞库下载不可用，所以当前镜像 OS CVE 结论仍如实为 `NOT_RUN_EXTERNAL_SCANNER_UNAVAILABLE`。
- 候选边界现已通过独占 inventory 和仓库外 staging 执行：493 个逐文件状态条目归为 `223 RELEASE_REQUIRED / 270 POST_RELEASE_DEFERRED / 0 UNKNOWN`，137 个运行 overlay 与 1 个显式删除进入隔离树，后置字节漂移、未知路径、symlink 和重复输出均失败关闭。隔离源的 API 为 458 项通过、Web 为 46 项通过并产出 API/Web/Worker digest；该树仍明确不是 commit 或 Release Candidate。

## 2026-08-26 共享 P0 进展

- `GOV-001`：Formal Result 已强制同时具备 `PRACTICE` 和 `HUMAN_EVALUATION` Evidence，并由真人 `PASS` Gate 签署；AI、积分、自证和阅读完成的单独输入均失败关闭。
- `GOV-002`：正式 Assignment 转换已集中化，数据库 `COMPLETED` 对外统一为 `PASSED`，跳过评审、覆盖 SubmissionVersion/Evaluation、非本人与非指定 Reviewer 均被阻断；四个模块的共享返工/通过载体已有合成机器证据，机器状态为 `MACHINE_READY_FOR_HUMAN`。
- `GOV-003`：`0020_shared_ai_provenance` 将完整 AI 披露固化到 SubmissionVersion 和 Evaluation，API、页面与数据库 CHECK 同时强制“只作建议”。本项机器状态为 `MACHINE_READY_FOR_HUMAN`，不代表真人 UAT PASS。
- `GOV-004`：`0021_incentive_ledger` 建立了追加式独立激励账本，复用不可变 `Outcome(PASS human Evaluation)` 作为贡献来源事实，并在数据库层阻断跨 Person 来源、覆盖/删除与不合规更正。本人仅有 GET 投影，明确 `formal_effect=NONE`；没有 Owner 签署规则就没有正式奖励写入口。
- `GOV-005/EXP-003`：`0022` 建立独立 `NEXT_TRAINING_STAGE` 决定与本人复核申请；`0027` 在不修改原决定的前提下追加 Operator 分配、独立 Reviewer 终局复核及 replacement-decision lineage。决定继续绑定同一 Person 的正式 Outcome 和恰好三项真人 PASS Evaluation；公开 Formal Admission 写路由仍不存在，历史表保持不破坏兼容。该运行纵切不等于通用高影响人才 Gate。
- `OPS-001`：显式本地合成环境已完成 AES 加密备份、隔离恢复、完整正式事实摘要核对、`0024→0023→0024` 相邻 schema 演练以及候选→Git HEAD 基线→候选的只读应用镜像回滚；API/Worker 健康、权限负向和合成告警决策通过。具名真人告警回执、off-host 恢复和冻结候选演练仍未运行，因此只记为 `PARTIAL_MACHINE_READY`。
- 空合成库 `0001 -> 0022` 升级、`0022 -> 0021 -> 0022` 回滚/重升级、1,490 项候选 Runtime API 测试（另 6 项如实跳过、4 个 subtest）、44 项 Web 契约、OpenAPI 一致性及 Web production build 已通过。候选 API 集明确排除了宿主机发布工具和 `REFERENCE_ONLY_NO_MIGRATION` 的旧审计文件；这不等于未过滤全仓测试 PASS。
- 仍未实现：带真实 policy/window 的通用高影响 HumanGate/Appeal、Owner 签署的激励规则与奖励命令、四模块真实 Owner 签署内容、真人 UAT 和候选冻结。

## 结论

施工包的 26 项 Requirement 均已进入矩阵，但当前不存在可称为完整功能或发布候选的项目状态。现有代码同时包含可复用 Runtime、未持久化机器合同候选、旧 Phase 0/Legacy 证据以及已延期的 Career/Certification 横向逻辑。它们必须按执行台账分别处置，不能因测试文件存在就认定需求完成。

当前评估分布：

- `PARTIAL_RUNTIME`：7；
- `MACHINE_READY_FOR_HUMAN`：9；
- `PARTIAL_MACHINE_READY`：2；
- `BLOCKED_OWNER_CONTENT`：5；
- `GAP_P1`：1；
- `NOT_RUN`：1；
- `RELEASE_NOT_AUTHORIZED`：1。

## 状态机对账

| 合同状态机 | 当前代码载体 | 主要差距 | 处置 |
| --- | --- | --- | --- |
| `formal-assignment.v1` | `AssignmentStatus`, `formal_assignment_workflow.py`, submission/review routes | 数据库终态保留 `COMPLETED` 兼容值；公开 API/UI 已统一 `PASSED`；Owner 内容与四模块真人闭环尚未完成 | 保留数据库兼容语义，所有 mutation 复用集中转换规则，不做破坏性枚举改写 |
| `content-lifecycle.v1` | `ContentDraftStatus`, Task/Journey versions, `ModuleContentPackageBinding` | 已闭合发布版本不可变、Owner/hash/Reviewer/有效期绑定；尚无完整 Domain/Boundary/Pilot/Monitor 生命周期 | 首发只开放签署包的最小发布和回读；完整生命周期后续实现，不伪造 Owner 内容 |
| `human-gate-appeal.v1` | `shared_domain.py`, `appeal_continuity.py`, `next_stage_review_routes.py`, `0027_next_stage_review` | 下一训练阶段复核已持久化 assignment/resolution/replacement lineage；通用高影响 Gate 的真实 policy/window 与 Owner/Reviewer 绑定仍未运行化 | 保留本纵切的共享追加式机制；不把下一训练阶段复核冒充高影响人才 Gate，等待真实政策与具名责任人后再启用该范围 |
| `guild-membership.v1` | 共享 Journey/Enrollment/Assignment 载体已可用 | 公会插件、加入/暂停/退出规则和导师池未签署，不能建立正式成员状态机 | 保持内容 Gate 关闭，不发明加入规则；等待 Owner 内容后再接共享 Membership 事实 |
| `release-candidate.v1` | candidate/release scripts and config | 当前 dirty tree、无固定候选、无真人 UAT/恢复/独立复核 | 保持 DEVELOPMENT；任何机器结果不得越级 |

旧 `FormalAdmissionDecisionType(ADMIT/DEFER/NOT_ADMIT)` 仍存在于 ORM。它只可作为历史兼容读取，不得作为探索营“下一训练阶段”页面或 API 语义；新语义必须独立 scope 并继续遵循此前 V0.3 非破坏性裁决。

## 最小 P0 共享纵切

选择：`固定 TaskVersion → Assignment AVAILABLE → Learner START → immutable SubmissionVersion → assigned human Review → NEEDS_REVISION → 新 SubmissionVersion → human PASS → Practice Evidence + Human Evaluation Evidence + signed HumanGate → formal-result eligibility`。

本纵切覆盖 `GOV-001`、`GOV-002`、`GOV-003`、`CORE-003`、`CORE-004`，并为四个模块复用。首轮不写 Owner 材料、不创建认证/Career 逻辑、不执行真实生产任务、不产生招聘/淘汰/项目准入结论。

首个实施 Gate：

1. 先为数据库 `COMPLETED` 到公开 `PASSED` 的兼容投影、合法/非法转换、不可变 Submission/Evaluation、Reviewer scope 和 AI actor 拒绝补测试；
2. 再集中正式 assignment transition 规则，避免 routes 各自推断；
3. 将已存在的 Evidence/HumanGate 合同投影接到该闭环；
4. 只在非生产合成库运行迁移/DB 约束测试；
5. 机器最多记录 `READY_FOR_HUMAN`。

## Owner 内容与真人 Gate

- 探索营四宝藏、三实操和 Rubric：`PENDING_OWNER_SIGNATURE`；
- 新手村 1—3 张任务卡、NPC/Reviewer/SLA：`PENDING_OWNER_SIGNATURE`；
- AI 学院首单元与公会插件：`PENDING_OWNER_SIGNATURE`；
- 真人 UAT：`NOT_RUN`；
- 独立 QA/Release review：`NOT_RUN`；
- Release GO：`NOT_AUTHORIZED`。

以上依赖不阻止共享、通用、合成数据 P0 继续施工，但阻止模块开放、候选签署和发布。
