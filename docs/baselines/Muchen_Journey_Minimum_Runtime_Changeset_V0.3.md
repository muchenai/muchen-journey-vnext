# Muchen Journey Minimum Runtime Changeset V0.3

> 状态：`PRO_CORRECTIONS_V0_3_READY_FOR_REVIEW / RUNTIME_NOT_RUN / DATABASE_AUDIT_NOT_RUN / MIGRATION_NOT_RUN / UAT_NOT_RUN / G3_PLUS_FROZEN / NO_RELEASE`
>
> 日期：2026-08-24
>
> 分支：`codex/full-module-development`
>
> 基线：`Muchen_Journey_Minimum_Runtime_Changeset_V0.2.md`
>
> 下一 Gate：`PRO_MINIMUM_RUNTIME_CHANGESET_V0_3_REVIEW`
>
> 本轮边界：只新增本 V0.3 设计文档；V0.2 及其他既有文件保持不变；未创建 migration，未写 Runtime，未修改数据库/API/页面/OpenAPI，未访问生产数据，未提交、合并或部署

## 1. 定向修正结论

V0.3 继承 V0.2 已冻结且未被本轮退回的全部内容，只关闭三个谱系缺口：

1. `ControlledTaskAuthorization`（下称 CTA）同时固定 JourneyVersion、JourneyStageVersion 和 TaskVersion；Acceptance 通过 Enrollment 与 Assignment 的复合键证明三者属于同一运行链。
2. Acceptance 固定 CTA 的 primary Reviewer；Enrollment 固定同一 Reviewer；后续 Review 只能从该 Enrollment 的 `reviewer_id` 创建。
3. `ACTIVE` 授权过期由使用数据库时钟、行锁和 revision CAS 的原子命令收敛；activate、expire 与 accept 不依赖客户端时间或定时任务最终一致。

V0.2 的 Legacy 决定非破坏性读取、Outcome/Handoff 不可变、最小人工复核请求、policy canonical serialization、Owner 分离和唯一运行纵切继续有效。本文件不新增产品对象、地图或通用框架。

唯一纵切仍为：

```text
探索营人工 Outcome/Handoff
→ NEXT_TRAINING_STAGE 真人 READY 决定
→ Person 主动 Acceptance
→ 一个新手村 Enrollment + 一个非 NULL JourneyStageVersion 的 Assignment
→ 现有 SubmissionVersion → 指定 Reviewer 的 Review/Evaluation → Outcome/Handoff
```

Journey 不执行生产作业；AI、积分或自证不能单独产生正式结果或下一训练阶段决定。

## 2. V0.3 修正后的谱系键

### 2.1 字段增量

V0.2 其余字段不变；只增加或修正下列字段：

| 表 | 字段 | 类型/空值 | 语义 |
| --- | --- | --- | --- |
| `controlled_task_authorizations` | `target_journey_stage_version_id` | UUID `NOT NULL` | 被授权的新手村 JourneyStageVersion；与目标 JourneyVersion、TaskVersion 构成一个不可变 scope |
| `controlled_task_authorizations` | `expired_by_user_id` | UUID nullable | 执行 expire 的真人或获批系统 actor；仅 EXPIRED 非空 |
| `controlled_task_authorizations` | `expired_at` | timestamptz nullable | expire 原子命令使用的 `db_now`；仅 EXPIRED 非空 |
| `handoff_acceptances` | `target_journey_stage_version_id` | UUID `NOT NULL` | 必须等于 CTA stage 及目标 Assignment stage |
| `handoff_acceptances` | `target_reviewer_user_id` | UUID `NOT NULL` | 必须等于 CTA `primary_reviewer_user_id` 和 Enrollment `reviewer_id` |

CTA 的 immutable scope、business version、partial ACTIVE scope 和 canonical hash 输入都加入 `target_journey_stage_version_id`。Reviewer 是授权内容的一部分，但不进入 ACTIVE partial UNIQUE 的 scope key：同一 Stage/Task 不得通过更换 Reviewer 并存两条 ACTIVE 授权；更换 Reviewer 必须新建 authorization version。

冻结后的授权 scope key 为：

```text
(organization_id,
 target_journey_version_id,
 target_journey_stage_version_id,
 task_version_id)
```

V0.2 §7 的 policy snapshot schema、RFC 8785 serialization、UTF-8/NFC 和 policy snapshot hash 本身不变。只修正 Authorization `scope_sha256` 的输入 object：在 `target_journey_version_id` 后加入必需 string key `target_journey_stage_version_id`，值为 lowercase canonical UUID；其后仍为 `task_version_id`、`task_version_sha256`。由于该 scope hash 尚未实现、迁移或承载数据，domain prefix 继续使用 V0.2 已冻结的 `muchen-journey-controlled-task-authorization-scope.v1\n`；V0.3 实现前必须重算并冻结新的 scope golden vector，旧的无 Stage 输入不得被接受。若发现任何环境已经生成 V0.2 scope hash，必须停止 migration 并返回 Pro 决定是否升级 prefix，而不是静默重算。

### 2.2 闭合键链

```text
CTA
  ├─ (Stage, Org, Journey, Task) ──FK──> JourneyStageVersion
  └─ primary Reviewer
          │
Acceptance
  ├─ (Enrollment, Org, Person, Journey, Reviewer) ──FK──> Enrollment
  ├─ (Assignment, Org, Enrollment, Stage, Task) ──FK──> Assignment
  └─ (CTA, Org, Journey, Stage, Task, Reviewer) ──FK──> CTA

Review.reviewer_id
  ──constraint trigger──> Assignment.enrollment_id → Enrollment.reviewer_id
```

由此可在数据库层证明：被接受的授权、目标 Journey、Stage、Task、Enrollment、Assignment、Learner 和 primary Reviewer 属于同一个 organization、同一条谱系。Acceptance 不复制 Outcome/Handoff 结果字段。

## 3. 逐表 DB 可执行约束增量矩阵

下列内容替换 V0.2 §4.1、§4.3、§4.5 中涉及 Stage、Reviewer 和过期生命周期的相应行；未列出的 V0.2 PK、UNIQUE、CHECK、复合 FK 和 immutable trigger 全部继承。名称是供后续 Pro 批准后转写 PostgreSQL/Alembic 的冻结候选，本轮没有执行 DDL。

### 3.1 既有表辅助约束

| 表 | 类型 | 约束/触发器名 | 可执行语义 | 作用 |
| --- | --- | --- | --- | --- |
| `journey_stage_versions` | UNIQUE | `uq_jsv_acceptance_lineage` | `UNIQUE (id, organization_id, journey_version_id, task_version_id)` | CTA 一次证明 Stage 属于 Journey 且绑定 Task |
| `enrollments` | UNIQUE | `uq_enrollments_acceptance_lineage` | `UNIQUE (id, organization_id, learner_id, journey_version_id, reviewer_id)` | Acceptance 一次绑定 Person、Journey 和 primary Reviewer |
| `assignments` | UNIQUE | `uq_assignments_acceptance_lineage` | `UNIQUE (id, organization_id, enrollment_id, journey_stage_version_id, task_version_id)` | Acceptance 一次绑定 Enrollment、Stage 和 Task |
| `assignments` | constraint trigger | `ct_assignment_journey_lineage_guard` | `AFTER INSERT OR UPDATE`；trigger function 在 UPDATE 谱系键未变化时立即返回；否则若 Enrollment 的 `journey_version_id IS NOT NULL`，要求 Assignment stage 非空，并存在相同 `(stage.id, org, enrollment.journey_version_id, assignment.task_version_id)`；失败抛错 | 普通 FK 无法跨 Assignment→Enrollment→Stage 比较 Journey；不把 JourneyVersion 复制进 Assignment |
| `reviews` | constraint trigger | `ct_review_enrollment_reviewer_guard` | `AFTER INSERT OR UPDATE`；trigger function 在 UPDATE 的 org/assignment/reviewer 均未变化时立即返回；否则读取 Assignment→Enrollment 并要求 `reviews.reviewer_id=enrollments.reviewer_id`；相关行 `FOR KEY SHARE` | 普通 FK 无法沿 Assignment 跨表比较 Reviewer；后续纯状态 UPDATE 快速返回 |

辅助 UNIQUE 创建前必须在获批只读数据库审计中验证无重复。它们不改写历史行。`ct_assignment_journey_lineage_guard` 只对新 INSERT 或被修改的谱系键执行：历史 `journey_stage_version_id IS NULL` 行不会被 backfill，也不会因普通状态变更被触发。其明确规则是：凡新建 Assignment 所属 Enrollment 已绑定 JourneyVersion，`journey_stage_version_id` 必须非 NULL；当前唯一纵切创建的 Enrollment 必定绑定 JourneyVersion，因此 NULL Stage 在数据库命令内失败。

现有 `journey_stage_versions(id, organization_id)`、`enrollments(id, organization_id, learner_id)` 等约束不删除；V0.3 辅助键是更强的 FK target。

### 3.2 `controlled_task_authorizations`

| 类型 | 约束/触发器名 | V0.3 可执行语义 |
| --- | --- | --- |
| UNIQUE | `uq_cta_acceptance_lineage` | `UNIQUE (id, organization_id, target_journey_version_id, target_journey_stage_version_id, task_version_id, primary_reviewer_user_id)` |
| UNIQUE | `uq_cta_stage_business_version` | `UNIQUE (organization_id, target_journey_version_id, target_journey_stage_version_id, task_version_id, authorization_version)` |
| partial UNIQUE | `uq_cta_one_active_stage` | `UNIQUE (organization_id, target_journey_version_id, target_journey_stage_version_id, task_version_id) WHERE status='ACTIVE'` |
| CHECK | `ck_cta_expiration_audit` | `status='EXPIRED'` 当且仅当 `expired_by_user_id`、`expired_at` 非空；非 EXPIRED 时二者均为空 |
| CHECK | `ck_cta_expiration_time` | EXPIRED 时 `expired_at >= expires_at`；命令和 trigger 另以 DB clock 判定 |
| Stage+组织+Journey+Task 复合 FK | `fk_cta_stage_lineage` | `(target_journey_stage_version_id, organization_id, target_journey_version_id, task_version_id) → journey_stage_versions(id, organization_id, journey_version_id, task_version_id)` |
| 组织复合 FK | `fk_cta_expired_by_scope` | nullable `(expired_by_user_id, organization_id) → users(id, organization_id)`；系统 actor 也必须是组织内受控服务身份 |
| mutation trigger | `trg_cta_guard_mutation` | 在 V0.2 规则上加入：Stage 是 immutable scope；只允许 `ACTIVE→EXPIRED` 且 `NEW.revision=OLD.revision+1`；EXPIRED 转换必须满足 `clock_timestamp() >= OLD.expires_at`，并固定 expired actor/time |
| activation constraint trigger | `ct_cta_activate_guard` | 在 V0.2 四角色/证据/有效期校验上加入 `fk_cta_stage_lineage` 已有效；激活时 `valid_from <= db_now < expires_at` |

V0.2 的 `uq_cta_acceptance_ref`、`uq_cta_task_business_version` 和 `uq_cta_one_active_task` 被上面三个含 Stage 的约束取代，不与其并存。`fk_cta_target_journey_scope` 与 `fk_cta_task_scope` 可保留为直接组织 FK，但不能替代更强的 `fk_cta_stage_lineage`。

允许状态转换仍为：

```text
DRAFT → PENDING_APPROVALS → ACTIVE ──→ REVOKED
                               └─────→ EXPIRED
```

其中图意为 ACTIVE 可转 REVOKED 或 EXPIRED；REVOKED、EXPIRED 都是 terminal。本批不新增恢复、续期或 EXPIRED→ACTIVE。

### 3.3 `handoff_acceptances`

| 类型 | 约束/触发器名 | V0.3 可执行语义 |
| --- | --- | --- |
| PK/UNIQUE/CHECK | 继承 V0.2 | `id` PK；Handoff、Enrollment、Assignment 各自一对一；decision scope 固定且只接 READY；append-only |
| Authorization 完整谱系复合 FK | `fk_ha_authorized_lineage` | `(controlled_task_authorization_id, organization_id, target_journey_version_id, target_journey_stage_version_id, target_task_version_id, target_reviewer_user_id) → controlled_task_authorizations(id, organization_id, target_journey_version_id, target_journey_stage_version_id, task_version_id, primary_reviewer_user_id)` |
| Enrollment 完整谱系复合 FK | `fk_ha_target_enrollment_lineage` | `(target_enrollment_id, organization_id, accepted_by_user_id, target_journey_version_id, target_reviewer_user_id) → enrollments(id, organization_id, learner_id, journey_version_id, reviewer_id)` |
| Assignment 完整谱系复合 FK | `fk_ha_target_assignment_lineage` | `(target_assignment_id, organization_id, target_enrollment_id, target_journey_stage_version_id, target_task_version_id) → assignments(id, organization_id, enrollment_id, journey_stage_version_id, task_version_id)` |
| constraint trigger | `ct_ha_authorization_guard` | INSERT 时锁定 CTA；以同事务 DB clock 要求 status ACTIVE 且 `valid_from <= db_now < expires_at`，并复核 revision/hash/Stage/Reviewer；失败则 Enrollment、Assignment、Acceptance、Audit、Outbox 全回滚 |
| immutable trigger | `trg_ha_reject_mutation` | `BEFORE UPDATE OR DELETE` 始终抛错 |

V0.2 的三个较弱 FK `fk_ha_authorized_target`、`fk_ha_target_enrollment`、`fk_ha_target_assignment` 被上述三个完整谱系 FK 取代。Handoff owner 与 READY decision 两条 V0.2 复合 FK 原样保留。

### 3.4 `reviews`

Review 不新增 Enrollment 或 Reviewer 副本字段。Review 创建命令必须：

1. 从目标 Assignment 读取 `enrollment_id`；
2. 从该 Enrollment 读取 `reviewer_id`；
3. 以此值写 `reviews.reviewer_id`，API body 不接受调用方自报 Reviewer；
4. `ct_review_enrollment_reviewer_guard` 再在数据库层检查实际写入值；
5. 后续 Evaluation 继续复用现有 Review→Reviewer 复合约束，不另建 Reviewer 事实。

如果 Reviewer 需要替补，不得直接把 Review 指给 CTA backup Reviewer。本 changeset 未授权 Reviewer replacement；必须经后续独立 Pro Gate 产生新的授权/Enrollment 处理规则。

### 3.5 为什么部分规则使用 trigger 或带锁命令

| 规则 | 普通 FK/CHECK 的限制 | 冻结机制 |
| --- | --- | --- |
| Assignment 的 Stage 同时属于 Enrollment Journey 且绑定 Assignment Task | Assignment 没有、也不应复制 `journey_version_id`；普通 FK 不能跨 Enrollment 再比较 Stage | `ct_assignment_journey_lineage_guard` + Acceptance→Assignment 完整复合 FK |
| Review Reviewer 等于 Enrollment Reviewer | Review 只有 Assignment FK；普通 FK 不能跨 Assignment 比较 Enrollment 列 | `ct_review_enrollment_reviewer_guard`；Review command 从 Enrollment 派生值 |
| Acceptance 时 CTA 仍 ACTIVE 且未过期 | status 可变，当前时间不适合作稳定 CHECK | CTA `FOR UPDATE` + 单次 DB `clock_timestamp()` + `ct_ha_authorization_guard` |
| ACTIVE 自动到时后给新版本让出 partial UNIQUE | PostgreSQL partial UNIQUE 不会因时间流逝改 predicate；客户端或 scheduler 可能延迟 | activate 在同 scope 锁内先原子 expire 旧行，再激活新行 |
| 并发 activate 两个版本 | 两条候选行之间没有天然共享行锁 | scope advisory transaction lock + scope 行按固定顺序 `FOR UPDATE` + partial UNIQUE 最终兜底 |

## 4. Acceptance 原子事务 V0.3

### 4.1 请求与服务器派生值

`POST /api/v1/me/handoffs/{handoff_id}/accept` 的未来候选请求在 V0.2 输入上增加：

- `expected_target_journey_stage_version_id`；
- 继续携带 `expected_target_journey_version_id`、`expected_target_task_version_id`、`expected_authorization_revision`、decision ID、authorization ID 和 `Idempotency-Key`；
- 不接受 `learner_id` 或 `reviewer_id` body 字段。Person 从认证上下文取得，Reviewer 从锁定的 CTA `primary_reviewer_user_id` 取得。

### 4.2 固定锁顺序

未来 accept command 必须固定按下列顺序；不得由调用方改变：

1. 幂等 advisory transaction lock；检查 `idempotency_records`；
2. Handoff `FOR UPDATE`；
3. NEXT_TRAINING_STAGE decision `FOR KEY SHARE`；
4. CTA `FOR UPDATE`；activate、expire、revoke 都以同一 CTA 行锁串行；
5. JourneyVersion、JourneyStageVersion、TaskVersion 按表顺序 `FOR KEY SHARE`；
6. Person、primary Reviewer、backup Reviewer 按 UUID 升序 `FOR KEY SHARE`；
7. 可能已存在的 Enrollment、Assignment、Acceptance 按此顺序 `FOR UPDATE`；
8. 所有锁取得后只调用一次 `SELECT clock_timestamp() AS db_now` 并完成最后校验与写入。

持有 CTA 行锁直到 COMMIT，因此 accept 与 expire/revoke/activate 对同一授权不能穿越彼此的有效性判定窗口。

### 4.3 写入与回滚

同一事务内：

1. 复核 Handoff owner、READY decision、CTA revision/hash 和完整 Journey/Stage/Task/Reviewer 谱系；
2. 要求 CTA `ACTIVE` 且 `valid_from <= db_now < expires_at`；`db_now >= expires_at` 即使 status 尚为 ACTIVE 也拒绝 Acceptance；
3. INSERT 一个 Enrollment：JourneyVersion=CTA target Journey，learner=本人，reviewer=CTA primary Reviewer；
4. INSERT 一个 Assignment：Enrollment=上一步，JourneyStageVersion=CTA target Stage，TaskVersion=CTA Task，`journey_stage_version_id NOT NULL`；
5. INSERT HandoffAcceptance，写入同一 Journey/Stage/Task/Reviewer 键；
6. INSERT Audit、Outbox、IdempotencyRecord；
7. COMMIT。任一步失败全部 ROLLBACK。

Acceptance append-only；后续授权 EXPIRED/REVOKED 不修改已有 Acceptance，也不修改 Outcome/Handoff。

## 5. ACTIVE 过期原子生命周期

### 5.1 唯一时间权威

所有 accept、activate、expire、revoke 的有效期判断只使用锁取得后的数据库时间：

```sql
SELECT clock_timestamp() AS db_now;
```

客户端时间、API 主机时间、消息时间、定时任务触发时间只能用于观测，不能决定授权有效性。定时任务可以调用相同 expire command 做卫生清理，但系统正确性不得依赖其最终一致。

### 5.2 expire 命令与入口

未来最小入口冻结为：

```text
POST /api/v1/ops/controlled-task-authorizations/{authorization_id}/expire
internal command: expire_controlled_task_authorization(
  organization_id,
  authorization_id,
  expected_revision,
  idempotency_key,
  actor_user_id
)
```

入口只允许获批 Operations/Data-Security 管理权限或受控内部服务身份；不能由 Person 接口调用。内部定时器若存在，也必须调用同一命令并提供受控 actor 与幂等键。

固定事务：

1. 取得命令幂等 advisory lock；相同 key+payload 回放既有响应，不重复 Audit/Outbox；
2. 只读取得 CTA immutable scope key；取得 `pg_advisory_xact_lock(hash(organization_id, journey, stage, task))`；
3. `SELECT ... FROM controlled_task_authorizations WHERE id=:id AND organization_id=:org FOR UPDATE`；
4. 比较 `revision=:expected_revision`；锁后执行一次 `clock_timestamp()`；
5. 若 status=ACTIVE 且 `db_now >= expires_at`，CAS 更新为 EXPIRED、`revision=revision+1`、`expired_by_user_id=actor`、`expired_at=updated_at=db_now`；
6. 同事务写一条 Audit 和一条不含敏感正文的 Outbox event `controlled_task_authorization.expired`；
7. 写 IdempotencyRecord 并 COMMIT；任一步失败全部 ROLLBACK。

结果语义：

| 当前事实 | 结果 |
| --- | --- |
| ACTIVE 且 `db_now >= expires_at`，revision 匹配 | 200；EXPIRED、revision+1、Audit/Outbox 各一条 |
| ACTIVE 但 `db_now < expires_at` | 409 `AUTHORIZATION_NOT_EXPIRED`；零写入 |
| revision 不匹配 | 409 `AUTHORIZATION_REVISION_CONFLICT`；零写入 |
| REVOKED | 409 `AUTHORIZATION_REVOKED`；不得改为 EXPIRED |
| 已 EXPIRED，相同幂等键/请求 hash | 200 replay；不重复事件 |
| 已 EXPIRED，不同幂等键 | 409 `AUTHORIZATION_ALREADY_EXPIRED`，响应返回当前 revision；零写入 |

### 5.3 activate 命令对旧 ACTIVE 的处理

activate 使用和 expire 相同的 authorization scope advisory lock。取得 scope lock 后，按 `(authorization_version, id)` 升序将该 scope 全部 CTA 行 `FOR UPDATE`，再取一次 `db_now`：

1. 候选必须为 `PENDING_APPROVALS`、revision 匹配、批准齐全，且 `valid_from <= db_now < expires_at`；
2. 如果旧 ACTIVE 存在且 `db_now < old.expires_at`，返回 409 `ACTIVE_AUTHORIZATION_EXISTS`；
3. 如果旧 ACTIVE 存在且 `db_now >= old.expires_at`，在同一事务先执行与 §5.2 相同的 EXPIRED CAS、revision+1、Audit/Outbox；
4. 旧行成功变为 EXPIRED 后，再把候选改为 ACTIVE、revision+1，并写 activation Audit/Outbox；
5. partial UNIQUE `uq_cta_one_active_stage` 最终兜底；任一步失败时旧行 expire 与新行 activate 一起 ROLLBACK。

本纵切选择“activate 同事务先 expire 旧行”，不要求运营者先发独立 expire 请求。独立 expire 入口仍用于显式清理和审计。无论哪条入口，实际状态变化都走同一数据库函数/命令内核，不允许复制两套时钟或转换逻辑。

### 5.4 并发线性化结果

| 并发场景 | 锁后顺序与预期结果 |
| --- | --- |
| 旧 ACTIVE 已过期 → 激活新版本 | scope lock 后先 EXPIRED 旧行，再 ACTIVE 新行；同事务成功，partial UNIQUE 始终满足 |
| 两个候选并发 activate 同 scope | scope advisory lock 串行；首个成功，第二个看到未过期 ACTIVE 后 409 |
| activate 与独立 expire 同一旧授权 | scope lock 串行；先执行者 expire；后执行者看到 EXPIRED。activate 可继续激活候选；expire 相同幂等 replay 或返回 already expired |
| expire 与 accept，expire 先锁 CTA | accept 等待，随后看到 EXPIRED，409；不创建 Enrollment/Assignment/Acceptance |
| expire 与 accept，accept 先锁且锁后尚未到期 | accept 提交当时有效的 append-only Acceptance；expire 到期后可执行，不回写历史 Acceptance |
| expire 与 accept，accept 先锁但锁后已到期 | accept 以 DB clock 拒绝，零新事实；expire 随后转换状态 |
| activate 与 accept 针对已过期旧 CTA | 都在旧 CTA 行串行；accept 无论先后均因 DB 时间或 EXPIRED 失败；activate 可先 expire 再激活新 CTA |
| activate 与 accept 针对尚有效旧 CTA | accept 可按旧授权完成；activate 因现有未过期 ACTIVE 返回 409 |
| CAS revision 竞争 | 取得行锁后 revision 不匹配的一方 409；不能覆盖胜者状态 |
| 任一 Audit/Outbox/Idempotency 写入失败 | 包含 expire/activate/accept 的整个事务 ROLLBACK，无半状态 |

## 6. API 与兼容边界增量

### 6.1 最小候选 API 变化

| API | V0.3 增量 | 当前状态 |
| --- | --- | --- |
| `GET /api/v1/me/handoffs/{id}` | 返回授权的 target JourneyStageVersion 与 primary Reviewer 展示信息；不把旧 legacy decision 当可接受决定 | `DESIGN_ONLY` |
| `POST /api/v1/me/handoffs/{id}/accept` | 增加 expected Stage；Reviewer 由服务端派生；完整复合键校验 | `DESIGN_ONLY` |
| `POST /api/v1/ops/controlled-task-authorizations/{id}/activate` | scope lock；旧 ACTIVE 到期时同事务 expire 后再 activate | `DESIGN_ONLY` |
| `POST /api/v1/ops/controlled-task-authorizations/{id}/expire` | 新增显式 expire；expected_revision、DB clock、Audit/Outbox | `DESIGN_ONLY` |
| 既有/候选 Review create | 不接收自报 Reviewer，固定使用 Enrollment.reviewer_id | `DESIGN_ONLY` |

V0.2 的最小 review-request 接收/本人回读接口不变：它只接收、回执、审计和通知，不修改原决定、不自动重新决定、不创建 Enrollment。

### 6.2 兼容与回滚

- Legacy `journey_admission_decisions` 继续原样读取；不改枚举、不 backfill、不映射 READY。
- 既有历史 Assignment 的 NULL Stage 不改写。新约束 trigger 只在新建或谱系键变更时执行；当前运行纵切的新 Assignment 必须非 NULL。
- 已有 Outcome、Handoff 和 Acceptance（未来若已启用）都是 immutable；授权后来过期不反向修改历史事实。
- Runtime 回滚首先关闭 V0.3 写入口，保留 additive 表、列、约束与事件。已经 EXPIRED 的授权不得恢复为 ACTIVE。
- 若 migration 尚未承载任何 V0.3 数据，可在独立批准和 dry-run 后逆序撤销 trigger/FK/UNIQUE；一旦存在 Acceptance，不允许删除 Stage/Reviewer 谱系列或降级为弱 FK。
- activate 同事务失败时由数据库回滚旧 expire 与新 activate；不需要补偿命令。响应丢失以同一幂等键回读。

## 7. 实施顺序与 Gate

本节只是后续获批后的顺序，不构成本轮实施授权。

| 顺序 | 后续最小工作 | 前置/出口 Gate |
| --- | --- | --- |
| 0 | 获批只读数据库审计：现有 JourneyStage/Enrollment/Assignment/Review 值域、NULL、重复、FK/trigger、调用方 | Data Owner + 独立技术/数据复核签署；本轮 `NOT_RUN` |
| 1 | canonical policy/hash 输入加入 target Stage，更新 golden vector | hash vector 与漂移测试 PASS；migration 前必须完成 |
| 2 | additive helper UNIQUE、Stage/Reviewer 字段、完整复合 FK、trigger 的 migration 草案与 downgrade dry-run | 独立数据库复核 PASS；本轮未创建 |
| 3 | 共用 authorization lifecycle DB command 内核；expire/activate 原子命令 | DB 约束和并发测试 PASS |
| 4 | Acceptance command 写固定 Stage/Reviewer，Review command 从 Enrollment 派生 Reviewer | API/事务/负向测试 PASS |
| 5 | 非生产环境真实受控任务 UAT | 全部阻断 Owner/Reviewer/见证人已本人接受并签署 |
| 6 | Pro 运行与发布裁决 | 本文不授予 Runtime 或 Release |

### 7.1 数据库与 API 负向测试 Gate

| 测试 ID | 负向/并发场景 | 必须结果 |
| --- | --- | --- |
| `db_cta_rejects_cross_journey_stage` | CTA Journey=A、Stage 属于 Journey=B | `fk_cta_stage_lineage` 拒绝 |
| `db_cta_rejects_wrong_stage` | Journey/Task 正确但传入另一 Stage | 复合 FK 拒绝 |
| `db_cta_rejects_wrong_stage_task` | Stage 的 Task 与 CTA Task 不同 | 复合 FK 拒绝 |
| `db_assignment_rejects_null_stage_for_journey_enrollment` | 新 Journey Enrollment 的 Assignment Stage=NULL | constraint trigger 拒绝，事务回滚 |
| `db_acceptance_rejects_assignment_stage_mismatch` | Acceptance Stage 与 Assignment Stage 不同 | `fk_ha_target_assignment_lineage` 拒绝 |
| `db_acceptance_rejects_assignment_task_mismatch` | Acceptance Task 与 Assignment Task 不同 | 同上拒绝 |
| `db_acceptance_rejects_enrollment_journey_mismatch` | Enrollment Journey 与 CTA Journey 不同 | `fk_ha_target_enrollment_lineage` 拒绝 |
| `db_acceptance_rejects_authorized_reviewer_mismatch` | Acceptance Reviewer 不等于 CTA primary Reviewer | `fk_ha_authorized_lineage` 拒绝 |
| `db_acceptance_rejects_enrollment_reviewer_mismatch` | Enrollment Reviewer 不等于 CTA/Acceptance Reviewer | `fk_ha_target_enrollment_lineage` 拒绝 |
| `db_review_rejects_enrollment_reviewer_mismatch` | 直接 INSERT Review，Reviewer 不等于 Enrollment Reviewer | `ct_review_enrollment_reviewer_guard` 拒绝 |
| `api_accept_rejects_client_reviewer` | accept body 自报/篡改 Reviewer | 400 schema error；零写入 |
| `api_review_rejects_reviewer_override` | Review create 尝试传非 Enrollment Reviewer | 400/403；零 Review |
| `db_activate_expires_old_active_then_activates_new` | 旧 ACTIVE 已到期、新候选有效 | 同事务旧 EXPIRED revision+1、新 ACTIVE；事件完整 |
| `db_activate_rejects_when_old_active_not_expired` | 旧 ACTIVE 未到期 | 409/DB 无状态变化 |
| `db_expire_uses_database_clock_boundary` | DB time 等于 expires_at | 成功 EXPIRED；不受客户端时间影响 |
| `db_expire_rejects_stale_revision` | expected_revision 落后 | 409；零写入 |
| `db_concurrent_activate_same_scope` | 两个候选并发 | 恰一条 ACTIVE；另一方冲突 |
| `db_concurrent_activate_expire` | activate/expire 同一旧 ACTIVE | 串行、无双事件、最终恰一条新 ACTIVE 或明确冲突 |
| `db_concurrent_expire_accept` | expire/accept 同一 CTA | 按 §5.4 线性化；过期边界后绝不创建 Acceptance |
| `db_concurrent_activate_accept` | activate/accept 同一旧 CTA | 按 §5.4；无过期授权 Acceptance |
| `db_lifecycle_rolls_back_on_outbox_failure` | lifecycle event INSERT 失败 | 状态/revision/Audit 全回滚 |

以上名称是未来测试合同，不是本轮已执行测试。必须同时有直接 SQL/数据库约束测试和 API 测试；仅 service unit test 不足以通过 DB Gate。

### 7.2 真人 UAT Gate

UAT 继续为 `NOT_RUN`。未来至少必须由真实 Person、执行 Reviewer、备 Reviewer、运营 Owner 和独立 UAT 见证人完成：正确 Stage/Task 展示、本人确认、Reviewer 收件、过期拒绝、旧版本到期后新版本激活、并发重放与审计回读。机器测试不能写成真人通过。

## 8. Owner 空缺与启用阻断

继承 V0.2 具名任命，不推断任何待接受角色已经接受：

| 角色 | 当前接受状态 | 阻断范围 |
| --- | --- | --- |
| 产品 Owner 刘默文 | `ACCEPTED` | 已承担产品裁决；不能替代独立复核/UAT |
| Tech Lead 刘默文 | `ACCEPTED` | 已承担技术主责；独立技术复核仍不可自签 |
| Data Owner / Security-Privacy 刘默文 | `ACCEPTED` | 已承担数据与安全主责；独立复核仍不可自签 |
| 探索营业务 Owner 郑田源 | `PENDING_PERSONAL_ACCEPTANCE` | 真实 Handoff 输入和 UAT |
| 新手村运营 Owner 屠元琦 | `PENDING_PERSONAL_ACCEPTANCE` | CTA 批准、activate/expire 运营入口、UAT |
| Reviewer/Panel Owner 屠元琦 | `PENDING_PERSONAL_ACCEPTANCE` | Reviewer 机制批准与 Review Gate |
| QA/UAT Owner 屠元琦 | `PENDING_PERSONAL_ACCEPTANCE` | UAT 组织；不能成为唯一 UAT 签署人 |
| 独立技术/数据复核人 | `VACANT` | 数据库审计、migration/constraint dry-run、hash 实现复核 |
| 新手村执行 Reviewer | `VACANT` | CTA ACTIVE、Enrollment/Review、真实 UAT |
| 备 Reviewer | `VACANT` | CTA ACTIVE、替补测试与真实 UAT |
| 独立 UAT 见证人 | `VACANT` | 真人 UAT PASS 与任何运行启用 |

空缺或待本人接受的 Owner 不阻断本设计评审，但阻断相应 authorization ACTIVE、真实任务创建、Review/UAT 和运行启用。屠元琦不能同时成为同一任务的运营者、唯一 Reviewer 和唯一 UAT 签署人。

## 9. 当前验证状态

本节只允许记录本轮实际执行命令。Product doctor/status 只验证 `config/muchen_journey_product.json` 和五地图产品总合同可读取、字段/枚举满足工具规则；它们不解析本 changeset 的复合 FK、trigger、锁顺序或并发语义，因此绝不代表 V0.3 changeset PASS。

验证状态冻结为：

| 项目 | 状态 |
| --- | --- |
| Product total contract doctor/status | `RUN`；含义仅限产品总合同 |
| V0.3 requirement scan | `PASS`；一次扫描词写错后修正并重跑，见 §9.3 |
| `git diff --check` | `PASS`；exit 0，见 §9.4 |
| Runtime tests | `NOT_RUN`；Runtime 未写 |
| Database constraint/audit/dry-run | `NOT_RUN`；未访问数据库、未创建 migration |
| Migration upgrade/downgrade | `NOT_RUN` |
| API/UI/OpenAPI tests | `NOT_RUN`；未修改实现 |
| 真人 UAT | `NOT_RUN` |
| Production data/access | `NOT_RUN` |

### 9.1 Product doctor

实际命令：

```bash
python3 '/Users/liumowen/.codex/plugins/cache/personal/muchen-journey-product/0.5.0+codex.20260823052858/skills/build-muchen-journey/scripts/muchen_product.py' doctor --repo '/Users/liumowen/Documents/Muchen Journey2.0'
```

退出码：`0`

关键输出：

```text
PRODUCT_DOCTOR=PASS
INVALID_CONTRACTS=none
PRODUCTION_MUTATION_EXECUTED=false
```

该 PASS 只属于产品总合同工具，不构成 V0.3 changeset、数据库约束或 Runtime PASS。

### 9.2 Product contract status

实际命令：

```bash
python3 '/Users/liumowen/.codex/plugins/cache/personal/muchen-journey-product/0.5.0+codex.20260823052858/skills/build-muchen-journey/scripts/muchen_product.py' status --repo '/Users/liumowen/Documents/Muchen Journey2.0'
```

退出码：`0`

关键输出：

```text
PRODUCT_CONTRACT=PASS
MAPS=探索营 -> 新手村 -> AI学院 -> 交付线工会 -> 认证竞技场
PROGRAM_MODE=five-map-parallel-workstreams
SHARED_PLATFORM_OWNER=muchen-journey-program-control
HUMAN_VALIDATION=NOT_INFERRED
PRODUCTION_MUTATION_EXECUTED=false
```

该命令没有读取或执行本文候选 DDL，也没有真人签署含义。

### 9.3 V0.3 必备项扫描

首次实际命令把中文正文中的“旧 ACTIVE”误写成英文扫描词 `old ACTIVE`：

```bash
v03_doc='docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.3.md'
v03_terms=('target_journey_stage_version_id' 'uq_jsv_acceptance_lineage' 'target_reviewer_user_id' 'ct_review_enrollment_reviewer_guard' 'expire_controlled_task_authorization' 'old ACTIVE' 'V0.2 → V0.3' 'PRO_MINIMUM_RUNTIME_CHANGESET_V0_3_REVIEW')
for v03_term in "${v03_terms[@]}"; do
  if ! rg -q --fixed-strings "$v03_term" "$v03_doc"; then
    echo "MISSING=$v03_term"
    exit 1
  fi
done
if rg -n ' +$' "$v03_doc"; then
  exit 1
fi
echo 'V0_3_REQUIREMENT_SCAN=PASS'
echo 'TRAILING_WHITESPACE=PASS'
```

退出码：`1`

关键输出：

```text
MISSING=old ACTIVE
```

这是扫描词与中文文案不一致，不是合同字段缺失。将该词修正为文档实际使用的 `旧 ACTIVE` 后，重新执行同一命令；其余命令行不变。

修正后退出码：`0`

关键输出：

```text
V0_3_REQUIREMENT_SCAN=PASS
TRAILING_WHITESPACE=PASS
```

把验证记录补入本文后又以相同修正命令执行一次最终扫描，退出码仍为 `0`，输出仍为上述两行。

### 9.4 Git diff check

实际命令：

```bash
git diff --check
```

退出码：`0`

关键输出：空。由于 V0.3 当前是 untracked 文件，`git diff --check` 本身不覆盖它；V0.3 的 trailing whitespace 由 §9.3 的独立 `rg` 检查覆盖。本轮没有用 add/commit 改变其状态。

把验证记录补入本文后再次执行同一命令，退出码仍为 `0`，输出仍为空。

### 9.5 文件状态与 dirty tree

实际命令：

```bash
git status --short --branch
```

退出码：`0`

关键输出显示当前分支为 `codex/full-module-development`；工作树原本已有大量未提交改动，包括 web/config/test 的 tracked modifications，以及 API、tests、outputs、docs 等 untracked 内容。本轮未清理或覆盖它们。

精确检查本 changeset 两个版本：

```bash
git status --short -- 'docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.2.md' 'docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.3.md'
```

退出码：`0`

输出：

```text
?? docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.2.md
?? docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.3.md
```

V0.2 是继承的既有未提交文件；本轮只新增 V0.3，没有修改 V0.2。

dirty-tree 数量摘要实际命令：

```bash
git status --porcelain=v1 | awk 'BEGIN {modified=0; untracked=0; other=0} /^ M/ {modified++; next} /^\?\?/ {untracked++; next} {other++} END {printf "TRACKED_MODIFIED=%d\nUNTRACKED_STATUS_ENTRIES=%d\nOTHER_STATUS_ENTRIES=%d\n", modified, untracked, other}'
```

退出码：`0`

输出：

```text
TRACKED_MODIFIED=10
UNTRACKED_STATUS_ENTRIES=114
OTHER_STATUS_ENTRIES=0
```

数量是 Git porcelain 顶层状态条目，不等同于递归文件数。只报告，不清理、不 stash、不提交。

## 10. V0.2 → V0.3 差异摘要

| 主题 | V0.2 | V0.3 |
| --- | --- | --- |
| CTA 目标 | JourneyVersion + TaskVersion | 增加 JourneyStageVersion；用四列 Stage helper UNIQUE 和复合 FK 闭合 Journey/Stage/Task |
| Acceptance 目标 | Enrollment/Assignment 只绑定 Journey/Task | 增加 Stage 与 Reviewer；三个完整谱系 FK 同时绑定 Authorization、Enrollment、Assignment |
| Assignment Stage | 字段既有但 nullable；纵切未给 DB 拒绝路径 | Journey Enrollment 的新 Assignment 由 trigger 强制非 NULL，并验证 Stage Journey/Task |
| Reviewer | CTA 有 primary/backup，Acceptance 未冻结实际 Reviewer | Acceptance 固定 primary；Enrollment 五列 helper UNIQUE；Review trigger 强制等于 Enrollment reviewer |
| ACTIVE 过期 | accept 以 DB clock 拒绝，但到期 ACTIVE 仍占 partial UNIQUE | 新增显式 expire command；activate 同事务先 expire 到期旧 ACTIVE，再激活新版本 |
| 并发 | 覆盖 accept/revoke/expire 概念结果 | 冻结 scope lock、行锁、revision CAS，以及 activate/expire/accept 线性化矩阵 |
| 验证 | V0.2 当轮记录 | V0.3 重新执行并明确 doctor 不是 changeset PASS；Runtime/DB/migration/UAT 均 NOT_RUN |

## 11. Pro correction closure

| # | `PRO_MINIMUM_RUNTIME_CHANGESET_V0_2_REVIEW` correction | V0.3 closure | 状态 |
| --- | --- | --- | --- |
| 1 | 闭合 JourneyStage 谱系 | §2、§3.1–§3.3、§4、§7.1 增加 Stage 字段、JSV helper UNIQUE、CTA/Acceptance/Assignment 完整复合链、NULL/跨 Journey/错 Stage/错 Task 负向 Gate | `READY_FOR_PRO_REVIEW` |
| 2 | 闭合 Reviewer 谱系 | §2.2、§3.1、§3.3–§3.4、§4、§7.1 固定 CTA primary→Acceptance→Enrollment→Review，增加 DB/API mismatch 负向 Gate | `READY_FOR_PRO_REVIEW` |
| 3 | 关闭 ACTIVE 过期生命周期缺口 | §3.2、§5、§7.1 固定 expire 入口、DB clock、scope/row lock、expected revision、Audit/Outbox、activate 先 expire 和并发矩阵 | `READY_FOR_PRO_REVIEW` |
| 4 | 增加 V0.2→V0.3 差异和 closure | §10 及本表完成；未扩展产品范围 | `READY_FOR_PRO_REVIEW` |
| 5 | 重做实际验证并限定 doctor 含义 | §9 记录实际命令、退出码、关键输出及一次扫描词修正；明确 doctor 只检查产品总合同；所有未执行项保持 NOT_RUN | `READY_FOR_PRO_REVIEW` |

## 12. 停止线与下一 Gate

当前未关闭风险：历史数据库与调用方审计未运行；现有数据能否无冲突增加 helper UNIQUE/trigger 尚未证明；canonical policy/hash 尚未实现 Stage 输入；migration upgrade/downgrade 未 dry-run；Runtime/API/OpenAPI/页面均未实现；独立复核、执行/备 Reviewer 和 UAT 见证人未就位。

本轮停止于设计文档。禁止创建 migration、写 Runtime、修改数据库/API/页面/OpenAPI、访问生产数据、提交、合并、打标签或部署；不得把候选合同或机器结果称为已运营化功能。

下一 Gate：`PRO_MINIMUM_RUNTIME_CHANGESET_V0_3_REVIEW`。
