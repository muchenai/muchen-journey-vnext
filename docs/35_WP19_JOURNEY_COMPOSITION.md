# 35｜WP-19 Journey Composition 构建合同

状态：`READY_FOR_REMOTE_GATE`

版本：V0.1

日期：2026-08-03

基线：`e474aa8db5d57d902c0ef9994dcdb471ad82dbcd`

## 1. 本工作包只关闭什么

WP-19 只补足正式产品缺失的多阶段编排层：

1. `JourneyDefinition` 提供组织内稳定旅程身份和用途分类；
2. `JourneyVersion` 固定标题、版本、发布与复核事实；
3. `JourneyStageVersion` 固定阶段键、类型、顺序、完成策略和 `TaskVersion`；
4. `Invite` 与 `Enrollment` 固定引用一版 `JourneyVersion`；
5. `Assignment` 固定引用其中一个 `JourneyStageVersion`；
6. Current Action 只返回顺序最前且尚未完成的阶段，并输出只读进度投影。

WP-19 不发布四个宝藏正文，不实现 `LEARNER_EVIDENCE` 完成命令，不生成正式综合 Outcome，不重做 `/review`、`/ops` 或完整 Learner 视觉地图，也不授权部署。

## 2. 数据与不可变性合同

| 对象 | 可写阶段 | 发布后规则 |
| --- | --- | --- |
| `JourneyDefinition` | Operator 创建、增加新版本 | 稳定键不变；撤销后不得再发布 |
| `JourneyVersion` | 单次发布事务 | 行不可更新或删除；在途 Enrollment 永久固定原版本 |
| `JourneyStageVersion` | 随 JourneyVersion 同事务发布 | 行不可更新或删除；位置从 1 连续递增且版本内唯一 |
| `Enrollment.journey_version_id` | 邀请交换时固定 | 不允许在途自动升级 |
| `Assignment.journey_stage_version_id` | 身份确认时按发布顺序生成 | 组织、旅程、任务与位置必须同时匹配 StageVersion |
| Journey Progress | 不可写 | 仅从 Enrollment 与 Assignment 状态推导 |

数据库使用复合外键同时约束组织、旅程版本、阶段、任务版本和位置，避免服务代码遗漏检查后产生跨组织、跨版本或顺序漂移。

## 3. 兼容与激活合同

- 已有 `TSK-001` 被迁移为一段单阶段 `ALPHA_VALIDATION` Journey；历史提交、评审、Outcome 与路由不改写。
- 旧 `task_version_id` 邀请请求仅作为过渡兼容输入；服务端必须唯一解析到一个单阶段 Alpha Journey，无法唯一解析时拒绝。
- 新邀请只选择 `journey_version_id`，身份确认一次性生成整版 Assignment：首阶段 `AVAILABLE`，后续阶段 `LOCKED`。
- `FORMAL_EXPLORATION` Journey 可以完成结构发布与审计，但在 WP-20/21 关闭内容、宝藏完成策略与正式 Outcome 前不得签发真实邀请。
- `LEARNER_EVIDENCE` 只在 schema 中锁定语义；WP-20 前不得被现有 Reviewer 路径伪装成“自动通过”。

## 4. 顺序与阶段推进

Current Action 的唯一规则是：

```text
按 JourneyStageVersion.position 排序
  → 忽略 COMPLETED / CANCELLED
  → 选择第一个剩余阶段
  → 根据该 Assignment 状态返回行动
```

不再先找“需要修订”或“可开始”状态。只要更早阶段仍在提交、评审或修订中，后续阶段就不能成为 Current Action。

Reviewer 通过一个非末尾阶段时，服务端在同一事务内：

1. 将当前 Assignment 置为 `COMPLETED`；
2. 将紧邻的 `LOCKED` Assignment 置为 `AVAILABLE`；
3. 保持 Enrollment 为 `ACTIVE`；
4. 不生成 Outcome。

只有支持完整结果合同的最后阶段才可以结束 Enrollment。正式探索营的多评测 Outcome 继续由 WP-21 实现，WP-19 不以最后一份 Evaluation 冒充综合结论。

## 5. API 最小面

- `POST /api/v1/ops/journey-definitions`
- `GET /api/v1/ops/journey-definitions`
- `POST /api/v1/ops/journey-definitions/{id}/publish`
- `POST /api/v1/ops/invites` 改为优先接收 `journey_version_id`
- `GET /api/v1/me/current-action` 增加最小 `journey` 只读投影

所有 Operator 写入继续要求真实角色、组织范围、幂等键、expected revision、固定复核人和审计事件；Web Server Action 只做输入收集，授权仍在 API 内执行。

## 6. 失败矩阵

| 场景 | 服务端结果 | 禁止的补偿 |
| --- | --- | --- |
| 阶段键重复、空阶段或位置不连续 | `422 VALIDATION_FAILED` | 前端自动改序 |
| TaskVersion 非本组织或未发布 | `422 VALIDATION_FAILED` | 复制任务正文 |
| Reviewer 非本组织有效 Reviewer | `422 VALIDATION_FAILED` | 用 Operator 代签 |
| Definition revision 过期 | `409 VERSION_CONFLICT` | last-write-wins |
| 修改/删除已发布 JourneyVersion 或 StageVersion | 数据库拒绝 | 原地改版本 |
| Invite 引用不可激活的正式 Journey | `409 INVALID_STATE_TRANSITION` | 降级成 TSK-001 |
| Enrollment 与 JourneyVersion 跨组织 | 数据库/服务端拒绝 | 仅靠页面隐藏 |
| Assignment 阶段、任务、位置与旅程不一致 | 数据库拒绝 | 运行时猜顺序 |
| 直接操作 `LOCKED` 阶段 | `409 INVALID_STATE_TRANSITION` | 允许 URL 跳关 |
| 前一阶段等待评审、后一阶段可用 | Current Action 仍返回前一阶段 | 状态优先级跳关 |
| 非末尾阶段通过 | 解锁下一阶段；Enrollment 保持 ACTIVE | 提前生成 Outcome |
| 正式多阶段最后一关在 WP-21 前完成 | 服务端拒绝综合完成 | 用最后一次 Evaluation 冒充结果 |

## 7. 关闭条件

- [x] migration 从 `0014` 前向升级并完整回填现有 Alpha 事实；
- [x] JourneyVersion/StageVersion 发布后数据库不可变；
- [x] Invite、Enrollment、Assignment 的复合范围约束通过；
- [x] 多阶段确认身份只开放第一阶段；
- [x] 等待评审、修订、完成和下一阶段解锁顺序通过；
- [x] Current Action 输出服务端推导的最小进度；
- [x] 旧 TSK-001 邀请、修订闭环与 Outcome 回归通过；
- [ ] Fast Gate 与迁移静态门禁通过；
- [x] 无部署、无真实业务数据改写、production 继续 `NO_GO`。

## 8. 本地构建证据

- WP-18 基线代码在本机 test DB 建立真实 `0014` fixture 后，当前 migration 完成 `0014 → 0015 → 0014 → 0015`；Journey 绑定空值与跨范围不一致均为 0；
- 当前源码在锁定 API 依赖镜像中从空库升级并运行完整测试：`269 passed`；
- Journey 专项覆盖精确正式结构发布但禁用邀请、发布不可变、整版确认、锁定跳关拒绝、等待不跳关、下一阶段解锁和 Outcome 不提前生成；
- Web ESLint、TypeScript、9 项 Node 合同测试与 production build 通过；OpenAPI runtime 与版本化合同完全一致；
- migration static、isolation、历史 Web-only、staging workflow、WP-11/12/12B/13-15/16/17 合同门禁通过；
- 标准 `make api-test` 的镜像重建在代码测试前因 PyPI TLS EOF 中止；不将挂载源码测试冒充干净镜像 Fast Gate，最终关闭等待远端 CI。
