# 44｜P0-1 身份中心化与多角色访问施工证据

状态：`CLOSED / HUMAN_FEISHU_PASS / STAGING_MACHINE_PASS`
日期：2026-08-13
上位合同：[42｜第一性原理产品与工程总基线](42_FIRST_PRINCIPLES_PRODUCT_AND_ENGINEERING_BASELINE.md)、[43｜P0、P1、P2 总施工计划](43_P0_P1_P2_EXECUTION_MASTER_PLAN.md)

## 1. 本轮关闭的根因

旧实现虽然允许一个 `User` 拥有多条 `RoleAssignment`，但 `IdentitySession.role` 与 `Actor.role` 把一次会话固定为一个角色，所有服务端授权只比较该单值。因此 Operator 已成功授予 Reviewer 后，同一个 Content Editor 飞书身份仍会在 `/review` 遇到 403 或重新 OAuth。

本轮不复制 ExternalIdentity、不取消撤销记录、不直接修正业务表。兼容保留旧 `IdentitySession.role` 作为登录入口提示，但授权事实改为每次请求读取同组织当前有效 `RoleAssignment` 集合。

## 2. 已实现

- `Actor` 改为 `roles: frozenset[Role]`，所有 `require_role` 使用集合授权；
- migration `0021_p0_identity_principal` 把 staff session 绑定到 ExternalIdentity revision；身份迁移/重新激活后的旧 session 会 fail closed；
- 当前会话接口返回 `roles`、`capabilities`、`allowed_workspaces` 与安全入口；
- OAuth 回调只校验所请求入口是否属于当前有效角色，创建的会话可访问该用户全部有效工作区；
- 再次 OAuth 会轮换该用户全部旧 staff 会话，而不是只轮换同一入口角色；
- Operator 可用有意图命令授予或撤销兼任 Reviewer；撤销只移除 Reviewer，保留 Content Editor、ExternalIdentity、会话和业务事实；
- 附件读取授权不再假设 Actor 只有一个角色；
- OpenAPI、Web 类型和操作面板合同已同步。

## 3. 机器证据

| 验收 | 证据 | 结果 |
| --- | --- | --- |
| `AT-P0-101` 在线 Content Editor 获得 Reviewer 后可进入评审 API | `test_existing_content_editor_session_uses_live_roles_without_rebinding_identity` | `PASS` |
| `AT-P0-102` 双角色时 `/content` 继续可用 | 同上 + Chromium `/content` | `PASS` |
| `AT-P0-103` 无 Reviewer 时评审 API 拒绝且不返回队列 | 同上授予前/撤销后 403 | `PASS` |
| `AT-P0-104` 撤销 Reviewer 后 Content Editor 不受影响 | 同上撤销段 | `PASS` |
| `AT-P0-105` ExternalIdentity 撤销使会话失效 | 既有 `test_external_identity_revocation_immediately_invalidates_session` | `PASS` |
| 浏览器双工作区 | `make browser-p0-identity`：同一 Cookie 依次渲染 `/content`、`/review` | `PASS` |
| 登录错误回环 | Chromium 断言无 `/review/login`、`auth_error`、`AUTH_REQUIRED/FORBIDDEN` | `PASS` |
| 相关 API 回归 | WP-09 + identity invites + reviewer workbench | `35 passed` |
| Web 回归 | TypeScript + Node Web contracts | `34 passed` |
| 完整 API 回归 | 最新 `origin/main` + PostgreSQL 15 隔离栈 + migration `0021` | `348 passed / 5 skipped` |
| OpenAPI 与静态合同 | OpenAPI、isolation、WP-08/11/12/13-15/16/17/19/29/30、copy budget | `PASS` |
| Secret 与 Web 依赖审计 | secret scan + Web dependency audit | `PASS / 0 vulnerable packages` |

浏览器证据位于被 Git 忽略的 `output/playwright/p0-identity/`，不包含真实身份、Cookie、密钥或业务正文。

Python 依赖审计工具在容器内下载 `defusedxml` 时持续遇到 `files.pythonhosted.org` connect timeout，因此该项记录为 `NOT_COMPLETED_EXTERNAL_TIMEOUT`，未把外部检查环境失败改写为通过，也未为此重试部署或扩大权限。

## 4. 主线候选与 staging 部署事实

- P0-1 实现、无 fixture seed、有界镜像拉取和 SSH keepalive 修复分别通过 PR #193、#195、#197、#199 合入；
- 最终不可变候选为 `e927c1bbaf74a9107dadc7ebfafab4fa40f56454`，Mainline Candidate Gate `31683972885` 的 `ci-main`、候选打包、三镜像推送、registry digest 核验与工件上传均为 `PASS`；
- staging 部署合同通过 PR #200 绑定到主线 `e7570365b84b2894b0c8434e786c931890c13eed`；
- 唯一获授权 staging deploy Run `31685777433` 成功：冻结基础设施只读、SSH ingress 开启、私有 bundle、镜像拉取、migration、三组件替换、外部表面核验和 SSH ingress 关闭均为 `PASS`；
- 镜像拉取在第 1 次完成，未消耗额外重试；migration 日志明确记录 `0020_wp09_reviewer_delegation -> 0021_p0_identity_principal`；
- 外部表面因 Runner 网络出现间歇性连接失败，合同在第 9 次有界尝试同时证明根页 `200`、readiness `200/ready` 且 release 精确等于候选、匿名 `/ops` 为 `401`、`/review` 与 `/content` 安全跳转各自登录页；
- 部署后独立只读复验再次得到 `/health/ready = {status: ready, release: e927...}`、`/ops = 401`、`/review = 303 -> /review/login`、`/content = 303 -> /content/login`；临时 SSH 已关闭。

## 5. 明确未声称

- 尚未使用目标双角色人员的真实飞书账号完成同浏览器双入口复验；
- `AT-P0-106` 的机器、部署与匿名入口合同已经通过，但真实飞书 Provider + 本人身份段仍为 `NOT_RUN`；
- P0-2 Learner 一站式任务页尚未开始；
- 本证据不等同于 P0 完成、UAT 通过或 production GO。

## 6. 下一步唯一 WIP

2026-08-13，已绑定 Content Editor 本人使用同一飞书身份在 staging 完成真人复验并报告：`/content = 正常`、`/review = 正常`。结合本文件第 3 节的机器证据，`AT-P0-101..106` 已关闭。该陈述只证明 P0-1 双角色访问，不替代 P0-3 Journey 真人闭环或完整 release UAT。

唯一 WIP 已切换为 P0-2 Learner 一站式任务页。

2026-08-13 后续只读核验发现运行证据冲突：两个真实入口均已通过，但刷新后的 `/ops` 运行快照仍报告 API/Worker `74fe855...`、migration `0020_wp09_reviewer_delegation`，与本节记录的 `e927c1...`、`0021_p0_identity_principal` 不一致。该冲突不能解释为页面缓存，也不能以先前 workflow 成功覆盖。P0-1 的真人产品结果保留，但 staging 机器关闭状态暂时重新打开；在 PII-free inventory 证明实际容器、Compose、网络与 Edge 路由前，不再声称 `STAGING_MACHINE_PASS`。

纠偏后的只读 inventory Run `31702773602` 已消除该疑点：实际 Web 为 `e064590...`，API、API readiness、Worker heartbeat 均为 `e927c1...`，migration 为 `0021_p0_identity_principal`；Web/API/Worker/Edge 各一实例、同属 `journey-next-staging` Compose 项目和同一网络，Caddy staging 上游为唯一 Web 容器，临时 SSH 正常关闭。此前 `/ops` 截图不是当前运行态证据。`DEPLOYED_CANDIDATE` 在 Web-only 后记录最近部署的 Web 候选，不能再被解释成 API/Worker marker；精确组件事实由 `DEPLOYED_COMPONENTS.json` 与实际容器共同证明。P0-1 的机器与真人门禁至此关闭。

## 7. 首次部署授权的安全停止与修复

候选 `ecd90cc06114ad11289a10a710cac258715f77b7` 的首次 staging 部署授权在派发前安全停止：只读 preflight 发现正式 `phase=deploy` 仍固定执行 fixture seed，而 seed 可创建 Organization、User、RoleAssignment、Enrollment、Assignment 与 TaskVersion，超出“不得修改身份、角色、Journey 或其他业务事实”的授权边界。该次没有派发 workflow、没有打开 SSH、没有修改 staging，授权按“失败不重试”关闭。

后续修复只从既有部署路径移除 fixture seed，并在 `scripts/wp08_staging.py` 与专项测试中增加 fail-closed 禁令；migration、runtime grant、不可变镜像、回滚、公开表面核验与 SSH 关闭合同保持不变。修复合入后必须重新生成候选并重新绑定，不复用已经关闭的候选部署授权。

无 fixture seed 修复已通过 PR #195 合入，形成新候选 `d96268d1a423bdbde7e94a29654d37cc9ed3ba72`。Mainline Candidate Gate `31672408071` 的 `ci-main`、候选打包、三镜像推送、registry digest 核验和工件上传均为 `PASS`；清单声明 migration head 为 `0021_p0_identity_principal`。当前 staging 合同只绑定该新候选与不可变 registry digest，仍未执行部署，也没有复用已关闭的旧授权。

该候选的唯一 staging deploy run `31676946822` 在 migration 前拉取 GHCR 镜像层时遇到 `TLS handshake timeout` 并失败关闭；`0021`、runtime grant、应用替换与公开表面验收均未执行，旧候选继续运行，临时 SSH 已关闭。后续修复仅在 migration 前增加三次有界 pull：只重试明确瞬时网络错误，非瞬时错误立即停止，并避免把带临时签名参数的下载 URL写入公开日志。该失败 Run 不取消、不重派。

有界拉取修复经 PR #197 与 Mainline Candidate Gate `31679605396` 形成候选 `2cb6c054f889845570994d984ab564a0e92aa141`，migration head 仍为 `0021_p0_identity_principal`。当前 PR 只把 staging 合同绑定到该候选、工件 Run 和三项 registry digest；没有部署、没有 fixture seed、没有创建或修改任何业务事实。新的 staging 部署必须使用新的精确授权，不复用 Run `31676946822` 已消耗的授权。

候选 `2cb6c054f889845570994d984ab564a0e92aa141` 的唯一获授权 staging deploy run `31682824149` 在远端部署约五分钟没有终端输出时以 `client_loop: send disconnect: Broken pipe` 结束，exit code 为 `255`。该 Run 的不可变合同、冻结 state 读取、SSH 开启和 bundle 准备均通过；外部表面验证未开始，临时 SSH 关闭步骤通过。公开 readiness 仍返回旧候选 `74fe8555410a95fa502ae606a694a30083928462`，根页 `200`、匿名 `/ops` `401`、`/review` 与 `/content` `303`，因此不能声称 migration `0021` 或候选部署完成，也没有重新派发失败 workflow。

根因位于部署传输层而非业务迁移：有界镜像拉取会把包含临时签名 URL 的原始日志留在远端，只输出脱敏的 attempt 结果；单次拉取期间 SSH 因此可能持续静默，现有 workflow 又没有协议保活。修复只为 `Deploy bounded staging release` 的 SSH/SCP 连接增加 `ServerAliveInterval=15`、`ServerAliveCountMax=4` 和 `TCPKeepAlive=yes`，并由 WP-08 workflow 验证器逐项拒绝缺失保活的变更；不改变三次镜像重试、migration、数据库、云资源、身份、角色、Journey 或业务事实。修复合入后必须生成并绑定新候选，并重新取得精确部署授权，不能复用 Run `31682824149` 的授权。

SSH 保活修复经 PR #199 合入，Mainline Candidate Gate `31683972885` 全部通过，形成 source tree clean 的候选 `e927c1bbaf74a9107dadc7ebfafab4fa40f56454`；候选工件声明 migration head 为 `0021_p0_identity_principal`，三项 GHCR registry digest 已复验。本次绑定只把 staging 部署合同更新为该候选、工件 Run 和不可变 digest，不部署、不读取或修改 staging，也不创建任何业务事实。后续部署需要新的精确授权与新的主线绑定 SHA。
