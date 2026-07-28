# Muchen Journey vNext 安全最佳实践报告

日期：2026-07-28

范围：当前 Greenfield 仓库的 Python/FastAPI、Next.js/React、staging Compose 与供应链门禁

结论：第一批检查发现 1 项 Sev-2 配置缺口和 2 项 Sev-3 硬化缺口，均已在当前变更中修复；另有 1 项有界、dev-only 的依赖例外仍需在 2026-08-31 前关闭。该报告不替代 WP-12 威胁模型、物理恢复、性能或 production 验收，production 继续 `NO_GO`。

## Sev-1

未发现可由当前仓库证据支持的 Sev-1 问题。

## Sev-2

### SEC-001｜禁用附件时非本地环境可能接受公开的本地默认密钥（已修复）

- Rule ID：PYTHON-CONFIG-FAIL-CLOSED / SECRET-NO-DEFAULT
- Severity：Sev-2
- Location：`apps/api/journey_api/config.py:77-100`；回归测试 `tests/test_config.py:99-112`
- Evidence：原校验把 staging/production 的公开本地默认 session、invite、import 和 identity secret 拒绝逻辑错误地放在 `attachments_enabled` 条件内。DEC-017 要求 Alpha 固定 `ATTACHMENTS_ENABLED=false`，因此应用层可能在附件关闭时绕过该拒绝；当前真实 staging secret 已独立配置，没有证据表明已发生利用。
- Impact：若未来部署遗漏真实 secret，攻击者可从公开仓库获知默认值，并可能伪造或破解会话、邀请、离线导入签名或外部身份 subject。
- Fix：非本地默认密钥拒绝现只取决于 `APP_ENV in {staging, production}`，与附件功能开关完全解耦；新增附件关闭条件下的负向测试。
- Mitigation：部署 bundle 仍校验独立 secret，GitHub Environment 持有实际值；候选部署前必须同时通过配置回归和 secret scan。
- False positive notes：不是已发生的 staging 凭据泄露；它是会在错误配置时放大为身份边界失守的 fail-open 代码缺口。

## Sev-3

### SEC-002｜应用容器缺少显式运行时最小权限（已修复）

- Rule ID：CONTAINER-NO-NEW-PRIVILEGES / CONTAINER-DROP-CAPS
- Severity：Sev-3
- Location：`deploy/staging/compose.yaml:13-18,21-65`；门禁 `scripts/wp12_candidate_hardening.py:15-29`
- Evidence：API/Web/Worker 镜像本身以非 root 用户运行，但 staging Compose 原先未显式禁止权限提升、未清空 Linux capabilities，也没有 PID 上限。
- Impact：应用或依赖一旦被利用，容器内横向动作和资源耗尽空间会高于必要范围。
- Fix：三个应用服务统一启用 `no-new-privileges:true`、`cap_drop: ALL` 和 `pids_limit: 256`；边缘代理因绑定低端口的能力需求未被本变更盲目套用。
- Mitigation：镜像继续使用非 root 用户，数据库不对公网发布端口，应用只使用必要的只读 CA volume。
- False positive notes：该问题不是容器逃逸证据，而是缺失 defense-in-depth；edge 的能力边界需要独立验证后再收窄。

### SEC-003｜生产浏览器 source map 策略依赖框架默认值（已修复）

- Rule ID：NEXTJS-CLIENT-SOURCEMAP-DISABLED
- Severity：Sev-3
- Location：`apps/web/next.config.ts:3-9`；构建扫描 `Makefile:57-64`
- Evidence：构建产物当时未发现浏览器 source map，但配置没有显式锁定，后续框架或构建变更可能在无人察觉时发布映射文件。
- Impact：source map 可能降低攻击者理解客户端代码、内部路径和错误处理的成本；它通常不是独立漏洞，但会扩大信息暴露。
- Fix：显式设置 `productionBrowserSourceMaps: false`，并在每次生产 Web build 后拒绝 `.next/static` 下任何 `.map` 文件。
- Mitigation：CSP nonce、`strict-dynamic`、无第三方脚本和无危险 DOM sink 的现有门禁继续保留。
- False positive notes：当前没有发现已发布 source map；这是把隐含默认值升级为可机器验证的发布合同。

### SEC-004｜一个 dev-only npm advisory 仍在限时例外内（开放）

- Rule ID：SUPPLY-CHAIN-BOUNDED-WAIVER
- Severity：Sev-3
- Location：`scripts/web_dependency_audit.py:16-18,66-87,115-121`
- Evidence：`make dependency-audit` 返回 `vulnerability_packages=9 waived_advisories=1 scope=dev-only waiver_expires=2026-08-31`；唯一 advisory 为 `GHSA-mh99-v99m-4gvg`。脚本逐节点确认影响仅为 dev dependency，任何新增 advisory、生产节点、范围扩大或到期都会 fail closed。Python audit 返回无已知漏洞。
- Impact：恶意或异常输入在受影响的开发工具链路径中可能造成拒绝服务；没有证据表明它进入生产运行时。
- Fix：Owner：Tech Lead；最迟 2026-08-31 升级上游依赖并删除精确 waiver，随后重新执行 lint、typecheck、build 和 dependency audit。
- Mitigation：CI 锁文件安装、精确 advisory URL、dev-only 节点验证、到期日和生产镜像最小化限制暴露范围。
- False positive notes：不是零风险，也不是生产漏洞豁免；它是受工程规则约束且会自动到期的临时接受项。

## 已核验的正向控制

- FastAPI 在非本地环境关闭 OpenAPI/Docs，并使用受信 Host、中间件级请求标识和结构化脱敏日志；
- session cookie 使用 Secure/HttpOnly/SameSite，写操作重鉴权并校验 CSRF；组织、角色和对象 scope 在服务端强制执行；
- CSP 使用逐请求 nonce，生产不启用 `unsafe-inline`；未发现 `dangerouslySetInnerHTML`、`eval`、浏览器 token storage 或第三方脚本；
- 镜像和 GitHub Actions 固定版本/摘要，候选生成 SBOM；gitleaks 未发现 secret，Python audit 未发现已知漏洞。

## 尚未由本报告关闭

- 仓库级 threat model 尚未完成；依据 DEC-019，必须把 Alpha 暂无独立灾备故障域作为显式、限时的已接受风险，不得假设尚未批准的跨地域方案；
- staging 性能/SLO、保留与删除任务、异机加密备份和空白恢复、RPO/RTO、N↔N+1 回滚尚未实测；
- DEC-018 延期的 TLS 外部采集、真实通知和告警演练继续为 `NOT_RUN`；有界主机审计只适用于 Alpha 临时观测；
- production 在上述物理门禁及审批关闭前保持 `NO_GO`。
