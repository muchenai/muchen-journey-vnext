# WP-13～WP-15 真人、时间与生产门禁执行包

状态：`HUMAN_UAT_STOPPED_RUNTIME_REPAIR_PRESTATE_VERIFIED`

结论：`UAT-WP13-001_REPAIRED / NEW_CANDIDATE_GENERATED / REBIND_PENDING_STAGING_DEPLOY / HUMAN_UAT_STOPPED / PRODUCTION_NO_GO`

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
| `config/wp13_uat_plan.json` | 精确绑定当前已部署候选 `02863d0…` 和 DEC-020 Alpha 条件入口；5 Learner、2 Reviewer、1 Operator、1 QA Recorder；AT-UAT-001..008；三类校准；三视口/键盘/200%/辅助技术；5 个签署角色；5 秒理解率 ≥90% | 首次真人执行在 `AT-UAT-003` 为 `FAIL` 并停止；旧计划不覆盖该失败事实 |
| `config/wp13_uat_rebind.json` | DEC-021 Web-only 影响核对、新候选 Mainline run/manifest/GHCR 摘要、失败部署/repair 尝试、只读 runtime inventory 及有界 runtime repair 合同 | `RUNTIME_REPAIR_PRESTATE_VERIFIED_UAT_REJECTED`；`human_uat_resume_allowed=false` |
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

WP-12B run `30525165474` 的原 1 秒合同保持 `FAIL/NOT_CLOSED`。DEC-020 已对同一候选批准仅限 WP-13 的 p95≤1.2 秒 Alpha 条件入口；候选漂移即失效，且不得外推 WP-14/production。真人执行前仍必须补齐：

1. 5 名 Learner、2 名独立 Reviewer、1 名 Operator、1 名 QA Recorder 的私有名册；
2. 核对冻结候选仍为 `02863d0b670ee9b00b9def3e75bc6699827f555a`、部署 run=`30519669770` 且 staging readiness 与候选一致；
3. UAT 日期、Recorder、支持联系人和停止联系人；
4. Reviewer 三类校准样本的私有内容与记录方式。

WP-14 只能在 WP-13 真人签署后开始，并真实经过 14 天。WP-15 还受 WP-11 外部通知/观测、WP-12 异机恢复/物理删除/staging 性能、production 独立资源和双人批准阻塞。

### 6.1 UAT-WP13-001｜运营邀请入口

2026-07-30 首次真人执行在 `AT-UAT-003` 停止：Operator 在 60 秒内无法从 `/ops` 找到新人邀请入口。该结果按 `SEV2` 记录为 `UAT-WP13-001`，原失败事实和私有证据保持不变，不能被后续修复覆盖。

修复范围仅限 Web 运营页：复用既有 organization-scoped `POST/GET /ops/invites` 与 revoke 合同，让 Operator 通过已绑定 Reviewer 和已发布 TaskVersion 的可读名称创建 24 小时一次性链接，并查看/撤销最近邀请；不要求人工输入 UUID，不新增 API、数据表、云资源或 IAM 权限。邀请 token 仍只在创建成功后的当前页面状态显示，并放在 `/join#token=…` fragment 中；刷新后不再回显。

修复已通过 PR #94 合入主线。Mainline run `30550010916` 为 `222096db506e95db887a8705b22ca4a439d0545d` 完成 `ci-main`、候选打包、三镜像 GHCR digest 验证和工件上传；manifest SHA-256 为 `2aa6ec1af6f8db02a1a514419cb4bc181460317f990edc30de772375fe80aecc`。

DEC-021 的影响核对确认 API、Worker、迁移与 OpenAPI 相对基线 `02863d0…` 未漂移，候选单提交的运行代码变化仅为 Web 邀请入口，因此不重跑 WP-12B，并保留原 run 的 `FAIL/NOT_CLOSED`。full deploy run `30556851235` 在镜像部署阶段超时取消；公开 readiness 显示 Web=`222096db…`，但受权 `/ops` 运行快照显示 API/Worker=`172c9f62…`、migration=`0013`、Worker stale。SSH 已关闭，但该混合状态不是成功部署。

`config/wp08_web_only.json`、`scripts/wp08_web_only.py` 与同一 `staging.yml/deploy.sh` 现建立两段有界合同。正常 Web-only 路径仍要求 API/Worker 精确等于基线 `02863d0…`、migration=`0014`、schema=3、Worker 非 stale；针对已观测混合状态的 `repair-runtime` 只允许前向 migration、runtime DML grant 和固定摘要 API/Worker 替换，明确禁止 Web、seed、业务事实、DNS、Terraform、云资源与 WP-12B 改写。当前只证明合同和现有 prestate 匹配，未获得部署授权、未执行修复；`deployment_run_id` 继续为 `null`、`human_uat_resume_allowed=false`，不得恢复 `AT-UAT-003`。

## 7. 当前判定

- WP-13：`HUMAN_UAT_STOPPED / AT-UAT-003_FAIL / UAT-WP13-001_SEV2 / NEW_CANDIDATE_GENERATED / REBIND_PENDING_STAGING_DEPLOY / NO_GO`
- WP-14：`NOT_STARTED / WAITING_FOR_WP13 / REAL_14_DAYS_REQUIRED`
- WP-15：`NO_GO / WAITING_FOR_WP13_WP14_AND_PRODUCTION_GATES`
- production mutation：`false`

因此本文件不是 WP-13、WP-14 或 WP-15 完成证明。
