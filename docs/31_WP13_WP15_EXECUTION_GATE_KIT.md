# WP-13～WP-15 真人、时间与生产门禁执行包

状态：`PREPARED_NOT_STARTED`

结论：`MACHINE_CONTRACT_READY / HUMAN_AND_TIME_EVIDENCE_NOT_RUN / PRODUCTION_NO_GO`

## 1. 第一性原则

WP-13 证明真人能否理解并完成真实闭环，WP-14 证明产品在真实 14 天内是否达到批准指标，WP-15 才决定是否允许生产写入。三者的核心证据分别是人的独立判断、真实经过的时间和明确生产授权，均不能由自动测试或 Agent 代替。

本执行包只把口径机器化，防止：

- 少跑一个 UAT 场景、少一个独立 Reviewer 或缺签字仍被写成通过；
- 在第 14 天之前预填 D+14，或通过改分母掩盖指标失败；
- UAT、试点和生产使用不同候选；
- 用同一人或同一证据引用伪造双人批准；
- `off_host_backup_restore`、外部观测或真实通知仍 `NOT_RUN` 时开放生产。

## 2. 固定合同

| 文件 | 固定内容 | 当前事实 |
| --- | --- | --- |
| `config/wp13_uat_plan.json` | 5 Learner、2 Reviewer、1 Operator、1 QA Recorder；AT-UAT-001..008；三类校准；三视口/键盘/200%/辅助技术；5 个签署角色；5 秒理解率 ≥90% | 合同已验证；真人结果 `NOT_RUN` |
| `config/wp14_pilot_plan.json` | 14 个自然日；D+1/D+3/D+7/D+14；DEC-010/013 七项阈值 | 合同已验证；观察窗未启动 |
| `config/wp15_release_plan.json` | 18 项生产前置，包含同一候选、物理隔离、受管密钥、真实通知/观测、异机恢复、RPO/RTO、双人批准和生产观察 | 合同已验证；全部生产动作未授权 |

`make wp13-15-plan-check` 只验证这些批准口径没有漂移，输出必须同时包含：

```text
status=PASS
human_actions_executed=false
production_mutation_executed=false
```

## 3. 私有证据规则

真人名册、外部身份、截图、签字和业务正文只能保存在 `evidence/private/` 或批准的受控证据库，不提交 Public Git。Git 中只允许记录不可逆 SHA-256 引用、聚合计数、场景状态和候选绑定。

私有 WP-13 证据必须包含：

- 完整 40 位 candidate SHA、staging deployment run、migration、config schema 和 OpenAPI SHA-256；
- 最小角色人数和私有名册引用；
- AT-UAT-001..008、三类 Reviewer 校准、六项可访问性检查逐项 `PASS/FAIL/NOT_RUN`；
- 5 秒理解正确数/总数；
- Sev-1/Sev-2 数量；
- Operator、Product Owner、QA Recorder、Reviewer 1/2 的独立签署引用。

验证入口：

```bash
python3 scripts/wp13_15_evidence.py uat-check evidence/private/wp13-uat.json
```

只有输出 `UAT_SIGNED` 才可启动 WP-14；任何缺项输出 `NO_GO` 和具体 blocker。

## 4. WP-14 真实时间门禁

WP-14 私有证据必须继承 WP-13 的同一 candidate SHA。`started_at` 到 `ended_at` 少于 14 天，当前时间尚未达到 `ended_at`，或任一 checkpoint 早于应到日期，验证器均输出 `STOPPED`。

指标使用原始 numerator/denominator：

- 完成率 ≥80%；
- 当前行动理解率 ≥90%；
- 两个工作日内评审比例 ≥90%；
- 重复事实 =0；
- 状态冲突 =0；
- 支持介入率 ≤20%；
- 可用性 ≥99.5%；
- Sev-1/Sev-2=0，缺陷趋势为 `STABLE` 或 `CONVERGING`。

验证入口：

```bash
python3 scripts/wp13_15_evidence.py pilot-check \
  evidence/private/wp14-pilot.json \
  --uat evidence/private/wp13-uat.json
```

## 5. WP-15 生产门禁

WP-15 验证器不包含部署、迁移、DNS、备份、切流或回滚代码。它只在 WP-13=`UAT_SIGNED`、WP-14=`PILOT_ACCEPTED`、三者 candidate SHA 完全一致、18 项生产检查全部 `PASS` 且至少两名不同角色提供不同签署引用时输出 `RELEASE_GO`。

验证入口：

```bash
python3 scripts/wp13_15_evidence.py release-check \
  evidence/private/wp15-release.json \
  --uat evidence/private/wp13-uat.json \
  --pilot evidence/private/wp14-pilot.json
```

即使验证器未来输出 `RELEASE_GO`，生产执行仍需当前会话中精确的 candidate SHA、镜像摘要、production 环境、时间窗口、动作范围和失败策略授权；计划批准不等于执行授权。

## 6. 当前必须人工提供的输入

当前没有需要立即打断工程准备的人工点击，但 WP-13 真正启动前必须补齐：

1. 5 名 Learner、2 名独立 Reviewer、1 名 Operator、1 名 QA Recorder 的私有名册；
2. 冻结候选的完整 SHA、三镜像摘要和一次明确授权的 staging 部署；
3. UAT 日期、Recorder、支持联系人和停止联系人；
4. Reviewer 三类校准样本的私有内容与记录方式。

WP-14 只能在 WP-13 真人签署后开始，并真实经过 14 天。WP-15 还受 WP-11 外部通知/观测、WP-12 异机恢复/物理删除/staging 性能、production 独立资源和双人批准阻塞。

## 7. 当前判定

- WP-13：`PREPARED / HUMAN_UAT_NOT_RUN`
- WP-14：`NOT_STARTED / WAITING_FOR_WP13 / REAL_14_DAYS_REQUIRED`
- WP-15：`NO_GO / WAITING_FOR_WP13_WP14_AND_PRODUCTION_GATES`
- production mutation：`false`

因此本文件不是 WP-13、WP-14 或 WP-15 完成证明。
