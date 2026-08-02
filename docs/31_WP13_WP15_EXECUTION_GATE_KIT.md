# WP-13～WP-15 真人、时间与生产门禁执行包

状态：`CONTROLLED_ALPHA_MINIMUM_HUMAN_LOOP_PASSED`

结论：`ONE_REAL_REVISION_LOOP_PASS / FULL_WP13_UNSIGNED / WP14_NOT_STARTED / CONTROLLED_ALPHA_DOMAIN_CUTOVER_APPROVED / FULL_PRODUCTION_NO_GO`

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
| `config/wp13_uat_plan.json` | 精确绑定当前已部署 Web 候选 `222096db…`、repair run `30616573615` 和 DEC-020/021 Alpha 条件入口；5 Learner、2 Reviewer、1 Operator、1 QA Recorder；AT-UAT-001..008；三类校准；三视口/键盘/200%/辅助技术；5 个签署角色；5 秒理解率 ≥90% | 技术入口已恢复；原 `AT-UAT-003` 失败事实保留，新一轮必须完整重跑并取得真人证据 |
| `config/wp13_uat_rebind.json` | 当前混合运行基线、`UAT-WP13-002`、修复候选 Mainline run/manifest/GHCR 摘要、变化与不变运行合同、部署与真人恢复边界 | `REPAIR_CANDIDATE_BOUND_PENDING_STAGING_DEPLOY`；`deployment_run_id=null`；`human_uat_resume_allowed=false` |
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

WP-12B run `30525165474` 的原 1 秒合同保持 `FAIL/NOT_CLOSED`。DEC-020 只覆盖原候选；修复候选改变 API 与公开合同，因此原 Alpha 性能条件不能自动继承，必须在部署前明确重新评估。真人执行前仍必须补齐：

1. 5 名 Learner、2 名独立 Reviewer、1 名 Operator、1 名 QA Recorder 的私有名册；
2. 在另行授权部署后，核对 Web/API/Worker 均为修复候选 `8f77ceec570e2ec5e9c52861fcdc27748d7bb44a`、migration=`0014`、schema=3、readiness 与运行 revision 一致；
3. UAT 日期、Recorder、支持联系人和停止联系人；
4. Reviewer 三类校准样本的私有内容与记录方式。

WP-14 只能在 WP-13 真人签署后开始，并真实经过 14 天。WP-15 还受 WP-11 外部通知/观测、WP-12 异机恢复/物理删除/staging 性能、production 独立资源和双人批准阻塞。

### 6.1 UAT-WP13-001｜运营邀请入口

2026-07-30 首次真人执行在 `AT-UAT-003` 停止：Operator 在 60 秒内无法从 `/ops` 找到新人邀请入口。该结果按 `SEV2` 记录为 `UAT-WP13-001`，原失败事实和私有证据保持不变，不能被后续修复覆盖。

修复范围仅限 Web 运营页：复用既有 organization-scoped `POST/GET /ops/invites` 与 revoke 合同，让 Operator 通过已绑定 Reviewer 和已发布 TaskVersion 的可读名称创建 24 小时一次性链接，并查看/撤销最近邀请；不要求人工输入 UUID，不新增 API、数据表、云资源或 IAM 权限。邀请 token 仍只在创建成功后的当前页面状态显示，并放在 `/join#token=…` fragment 中；刷新后不再回显。

修复已通过 PR #94 合入主线。Mainline run `30550010916` 为 `222096db506e95db887a8705b22ca4a439d0545d` 完成 `ci-main`、候选打包、三镜像 GHCR digest 验证和工件上传；manifest SHA-256 为 `2aa6ec1af6f8db02a1a514419cb4bc181460317f990edc30de772375fe80aecc`。

DEC-021 的影响核对确认 API、Worker、迁移与 OpenAPI 相对基线 `02863d0…` 未漂移，候选单提交的运行代码变化仅为 Web 邀请入口，因此不重跑 WP-12B，并保留原 run 的 `FAIL/NOT_CLOSED`。full deploy run `30556851235` 在镜像部署阶段超时取消；公开 readiness 显示 Web=`222096db…`，但受权 `/ops` 运行快照显示 API/Worker=`172c9f62…`、migration=`0013`、Worker stale。SSH 已关闭，但该混合状态不是成功部署。

`config/wp08_web_only.json`、`scripts/wp08_web_only.py` 与同一 `staging.yml/deploy.sh` 建立两段有界合同。唯一 repair run [`30616573615`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30616573615) 基于主线 `100e89494b8c42a6b04a86f5bdc26c06ab690fa7` 成功：Web 保持 `222096db…`，API/Worker/heartbeat 恢复 `02863d0…`，migration=`0014`、schema=3、Worker 非 stale；root=200、匿名 `/ops`/`/review`=401，SSH 已关闭。Terraform、DNS、云资源、seed、消息和 WP-12B 均未执行。该 run 现作为 `deployment_run_id` 激活技术 UAT 入口，但不替代真人重跑或签署。

### 6.2 UAT-WP13-002｜Learner 会话连续性

2026-08-02 的 Round-2 真人路径已经完成真实邀请、任务提交和 Reviewer `REQUEST_REVISION`。Learner 在提交约 11 小时后返回 `/app`，页面显示通用服务端错误摘要 `3990910455`，无法进入修订工作区。截图只证明 Web 错误页，不单独证明 API 401；但代码与时间合同显示 Learner session 固定 8 小时，Learner 页面没有 Reviewer/Operator 已有的过期恢复处理，原一次性邀请又已消费，因此将该结果按 `UAT-WP13-002/SEV2` 记录并停止 `AT-UAT-002`。

修复不延长 session TTL，也不创建新的身份或业务闭环。Operator 只能对同组织原 ACTIVE Enrollment 生成默认 30 分钟的一次性重新进入链接；服务端校验原 Learner、Enrollment、Reviewer 与 TaskVersion，确认后轮换旧 Learner session，并保持原 Submission/Review/Evaluation 与修订反馈不变。API 回归显式比较重新进入前后的 User、Enrollment、Assignment、SubmissionVersion、Review、Evaluation 和业务 Outbox 计数；Web 对缺失或 API 401 的 Learner session 显示联系运营获取替换链接的明确提示。

修复已通过 PR #104 以主线 `8f77ceec570e2ec5e9c52861fcdc27748d7bb44a` 合入。Mainline run [`30709982868`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30709982868) 完成 `ci-main`、三组件镜像、SBOM、manifest、GHCR 推送与摘要复验；manifest SHA-256 为 `a7de07e531de4ee86562a04674d8807e4a9ce5cfc77fc8adcc98f4111809d637`。候选保持 migration=`0014`、schema=3、TaskVersion artifact 不变；API/Web/OpenAPI 改变，Worker 源码、迁移、锁文件和 Compose 不变。

候选随后由 staging deploy run `30729705773` 成功部署；公开 readiness 与受权运行快照确认 Web/API/Worker=`8f77ceec…`、migration=`0014_wp12_data_lifecycle`、schema=3。没有重跑 WP-12B，原 1 秒性能 FAIL 继续保留。

真人随后完成同一条受控业务事实的最小修订闭环：Operator 生成安全重新进入路径，Learner 看到原 `REQUEST_REVISION` 反馈、再次提交新 SubmissionVersion，Reviewer 最终判断 `PASS`，Learner 进入 `COMPLETED`。原失败截图和旧 Submission/Review 事实均未被覆盖。该结果关闭 `UAT-WP13-002` 的本场景真人复验，但样本不足以把完整 WP-13 记为 `UAT_SIGNED`。

### 6.3 DEC-023｜正式域名受控 Alpha 路径

基于上述真人最小闭环，Owner 授权将 `journey.muchenai.com` 切换为单一组织私密名单的正式 Alpha 入口。受保护主线新增唯一运行手册 `docs/runbooks/WP15_ALPHA_PRODUCTION_CUTOVER.md`：先把当前 staging 数据库只读备份并恢复到空白 `journey_next_production`，比较 migration/schema/逐表计数并把加密 dump 保存到现有私有 TOS；再部署独立 production Compose/application secrets，并配置 TLS、飞书正式回调、allowed host 与 canonical result URL；维护页是一键止血，旧站 DNS 只允许入口回退，不允许覆盖或写回 vNext 业务事实；staging 始终保留。

该路径共享现有北京 ECS/RDS/Caddy 物理故障域，仅实现逻辑隔离。它是 DEC-019 的 30 日 Alpha 延期边界，不是完整 production isolation。WP-11 延期项、WP-12B 原 FAIL、完整 WP-13 签署和 WP-14 仍未完成，因此正式域名开放不等同 `RELEASE_GO`。

## 7. 当前判定

- WP-13：`ONE_REAL_REVISION_LOOP_PASS / UAT-WP13-002_SCENARIO_REVERIFIED / FULL_UAT_UNSIGNED`
- WP-14：`NOT_STARTED / WAITING_FOR_WP13 / REAL_14_DAYS_REQUIRED`
- WP-15：`CONTROLLED_ALPHA_DOMAIN_CUTOVER_APPROVED / FULL_RELEASE_GATE_NO_GO`
- production mutation：`false`

因此本文件只证明最小真人修订闭环和受控 Alpha 切换授权，不是完整 WP-13、WP-14 或 WP-15 完成证明。
