# Muchen Journey G1 共享领域模型去重审计与唯一运行纵切 V0.2

> 状态：`PRO_G1_CORRECTIONS_READY_FOR_REVIEW / RUNTIME_IMPLEMENTATION_NOT_STARTED / G35_PLUS_FROZEN / NO_RELEASE`
>
> 日期：2026-08-24
>
> 分支：`codex/full-module-development`
>
> Pro 裁决：`PRO_G1_DEDUP_AUDIT_PASS / G2_RUNTIME_SLICE_APPROVED_WITH_CORRECTIONS / OPERATIONALIZATION_NOT_APPROVED / NO_RELEASE`
>
> 当前解释：G1—G34 仅为机器合同候选，不是已完成功能或已运营化能力
>
> 本轮边界：只收口 V0.2 文档；未开始 migration、API、页面或数据库实现

## 1. V0.2 裁决摘要

G1 不建立第二套 People 运行域。唯一权威运行事实仍由现有 ORM 承担：

`User → Enrollment → Assignment → TaskVersion → Submission/SubmissionVersion → Review/Evaluation → Outcome/Handoff`

本次 Pro 校正形成五项冻结决定：

1. `JourneyAdmissionDecision` 在本纵切中只表示“下一训练阶段决定”，不表示任何雇佣、正式项目准入、晋升、绩效或其他高影响人才结论。
2. 首批运行接线只保留“探索营人工结果包 → 新手村一个受控任务”这一条纵切；G3—G34 不接入运行表面，G35+ 继续冻结。
3. 受控任务授权改用本文件第 5 节的逐字段冻结表，不再以“六项授权”等概括语句作为实现或验收依据。
4. 屠元琦不得同时成为同一任务的运营者、唯一 Reviewer 和唯一 UAT 签署人；执行 Reviewer、备 Reviewer、独立 UAT 见证人必须由不同职责主体补齐。
5. 当前机器测试和静态证据只证明候选合同可检查，不证明真人签署、真实 UAT、运行接线或发布已完成。

`operationalized_contracts` 继续为空。未经 Pro 复核，不得开始本文件列出的任何运行实现。

## 2. G1 去重结论与权威对象复用

### 2.1 对象复用矩阵

| 领域语义 | 继续复用的权威对象 | V0.2 去重决定 | 不允许新增的重复事实源 |
| --- | --- | --- | --- |
| Person | `User`、`RoleAssignment` | `PersonContract.person_id = users.id`，只读引用 `organization_id + users.id` | `people`、`persons`、模块私有 Person/Profile 表 |
| 地图参与 | `Enrollment` | 每个目标地图只创建一个符合唯一键的 Enrollment | `map_enrollments`、候选合同自带 Enrollment 表 |
| 任务定义与版本 | `TaskDefinition`、`TaskVersion` | 授权绑定一个已发布、不可变的 TaskVersion 及摘要 | 第二份任务正文或可变“授权任务版本” |
| 任务实例 | `Assignment` | 复用 `AssignmentStatus` 与现有 revision；本纵切原子创建一个 Assignment | `FormalWorkStatus`、第二套任务状态机 |
| 学员提交 | `Submission`、`SubmissionVersion`、`SubmissionDraft` | 正式证据只引用固定 SubmissionVersion，不复制提交正文 | `evidence_submissions`、候选 Evidence 正文表 |
| 附件证据 | `Attachment`、`SubmissionVersionAttachment` | 复用扫描、固定版本绑定和访问边界 | 第二套附件或证据文件表 |
| Reviewer 工作 | `Review` | 复用分配、开始、定稿事实 | 通用 Human Gate Review 镜像表 |
| 人工评价 | `Evaluation` | 复用决定、Rubric、理由、Reviewer、时间 | `human_gate_decisions`、候选 Evaluation 表 |
| 探索营结果包 | `Outcome`、`JourneyOutcomeEvidence` | 复用 Outcome 与固定 Evaluation 关联 | 通用 Evidence ledger；`JourneyOutcomeEvidence` 是既有专用关联表，不是本轮新增 |
| 下一训练阶段决定 | `JourneyAdmissionDecision`（仅兼容复用） | 保留同一事实表，增加固定 `decision_scope`，对外改名；不得新建第二张 decision 表 | `next_training_stage_decisions` 与旧表并存 |
| 跨地图交接 | `Handoff` | 复用 Handoff；Person 确认和目标谱系拟直接扩展同一行，不再另建 `handoff_acceptances` | 第二套 Handoff/Acceptance 当前状态表 |
| 审计、幂等、异步通知 | `AuditEntry`、`IdempotencyRecord`、`OutboxEvent`、现有 Notification ORM | 复用，且不放敏感正文 | 模块私有审计、幂等或通知事实表 |
| 申请人工复核 | 本批尚无运行对象 | 仅设计固定于“下一训练阶段决定”的最小 request；不复用 G10/G15/G28/G33 候选为已运行平台 | 通用 Appeal/Panel 平台 |
| Growth Plan | 无运行表 | 本批排除，不创建 | 任何 Growth Plan 运行表或跨图动作表 |

### 2.2 只读共享合同的边界

`PersonContract`、`EvidenceContract`、`HumanGateContract` 以及 `shared_domain_projection.py` 是候选只读解释层，不是 ORM 运行事实：

- Person 只从同组织 `User` 投影；
- PRACTICE Evidence 只从 `TaskVersion + Assignment + SubmissionVersion` 投影；
- HUMAN_EVALUATION Evidence 只从 `Review(FINALIZED) + Evaluation` 投影；
- Human Gate 只从固定 Evidence 集、真人 Evaluation 和签署信息确定性解释；
- 投影不能由客户端提交后直接落库，所有展示必须回读源表并重新验证组织、版本、Reviewer 和证据范围。

因此，本批不新增 Person、Evidence、Human Gate 第二事实表，也不开放这些投影的写 API。

## 3. `JourneyAdmissionDecision` 的唯一允许语义

### 3.1 命名冻结

| 层面 | V0.2 允许名称 | 禁止名称或暗示 |
| --- | --- | --- |
| 中文领域名称 | **下一训练阶段决定** | 正式准入、录用决定、淘汰决定、人才决定 |
| Person 页面展示 | **下一训练阶段安排**；动作使用“查看下一阶段安排”“申请人工复核” | “已录用”“未录用”“淘汰”“晋升”“绩效结论” |
| Operator 页面展示 | **下一训练阶段决定** | “Operator 人工准入”“正式入营决定” |
| API 资源名 | `next-training-stage-decision` | `formal-admission`、`admission-decision` |
| API JSON 字段 | `next_training_stage_decision`、`decision_scope` | `operator_admission`、`admission_decision` |
| 允许的公开决定值 | `READY`、`DEFER`、`NOT_READY` | `ADMIT`、`NOT_ADMIT` 以及任何 hiring/promotion/performance 值 |
| 固定 scope | `NEXT_TRAINING_STAGE` | `EMPLOYMENT`、`PROJECT_ADMISSION`、`PROMOTION`、`PERFORMANCE` 或自由文本 scope |

中文解释固定为：

- `READY`：建议/决定进入下一训练阶段；仍须 Person 主动确认且目标受控任务授权有效，系统不得自动分配。
- `DEFER`：暂缓下一训练阶段；Person 只能申请人工复核，不产生其他人才状态。
- `NOT_READY`：当前未准备好进入下一训练阶段；Person 只能申请人工复核，不产生淘汰、拒聘或绩效后果。

### 3.2 明确禁止语义

该决定不得表示、推导、触发或在页面文案中暗示：

- 录用、拒聘、解聘或淘汰；
- 正式客户项目、正式生产项目或岗位准入；
- 晋升、降级、调薪、奖金或绩效；
- 认证、任职资格、人才盘点或其他高影响人才结论；
- 由 AI、积分、总分、推荐档位或 Person 自证单独产生的正式状态。

如其他系统需要上述结论，必须由其自身的独立政策、证据、权限、真人签署与申诉程序产生；Journey 不得复用本决定代替。

### 3.3 是否继续复用现有对象

V0.2 决定：**继续复用现有 `JourneyAdmissionDecision` 的同一数据库事实，不新建第二张决定表；但在 Pro 批准后的最小 migration 中进行语义收窄。**

兼容策略如下：

1. 在现表增加非空 `decision_scope`，本纵切唯一合法值为 `NEXT_TRAINING_STAGE`；数据库 CHECK 与服务端 enum 同时拒绝其他值。
2. ORM 对外名称改为 `NextTrainingStageDecision` 并继续映射现表；`JourneyAdmissionDecision` 只可作为迁移期内部兼容别名，禁止出现在新 API、页面、审计动作名和业务文档中。
3. 现有 `ADMIT / DEFER / NOT_ADMIT` 数据值按已批准 migration 一次性映射为 `READY / DEFER / NOT_READY`；迁移前不得宣称语义已校正。
4. 每个读写查询都必须显式约束 `organization_id + decision_scope=NEXT_TRAINING_STAGE`；不得提供“任意 scope”接口。
5. 唯一键继续绑定源探索营 Enrollment 与 JourneyVersion；同一作用域不得存在第二个当前决定。后续重审如获批，使用 revision/supersedes 谱系，不覆盖或复制源事实。
6. Audit/Outbox 记录必须包含 `decision_scope`、源 Outcome、真人决定人和决定版本，但不得携带敏感评分正文。
7. API 与页面切换完成前，现有 `/formal-admission`、`operator_admission`、`ADMIT/NOT_ADMIT` 均记为未关闭语义风险，阻塞唯一纵切运行启用。

建议的未来 API 名称为：

- `POST /api/v1/ops/enrollments/{enrollment_id}/next-training-stage-decision/preview`
- `POST /api/v1/ops/enrollments/{enrollment_id}/next-training-stage-decision`
- `GET /api/v1/me/result` 响应字段 `next_training_stage_decision`

本文件只冻结名称和迁移方向，未修改任何现有路由、schema、ORM 或 OpenAPI。

## 4. 唯一运行纵切

### 4.1 首批唯一允许链路

```text
探索营人工结果包
→ Person 查看交接内容
→ Person 主动确认
→ 校验新手村受控任务授权
→ 一个事务内创建一个新手村 Enrollment 和一个 Assignment
→ 复用现有 SubmissionVersion
→ 复用现有 Review / Evaluation
→ Evaluation=APPROVE 后复用现有 Outcome / Handoff
```

这里的 `APPROVE` 是新手村受控任务的真人 Review/Evaluation 通过语义；实际实现应以现有 `Evaluation.decision` 可兼容的值为准，并在 API 契约中避免再造第二套评价状态。

### 4.2 原子创建的必要前置条件

Person 确认事务在写入前必须同时满足：

1. 源探索营 `Outcome + JourneyOutcomeEvidence + Handoff + 下一训练阶段决定` 同组织、同 Person、同 Enrollment，且决定 scope 为 `NEXT_TRAINING_STAGE`、值为 `READY`；
2. 源 Outcome 的 REVIEW_REQUIRED 阶段均有固定 SubmissionVersion、`Review(FINALIZED)` 和真人通过 Evaluation；
3. Handoff 未被确认、未撤销且 revision 与调用方 `expected_revision` 一致；
4. Person 本人发起，身份、CSRF、`Idempotency-Key` 和组织范围有效；Operator 不得代确认；
5. 目标新手村 TaskVersion 已发布且与 ACTIVE 授权的 ID、version、摘要完全一致；授权在有效期内、未撤销，主/备 Reviewer 可用；
6. 目标 Enrollment 和 Assignment 的唯一键尚不存在；重复或并发请求只能回放同一结果；
7. 事务只创建一个 Enrollment、一个 Assignment，并在同一 Handoff 上记录确认与目标谱系，同时写 Audit/Outbox；任一失败全部回滚；
8. Journey 不持有生产凭据、不调用生产写接口、不自动投递产物。

### 4.3 明确排除

首批运行接线排除：

- Growth Plan 运行表、Growth Plan 页面或自动成长动作；
- 通用跨地图入站、统一来源 Resolver 或跨地图框架；
- G3—G34 的 runtime routes、ORM、migration、OpenAPI 或页面接线；
- 认证、Panel、复杂申诉、替换 Panel 或认证注册/Attempt；
- 自动跨图分配；
- 生产作业执行、生产凭据、生产写入或生产数据迁移。

### 4.4 `DEFER / NOT_READY` 的最小人工复核接口

`DEFER` 或 `NOT_READY` 不进入目标 Enrollment/Assignment 事务，只保留以下候选接口设计：

- Person 页面动作：`申请人工复核`；
- API：`POST /api/v1/me/next-training-stage-decisions/{decision_id}/review-requests`；
- 请求字段：`reason`、可选 `evidence_refs[]`、`expected_decision_revision`、`Idempotency-Key`；
- 最小持久化候选：`next_training_stage_review_requests`，只保存 request ID、组织、Person、原决定、理由、证据引用、请求时间、`RECEIVED/CLOSED`、revision；
- 初批只完成接收、回执、审计和通知设计；不实现通用 Appeal、Panel、自动重新决定或自动 Enrollment；
- 原决定人不得成为该请求的唯一复核人。复核流程和 replacement decision 在后续单独 Pro Gate 决定。

## 5. 新手村受控任务授权字段冻结

### 5.1 存储原则

授权只绑定一个已发布 TaskVersion。建议最小持久化为：

- `controlled_task_authorizations`：唯一授权 scope、生命周期与并发事实；
- `controlled_task_authorization_signatures`：对同一 scope 摘要的逐角色、追加式签署元数据；
- 完整签署文件、隐私细则或长篇政策保存在获批准的外部证据库；数据库只保存稳定引用和 SHA-256，不复制全文。

除以上授权事实外，不新增任务正文、Person、Evidence、Review、Evaluation、Outcome 或 Human Gate 表。

### 5.2 精确字段表

| 字段 | 类型/约束 | 保存位置 | ACTIVE 后可变性 | 验收规则 |
| --- | --- | --- | --- | --- |
| `authorization_id` | UUID，PK | 数据库主表 | 不可变 | 全局稳定引用 |
| `organization_id` | UUID，FK/索引 | 数据库主表 | 不可变 | 与项目、TaskVersion、Reviewer、签署人同组织 |
| `authorized_project_ref` | varchar(300) | 数据库主表 | 不可变 | 指向唯一授权项目，不得使用自由文本“任意项目” |
| `project_owner_user_id` | UUID，FK `users.id` | 数据库主表 | 不可变 | 项目 Owner 必须实名且完成对应 scope 签署 |
| `task_version_id` | UUID，FK/UNIQUE `task_versions.id` | 数据库主表 | 不可变 | 只能绑定已发布 TaskVersion |
| `task_version_number` | integer ≥ 1 | 数据库主表 | 不可变 | 与 TaskVersion 当前行一致 |
| `task_version_sha256` | char(64) | 数据库主表 | 不可变 | 覆盖全部可执行内容；读取时重算 |
| `training_purpose` | varchar/text，非空 | 数据库主表 | 不可变 | 只允许训练用途，不得写“生产交付” |
| `allowed_input_schema_ref` | varchar(300) | 数据库主表；完整 schema 外部存证 | 不可变 | 精确列出允许输入字段/附件类型及版本 |
| `allowed_input_schema_sha256` | char(64) | 数据库主表 | 不可变 | 固定外部 schema 内容 |
| `data_classification` | enum | 数据库主表 | 不可变 | 只允许批准的数据等级；默认失败关闭 |
| `deidentification_rule_ref` | varchar(300) | 数据库主表；规则全文外部存证 | 不可变 | 说明删除、替换、聚合和禁止字段 |
| `deidentification_rule_sha256` | char(64) | 数据库主表 | 不可变 | 规则漂移使授权失效 |
| `execution_environment` | 固定 `CONTROLLED_NON_PRODUCTION` | 数据库主表 + CHECK | 不可变 | 其他值拒绝 |
| `production_isolation_rule_ref` | varchar(300) | 数据库主表；边界文档外部存证 | 不可变 | 明确网络、账号、凭据、数据和输出隔离 |
| `production_isolation_rule_sha256` | char(64) | 数据库主表 | 不可变 | 固定隔离边界版本 |
| `prohibited_action_codes` | 受控 enum 数组/关联行 | 数据库主表 | 不可变 | 至少含生产写入、生产凭据、自动发布、代替授权人执行 |
| `learner_visibility` | enum/布尔策略 | 数据库主表 | 不可变 | Learner 只看任务、自己证据、边界与结论 |
| `reviewer_visibility` | enum/策略引用 | 数据库主表 | 不可变 | 仅被分配 Reviewer 看固定 SubmissionVersion 与所需证据 |
| `operator_visibility` | enum/策略引用 | 数据库主表 | 不可变 | Operator 只看运营所需字段，不默认看敏感正文 |
| `primary_reviewer_user_id` | UUID，FK `users.id` | 数据库主表 | 不可变 | 不能等于备 Reviewer；不能是任务/项目 Owner 的唯一自审人 |
| `backup_reviewer_user_id` | UUID，FK `users.id` | 数据库主表 | 不可变 | 必须已接受并具备 Reviewer 角色 |
| `reviewer_substitution_condition_ref` | varchar(300) | 数据库主表；完整规则外部存证 | 不可变 | 列明超时、缺席、冲突和撤回的替补条件 |
| `reviewer_substitution_condition_sha256` | char(64) | 数据库主表 | 不可变 | 替补规则漂移使授权失效 |
| `retention_policy_ref` | varchar(300) | 数据库主表；完整政策外部存证 | 不可变 | 指明法源/内部政策版本 |
| `retention_days` | integer > 0 | 数据库主表 | 不可变 | 与政策一致 |
| `disposition` | `DELETE` 或 `ARCHIVE` | 数据库主表 | 不可变 | 到期动作明确，不允许空值 |
| `legal_hold_allowed` | boolean | 数据库主表 | 不可变 | 仅表示是否可封存，不代表已封存 |
| `valid_from` | timestamptz | 数据库主表 | 不可变 | 不早于最后一份批准签署 |
| `expires_at` | timestamptz | 数据库主表 | 不可变 | 必须晚于 `valid_from` |
| `scope_sha256` | char(64) | 数据库主表 | 不可变 | 覆盖本表所有不可变 scope 字段 |
| `status` | `DRAFT/PENDING_SIGNATURES/ACTIVE/REVOKED/EXPIRED` | 数据库主表 | 仅允许受控状态转换 | 只有完整真人签署、有效期和 scope 校验后可 ACTIVE |
| `revision` | integer ≥ 1 | 数据库主表 | 可递增 | 所有命令要求 `expected_revision`；CAS 失败返回冲突 |
| `created_by/created_at` | UUID + timestamptz | 数据库主表 | 不可变 | 创建审计 |
| `updated_at` | timestamptz | 数据库主表 | 可变 | 每次状态变更更新 |
| `revoked_by/revoked_at/revocation_reason` | UUID + timestamptz + text，可空 | 数据库主表 | ACTIVE 后仅撤销时写一次 | 撤销后不能恢复 ACTIVE；需新 authorization revision |
| `signature_id` | UUID，PK | 数据库签署表 | 不可变 | 逐签署稳定引用 |
| `signer_user_id` | UUID，FK `users.id` | 数据库签署表 | 不可变 | 必须是已认证真人账号 |
| `signer_role` | `PROJECT_OWNER/DATA_SECURITY_OWNER/REVIEWER_OWNER` 等受控 enum | 数据库签署表 | 不可变 | 新手村至少覆盖项目 Owner、Data/Security、Reviewer Owner；不得由 AI/自证代签 |
| `signature_decision` | `APPROVE/REJECT` | 数据库签署表 | 不可变 | 任一 REJECT 阻断 ACTIVE |
| `signed_scope_sha256` | char(64) | 数据库签署表 | 不可变 | 必须等于主表 `scope_sha256` |
| `signed_at` | timestamptz | 数据库签署表 | 不可变 | 不得早于 scope 创建时间 |
| `signature_evidence_ref` | varchar(300) | 数据库签署表；签署原件在外部证据库 | 不可变 | 引用可访问、可核验、受保留策略约束 |
| `signature_evidence_sha256` | char(64) | 数据库签署表 | 不可变 | 防止外部证据静默替换 |

### 5.3 发布后不可变与变更方式

授权进入 `ACTIVE` 后，项目、Owner、TaskVersion、训练用途、输入、数据等级、脱敏、隔离、禁止动作、可见范围、Reviewer、替补条件、保留处置、有效期、scope 摘要和签署均不可原地修改。

允许的运行期变化只有：

- 通过 `expected_revision` 将 ACTIVE 授权撤销或标记过期；
- 写入一次性撤销主体、时间和理由；
- 因内容、人员、规则或有效期变化创建新的 authorization revision，重新计算摘要并重新取得全部真人签署。

替补 Reviewer 实际接管属于按已签署条件发生的 Review 分配事件，不回写授权 scope；若替补人员本身变化，必须新建授权 revision。

## 6. 具名责任、职责分离与 Gate

### 6.1 日期解释

下表沿用《Owner 任命与接受记录 V0.1》中已有的接受/七日 Gate：郑田源、屠元琦本人接受建议截止为 2026-08-25 18:00；刘默文已接受角色的七日结果截止为 2026-08-30。新增待补角色的 2026-08-27/30 日期是 **V0.2 提议，尚待刘默文确认**，不是已被本人接受的承诺。

### 6.2 责任表

| 角色 | 人员 | 首个责任结果 | 接受状态 | 截止日期 | 验收证据 | 未就位时阻塞 |
| --- | --- | --- | --- | --- | --- | --- |
| 产品 Owner | 刘默文 | 签署 V0.2 纵切范围、禁止项、公开名称和最小实现清单 | `ACCEPTED` | 2026-08-30（既有 Gate） | 本人 Pro 复核记录 + V0.2 决议版本 | 所有 migration/API/page 开工 |
| Tech Lead | 刘默文 | 签署单一事实源、事务边界、迁移回滚和不导入 G3—G34 的技术方案 | `ACCEPTED` | 2026-08-30（既有 Gate） | 技术评审记录、迁移 dry-run 方案、路由/模型清单 | 技术实现与候选迁移 |
| Data Owner | 刘默文 | 签署字段分级、外部证据引用、保留/删除/封存和数据质量规则 | `ACCEPTED` | 2026-08-30（既有 Gate） | 数据字典、保留策略签署、零生产数据证明 | 授权表设计与任何数据演练 |
| Security/Privacy | 刘默文 | 签署非生产隔离、脱敏、最小可见范围和禁止动作 | `ACCEPTED` | 2026-08-30（既有 Gate） | 安全/隐私评审记录、负向场景清单 | 首个 TaskVersion 授权与真实 UAT |
| 探索营业务 Owner | 郑田源 | 确认探索营人工结果包、下一训练阶段口径和交接内容版本 | `PENDING_PERSONAL_ACCEPTANCE` | 2026-08-25 18:00 接受；接受后 7 日交付 | 本人接受记录 + 结果包/交接签署 | 源结果包不可作为纵切入口 |
| 新手村运营 Owner | 屠元琦 | 形成一个受控任务运营包、队列、SLA、异常升级和替补触发 | `PENDING_PERSONAL_ACCEPTANCE` | 2026-08-25 18:00 接受；接受后 7 日交付 | 本人接受记录 + 运营 Runbook | 新手村任务不可进入真实 UAT |
| Reviewer/Panel Owner | 屠元琦 | 提交执行 Reviewer 与备 Reviewer 名单、接受证据、校准和冲突检查 | `PENDING_PERSONAL_ACCEPTANCE` | 2026-08-25 18:00 接受；接受后 7 日交付 | 本人接受记录 + Reviewer roster/calibration | Review Gate 不可启用 |
| QA/UAT Owner | 屠元琦 | 冻结真实 UAT 剧本、测试 Person、环境和独立见证人安排 | `PENDING_PERSONAL_ACCEPTANCE` | 2026-08-25 18:00 接受；接受后 7 日交付 | 本人接受记录 + UAT plan | 不能声称真实 UAT 开始或通过 |
| 独立技术/数据复核人 | `待刘默文指定，待本人接受` | 独立复核 migration、约束、事务、数据字典和回滚，不参与实现签署自审 | `VACANT` | 2026-08-27 指定/接受；2026-08-30 首审（提议） | 本人接受 + 独立 review report | migration Gate、数据 Gate |
| 新手村执行 Reviewer | `待屠元琦提名、刘默文确认，待本人接受` | 对首个固定 SubmissionVersion 依 Rubric 完成 Review/Evaluation | `VACANT` | 2026-08-27 指定/接受；UAT 前校准（提议） | 本人接受 + 校准样例 + 首例签署 | 首个受控任务 Review 与 UAT |
| 备 Reviewer | `待屠元琦提名、刘默文确认，待本人接受` | 在已签替补条件触发时接管，且不改写主 Reviewer 原记录 | `VACANT` | 2026-08-27 指定/接受；UAT 前演练（提议） | 本人接受 + 替补演练审计 | 授权不能 ACTIVE、缺席路径 UAT |
| 独立 UAT 见证人 | `待刘默文指定，待本人接受` | 见证 Person、Reviewer、异常和职责分离场景，独立签署事实结果 | `VACANT` | 2026-08-27 指定/接受；2026-08-30 剧本复核（提议） | 本人接受 + witness log + UAT 签署 | 真人 UAT Gate 与任何运营化表述 |
| 首批受控任务项目 Owner | `逐 TaskVersion 待指定，待本人接受` | 对授权项目、训练用途、禁止生产使用和固定 TaskVersion 签署 | `VACANT` | 首个授权进入 PENDING_SIGNATURES 前 | 本人接受 + 项目授权签署证据 | 授权不能 ACTIVE、任务不能分配 |

### 6.3 强制职责分离

- 屠元琦可以担任新手村运营 Owner、Reviewer/Panel Owner 和 QA/UAT Owner，但不能成为同一任务的运营执行者、唯一 Reviewer、唯一 UAT 签署人。
- 首例必须至少有：新手村运营 Owner、执行 Reviewer、备 Reviewer、独立 UAT 见证人；执行 Reviewer 与独立 UAT 见证人不得为同一人。
- 项目 Owner 不能成为自己授权任务的唯一执行 Reviewer。
- 刘默文可承担产品、技术、数据和安全终签，但 migration/数据方案仍须独立技术/数据复核人出具独立记录。
- 沉默、参会、收到文档、机器账号写入或他人代填均不算本人接受。

## 7. Pro 后才可评审的最小运行接线

本节是下一 Gate 的评审清单，不是已开始实现。

### 7.1 最小 migration

1. 复用 `journey_admission_decisions`：新增固定 `decision_scope`，迁移公开决定值，增加 scope/版本约束；不新建第二张决定表。
2. 复用 `handoffs`：增加 Person 确认、目标 Enrollment/Assignment/TaskVersion/Authorization 引用和 revision；不新建 `handoff_acceptances`。
3. 新增 `controlled_task_authorizations` 与 `controlled_task_authorization_signatures`，字段严格按第 5 节；不落外部证据全文。
4. 仅在 Pro 同意 DEFER/NOT_READY 接收能力后新增 `next_training_stage_review_requests`；不得扩成通用 Appeal/Panel schema。
5. 增加原子事务所需唯一键、FK、CHECK 和并发索引；所有迁移先在隔离测试数据库 dry-run/rollback。

### 7.2 最小 API

- Operator：下一训练阶段 preview/decide（改名且固定 scope）；受控任务授权 draft/sign/activate/revoke；
- Person：读取结果包与 Handoff；主动 confirm；DEFER/NOT_READY 时提交最小 review request；
- Reviewer：复用现有 Review 列表、开始、定稿和 Evaluation；
- Ops：只读 Handoff/授权阻塞原因、Reviewer SLA 和 review request 回执；不得代 Person 确认或绕过 Review。

所有新增/改名路由必须先形成 OpenAPI 候选并通过权限、跨组织、并发、幂等和敏感信息负向测试；Pro 与真实 UAT 签署前保持未运营化。

### 7.3 最小页面

- Person 结果页：显示“下一训练阶段安排”、证据来源、决定人/时间、Handoff 内容、主动确认或“申请人工复核”；
- Person 任务页：显示项目、训练用途、数据等级、脱敏、生产隔离、禁止动作、主/备 Reviewer、保留处置和授权有效期；
- Reviewer Workbench：复用现有页面，补固定 TaskVersion/SubmissionVersion、授权摘要、Rubric、隔离边界与替补状态；
- Ops 页面：授权完整性、Handoff 阻塞、Reviewer SLA、复核请求回执；不提供代确认、强制通过或生产执行按钮。

## 8. Reviewer Gate 与真实 UAT

### 8.1 Reviewer Gate

1. 探索营人工结果包：每个 REVIEW_REQUIRED 阶段必须存在固定 SubmissionVersion、独立真人 `Review(FINALIZED)` 和通过 Evaluation；下一训练阶段决定不能替代这些评价。
2. Person 交接：Person 亲自理解并确认；Operator、Reviewer 或自动化不能代替。
3. 受控任务授权：TaskVersion 摘要、有效期、撤销状态、签署摘要和主/备 Reviewer 全部匹配，否则失败关闭。
4. 新手村任务：指定真人 Reviewer 只能对固定 SubmissionVersion 按固定 Rubric 给出返工或批准，理由必填；旧版本、旧 Review 和旧 Evaluation 可追溯。
5. 只有真人批准的 Evaluation 才能复用现有 Outcome/Handoff；Assignment 完成、AI 建议、积分或 Person 自证单独均不能产生正式结果。

### 8.2 真实 UAT 必须形成的证据

| UAT 场景 | 真人参与 | 通过证据 |
| --- | --- | --- |
| 结果包理解与主动确认 | 至少 3 名目标 Person | 3/3 无引导找到内容、复述边界并主动确认；录像/观察记录与本人反馈 |
| 正常通过 | Person + 执行 Reviewer | 一个固定 SubmissionVersion、Finalized Review、批准 Evaluation、Outcome/Handoff 谱系 |
| 返工后通过 | Person + 执行 Reviewer | 两个 SubmissionVersion、两轮 Review/Evaluation；旧版不可覆盖 |
| DEFER/NOT_READY | Person + 非原决定人接收 | “申请人工复核”可发现、可提交、可回读；不自动改变决定或创建 Enrollment |
| 主 Reviewer 缺席 | 备 Reviewer + 运营 Owner | 已签替补条件命中、权限切换、SLA、Audit/Outbox 正确 |
| 并发/重复确认 | Person + QA | 同一幂等结果，仅一个 Enrollment、一个 Assignment，半失败全回滚 |
| 过期/撤销/内容漂移 | QA + Data/Security | 过期授权、撤销授权、TaskVersion 摘要漂移全部拒绝 |
| 跨组织和最小可见范围 | 不同角色账号 | Learner/Reviewer/Operator 越权读取和客户端伪造全部拒绝 |
| 生产隔离 | Security/Privacy + 独立见证人 | Journey 凭证不能写生产系统；无生产数据、凭据或自动投递 |
| 响应式和可访问性 | 真实 Person/Reviewer + 独立见证人 | 390/768/1280、键盘、触控、错误、加载、重进均有事实记录 |
| 恢复与留存 | Tech/Data + 独立复核人 | 隔离库备份恢复、rollback、幂等重放、删除/封存 dry-run 记录 |

机器测试不得填写“真人通过”。当前 `human_validation=NOT_RUN`，`real_uat_run=false`。

## 9. 去重与未接线证据

### 9.1 删除位置与对应测试

| 校正 | 当前代码位置/删除位置 | 当前对应机器测试 | 证据结论 |
| --- | --- | --- | --- |
| 删除 `FormalWorkStatus`、`FORMAL_WORK_TRANSITIONS`、`require_formal_work_transition` | `apps/api/journey_api/shared_domain.py`：`JourneyModuleKey` 结束于第 23 行，随后第 26 行直接进入 `PersonContract`；全仓运行代码搜索 0 命中 | `test_g2_synthetic_loop_preserves_revision_and_human_gate_without_formal_promotion`；`test_formal_result_accepts_practice_evidence_and_a_human_signature`；`test_needs_revision_gate_cannot_create_a_formal_result` | 任务状态复用 `AssignmentStatus`，正式通过依赖 Submission/Review/Evaluation，不保留第二状态机 |
| 删除 `PersonContract.profile_revision` 与 `cohort_ids` | `apps/api/journey_api/shared_domain.py:26` 的 `PersonContract` 仅含 `contract_version/organization_id/person_id/source`；字段止于第 32 行 | `test_person_contract_reuses_user_as_the_only_person_source`；`test_contracts_are_strict_machine_readable_schemas` | Person 只引用 `users.id`，多余字段因 strict/extra=forbid 不能进入合同 |
| 不新增 Person/Evidence/Human Gate ORM | `apps/api/journey_api/models.py` 与 `migrations/versions/0001...0019` | `test_practice_evidence_requires_fixed_task_assignment_and_submission_versions`；`test_human_gate_cannot_be_self_signed`；`test_ai_self_attestation_and_points_cannot_create_formal_results` | 只有 Pydantic 只读投影；既有 `JourneyOutcomeEvidence` 保持 Outcome↔Evaluation 专用关联 |

历史测试名 `test_formal_work_requires_submission_and_review_before_pass` 随重复状态机删除，不应继续作为当前测试证据。V0.2 使用上表中的现有测试证明源事实链与真人 Gate；本轮未新增或改写测试。

### 9.2 当前复用 ORM 清单

当前纵切继续复用：

- 身份与权限：`User`、`RoleAssignment`；
- 旅程与任务：`JourneyDefinition`、`JourneyVersion`、`JourneyStageVersion`、`Enrollment`、`TaskDefinition`、`TaskVersion`、`Assignment`；
- 提交与附件：`Submission`、`SubmissionVersion`、`SubmissionDraft`、`Attachment`、`SubmissionVersionAttachment`；
- 人工审查与结果：`Review`、`Evaluation`、`Outcome`、`JourneyOutcomeEvidence`、`JourneyAdmissionDecision`（待 scope 校正）、`Handoff`；
- 控制面：`AuditEntry`、`OutboxEvent`、`IdempotencyRecord`、`NotificationDelivery`、`NotificationEndpoint`、`NotificationAttempt`。

### 9.3 没有第二事实表的静态证明

2026-08-24 的只读检查：

```bash
rg -n "class (Person|Evidence|HumanGate)|__tablename__.*(people|persons|evidence_records|human_gates|human_gate_decisions)" \
  apps/api/journey_api/models.py migrations
```

结果：`0 matches`。`JourneyOutcomeEvidence` 在既有 `models.py` 和 `0015_wp19_formal_journey.py` 中存在，职责只是一对固定 Outcome/Evaluation/Stage 的关联；本轮没有新增 Person、通用 Evidence 或 Human Gate 表、migration 或写路由。

### 9.4 G3—G34 未进入 runtime 的静态证明

检查范围：

- `apps/api/journey_api/main.py`
- `routes.py`、`submission_routes.py`、`identity_routes.py`、`review_routes.py`、`outcome_routes.py`、`ops_routes.py`、`oauth_routes.py`、`content_routes.py`
- `apps/api/journey_api/models.py`
- `migrations/versions/*.py`
- `contracts/openapi.json`

结果：

1. `main.py` 只注册上述既有八组 router；未注册 G3—G34 候选 router。
2. 对 G3—G34 候选模块名（`career_*`、`certification_*`、`stage_entry_*`、`appeal_continuity`、`controlled_task_authorization` 等）在上述运行入口、ORM、迁移和 OpenAPI 中搜索为 `0 matches`。
3. OpenAPI 未出现 `/appeals`、`/certifications`、`/career`、`/growth-plans` 或 `/stage-entries` 运行路径。
4. 候选 Python 文件、Build Contract、config 登记、outputs 与 tests 的存在只表示机器合同候选；它们不等于 runtime import、数据库迁移、API 暴露或页面可用。

### 9.5 已记录机器结果与本轮文档检查

`outputs/controller-integration/shared-people-domain-g1/pro-dedup-audit.json` 记录的上一轮机器结果：

- G1/G2 及相邻候选回归：153 passed；
- API 隔离测试库：1481 passed，5 skipped；
- Web Node tests：40 passed；
- Web typecheck、ESLint、production build：PASS；
- OpenAPI unchanged：PASS；
- product doctor/contract：PASS；`production_mutation_executed=false`。

这些是机器结果，不是本轮重新执行的运行 UAT，也不是任何真人签署。V0.2 本轮只执行 Markdown/引用/静态搜索和 `git diff --check`；真人验证、Pro 复核、运行实现、生产访问均未进行。

## 10. 未关闭风险

1. 当前运行代码和 OpenAPI 仍使用 `formal-admission`、`operator_admission`、`ADMIT/NOT_ADMIT`；语义校正尚未实现，唯一纵切不得启用。
2. `decision_scope`、Handoff 确认字段、受控授权表和最小 review request 均未迁移。
3. 郑田源、屠元琦尚无本人接受记录；四个新增独立角色及首批项目 Owner 均未就位。
4. 没有真实受控项目、固定 TaskVersion、真人授权签署、执行 Reviewer/备 Reviewer 校准或独立 UAT 见证证据。
5. G1—G34 候选仍存在宽泛模型和测试资产；它们虽未进入 runtime，但必须保持冻结，避免被误导入。
6. config 中历史并行工作流登记不能解释为恢复横向开发；`pro_audit_control` 和本次 Pro 裁决优先约束当前阶段。
7. 未运行真实 UAT，未访问生产数据，未验证生产外部系统隔离事实。

## 11. 下一 Gate 与停止条件

下一 Gate：`PRO_G1_V0_2_CORRECTION_REVIEW_AND_MINIMUM_RUNTIME_CHANGESET_APPROVAL`

Pro 复核至少必须明确：

- 是否批准本文件的下一训练阶段命名、`decision_scope` 与旧值迁移策略；
- 是否批准直接扩展现有 Handoff，而不是新增 Acceptance 状态表；
- 是否批准第 5 节授权字段、签署证据引用和 ACTIVE 后不可变规则；
- 是否确认新增角色、提议日期和职责分离；
- 是否批准第 7 节最小 migration/API/page 清单及真实 UAT 剧本。

Gate 通过前停止：不进入 migration、API、页面或数据库实现；不新增 G35+ 合同；不继续横向扩展领域模型；不提交、不合并、不打标签、不部署；不访问或迁移生产数据；不把机器测试写成真人通过；不把 G1—G34 称为已完成功能。
