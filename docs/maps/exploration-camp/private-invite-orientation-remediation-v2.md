# 探索营私密邀请定向修复契约 V2

状态：`IMPLEMENTATION_READY_CONTRACT / RUNTIME_NOT_IMPLEMENTED`

本契约修复当前唯一黄金路径 `exploration-camp-first-meaningful-action` 的 P1 叙事连续性阻断，
不创建第二条黄金路径。冻结基线 `a9381f0944fb4c8c852c115e3bc708363ac67a37`、旧候选清单、
旧浏览器证据和真人门禁保持原样。

权威黄金路径仍为 `config/muchen_journey_product.json#/current_golden_path`：

- 起点：`private-invitation-entry`；
- 终点：`first-required-learning-material-opened`；
- 路由：`/`、`/join`、`/app`；
- 真人 10 秒门槛：3/3 能说出 Journey 有五张地图、当前从探索营开始、下一步做什么。

## 修复结果

自然私密邀请打开 `/join#token=…` 后，Learner 在执行第一个主操作前就能看见并复述：

1. Muchen Journey 由五张地图组成；
2. 当前从第 1 张地图“探索营”开始；
3. 现在执行页面唯一主操作，随后进入探索营并打开第一份必读材料。

定向信息是非交互上下文，不增加第二个按钮、地图导航或未来地图入口。现有表单按钮继续是页面
唯一主操作：验证前为“验证专属邀请”，身份确认阶段为“开启旅程”，re-entry 为“继续旅程”。

## 不可改变的不变量

- 邀请继续使用 `/join#token=…` fragment；不得改为 query、服务端日志参数或持久化明文。
- Client hydration 后继续立即用 `history.replaceState` 清除 fragment；正文、错误、console、network
  证据和截图不得出现 token。
- `/api/v1/join/exchange`、一次性交换、Join Context、session cookie、CSRF cookie 和
  `/api/v1/identity/confirm` 语义不变。
- 现有身份、角色、权限、组织隔离、Enrollment、Assignment、re-entry 和审计事实不变。
- 不迁移、不回填、不重发旧邀请；不改写已接受事实。
- `/`、`apps/web/src/app/page.tsx`、首页专属 CSS 与
  `apps/web/scripts/product-entry-contract.test.mjs` 保持只读。
- Person、Capability、Evidence、Progress、Identity 共享事实源保持只读。

## 实施边界

总控只需修改 `/join` 展示层并新增专用合同测试。精确文件、内容结构、兼容性、迁移和验收见：

- `outputs/map-workstreams/exploration-camp/remediation-v2/contract.json`
- `outputs/map-workstreams/exploration-camp/remediation-v2/content-structure.md`
- `outputs/map-workstreams/exploration-camp/remediation-v2/compatibility-and-migration.md`
- `outputs/map-workstreams/exploration-camp/remediation-v2/acceptance.md`
- `outputs/map-workstreams/exploration-camp/remediation-v2/controller-runtime-patch.md`

本契约通过只表示实现输入齐全，不表示运行时存在、机器通过或真人通过。
