# 总控可实施运行时补丁说明

状态：`PATCH_SPEC_READY / CODE_NOT_WRITTEN`

## 精确写入文件

1. 修改 `apps/web/src/app/join/page.tsx`。
2. 修改 `apps/web/src/app/join/invite-token-exchange-form.tsx`。
3. 新增 `apps/web/src/app/join/private-invite-orientation.tsx`。
4. 新增 `apps/web/src/app/join/private-invite-orientation.module.css`。
5. 新增 `apps/web/scripts/exploration-camp-private-invite-orientation-contract.test.mjs`。

除此之外不需要运行时写入。

## 1. `private-invite-orientation.tsx`

实现纯展示 Server Component：

```tsx
type OrientationPhase = "VERIFY_INVITE" | "CONFIRM_IDENTITY" | "REENTRY";

export function PrivateInviteOrientation({
  phase,
  descriptionId,
}: {
  phase: OrientationPhase;
  descriptionId: string;
}) {
  // phase 只选择 content-structure.md 中的“现在/随后”文案。
  // 输出 aside/section + p + h2 + dl；不得输出任何交互元素。
}
```

组件必须包含固定 `01 / 05`、五地图、探索营起点；phase 只控制“现在/随后”，不控制安全或业务状态。

## 2. `page.tsx`

- 定义稳定 id：`join-whole-journey-next-action`。
- `summary === null` → `VERIFY_INVITE`。
- `summary?.flow === "JOIN"` → `CONFIRM_IDENTITY`。
- `summary?.flow === "REENTRY"` → `REENTRY`。
- 在现有 H1 后、error 与 `summary ? ... : ...` 之前渲染组件。
- 身份确认 `<form action={confirmIdentity}>` 增加
  `aria-describedby="join-whole-journey-next-action"`。
- 调用 `<InviteTokenExchangeForm orientationDescriptionId={...} />`。
- 其余 cookie 解析、错误、字段、按钮、action 与 redirect 不变。

## 3. `invite-token-exchange-form.tsx`

- props 新增 `orientationDescriptionId: string`。
- token 缺失与 token 已读取两个 `<form>` 都设置
  `aria-describedby={orientationDescriptionId}`。
- `capturedToken`、fragment 读取、`history.replaceState`、hidden input、完整链接输入、按钮与 action 不变。

## 4. CSS module

只定义组件局部 class：容器、eyebrow、标题、说明、facts、nextAction。要求：

- 390px 不溢出，长中文可换行；
- 颜色使用现有 CSS variables 或当前 join 色值；
- 不定义 animation、transition、fixed/absolute overlay；
- 不导入或改写 `.landing-*`、`.button`、`.join-token-form` 等全局选择器；
- 事实块在 390 为单列，在 ≥768 可为两列，但阅读顺序不变。

## 5. 专用合同测试

新测试直接读取上述两个 TSX 与 CSS module，至少断言：

- 固定内容包含 `01 / 05`、`五张地图`、`探索营`、`第一份必读材料`；
- 三个 phase 和对应的真实文案均存在；
- orientation 组件源码不含 `<a`、`<button`、`<input`、`<form` 或 `tabIndex`；
- page 在 `summary` 分支之前渲染 orientation，并把同一 description id 传给两类表单；
- invite form 两个分支均有 `aria-describedby`，且原 fragment/history 安全代码仍存在；
- CSS module 不含 animation/transition、`.landing-` 或全局 `.button` 选择器；
- 共享首页文件与共享首页测试不在该提交 diff 中。

合同测试只是快速防漂移；完整浏览器与 API 回归仍按 `acceptance.md` 执行。
