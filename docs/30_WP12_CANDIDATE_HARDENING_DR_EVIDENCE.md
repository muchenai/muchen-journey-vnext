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

最终 PR 仍必须通过远端 required `WP-07 / quick`；合并后主线全量门禁与候选摘要才是 canonical 证据。

## 4. 当前安全结论

- Sev-1：未发现；
- Sev-2：1 项非本地默认密钥 fail-open 已修复并回归；
- Sev-3：容器运行时最小权限和 source map 显式门禁已修复；唯一 dev-only npm advisory 继续按精确 URL 和 2026-08-31 到期日 fail closed 管理，Owner 为 Tech Lead；
- 仓库级 threat model 已完成，覆盖公网入口、邀请/飞书身份、跨组织/对象授权、不可变业务事实、Worker/Feishu 副作用、CI/GHCR 供应链、可观测和恢复边界；未发现有仓库证据支持的 critical 风险。高优先级残余风险继续由授权负测、身份治理、候选摘要和 release gate 控制。依据 DEC-019，“Alpha 无独立灾备故障域”明确记录为时限风险，而不是假设尚未批准的跨地域方案；见 `muchen-journey-vnext-threat-model.md`。

## 5. 尚未关闭的 WP-12 门禁

- staging 常规读取和核心命令 p95 ≤1 秒 benchmark、99.5% 试点可用性证据；
- 3 年/1 年/180 天/30 天数据保留任务和 30 天删除/纠错流程；
- 每日加密备份、独立故障域副本、空白隔离恢复、RPO ≤24 小时和 RTO ≤4 小时实测；
- N→N+1→N 或维护模式演练，且不回滚已接受业务事实；
- DB、Web、Worker、storage、identity、notification 故障卡；
- 精确 RC、release notes、已知问题、值守、审批和候选冻结证明；
- DEC-018 延期项及 production 所需真实观测门禁。

因此当前只能记 `IN_PROGRESS`，不得记 `RC_TECHNICALLY_READY` 或发布 GO。

## 6. 下一步单一 WIP

在不部署、不新增云资源的前提下，下一单一 WIP 是保留/删除任务和基础恢复校验的可测试实现；同时准备 staging benchmark 与回滚合同。独立故障域选型等到 DEC-019 的 30 日成熟检查点再重开。任何真实备份目的地、KMS/存储资源、staging 写入或恢复演练均需另行获得精确授权。
