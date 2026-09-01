# JOURNEY2 DOMAIN MODEL REBASE PACKAGE V0.1

> 日期：2026-08-26
> Owner 决策：`REFERENCE_ONLY_NO_MIGRATION`
> 状态：`READY_FOR_PRO_REVIEW / DESIGN_ONLY / DATABASE_UNCHANGED / NO_RELEASE`
> 下一 Gate：`PRO_JOURNEY2_DOMAIN_MODEL_REBASE_REVIEW`

## 1. Rebase 结论

Journey2.0 从产品合同重新建立领域边界，不从旧 23 表反向生成 schema。现有 `apps/api/journey_api/models.py`、未提交的 `0020`—`0024` migration 文件及其 Runtime 路由只作为待核对的技术候选；每个保留或新增实体都必须能回到批准的 MAP-ID、冲突裁决、Build Contract 或 Owner 明确决策。

Person 继续复用 `users`；任务、提交、评价和结果继续复用 `Assignment → SubmissionVersion → Review/Evaluation → Outcome/Handoff`。不新建第二套 Person、Evidence、Human Gate、Assignment、Submission、Review、Evaluation 或 Outcome 事实表。

当前脏工作树已经存在上述未提交候选，并不等于 migration 已执行、Runtime 已授权或功能已运营化。本包不新增或修改 migration、ORM/Runtime/API/OpenAPI/页面，不连接或清空数据库，也不把 G1—G34 机器合同候选称为已运营功能。

## 2. 产品依据

| 优先级 | 依据 | 本包用法 |
|---:|---|---|
| 1 | `Muchen_Journey_产品-代码继承映射表_V0.1.md` | 只采用已裁决方向和 MAP-ID；旧数据迁移条目由本次 Owner 决策取代 |
| 2 | `Muchen_Journey_冲突裁决清单_V0.1.md` 与 `OWNER_LEGACY_DISPOSITION_DECISION_REFERENCE_ONLY_NO_MIGRATION_V0.1.md` | 冲突裁决和 Legacy 处置边界 |
| 3 | `build-contracts/BC-001`—`BC-006`、`01_Shared_People_Domain_Contract`、`02_G2` | 定义模块行为、人工 Gate、复用边界和候选实体 |
| 4 | `Muchen_Journey_Minimum_Runtime_Changeset_V0.3.md` | 仅作已审设计输入；不等于 Runtime/migration 授权 |
| 5 | `config/muchen_journey_product.json` | 五地图、共享平台、People AI 治理和当前冻结状态 |

旧飞书表、旧代码载体、原型和机器测试不是产品依据；它们只出现在 §4 参考映射。

## 3. 新领域实体清单

### 3.1 继续作为唯一事实源的现有实体

| 领域 | 实体/关系 | 产品合同来源 | 数据 Owner | 状态 |
|---|---|---|---|---|
| 组织与 Person | `Organization`；`User` 作为 Person；`RoleAssignment` | MAP-001、003；Shared People §2.1；BC-001/002 | Product + Security/Privacy | `REUSE_CANONICAL`；禁止 `people` 镜像表 |
| 身份与进入 | `Invite`、`InvitationControl`、`JoinContext`、`ExternalIdentity`、`IdentitySession` | MAP-002；BC-001 §2/§3 | Security/Privacy | `REUSE_CANONICAL` |
| 任务内容 | `TaskDefinition`、`ContentDraft`、`TaskVersion` | MAP-004、005、015—017；BC-001—004 | 对应 Content/业务 Owner | `REUSE_CANONICAL`；发布版本不可原地改写 |
| Journey 内容 | `JourneyDefinition`、`JourneyVersion`、`JourneyStageVersion` | MAP-003、015—018；BC-001 | Product + 对应业务 Owner | `REUSE_CANONICAL`；Stage 必须绑定 Journey/Task 版本 |
| 学习行为 | `LearningMaterialCompletion` | MAP-007；BC-001/003 | 对应业务 Owner | `REUSE_CANONICAL`；只证明阅读行为 |
| 参与和任务 | `Enrollment`、`Assignment` | MAP-003、006；BC-001—004 | 运营 Owner | `REUSE_CANONICAL`；Assignment 不单独证明通过 |
| 提交与附件 | `Submission`、`SubmissionDraft`、`SubmissionVersion`、`Attachment`、`SubmissionVersionAttachment` | MAP-008、019、022；BC-001—005 | Person 对产物负责；Data/Security 管治理 | `REUSE_CANONICAL`；版本/附件 hash 保留 |
| 人工评价 | `Review`、`Evaluation` | MAP-009、021—023；BC-001—005 | Reviewer Owner | `REUSE_CANONICAL`；最终结论必须真人签署 |
| 结果与交接 | `Outcome`、`JourneyOutcomeEvidence`、`Handoff` | MAP-010、014、017、018；BC-001/002/006 | 业务 Outcome Owner | `REUSE_CANONICAL / IMMUTABLE` |
| 审计与命令 | `AuditEntry`、`OutboxEvent`、`IdempotencyRecord` | MAP-013、022、023；Shared People §5 | Tech + Data/Security | `REUSE_PLATFORM` |
| 数据权利 | `DataRightsRequest` | MAP-022、023、031；BC-006 | Data/Security | `REUSE_PLATFORM` |

### 3.2 Rebase 后的增量候选与当前代码事实

下列对象已出现在当前未提交工作树，但仍只进入 Pro 设计评审；统一状态为 `UNCOMMITTED_MACHINE_CANDIDATE / MIGRATION_NOT_RUN / PRODUCT_AUTHORITY_NOT_INFERRED`：

| 候选事实/字段 | 当前技术载体 | 必要性与非重复边界 | 产品合同来源 |
|---|---|---|---|
| `SubmissionVersion.ai_use`、`Evaluation.ai_use` | `models.py`；`0020_shared_ai_provenance.py` | 只记录 AI 使用来源且固定 advisory-only；不产生 Human Gate 或正式结果 | MAP-012、021；CON-005；Shared People §2.2 |
| `IncentiveLedgerEntry` | `models.py`；`0021_incentive_ledger.py` | 与能力、评价、人才和准入事实隔离；只可引用既有 Outcome，不反向改变 Outcome | MAP-011、020；CON-006；BC-002/004 |
| `NextTrainingStageDecision` | `models.py`；`0022_next_training_stage_review.py` | 新的独立事实，scope 固定为 `NEXT_TRAINING_STAGE`；不改写历史 `journey_admission_decisions`，不表达录用、淘汰、晋升或项目准入 | CON-007；BC-001；Minimum Changeset V0.3 |
| `NextTrainingStageReviewRequest` | `models.py`；`0022_next_training_stage_review.py` | DEFER/NOT_READY 的最小人工复核接收、回执、审计和通知；不改原决定、不自动重决、不创建 Enrollment | CON-007；BC-001；Minimum Changeset V0.3 |
| `ControlledTaskAuthorization`、`ControlledTaskAuthorizationApproval` + versioned policy snapshot 引用 | `models.py`；`0023_controlled_task_acceptance.py` | 只记录受控任务权限、责任人、范围、版本、有效期、状态、签署和证据 hash；不复制 TaskVersion 内容或治理正文 | MAP-019；BC-002；Minimum Changeset V0.3 |
| `HandoffAcceptance` | `models.py`；`0023_controlled_task_acceptance.py` | Person 对既有 immutable Handoff 的 append-only 一次确认；一对一绑定 handoff，不复制 Outcome/Handoff 结果字段 | BC-001/002；Minimum Changeset V0.3 |
| `ModuleContentPackageBinding` | `models.py`；`0024_module_content_package_binding.py` | 只把已签署的 AI 学院/交付线公会内容包 hash、Owner、Reviewer、SLA 和安全边界绑定到既有 immutable `JourneyVersion/TaskVersion`；不复制 Assignment、Review、Evaluation、Outcome 或 Person 事实 | MAP-027/028；BC-003/004；G9 Build Contract |

当前候选路由包括下一训练阶段复核接收、受控任务授权生命周期和 Handoff 确认。其存在只证明代码候选已经写入脏工作树；本包不授予 schema 执行、数据库写入、真实授权配置、Runtime 启用或发布。最终表、字段、约束和路由必须分别通过 Pro rebase、migration、Runtime 与真人 UAT Gate。

### 3.3 产品需要但 schema 仍未获批的概念

| 概念 | 当前裁决 | 来源 |
|---|---|---|
| 激励积分/徽章账本 | 当前已有 `IncentiveLedgerEntry` 未提交机器候选，但首批奖励规则、字段适用范围和业务 Owner 未批准；不得运行或从旧积分表复制 | MAP-011、020；CON-006；BC-002/004 |
| 公会成员关系 | `APPLIED/ACTIVE/PAUSED/EXITED` 只是 BC-004 候选语义；首批公会和 Owner 未批准前不建表 | MAP-028；BC-004 |
| 认证 Definition/Version、Attempt、Panel、Credential、Appeal | 需要独立 Pro/治理合同；不得复用积分或 AI 分数授证，也不得与 Evaluation/Outcome 重复 | MAP-030；BC-005 |
| RoleProfile/CapabilityDefinition、EvidenceLink、GrowthPlan/Action、VisibilityGrant | 需要 Career Map 产品与可见性合同；EvidenceLink 只能引用权威证据，不能复制原事实 | MAP-031；BC-006 |
| 通用 Human Gate、Appeal、Growth Plan | G1 合同层语义；当前唯一纵切不建立通用平台或第二事实表 | Shared People；G1/G2 Pro 范围 |

## 4. 旧 23 表概念映射（仅供参考）

| 旧概念组 | 旧表 | Journey2.0 参考概念 | 处置 |
|---|---|---|---|
| 学员/预习 | Day0 预习确认、学员档案 | `User`、`Enrollment`、`LearningMaterialCompletion` | 不导入；不复制档案字段；新事实由新流程产生 |
| NPC/权限 | NPC资源、系统用户权限 | `User`、`RoleAssignment`、Reviewer assignment | 不导入；旧角色不授予新权限 |
| 任务/内容 | AI Prompt、任务包、学习路径、月度主题、组织资产、课程资源、任务卡、区域任务源、岗位路线 | `TaskDefinition/Version`、`JourneyVersion/StageVersion` | 只作为需求参考；内容必须由新 Content Owner 重新批准和发布 |
| 提交/点评 | 任务提交与审核、AI月度点评 | `SubmissionVersion`、`Review/Evaluation` | 不导入；旧点评不成为新 Human Gate |
| 积分/兑换/等级 | 积分与徽章、积分兑换、任务兑换审批、等级规则 | 待批准的独立激励账本 | 不导入；不复制规则；不影响能力/人才状态 |
| 能力证据 | 能力证据表 | 对现有 Submission/Evaluation/Outcome 的 Evidence 投影/引用 | 不导入；不建立第二 Evidence 事实表 |
| 阶段/准入 | 阶段评审与分流、项目准入条件、岗位认证规则 | 下一训练阶段决定、ReviewRequest；未来认证合同 | 不导入；旧结论不转成新版准入、认证或人才状态 |

上述映射不包含真实 table ID，不表达字段级对应，也不允许自动生成 DDL。

## 5. 明确废弃或不继承的旧结构

- 旧 23 表作为 Journey2.0 schema 模板；
- 旧学员档案作为 Person SSOT；
- NPC 资源表或系统权限表直接授予新 RBAC；
- AI 自查、点评、积分、徽章、兑换、等级或排行榜直接产生能力/人才状态；
- 阶段分流/项目准入旧值直接回填 `JourneyAdmissionDecision`；
- 旧能力证据表复制为第二 Evidence 账本；
- 旧记录逐条 migration、Legacy migration manifest 和导入 UAT；
- `ImportBatch/ImportRecord` 用于本次 Legacy 正式导入。

`ImportBatch/ImportRecord` 作为通用技术资产是否保留，由后续技术清理 Gate 决定；本裁决只禁止其承载本次 Legacy 导入。

## 6. 数据所有权与状态机

| 聚合 | Owner/写入者 | 允许状态机或不可变规则 | 禁止关系 |
|---|---|---|---|
| Person/Identity | Security/Privacy；授权身份命令 | User `PENDING_IDENTITY→ACTIVE→DISABLED`；身份链接可撤销 | 展示名/外部 subject 不能作跨模块主键 |
| 内容版本 | 业务/Content Owner；发布命令 | Definition `DRAFT→PUBLISHED→WITHDRAWN`；已发布 Version append-only | 旧表字段或机器原型不能自行发布 |
| Enrollment | 运营 Owner；受控命令 | `PENDING_IDENTITY→ACTIVE→COMPLETED/CANCELLED` | 不能由积分/AI自动创建或完结 |
| Assignment | 运营/Reviewer 受控命令 | `AVAILABLE→IN_PROGRESS→SUBMITTED→IN_REVIEW→NEEDS_REVISION→…→COMPLETED`；可取消 | `COMPLETED` 不单独等于 Human PASS |
| SubmissionVersion | Person | append-only，version_no 单调 | 不覆盖旧提交 |
| Review/Evaluation | 指定 Reviewer | Review `ASSIGNED→IN_REVIEW→FINALIZED`；Evaluation append-only并固定 Review scope | 禁止本人自审、AI finalize、客户端自报 Reviewer |
| Outcome/Handoff | 授权业务命令 | immutable；只引用固定 Evaluation/Enrollment | Acceptance 不得回写或复制结果字段 |
| NextTrainingStageDecision | 授权真人决策者 | 新事实 immutable；`READY/DEFER/NOT_READY` 且 scope 仅为下一训练阶段 | 不得复用为录用、淘汰、正式项目准入、晋升或绩效 |
| CTA | 项目/运营/Data-Security/Reviewer approvals | `DRAFT→PENDING_APPROVALS→ACTIVE→EXPIRED/REVOKED`，revision CAS，DB clock | Journey 不执行生产动作；过期/撤销不得 accept |
| ReviewRequest | Person 提交；运营接收 | append-only intake + 受控接收状态 | 不改原决定、不自动重决或建 Enrollment |
| IncentiveLedgerEntry | 对应未来业务 Owner；机器候选当前只允许 append-only/correction | 与 Outcome 单向引用且不产生正式状态 | 首批奖励规则未批；禁止因候选 schema 存在而启用 |
| 公会/认证/Career | 对应未来 Owner | 未批准，不冻结 schema/state machine | 禁止 Codex 自行发明 |

## 7. PII 与审计字段

### 7.1 分类

| 分类 | 典型字段/载体 | 控制 |
|---|---|---|
| 直接 PII | `User.display_name`、外部身份 subject、附件原文件名、提交正文、Reviewer 反馈、Outcome/Handoff 自由文本 | 组织隔离、最小可见、目的限制、保留/删除策略；不得进普通日志或 review manifest |
| 间接/可关联标识 | UUID、assignment/review/evaluation lineage、角色、时间戳、内容/附件 hash | 按人员数据处理；导出只用最小必要引用和脱敏 hash |
| 敏感成长/评价 | Rubric 分数、Evaluation、Outcome、下一阶段决定、申诉 | 仅本人和获授权 Reviewer/Owner；高影响结论必须真人负责且可复核 |
| 安全秘密 | session/token/CSRF hash、外部凭证 | 永不进入本包、Git、Markdown、stdout 或审计正文 |

### 7.2 每个新事实的最小审计列

所有未来新事实至少需要：`id`、`organization_id`、固定主体/来源 FK、`created_at`、`created_by` 或 actor、`revision`（可变聚合）、状态、`request_id`/幂等引用，以及对应 `AuditEntry`/`OutboxEvent`。版本化 policy/evidence 记录 canonical serialization version、content SHA-256 和 evidence reference，不复制外部签署正文。

Append-only/immutable 事实不用 `updated_at` 伪装可变；更正通过新事实、替代引用或 Data Rights 受控流程完成。

## 8. Schema migration 与 rollback 设计

### 8.1 迁移策略

1. 以已提交 Alembic `0019_wp30_invitation_control` 为稳定技术基线；将当前未提交的 `0020`—`0024`、ORM diff 和路由 diff 作为同一待审候选链逐项核对，不能把文件存在写成 migration 已开始或已执行。
2. 候选链只允许 advisory AI provenance、隔离激励账本、独立下一训练阶段决定/复核接收、additive helper UNIQUE/FK、CTA policy snapshot 引用、HandoffAcceptance，以及只引用既有 Journey/Task/User 的 immutable ModuleContentPackageBinding；不得包含 Legacy 数据 INSERT/backfill。
3. 历史 `journey_admission_decisions` 不做枚举或语义重写。新写使用独立 `next_training_stage_decisions`，其 `decision_scope=NEXT_TRAINING_STAGE`；兼容读取保持旧事实和值域原样。
4. Pro rebase 通过后，先做静态 migration/ORM/OpenAPI 一致性复核；migration Gate 另行授权后，才可在空 `journey_next_test.public` 执行 `base→head→down→head`，再用纯合成数据验证组织、Stage/Task/Reviewer 谱系和并发。
5. migration、ORM、OpenAPI 和 Runtime 必须分别过 Gate；本包不批准现有 `0020`—`0024`，也不授权执行、启用或发布。

### 8.2 Rollback

- Runtime 首先 feature-off/关闭新写入口；
- additive migration 在没有新事实时可按独立批准逆序撤销；
- 一旦存在 Acceptance/ReviewRequest/CTA 审计事实，不允许用 downgrade 删除事实，改为 forward fix；
- Outcome/Handoff/SubmissionVersion/Evaluation 不回写、不删除；
- 数据库级恢复只在 §9 全部 Gate 通过的 development/test 环境执行。

`LEGACY_FORMAL_MIGRATION=NOT_REQUIRED`，因此 rollback 不包含 Legacy 导入补偿、记录级回滚或源数据回写。

## 9. Development/Test 数据库清空与重建 Gate

### 9.1 唯一允许候选范围

| 环境 | 显式数据库 | 显式 schema | 本包状态 |
|---|---|---|---|
| development | `journey_next_dev` | `public` | `CLEAR_NOT_AUTHORIZED` |
| test | `journey_next_test` | `public` | `CLEAR_NOT_AUTHORIZED` |
| staging/production | 任何 | 任何 | `CLEAR_PROHIBITED` |

不得以 `$DATABASE_URL`、未解析变量、通配符、容器 volume、目录或宽泛路径作为清空目标。

### 9.2 清空前五项硬证据

1. 数据库返回的显式名称与上表完全一致，且环境分类为 development/test；
2. Data Owner 签署“不含正式业务数据”，并附只读行数/来源审计；
3. 为该精确数据库生成可恢复的 custom-format 备份及 SHA-256；
4. 清空命令文本固定到精确数据库和 `public` schema，并由独立复核人批准；
5. 在独立临时恢复数据库完成 restore、关键表计数/hash 对账和应用 smoke test，结果 `ROLLBACK_REHEARSAL=PASS`。

任一项缺失即 `CLEAR_BLOCKED`。备份存在但未实际恢复，不算 rollback 演练通过。

### 9.3 获批后实施顺序（本轮不执行）

`停写开发服务 → 只读盘点 → 显式数据库备份 → SHA 校验 → 独立恢复演练 → 再次核对精确目标 → 清空 public schema → Alembic base→head → seed 合成数据 → 回归 → 保留恢复点`

生产环境始终禁止清空。开发/test 重建也不能导入 Legacy 记录。

## 10. Gate、风险和下一步

### 已闭合

- Legacy 原 `FAIL` 未覆盖；
- 正式 Legacy migration 与迁入数量固定为 0；
- 旧 23 表与新 schema 解耦；
- Person/Evidence/Human Gate 去重边界保留；
- DB 清空被五项硬证据阻断；本轮未执行；
- 临时飞书应用仅提交撤销清单，未撤销。

### 未关闭

- 本实体清单尚未获 Pro rebase 批准；
- 当前 ORM、未提交 `0020`—`0024`、路由与 OpenAPI 的逐表/逐接口一致性审计未完成；
- CTA/HandoffAcceptance/NextTrainingStageDecision/ReviewRequest/ModuleContentPackageBinding 仍只是未批准机器候选；
- IncentiveLedgerEntry 已有未提交 schema 候选，但业务规则仍待 Owner 批准；公会、认证、Career Map 的具体模型均待对应 Owner/合同批准；
- development/test 数据是否含正式业务数据、备份与恢复演练均 `NOT_RUN`；
- Security/Privacy Owner 尚未确认临时应用撤销清单；
- Runtime、migration、database clear、UAT、release 均未授权。

下一 Gate：`PRO_JOURNEY2_DOMAIN_MODEL_REBASE_REVIEW`。
