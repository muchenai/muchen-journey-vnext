# WP-12 候选硬化与灾备构建证据

状态：`IN_PROGRESS`

结论：`FIRST_HARDENING_SLICE_VERIFIED / RC_TECHNICALLY_READY_NOT_REACHED / PRODUCTION_NO_GO`

## 1. 本工作包目标与边界

WP-12 追溯 `DEC-008/013/014`、`REQ-NFR-005/008/010`、`AT-DATA-008`、`AT-ISO-007` 和 `AT-ARCH-001/007`。目标是把同一精确候选的安全、性能、数据生命周期、异机恢复和回滚证据闭环，而不是继续扩展产品模块。

DEC-018 仅允许 Alpha 延期 TLS 外部日志采集、真实通知和告警演练，并以有界、只读、脱敏的主机审计临时观测。延期项仍为 `NOT_RUN`，不计入 WP-12 通过证据，production 继续 `NO_GO`。本批次没有部署、没有新增云资源，也没有修改业务事实。

DEC-019 进一步将跨地域/独立灾备故障域选型延期至真实 Alpha 连续稳定运行 30 个自然日后的成熟检查点。延期不取消基础备份与恢复工程，不关闭 release gate 的 `off_host_backup_restore`；异机恢复继续 `NOT_RUN`，WP-12 仍不得记 `RC_TECHNICALLY_READY`。

## 2. 第一批已实现硬化

- 修复非本地配置 fail-open：staging/production 对公开本地默认 session、invite、import signing 和 identity subject secret 的拒绝不再依赖附件开关；这与 Alpha `ATTACHMENTS_ENABLED=false` 边界解耦；
- API、Web、Worker staging 容器统一禁止权限提升、清空 Linux capabilities 并设置 PID 上限；edge 保持原合同，避免在未验证低端口能力前造成可用性回归；
- Next.js 显式关闭生产浏览器 source map，生产 build 后扫描 `.next/static`，发现任何 `.map` 即失败；
- 把上述 Compose 与 Next.js 合同加入 `ci-fast` 的只读 `wp12-hardening-check`；
- 形成 `security_best_practices_report.md`，逐项记录严重度、证据、影响、修复和剩余风险。

## 2.1 数据生命周期计划基线

- `config/wp12_data_lifecycle.json` 把 DEC-008 固定为机器合同：身份/提交/评价/结果/审计 1095 天、附件 365 天、通知 180 天、幂等 30 天，删除/纠错请求 30 天；
- migration `0014_wp12_data_lifecycle` 新增 data-rights request 台账，记录主体、类型、30 日到期、合法保留、状态、解决码和 revision；数据库约束禁止开放请求伪造完成字段、已完成请求缺少解决证据或无理由 legal hold；
- `journey_api.data_lifecycle` 只提供 `policy-check` 与 `PLAN_ONLY`。计划按明确 `as_of` 生成各数据类 cutoff、到期数量、逾期 rights request 和 legal hold 数量，不输出记录标识，不执行删除；
- 当前没有非本地 APPLY 路径。真实删除必须在下一受审查切片中处理外键顺序、附件对象删除、主体最小化和不可变审计，再以精确环境授权执行。

## 3. 本地机器证据

2026-07-28 定向复验：

```text
docker compose build api
PASS

docker compose run --rm --no-deps api pytest -q \
  tests/test_config.py \
  tests/test_wp12_candidate_hardening.py \
  tests/test_wp08_staging.py
24 passed

make wp12-hardening-check
WP12_HARDENING=PASS app_sandbox=3 source_maps=disabled

make web-check
lint PASS / typecheck PASS / production build PASS
WP08_WEB_RUNTIME=PASS readiness=200 anonymous_ops=401 anonymous_review=401 \
  expired_reviewer=explicit-relogin root=200 csp_nonce=per-request \
  oauth_redirect=root-relative

make dependency-audit
WEB_DEPENDENCY_AUDIT=PASS vulnerability_packages=9 waived_advisories=1 \
  scope=dev-only waiver_expires=2026-08-31
No known vulnerabilities found (Python)

make secret-scan
PASS / no leaks found
```

### 3.1 本地只读性能基线

`scripts/wp12_local_readiness.py` 强制目标为 loopback HTTP，使用本地 fixture 身份，只读取 readiness、Learner Current Action、Reviewer queue 和 Operator runtime，不执行业务命令。每条路径预热 3 次、采样 25 次，任一非 200 或 p95 超过 1 秒即失败；报告权限为 owner-only，并固定 `staging_benchmark=NOT_RUN`、`pilot_availability_99_5_percent=NOT_RUN`。

2026-07-28 本地报告 `artifacts/wp12/local-benchmark-20260728T165730Z-c04f75cd.json` 为 `PASS`：readiness p95 `0.002298s`、Current Action `0.004462s`、Reviewer queue `0.014472s`、Operator runtime `0.004550s`。这是本机 fixture 的工程余量，不包含公网、Caddy、ECS、RDS 网络、真实数据量或并发，不能关闭 staging benchmark 和 14 日可用性门禁。

### 3.2 本地隔离恢复与当前迁移回滚

`make wp12-local-recovery` 仅操作 Compose 开发库与空白 `db-test`：先升级/seed，再生成 owner-only 加密备份及签名 manifest，在全新随机数据库恢复，核对 migration、计数、约束、跨组织关键不变量和 TaskVersion 指纹，然后执行当前 `0013 → 0014 → 0013 → 0014` 隔离演练。若 `0014` 已存在 data-rights 事实，脚本拒绝 schema 回退并要求维护模式或前滚修复，禁止通过回滚抹除已接受事实。

2026-07-28 报告 `artifacts/wp06/wp06-20260728T165823Z-7cd0532e/restore-rollback-report.json` 为 `PASS`：恢复与 re-upgrade 通过、`accepted_business_facts_rolled_back=false`、用时 `6.110s`、本地备份年龄 `0.696s`。`local_rto_within_budget=true` 与 `local_rpo_artifact_age_within_budget=true` 只说明本机演练低于 DEC-013 数值预算；`production_restore` 和 `off_host_restore` 均继续 `NOT_RUN`。

最终 PR 仍必须通过远端 required `WP-07 / quick`；合并后主线全量门禁与候选摘要才是 canonical 证据。

## 4. 当前安全结论

- Sev-1：未发现；
- Sev-2：1 项非本地默认密钥 fail-open 已修复并回归；
- Sev-3：容器运行时最小权限和 source map 显式门禁已修复；唯一 dev-only npm advisory 继续按精确 URL 和 2026-08-31 到期日 fail closed 管理，Owner 为 Tech Lead；
- 仓库级 threat model 已完成，覆盖公网入口、邀请/飞书身份、跨组织/对象授权、不可变业务事实、Worker/Feishu 副作用、CI/GHCR 供应链、可观测和恢复边界；未发现有仓库证据支持的 critical 风险。高优先级残余风险继续由授权负测、身份治理、候选摘要和 release gate 控制。依据 DEC-019，“Alpha 无独立灾备故障域”明确记录为时限风险，而不是假设尚未批准的跨地域方案；见 `muchen-journey-vnext-threat-model.md`。

### 4.1 Alpha 故障卡

| 故障 | 第一动作 | Alpha 恢复证明 | 当前状态 |
| --- | --- | --- | --- |
| DB 不可用/高延迟 | 停止新写并进入维护；保留事务与连接证据 | readiness、migration、约束、关键计数与指纹 | 卡片已定义；真实演练 `NOT_RUN` |
| Web 不可用但 API 正常 | 切维护页或回滚兼容 Web，不动数据库事实 | 三视口、release/readiness、Current Action/Review | 卡片已定义；真实演练 `NOT_RUN` |
| Worker 停滞/backlog | 暂停领取、保护 lease/idempotency，修复后有界重驱 | heartbeat、backlog、attempt 历史且不重复 | 卡片已定义；外部告警演练 `NOT_RUN` |
| Storage/附件故障 | 保持 `ATTACHMENTS_ENABLED=false`；不得临时开放不安全上传 | 无附件 TSK-001 V1 仍可完成闭环 | Alpha 安全禁用 |
| Identity/Feishu 故障 | 停新绑定；已有会话按撤销/轮换合同处理，不降级为 fixture | OAuth state/browser binding、403/404、revoke audit | 真人矩阵部分通过；广泛故障演练 `NOT_RUN` |
| Notification/Feishu 故障 | 业务事实继续提交；不配置接收人，保留 outbox/attempt | 无重复业务事实，恢复后有界投递 | DEC-018 延期，`NOT_RUN` |

## 5. 尚未关闭的 WP-12 门禁

- staging 常规读取和核心命令 p95 ≤1 秒 benchmark、99.5% 试点可用性证据；
- data-rights Operator 流程、受控删除执行器、法律保留/附件对象删除与真实删除证据；
- 每日加密备份、独立故障域副本、空白隔离恢复、RPO ≤24 小时和 RTO ≤4 小时实测；
- staging/production 的 N→N+1→N 或维护模式演练，且不回滚已接受业务事实；
- DB、Web、Worker、storage、identity、notification 故障卡的真实运行演练；
- 精确 RC、release notes、已知问题、值守、审批和候选冻结证明；
- DEC-018 延期项及 production 所需真实观测门禁。

因此当前只能记 `IN_PROGRESS`，不得记 `RC_TECHNICALLY_READY` 或发布 GO。

## 6. 下一步单一 WIP

在不部署、不新增云资源的前提下，下一单一 WIP 是 data-rights Operator 流程和受控数据生命周期执行器；随后准备 staging benchmark 的只读执行合同。独立故障域选型等到 DEC-019 的 30 日成熟检查点再重开。任何真实数据删除、备份目的地、KMS/存储资源、staging 写入或恢复演练均需另行获得精确授权。
