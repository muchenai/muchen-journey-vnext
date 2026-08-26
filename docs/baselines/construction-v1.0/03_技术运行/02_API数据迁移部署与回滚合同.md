# 技术运行 02｜API、数据、迁移、部署与回滚合同

## 1. API合同

首发至少提供以下资源能力，具体路径可适配现有路由，但语义不可改变：

| 能力 | 最小命令/查询 |
| --- | --- |
| 身份/首页 | consume invite、current person、current actions、module summaries |
| 内容 | published module/content/task versions（只读） |
| Assignment | start、get current、list mine |
| Submission | save draft、submit、resubmit、history |
| Review | queue、detail、start、request revision、pass |
| Evidence/Result | evidence list、result package、timeline |
| Human Gate | sign next stage/task/capability result（授权真人） |
| Appeal | submit、assign independent reviewer、resolve、read lineage |
| Operator | publish approved versions、assign reviewer、queue/SLA、freeze invites |
| Runtime | readiness、release marker、worker/backlog、audit-safe status |

所有写接口：认证、scope校验、CSRF（会话场景）、幂等、expected revision、reason、审计、严格schema。错误响应不泄露对象是否存在。

## 2. 正式写入不变量

- 只有 Learner 可提交自己的Assignment；
- 只有被分配且有效的Reviewer可finalize；
- Evaluation绑定固定SubmissionVersion与RubricVersion；
- `PASS` 同事务产生formal evidence/result所需事实和outbox；
- AI、self attestation和points不能调用formal gate；
- 真实任务没有有效authorization时不可发布或分配；
- production任务无自动写回；
- 所有历史修订append-only。

## 3. 数据与迁移

### 新数据库

- 以候选代码从空 PostgreSQL 库执行完整 Alembic upgrade；
- 禁止手工改表代替migration；
- 每个migration有upgrade、可行的downgrade或明确forward-fix策略；
- DB约束覆盖唯一性、scope、状态时间、版本不可变和关键外键；
- schema dump/hash进入候选manifest。

### 历史数据

- 正式迁移记录数固定为0；
- 不建立旧系统到新人才状态的枚举映射；
- 源文件作为只读参考保留，不写入Journey2.0；
- 若未来要迁移，必须另开版本化migration manifest和Owner批准，不属于9/1候选。

### 开发/测试数据重置

只允许明确标识的 local/test 数据库；执行前验证数据库名、环境标识、host和生产拒绝条件，生成备份或确认可重建，记录命令/时间/摘要。模糊DSN、默认生产连接、无环境标签时失败关闭。

## 4. 内容包

产品内容不埋在组件文案中。内容包至少含：module/task/content/rubric IDs与版本、来源、Owner、hash、发布日期、可见范围、数据等级、有效期。构建/发布manifest绑定内容包hash；内容漂移需要重新UAT或明确影响评估。

## 5. 环境

| 环境 | 用途 | 数据 | 身份 |
| --- | --- | --- | --- |
| local | 开发 | 合成/可重建 | fixture可用 |
| test | 自动测试 | 每次重建 | 仅fixture |
| staging/uat | 候选真人UAT | 受控试点 | 真实身份，禁止fixture |
| production | 最多25人受控发布 | 新批次正式事实 | 真实身份，最小权限 |

环境必须独立secret、数据库逻辑边界和release marker。local默认secret不得被production接受。

## 6. 候选manifest

必须固定：完整Git SHA、分支、clean=true、construction package hash、requirements hash、OpenAPI hash、migration head/schema hash、web/api/worker digest、content package hash、config hash、测试报告hash、生成时间和签署状态。任何一项变化使旧UAT/签署失效。

## 7. 备份、恢复与回滚

候选前24小时内生成加密备份并记录范围、hash、密钥保管和Owner。在隔离数据库实际恢复并对账：migration、表数、关键计数、抽样hash和应用只读查询。

回滚分两类：

- 应用回滚：回到上一镜像，不丢已写业务事实；
- 数据forward-fix：已产生正式提交/评审后，不以破坏性downgrade覆盖事实。

演练必须包含：维护/冻结邀请、停止worker、备份、应用切换、DB兼容检查、健康/关键路径、恢复通知、审计记录。

## 8. 观测与故障处理

P0指标：readiness、HTTP 5xx、登录失败、任务/提交/评审命令失败、DB连接、worker heartbeat、outbox oldest age/dead、Reviewer SLA、备份年龄。

故障动作：

- 身份/越权/数据泄露：立即冻结邀请和相关访问；
- 提交/评审丢失：停止相关mutation，保护数据库和日志；
- 通知失败：业务事实继续，使用站内/人工补充通知；
- 性能下降：限流/降级非P0视图，保持提交/评审；
- 不能在观察窗口证明安全：回滚或暂停小名单，不扩大访问。

