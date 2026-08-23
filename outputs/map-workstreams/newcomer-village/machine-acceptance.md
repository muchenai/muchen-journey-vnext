# 新手村机器验收记录

候选：`newcomer-village-first-real-integration-action`  
状态：`READY_FOR_HUMAN`（候选冻结；真人证据 `NOT_RUN`）  
入口：`/prototypes/newcomer-village/index.html`

## 机器结论

地图契约的 7 条机器标准均通过：每一状态只有一个视觉主动作；上下文先于行动；真实行动自述先于证据表单；回执具备最小字段与隐私边界；390/768/1280 无文档级横向溢出；校验、键盘、reduced motion、未完成草稿恢复与重启可用；原型没有业务数据网络请求或共享事实写入。

静态合同测试为 `6/6 PASS`。浏览器遍历中，390 与 1280 均从起点到证据回执；768 核对上下文与行动选择状态。控制台为 `0 errors / 0 warnings`。全部网络请求仅为本地 `index.html`、共享视觉 token CSS、地图 CSS 与地图 JS 静态资源。

## 代表证据

- `browser-evidence/1280-arrival.png`：桌面起点、探索营真人未验证警示、唯一主动作。
- `browser-evidence/1280-receipt.png`：桌面本地证据回执与共享写入边界。
- `browser-evidence/768-context.png`：中屏只读基线、岗位/组织字段及事实边界。
- `browser-evidence/768-action.png`：中屏三选一真实行动与时间计划。
- `browser-evidence/390-arrival.png`：移动起点和可达主动作。
- `browser-evidence/390-receipt.png`：移动回执，无横向溢出。
- `browser-evidence/manifest.json`：尺寸、SHA-256 与机器检查摘要。

## 未触碰门槛

机器证据不能证明目标新人能理解输入来源、独立形成行动卡、实际完成工作互动、写出可接受证据，或愿意继续。契约中的 5 条真人标准均未运行，因此候选必须冻结，不能晋级、集成或发布。
