# 45｜P0-2 Learner 一站式任务页施工合同

状态：`WEB_STAGING_PASS / RUNTIME_TRUTH_RECONCILIATION_IN_PROGRESS / HUMAN_TEST_NOT_RUN`
日期：2026-08-13
上位合同：[42｜第一性原理产品与工程总基线](42_FIRST_PRINCIPLES_PRODUCT_AND_ENGINEERING_BASELINE.md)、[43｜P0、P1、P2 总施工计划](43_P0_P1_P2_EXECUTION_MASTER_PLAN.md)

## 1. 用户结果

新人进入任一站后，不需要研发或运营解释，5 秒内能说出：

1. 当前要得到什么；
2. 先打开哪些学习材料；
3. 完成材料后要提交什么；
4. 页面当前唯一可执行动作。

页面固定按“当前站 → 学习输入 → 默认可见的要求 → 输出 → 唯一提交动作 → 完成反馈”组织。空白输入区不得先于材料和要求出现。

## 2. 当前代码真实基线

已具备：

- 学习材料早于输出区；
- HTTPS 材料具有独立可点击动作；
- 必读材料按顺序解锁；
- 路线节点和线路共享 SVG 坐标源；
- `/review`、`/content` 已有无会话登录页。

本轮施工前仍需修正：

- “如何完成/完成标准”仍默认折叠，首次进入无法直接看见任务要求；
- 页面存在“先完成输入/学习材料/完成当前材料/小任务自动出现”等重复解释；
- 表单同时突出“提交”和“保存草稿”，不满足一个主动作的视觉层级；
- P0-2 没有覆盖八站真实数据的可点击材料清单与首次展开证据；
- 没有 390/768/1280 的路线几何自动断言；
- 会话过期、邀请失效和服务失败的恢复路径没有统一的浏览器验收矩阵；
- 三名未看说明新人的 5 秒理解测试尚未执行。

本轮实现已将任务要求移出折叠区、删除重复锁定文案，并为路线节点增加可测量的共享坐标锚点；最终状态以第 4 节机器矩阵和真人测试为准，不能以代码完成替代产品通过。

## 3. 页面合同

### 3.1 首屏

- 只保留站点身份、结果导向标题和预计用时；
- 当前材料是唯一主动作；完成材料后，任务输出成为唯一主动作；
- 不使用“进入这一站”“完成本阶段”等重复按钮或标题。

### 3.2 学习输入

- 外部材料显示标题、来源、预计时长和“打开材料”；
- 原始 URL 不作为正文展示；
- 每个必读材料必须可从真实 Journey V3 UI 打开；
- 未完成材料时不渲染输出框。

### 3.3 任务要求

- 首次进入默认可见；
- 显示一句结果、3–5 条要求和完成标准；
- 完成材料或已有草稿后允许折叠，但始终保留明确入口；
- 不重复显示 purpose、outcome、deliverables、instructions 的同义句。

### 3.4 输出与动作

- 输出区只在学习输入完成后出现；
- 主 CTA 只可能是“开始小任务”“提交/提交修订”之一；
- “保存草稿”为次级动作，视觉不可与主 CTA 竞争；
- 提交后明确展示事实已保存、等待对象和下一步。

### 3.5 恢复

- 会话过期：说明事实仍保留，并提供安全重新进入动作；
- 邀请无效/过期：不创建新事实，提供联系运营/新邀请动作；
- 服务失败：不裸露 JSON，保留 request ID 和重试/返回动作。

## 4. 自动化验收

| 编号 | 自动化证据 | 退出条件 |
| --- | --- | --- |
| `AT-P0-202` | 八站生产等价结构 fixture/browser matrix + 正式内容源人工核验 | 机器证明每站材料均为 HTTPS 可点击动作；真人证明已发布 Journey V3 的真实材料可打开 |
| `AT-P0-203` | 首次进入八站 browser matrix | 要求与完成标准默认可见，输出区仅在材料完成后出现 |
| `AT-P0-204` | DOM copy budget + CTA hierarchy | 无重复动作；每状态至多一个 primary CTA |
| `AT-P0-205` | Chromium 390/768/1280 geometry | 所有可见节点中心在线路容差内，无横向溢出 |
| `AT-P0-206` | browser recovery matrix | 三类失败均有可执行恢复动作且无裸 JSON |

`AT-P0-201` 必须由三名未看说明的真实新用户完成，自动化不得替代。

## 5. 停止边界

- 不修改 Journey V3 内容事实、身份、角色、邀请或评审事实；
- 不新增 CMS、附件、通知、AI 判断或第二 Learner 首页；
- 不为了测试美观伪造与真实八站不同的页面结构；
- 若 5 秒测试需要口头解释，记录失败并修正页面，不培训测试者。

## 6. 2026-08-13 机器证据

已通过：

- Web：39 项合同测试、TypeScript、ESLint；
- Chromium：八站依次完成学习输入与首次要求可见检查；390/768/1280 三档路线节点中心与共享线路坐标误差不超过 1.5 px，且无横向溢出；
- 动作层级：旅程页及八站首次进入状态均只有一个可见 primary CTA；
- 恢复矩阵：无效邀请、服务失败、旧会话失效均展示边界和恢复动作，不出现原始 API JSON；
- 闭环回归：八站提交、Reviewer 要求修订、新浏览器重新进入、再次提交、通过与最终结果完成；
- 清理：隔离容器、网络和数据卷均已删除。

证据边界：浏览器夹具只证明与生产相同的八站结构、状态机和 HTTPS 链接呈现，不证明已发布 Journey V3 外部材料当前可达；`AT-P0-202` 仍需正式内容源人工打开核验。`AT-P0-201` 三名新人 5 秒测试同样保持 `NOT_RUN`，因此 P0-2 尚未关闭，也不得开始 P0-3。

## 7. 2026-08-13 staging 候选绑定

PR #202 合入主线后，Mainline Candidate Gate `31693205762` 完整通过 `ci-main`、候选打包、三镜像推送、registry digest 核验和工件上传，形成 source tree clean 候选 `e064590049eecc05ad8db26e9ba94f51420d7397`。候选 migration head 仍为 `0021_p0_identity_principal`，没有新增 migration。

本次变更只把 WP-08 staging 的不可变候选、工件 Run 与三项 registry digest 绑定到上述证据；不部署、不读取或修改 staging、不运行 Terraform plan/apply/import、不创建邀请、不发送消息，也不修改 Journey、身份、角色或其他业务事实。绑定 PR 合入后，staging 部署仍必须作为单独动作执行；在部署和真人核验发生前，P0-2 状态保持 `MACHINE_PASS / HUMAN_5_SECOND_TEST_NOT_RUN`。

## 8. 首次 staging 部署失败与范围收敛

唯一一次全量部署 Run `31694785627` 在 `Deploy bounded staging release` 失败。三次镜像拉取均在合同规定的 8 分钟边界内返回 `COMMAND_TIMEOUT`；外部 readiness 始终保持旧候选 `e927c1bbaf74a9107dadc7ebfafab4fa40f56454`，没有发生部分切流，`Close SSH ingress` 为 `PASS`。因此该 Run 不重试。

候选 `e064590049eecc05ad8db26e9ba94f51420d7397` 相对其直接父提交仅修改 Learner Web、Web 浏览器合同和治理证据；相对当前健康基线 `e927c1bbaf74a9107dadc7ebfafab4fa40f56454`，`apps/api/`、`apps/worker/`、`contracts/openapi.json` 与 `migrations/` 均无差异。后续部署范围收敛为 `deploy-web`：只拉取并替换候选 Web 镜像，API、Worker、migration、身份、角色、Journey 和业务事实保持基线；执行前后均核验基线运行态，失败自动回退 Web。P0-2 仍保持 `MACHINE_PASS / STAGING_NOT_UPDATED / HUMAN_5_SECOND_TEST_NOT_RUN`。

## 9. Web-only staging 部署证据

Web-only 部署合同通过 PR #204 合入主线 `7bcabf190fa41aa84fb2d129fca6c0af18903ab1`。唯一一次 `deploy-web` Run `31698795418` 成功完成：

- 不可变合同确认候选 Web 为 `e064590049eecc05ad8db26e9ba94f51420d7397`，API/Worker 基线保持 `e927c1bbaf74a9107dadc7ebfafab4fa40f56454`；
- 仅候选 Web 镜像在第 2 次有界拉取成功，第 1 次明确归类为 `TRANSIENT_NETWORK`；
- `WP08_WEB_ONLY_DEPLOY=PASS`，migration 保持 `0021_p0_identity_principal`，未执行 Terraform plan/apply/import、DNS 或云资源写入；
- 外部表面在第 6 次有界尝试全部通过：根页 `200`、readiness `200/ready` 且 release 精确为 `e064590...`、匿名 `/ops` 为 `401`、`/review` 与 `/content` 均 `303` 跳转各自登录页并带 `no-store`；
- `WP08_SSH_INGRESS=CLOSED`，临时 SSH 已关闭；
- 部署后的独立只读复验再次得到相同 release 与路由结果。

P0-2 的机器实现和 staging 交付至此关闭。产品验收仍保留两项人工事实：逐一打开已发布 Journey V3 的真实外部材料，以及由三名未看说明的新 Learner 完成 5 秒理解测试。在两项均通过前，不把 P0-2 记为关闭，也不进入 P0-3。

部署后刷新两个独立的已登录 `/ops` 会话，运行快照均报告 API/Worker `74fe855...` 与 migration `0020_wp09_reviewer_delegation`，而 Web-only 部署日志声称所保留基线为 API/Worker `e927c1...` 与 migration `0021_p0_identity_principal`。公开 readiness 只能证明 Web `e064590...`，不能证明其实际连接的后端版本。该矛盾存在期间暂停真人 P0-2 测试，先通过扩展后的 PII-free `inspect-runtime` 对账三组件 marker、实际容器、Compose 元数据、网络别名和 Caddy 上游；不部署、不改库、不修改业务事实。

首次扩展 inventory Run `31702193785` 发现 `DEPLOYED_CANDIDATE` 与 `DEPLOYED_COMPONENTS` 的 API/Worker marker 不一致后立即停止，未输出实际容器清单；临时 SSH 正常关闭。marker 不一致正是待诊断事实，不应阻断实际容器只读盘点，因此后续审计器把各 marker 关系作为布尔结果输出，同时继续读取实际容器；仍不修 marker、不改变运行态。
