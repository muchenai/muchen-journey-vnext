# 44｜P0-1 身份中心化与多角色访问施工证据

状态：`IMPLEMENTED_LOCAL / STAGING_NOT_DEPLOYED / HUMAN_FEISHU_NOT_RUN`
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

## 4. 明确未声称

- 尚未部署 staging；
- 尚未使用真实飞书账号执行 OAuth；
- `AT-P0-106` 只有本地真实 Chromium 的完整 Cookie/路由证据，真实飞书 Provider 段仍为 `NOT_RUN`；
- P0-2 Learner 一站式任务页尚未开始；
- 本证据不等同于 P0 完成、UAT 通过或 production GO。

## 5. 下一步唯一 WIP

通过 PR 合入并部署 staging 后，仅使用已绑定 Content Editor 本人执行一次飞书登录：先确认 `/content`，再在同一浏览器直接打开 `/review`。两端均通过后关闭 P0-1 真人门禁，再启动 P0-2。
