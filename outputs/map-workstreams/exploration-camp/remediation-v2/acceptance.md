# Remediation V2 验收标准

状态：`DEFINED / NOT_RUN`

## A. 契约与冻结

- [ ] 仍绑定 `exploration-camp-first-meaningful-action`；不存在第二条活动黄金路径。
- [ ] `a9381f0944fb4c8c852c115e3bc708363ac67a37`、旧候选清单与旧证据未改写。
- [ ] 实际 diff 只包含 `runtime-write-set.json` 中五个文件。
- [ ] 首页、首页专属 CSS、共享首页测试、Server Actions、API、migration 与 config 零 diff。

## B. 内容与一个主操作

对 `FRAGMENT_PRESENT_UNEXCHANGED`、`NO_FRAGMENT_MANUAL_RECOVERY`、`JOIN_CONTEXT_READY`、
`REENTRY_CONTEXT_READY`、pending 和 error 状态逐一验证：

- [ ] 第一个表单主操作之前可见“5 张地图”“探索营”“现在/随后”的真实说明。
- [ ] 定向块零交互、零 tab stop、零未来地图入口。
- [ ] 每个可操作状态恰好一个 `.button.primary`，按钮文案与 phase 相符。
- [ ] JOIN 不把 re-entry 写成重新开始；REENTRY 不承诺打开第一份材料。

## C. Token、身份与事实连续性

- [ ] 真实格式本地合成邀请仍为 `/join#token=…`；未改 query 参数。
- [ ] hydration 后 `location.hash === ""`，`location.search === ""`。
- [ ] token 不出现在 `document.body.innerText`、截图、console、错误或服务端日志证据。
- [ ] 同一 token 首次交换成功，重复交换仍按现有合同拒绝。
- [ ] JOIN 创建原有一组身份/Enrollment/Assignment 事实；REENTRY 不创建新的这些事实。
- [ ] 缺失/错误 CSRF 仍拒绝，正确 CSRF 才允许 confirm；组织与角色边界不变。

## D. 浏览器机器验收

使用本地 `SYNTHETIC_NO_REAL_PII` fixture，从私密邀请自然走到首份必读材料：

- [ ] 390×844、768×1024、1280×900 均无横向溢出、无遮挡主操作。
- [ ] 自然路径不手动访问 `/`，仍能在 `/join` 看见五地图、探索营起点和下一步。
- [ ] 键盘 Tab/Enter、触摸 click、pending、无效/过期、re-entry 和刷新恢复都有一个清楚下一步。
- [ ] `prefers-reduced-motion: reduce` 下无新增运动；本组件默认不含动画。
- [ ] 终点第一份 required material 可见，作答区仍在输入之后。
- [ ] console 0 error / 0 warning。
- [ ] `npm run lint`、`npm run typecheck`、`npm test`、production build 与相关 API 身份/邀请测试通过。

## E. 真人门槛

运行时机器验收通过后，仍须使用权威真人模板重新执行原四项标准：

- 3/3 在 10 秒内说出五地图、探索营起点与下一步；
- 3/3 在 60 秒内打开首份材料；
- 进度清晰度和继续意愿中位数分别 ≥4/5；
- 主持人介入总数 0。

当前全部 `NOT_RUN`。合同通过、源代码测试、浏览器自动化或模型评估均不得替代真人结果。
