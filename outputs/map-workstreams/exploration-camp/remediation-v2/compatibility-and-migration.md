# 兼容性与迁移

状态：`ZERO_DATA_MIGRATION / VIEW_ONLY_PATCH`

## 兼容性

本修复只增加 `/join` 的服务端可见上下文和表单可访问性关联：

- 现有 `/join#token=…` 链接无需重发或改写；
- `readFragmentToken`、`useSyncExternalStore` 与 `history.replaceState(null, "", "/join")` 保持原样；
- `exchangeInvite` 继续只从 fragment/完整链接提取 token，并向 `/api/v1/join/exchange` 提交；
- Join Context、CSRF、identity confirm、session 轮换和 redirect `/app` 保持原样；
- JOIN 与 REENTRY 继续共享现有 API，但定向文案按 phase 分开；
- 无 JavaScript 首屏仍能看见五地图、探索营起点和页面下一步；token 交换仍需现有 hydration；
- 现有屏幕阅读器、键盘、触摸和 reduced-motion 行为不增加交互分支。

## 数据与业务迁移

迁移数量：`0`。

不得新增或修改数据库 migration、API schema、cookie、邀请表、User、RoleAssignment、Enrollment、
Assignment、Submission、Review、Evaluation、Outcome、Evidence、Progress 或审计事实。不得从旧点击或
历史邀请推断新 People AI 事实。

## 回滚

运行时补丁可按同一候选提交整体回滚五个文件，不需要数据库回滚、数据清理或邀请重发。回滚后旧 P1
会恢复，因此回滚只表示恢复旧技术状态，不表示产品门槛通过。

## 并发与所有权

- `apps/web/src/app/page.tsx`、首页专属 CSS 与 `product-entry-contract.test.mjs` 由
  `shared-home-whole-journey-entry` 独占，本补丁不得修改。
- 新 CSS 必须使用 `/join` 局部 CSS module，禁止在 `globals.css` 增加或改写首页/共享选择器。
- 新测试使用独立文件，`npm test` 会自动通过 `scripts/*.test.mjs` 收集；不修改共享首页测试。
- 总控合入前需与当前 `/join` 未提交候选逐文件核对，保留已有 token、安全表单和 pending 行为。
