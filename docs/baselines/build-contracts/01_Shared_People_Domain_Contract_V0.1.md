# Muchen Journey 共享 People 领域合同 V0.1

> 状态：`G1_PRO_DEDUP_AUDIT_MACHINE_CANDIDATE / PRO_REVIEW_REQUIRED / DATABASE_NOT_MIGRATED`  
> 日期：2026-08-23  
> Owner：`muchen-journey-program-control`  
> 适用模块：BC-001—BC-006  
> 机器合同：`apps/api/journey_api/shared_domain.py`

## 1. 本阶段结果与边界

本合同建立 Person、Evidence、Human Gate、Appeal 和 Growth Plan 的共享语义、状态、权限与迁移草案。它复用现有 `User → Assignment → SubmissionVersion → Review/Evaluation → Outcome` 权威事实链，不创建第二套人员、任务、提交、评价或结果事实源。

本阶段不新增生产连接，不运行数据库迁移，不回填历史数据，不开放新运行时写接口，也不把机器测试结果解释为真人 Gate。后续模块只能引用此合同，不得在模块内定义同名本地事实。

## 2. 共享模型

### 2.1 Person

- `person_id` 固定引用现有 `users.id`；Person 是跨模块引用合同，不是新 Person 表。
- `organization_id` 是全部人员、证据、Gate、申诉与计划的硬隔离边界。
- Person 合同只保留 `organization_id + users.id` 引用；不存在权威 Profile/Cohort 表前，不声明 `profile_revision` 或 `cohort_ids`。
- 模块不得用邮箱、飞书 subject、展示名或本地 learner id 作为跨模块 Person 主键。

### 2.2 Evidence

每条 Evidence 至少固定：Person、组织、模块、授权来源、发生时间、创建者、版本链、AI 使用说明、可见范围、数据等级和保留策略。

权威分类：

- `PRACTICE`：必须固定引用 `TaskVersion + Assignment + SubmissionVersion`；
- `HUMAN_EVALUATION`：必须固定引用现有 `Evaluation`；
- `HUMAN_OBSERVATION`、`SYSTEM_FACT`：只记录获授权且可审计的事实；
- `AI_ADVISORY`：必须记录用途、模型版本和 Prompt 版本，且只能是建议；
- `SELF_ATTESTATION`、`INCENTIVE_LEDGER`：可以保留，但永远不是正式人才状态的充分依据。

Evidence 修订以追加新版本完成；不得覆盖原始提交、Evaluation 或既有 Evidence。

### 2.3 Human Gate

- Gate 固定引用完整 Evidence 集、Rubric 版本、理由、真人签署人与签署时间。
- 被评价者不能签署自己的正式 Gate。
- 正式通过必须至少包含一条 `PRACTICE` Evidence 和一个有效真人 Gate；AI、积分、自证的任意组合都不能替代实操。
- `HIGH_IMPACT_PEOPLE_RESULT` 必须同时提供申诉政策和未来结束的申诉窗口。
- Journey 内的 Gate 不得自动改写录用、晋升、淘汰、薪酬或绩效评级。

### 2.4 Appeal

- 申诉固定引用原 Human Gate，不修改原结论；复核结果追加为独立事实。
- 原 Gate 签署人不得成为该申诉的独立复核人。
- `UPHELD / OVERTURNED / RETURNED_FOR_REVIEW` 必须有独立复核人、理由和时间。
- 申诉结果如需形成替代 Gate，后续必须创建新的 Human Gate 版本并完整引用申诉事实。

### 2.5 Growth Plan

- Growth Plan 必须固定引用 Evidence 与 Human Gate，且至少包含一个可执行行动。
- 版本大于 1 时必须引用被替代版本；旧版本只读保留。
- `CONFIRMED` 必须同时保留 Person 本人确认和一条由授权真人签署的 `GROWTH_PLAN_CONFIRMATION` Gate；任一方都不能代替另一方。
- AI 可以提出行动建议，但必须携带来源说明并保持 `advisory only`。
- 合同不包含自动录用、晋升、绩效或薪酬字段；额外字段会被严格拒绝。

## 3. 任务状态只复用运行模型

G1 不再定义第二套 `FormalWorkStatus`。任务进度只读取现有 `AssignmentStatus`，人工结论只读取 `Review(FINALIZED) + Evaluation.decision`，结果包只读取 `Outcome + Handoff`。是否通过不能由 Assignment 单字段推断：`AssignmentStatus.COMPLETED` 必须结合 completion policy 与 Evaluation 解释。

现有探索营 `LEARNER_EVIDENCE` 直完成功能只表示学习阶段完成，不得映射为人工通过、正式 Evaluation 或人才 Outcome。受控任务仍必须经过 `SubmissionVersion → Review → Evaluation`，但状态转换由现有运行服务和数据库约束负责，不在共享合同复制一份。

## 4. API 草案（尚未开放路由）

所有写命令继续使用 `Idempotency-Key + expected_revision`，所有 GET 无副作用，响应使用现有 request/error 包络。

| Actor | Method / Path | 语义 | 写入条件 |
| --- | --- | --- | --- |
| Person | `GET /api/v1/me/person` | 读取自身共享 Person 引用与最小 Cohort | 本人、同组织 |
| Person | `GET /api/v1/me/evidence` | 按可见范围读取证据账本 | 本人、同组织、游标分页 |
| Assigned Reviewer/Panel | `POST /api/v1/human-gates/{id}/sign` | 对固定 Evidence 集签署 Gate | 已分配、非本人、Rubric 完整 |
| Person | `POST /api/v1/me/appeals` | 对可申诉 Gate 提交申诉 | 本人、窗口有效、幂等 |
| Appeal Reviewer | `POST /api/v1/appeals/{id}/resolve` | 独立复核 | 非原签署人、理由完整 |
| Person/Coach | `POST /api/v1/me/growth-plans` | 建立草案 | 固定 Evidence/Gate 来源 |
| Person | `POST /api/v1/me/growth-plans/{id}/confirm` | 本人确认版本 | 仅本人、expected revision |
| Person | `GET /api/v1/me/growth-plan` | 读取当前版本及历史 | 事实、人工判断、AI 建议分层 |

正式路由接入前必须把 Pydantic 合同纳入 FastAPI OpenAPI，并通过运行时与 `contracts/openapi.json` 零漂移测试。

## 5. 最小权限矩阵

| 资源/动作 | Person | Assigned Reviewer/Panel | Appeal Reviewer | Coach | Operator | Program Controller |
| --- | --- | --- | --- | --- | --- | --- |
| 读 Person | 本人 | 否 | 否 | 否 | 否 | 最小必要范围 |
| 读 Evidence | 本人 | 仅已分配 | 仅已分配 | 否 | 否 | 最小必要范围 |
| 签 Human Gate | 否 | 已分配且非本人 | 否 | 否 | 否 | 否 |
| 提交 Appeal | 本人 | 否 | 否 | 否 | 否 | 否 |
| 解决 Appeal | 否 | 否 | 已分配且非原签署人 | 否 | 否 | 否 |
| 起草 Growth Plan | 本人 | 否 | 否 | 可以 | 否 | 否 |
| 签 Growth Plan 确认 Gate | 否 | 否 | 否 | 已授权且非本人 | 否 | 否 |
| 确认 Growth Plan | 仅本人确认本人一侧 | 否 | 否 | 授权后签确认 Gate | 否 | 否 |

每次敏感读写必须记录组织、Actor、用途、资源、结果和 request id。Program Controller 权限不是超管旁路，仍受目的限制与最小必要原则约束。

## 6. 数据库迁移草案（未执行）

### 6.1 复用，不新建

- Person：复用 `users`、`role_assignments`、未来获批的 Cohort 关系；不建 `people` 镜像表。
- Practice Evidence 来源：复用 `task_versions`、`assignments`、`submission_versions`、附件绑定。
- Human Evaluation 来源：复用 `reviews`、`evaluations`；不复制 Rubric 结论正文。

### 6.2 Pro 去重结论

唯一运行纵切不新建 `people`、`evidence_records`、`human_gate_decisions`、第二套 Assignment/Submission/Review/Evaluation/Outcome 或 Growth Plan 表。Person、Practice Evidence、Human Evaluation 与 Gate 先作为现有权威行的确定性只读投影；投影不得被 API 直接写入或声称已持久化。

只有现有模型无法表达且该纵切不可绕过的事实才可进入后续迁移候选：受控任务六项授权、Handoff 确认及目标 Assignment 谱系、可申诉决定登记。其字段、唯一约束和组织复合外键必须在 Pro 复核后单独批准。

### 6.3 演练顺序

1. 先在空库进行前向迁移、约束测试和备份恢复；
2. 用合成数据验证跨组织、重复签署、并发 finalize、原签署人复核等拒绝路径；
3. 对现有 Evaluation/Outcome 生成只读映射报告，不回填；
4. 由 Data/Security Owner 批准字段等级、保留和删除规则；
5. Pro G1 复核通过后才允许编写 Alembic migration candidate；
6. 历史数据仍需单独审计、分类、quarantine 与只读演练，不能随 schema migration 自动导入。

## 7. G1 机器验收

- `AT-G1-001`：五类严格模型均拒绝未知字段，并能生成 JSON Schema；
- `AT-G1-002`：现有 Assignment/Submission/Review/Evaluation 状态机不能被共享投影绕过或覆盖；
- `AT-G1-003`：Practice Evidence 固定任务、Assignment 与提交版本；
- `AT-G1-004`：AI 使用必须有模型/Prompt/用途说明且只能建议；
- `AT-G1-005`：AI、积分、自证不能形成正式结果；
- `AT-G1-006`：高影响 Gate 必须可申诉，且原签署人不能复核；
- `AT-G1-007`：Growth Plan 版本、本人确认与授权真人确认 Gate 均不可绕过；
- `AT-G1-008`：权限测试覆盖本人、已分配 Reviewer 和独立申诉人职责分离。

## 8. 未关闭 Gate 与风险

- **Pro G1 复核未完成**：模型/API/权限/迁移草案需要 MacBook Pro 做继承一致性和治理校正。
- **Owner/Build Contract 签署仍未完成**：本候选不等于 `APPROVED_FOR_BUILD` 或发布授权。
- **Cohort 权威模型未批准**：Person 目前只保留 Cohort 引用，禁止模块自建成员事实。
- **保留/删除期限未批准**：Evidence/Appeal/Growth Plan 只有策略引用，不能迁移真实数据。
- **Panel 与 Appeal Reviewer 身份映射未落库**：API 接入前需扩展现有角色/授权关系，不能只信客户端 role。
- **既有 `AssignmentStatus.COMPLETED` 与共享 `PASSED` 需适配层**：必须区分学习证据完成、任务通过与正式人才结论。

下一 Gate：`G1_PRO_REVIEW`。通过后进入 G2，只接探索营与新手村的最小纵向闭环；未获真人证据的候选继续冻结，发布与生产变更继续阻断。
