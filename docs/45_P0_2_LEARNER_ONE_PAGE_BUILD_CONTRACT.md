# 45｜P0-2 Learner 一站式任务页施工合同

状态：`WEB_STAGING_PASS / MATERIALS_15_OF_15_PASS / HUMAN_3_PERSON_TEST_NOT_RUN`
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

证据边界：浏览器夹具只证明与生产相同的八站结构、状态机和 HTTPS 链接呈现；已发布 Journey V3 外部材料的真实可达性证据见第 10 节。`AT-P0-201` 三名新人 5 秒测试保持 `NOT_RUN`，因此 P0-2 尚未关闭，也不得开始 P0-3。

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

P0-2 的机器实现和 staging 交付至此关闭。真实外部材料验收已于第 10 节关闭；产品验收只剩三名未看说明的新 Learner 完成无引导理解测试。在该项通过前，不把 P0-2 记为关闭，也不进入 P0-3。

部署后刷新两个独立的已登录 `/ops` 会话，运行快照均报告 API/Worker `74fe855...` 与 migration `0020_wp09_reviewer_delegation`，而 Web-only 部署日志声称所保留基线为 API/Worker `e927c1...` 与 migration `0021_p0_identity_principal`。公开 readiness 只能证明 Web `e064590...`，不能证明其实际连接的后端版本。该矛盾存在期间暂停真人 P0-2 测试，先通过扩展后的 PII-free `inspect-runtime` 对账三组件 marker、实际容器、Compose 元数据、网络别名和 Caddy 上游；不部署、不改库、不修改业务事实。

首次扩展 inventory Run `31702193785` 发现 `DEPLOYED_CANDIDATE` 与 `DEPLOYED_COMPONENTS` 的 API/Worker marker 不一致后立即停止，未输出实际容器清单；临时 SSH 正常关闭。marker 不一致正是待诊断事实，不应阻断实际容器只读盘点，因此后续审计器把各 marker 关系作为布尔结果输出，同时继续读取实际容器；仍不修 marker、不改变运行态。

纠偏后的只读 inventory Run `31702773602` 成功并关闭临时 SSH：实际 Web `e064590...`、API/Worker `e927c1...`、migration `0021_p0_identity_principal`，三组件均与 `DEPLOYED_COMPONENTS.json` 精确一致；四个 Compose 服务均为单实例、网络别名唯一，Caddy staging 上游指向唯一 Web。原矛盾来自把最近一次 Web-only 候选 marker 错解释为后端 marker，而非实际运行态回退。运行态真相对账关闭，可以恢复 P0-2 的真实材料与 3 人 5 秒理解测试。

## 10. 正式材料只读验收

2026-08-13 在已登录的真实浏览器中，从 staging Journey V3 运营读回逐一打开全部外部材料动作：八站共十五份有效 HTTPS 材料，结果为 `15/15 PASS`；其中两个视频文件页也单独核验到可见文件标题和内容页面。全过程不修改 Journey、TaskVersion、身份、角色、邀请或其他业务事实。

唯一正式飞书表共有十六条材料记录，但 `TRE-002` 第 2 条正文为“无，自行观看”且没有 URL；它是无来源占位记录，不构成第十六份可发布材料。运行态十五份材料与十五条有效 URL 一一对应，每站至少一份，故 `AT-P0-202=PASS`，不存在漏导入。

P0-2 当前唯一未关闭的产品门禁是 `AT-P0-201`：三名未看说明、未参与建设且属于目标用户的真实新人，分别在无口头提示下完成 5 秒当前位置/下一步判断和 60 秒首动作。通过标准为 `3/3`；任何一人需要解释均记为失败并返回页面修正，不培训测试者。

## 11. 真人测试准备中的恢复缺陷

2026-08-13 准备三条独立测试邀请时，当前 Operator 会话已经失效。直接提交邀请表单未进入 API 写入，而是被 Web 代理返回的裸 `AUTH_REQUIRED` 响应带入全局失败页；因此没有继续创建 L2/L3，也没有把 L1 记为已创建。该现象违反第 3.5 节“失败必须提供可执行恢复动作”的合同。

修复范围只包含 Operator Web 恢复路径：HTML 导航和过期后的 Server Action 安全转入 `/ops/login`，页面只提供“使用飞书进入”主动作并固定回到 `/ops`；非浏览器 JSON 请求继续 `401/no-store`，不削弱 fail-closed 边界。修复不得读取或修改身份、角色、邀请、Journey 或数据库事实。部署前 `AT-P0-201` 继续为 `NOT_RUN`。

## 12. Operator 恢复候选绑定

PR #210 已将上述恢复路径合入主线 `58bebbecab0dac832ce85bfd2a0ac4ab852bfe5d`。Fast Gate `31707252769` 与 Mainline Candidate Gate `31707513746` 均通过；候选 migration 仍为 `0021_p0_identity_principal`，OpenAPI 摘要仍为 `d116ce052e41f1fd8757a3e9d585a035eb8fbc998b0d27fbd80d3fd9c2ac3389`。候选 Web registry digest 为 `sha256:35ba32c25b40dc0447a3f6ef84be68815e045c2780ad78bc8a93da737582a3cc`。

本次部署合同继续收敛为 Web-only：Web 升级至 `58bebbe...`，API、Worker 与 migration 保持健康基线 `e927c1... / 0021_p0_identity_principal`。候选相对直接父提交只修改 Web、P0-2 证据和真实 Web 运行合同；不修改 API、Worker、OpenAPI 或 migration。绑定本身不部署，也不修改 Journey、邀请、身份、角色或业务事实。

真人报告再次确认 `/content = 正常`、`/review = 正常`；该证据关闭 P0-1 双角色入口，不替代 P0-2 的三人无引导理解测试。`AT-P0-201` 继续为 `NOT_RUN`。

## 13. Web-only 预检停止

唯一部署 Run `31709352629` 在镜像拉取和容器替换前 fail-closed，原因是部署脚本仍把 `DEPLOYED_CANDIDATE` 解释为 API/Worker 基线；而第 9 节只读 inventory 已证明该 marker 在 Web-only 发布后表示最近部署的 Web 候选，精确组件基线应以 `DEPLOYED_COMPONENTS.json` 和真实容器为准。公开 readiness 仍为旧 Web `e064590...`，匿名 HTML `/ops` 仍返回旧版 `401`；临时 SSH 已关闭。本次 Run 不重试，也不声称 staging 已更新。

最小修复只把 Web-only 写入前的静态 marker 预检改为：`DEPLOYED_COMPONENTS.json.api/worker` 必须精确等于 `e927c1...`；随后既有 `verify_web_only_runtime` 仍从运行容器、数据库 migration 和 Worker heartbeat 独立复验真实基线。它不放宽 runtime 验证、不修改 marker、数据库或业务事实，并增加 fail-closed 回归测试。任何后续 staging 发布都是新的独立尝试。

## 14. Operator 恢复 staging 验收

修复经 PR #212 合入后，新的独立 Web-only Run `31710086549` 成功：

- 候选 Web 镜像第 1 次有界拉取通过；`WP08_WEB_ONLY_DEPLOY=PASS` 报告 Web=`58bebbecab0dac832ce85bfd2a0ac4ab852bfe5d`、API/Worker=`e927c1bbaf74a9107dadc7ebfafab4fa40f56454`；
- API、Worker、migration 与 heartbeat 继续由既有真实运行态检查验证，migration 保持 `0021_p0_identity_principal`；
- 公开表面在第 7 次有界尝试共同通过：root `200`、readiness `200/ready` 且 release 精确为 `58bebbe...`、非浏览器匿名 `/ops` `401`、`/review` 与 `/content` 安全进入各自登录页；
- `WP08_SSH_INGRESS=CLOSED`，未运行 Terraform plan/apply/import、DNS、云资源写入、数据库迁移、seed、邀请或消息。

部署后的独立真实浏览器复验再次证明：匿名 HTML 访问 `/ops` 得到 `303/no-store -> /ops/login`，页面显示唯一“使用飞书进入”动作；非浏览器 JSON 客户端仍为 `401`。恢复缺陷关闭。

当前飞书授权页默认显示郑田源身份，该身份是 Content Editor/Reviewer，不是 Operator，因此没有执行错误授权。后续由既有 Operator 选择“使用其他账号”完成登录；登录后必须先只读核对是否已存在用途为 `P0-2 无引导理解测试 L1` 的邀请，再决定是否创建 L1/L2/L3，避免前次未知写入造成重复业务事实。`AT-P0-201` 仍为 `NOT_RUN`。

## 15. 三人无引导测试启动

2026-08-13，既有 Operator 完成真实飞书恢复后，先只读核对最近邀请；未发现用途为 `P0-2 无引导理解测试 L1；仅用于 5 秒定位与 60 秒首动作验证` 的既有邀请。随后仅创建一条绑定已发布 Journey V3、Reviewer 为郑田源、有效期 24 小时的 L1 受控邀请。运营页读回状态为 `待使用`；完整链接已通过页面复制动作放入本机剪贴板，原始 token 未写入文档、日志或对话。

为避免覆盖一次性链接，L2/L3 暂不创建。L1 必须交给一名未看说明、未参与建设且属于目标用户的真实新人；观察者不得口头引导。记录 5 秒内能否说出“我在哪里/下一步做什么”，以及 60 秒内是否完成首个有意义动作。只有 L1 结果回收后才创建下一条独立邀请；`AT-P0-201` 仍为 `IN_PROGRESS (0/3)`。

## 16. L1 真人无引导结果

2026-08-13，L1 真人在无提示条件下完成测试：5 秒定位通过、60 秒首动作通过，`AT-P0-201` 更新为 `IN_PROGRESS (1/3)`。真人原始体验反馈去重后为：页面视觉“不够科技、比较苍白朴实”；邀请首屏大标题“这张通行证，只属于你。”的换行和排版不合理，建议在可用宽度允许时保持同一行。

该反馈记为 P0-2 体验缺陷，但在 L2/L3 完成前不修改候选，以保持三名测试者面对同一版本、避免样本不可比较。通过标准只证明首次定位和首动作，不表示视觉体验已达标。下一步是使用同一候选创建唯一 L2 邀请并继续无引导测试。

## 17. L2/L3 真人联合旅程反馈

2026-08-14，Release Owner 确认以下结果来自 L2 与 L3 两名真人共同反馈。由于反馈无法拆分到单个测试者，且没有分别提供两人的 5 秒定位、60 秒首动作和是否需要提示三项数据，本节只作为联合定性证据，不拆成两份独立通过样本，也不补造缺失字段；`AT-P0-201` 严格计数继续保持 `IN_PROGRESS (1/3)`。

两人共同指出：

1. 宝藏页要求“小测”，但没有说明小测是什么、在哪里完成；
2. 评测页要求提交飞书文档，但页面没有可识别的提交入口；
3. 对未接触过飞书的新人，没有提供创建副本和完成提交所需的最小引导；
4. 点击“已完成”或“继续”后会突然回到首页，当前位置和下一步上下文丢失；
5. 已完成阶段无法回溯，学员不能重新查看已经学习的信息；
6. 多处文字排版异常，题面链接与段落发生重叠；
7. 完成长时间学习任务后的结果页过于朴实，缺少获得感和归属感。

这些问题不是单纯视觉偏好：第 1～5 项直接破坏“理解任务—完成学习—形成输出—提交评测—继续旅程”的主闭环，第 6 项影响内容可读性，第 7 项削弱完成反馈。当前候选因此标记为 `REPAIR_REQUIRED`，不得以 L1 的首分钟通过推导 P0-2 已通过；在修复并完成同版本独立复验前，不扩大真实邀请规模，也不关闭 P0-2。

## 18. P0-2R 联合反馈修复合同

本轮不继续逐条打补丁，而按一个 Learner 主闭环修复，目标是让第一次进入的学员始终能回答三个问题：我现在在哪一步、现在要做什么、做完会去哪里。

| 联合反馈 | P0-2R 产品合同 | 自动化证据边界 |
| --- | --- | --- |
| “小测”含义不明 | 所有宝藏与评测统一呈现为“完成学习材料 → 完成本主题实践/评测 → 进入下一站/交给 Reviewer”的三步路径；不再出现没有落点的“小测/小任务” | DOM 合同验证三步路径、动作名称和唯一主动作；仍需真人判断是否真正看懂 |
| 飞书文档没有提交入口 | 需要外部文档的题面直接显示“飞书文档链接”输入框；提交时把链接与补充说明组成不可丢失的标准化交付正文 | Web 合同与 TypeScript 验证入口和服务端 HTTPS/飞书域名校验；不创建或读取学员飞书文档 |
| 新人不懂飞书副本 | 在交付入口旁只保留三步最小提示：创建自己的副本、复制完整链接、粘贴并提交 | 文案合同只证明指引存在；理解程度必须由未受训新人复验 |
| 完成后突然回首页 | 学习材料完成后留在同一任务并定位下一材料或题面；提交后进入旅程页时显示“已保存/下一站已解锁或等待 Reviewer”并定位下一动作 | 跳转、锚点和状态提示合同测试 |
| 已完成阶段不能回看 | 路线图中当前和已完成节点均可进入，未来锁定节点仍不可进入 | 访问合同验证 `CURRENT/COMPLETED` 可进入、`LOCKED` 不可进入；不改变任何完成事实 |
| 链接与段落重叠 | 任务正文、材料链接和提交正文统一允许安全断行；移动端三步路径改为纵向 | 390px 样式合同与生产构建；真实内容仍需浏览器几何复验 |
| 完成反馈过弱 | 本轮先补足即时状态反馈和 Reviewer/下一站去向；最终八站完成的获得感与归属感作为 P0-3 完整旅程验收项，不在本轮伪造“庆祝通过” | 本轮只验证事实型过渡反馈；最终完成体验不得在未完成 Journey 时提前出现 |

由于已发布 Journey V3 的正文不可原地修改，本轮对“需要飞书文档”的识别采用受控兼容规则：正式三项能力评测均启用外部文档入口；其他任务仅在冻结题面明确包含“飞书/文档副本/文档链接/提交文档”时启用。长期正确模型是 TaskVersion 的结构化 `submission_mode`，列入 P1 内容模型；P0 不为此改写已发布任务事实或新增 migration。

当前状态为 `CODE_IN_BUILD / HUMAN_RETEST_NOT_RUN`。退出条件不是机器门禁单独通过，而是：构建与浏览器矩阵通过后，使用同一 staging 候选由未接受口头提示的真人重新完成宝藏学习、飞书交付、提交过渡和已完成阶段回看；复验失败则继续保持 `REPAIR_REQUIRED`，不得扩大邀请或关闭 P0-2。

## 19. P0-2R 本地机器验收

2026-08-15，本轮修复在本地隔离环境完成以下验证：

- Web 合同测试 `45/45 PASS`，TypeScript、ESLint、production build 均通过；
- Fast Gate 通过：API `352 passed / 5 skipped`、OpenAPI、migration、隔离、密钥扫描、Python 与 Web 依赖审计全部通过；
- Fast Gate 首次发现 `nanoid 3.3.17` 对应未豁免高危公告 `GHSA-2v37-7h3g-55p8`，已将既有最小 override 固定为 `3.3.18`，复验为 Web 依赖漏洞 `0`；
- Chromium 1232 隔离闭环通过：八站学习与提交、390/768/1280 三档页面、路线几何、材料完成后的上下文定位、已完成阶段回看、三项评测的飞书链接交付入口、Reviewer 安全打开飞书域名链接、要求修订、新浏览器重新进入、再次提交、通过及最终结果；
- 浏览器夹具、容器、网络和数据卷均为本地一次性资源，测试结束后已清理；没有访问或修改 staging、production、Journey V3、身份、角色、邀请或真实业务事实。

机器结果把状态推进为 `MACHINE_PASS / STAGING_NOT_UPDATED / HUMAN_RETEST_NOT_RUN`，不等于 P0-2 关闭。下一候选进入 staging 后，真人必须复验第 18 节四段主路径；L2/L3 的联合反馈不能倒推为两份独立通过证据。最终完成页的获得感和归属感缺陷进入紧随其后的 P0-3，不降级为 P1，也不以当前合成闭环的“能完成”替代真实体验验收。

## 20. P0-2R 主线候选与 staging 绑定

PR #215 将 P0-2R 合入主线 `824ecd0b2f76973015765260e3934219270a565e`。Fast Gate `31831757432` 与 Mainline Candidate Gate `31832092834` 均通过；主线候选 registry 状态为 `VERIFIED`，Web digest 为 `sha256:28f378d52607b3f88398416552865dd686fd5b5784b3aadaa327f66ad7f46dd8`。候选相对直接父提交只修改 `apps/web/`、P0-2 证据、本地浏览器合同及其隔离夹具；API、Worker、OpenAPI 与 migration 相对健康基线无差异。

本次 staging 合同继续采用 Web-only：Web 升级至 `824ecd0...`，API、Worker 与 migration 保持 `e927c1b... / 0021_p0_identity_principal`。当前候选没有可用的 `phase=deploy` 全量派发确认，绑定 PR 本身不部署、不运行 migration 或 seed，不修改 Journey V3、邀请、身份、角色或其他业务事实，也不运行 Terraform plan/apply/import、DNS、WP-12B 或云资源变更。只有绑定门禁通过后才能执行一次 `deploy-web`；失败不重试并必须关闭临时 SSH。部署与同候选真人复验发生前，P0-2 仍为 `MACHINE_PASS / STAGING_NOT_UPDATED / HUMAN_RETEST_NOT_RUN`。

## 21. P0-2R Web-only staging 验收

绑定 PR #216 经 Fast Gate `31837410125` 合入主线 `4061a8495165ccc158ecdc0d733c47db067bce05`，其 Mainline Candidate Gate `31837726413` 通过。随后仅派发一次 `deploy-web` Run `31838391751`，结果为 `PASS`：

- 候选 Web digest 第 1 次有界拉取成功，`WP08_WEB_ONLY_DEPLOY=PASS` 精确报告 Web=`824ecd0b2f76973015765260e3934219270a565e`、API/Worker=`e927c1bbaf74a9107dadc7ebfafab4fa40f56454`；
- migration 保持 `0021_p0_identity_principal`，没有执行 migration、seed、Terraform plan/apply/import、DNS、WP-12B 或云资源变更；
- 外部表面第 1 次检查全部通过：根页 `200`，readiness=`200/ready/824ecd0...`，匿名 JSON `/ops`=`401`，`/review` 与 `/content` 均为 `303/no-store` 并分别进入专用登录页；
- `WP08_SSH_INGRESS=CLOSED`，临时 SSH 已关闭；没有创建邀请、发送消息或修改 Journey、身份、角色及其他业务事实；
- 部署完成后的独立只读 HTTP 复验再次得到同一 Web revision 和相同路由结果。

P0-2 机器交付与 staging 交付现为 `PASS`，但产品验收仍是 `HUMAN_RETEST_REQUIRED`。下一项唯一 WIP 是在该同一候选上，由未接受口头提示的真人复验：宝藏学习路径、飞书文档交付、提交后的上下文连续性、已完成阶段回看。L2/L3 共同反馈不是通过证据；真人未报告结果前不得关闭 P0-2，也不得提前启动 P0-3。

## 22. 三人真人复验与 Day 0 节奏返工

2026-08-18，Release Owner 确认三名目标新人已完成无讲解测试，并提供《新人启航》《新人启航（测试反馈）》与八站快速体验记录。真人证据与机器、浏览器证据分开记录：本轮三人反馈不能被既有自动化 PASS 覆盖，也不能因三人均完成流程而推导产品体验通过。

三人共同暴露的首要问题是 Day 0 不知道“要学习什么、判断什么、证据是什么”；其后路径虽然逐渐清晰，但一天内连续阅读大量文字和视频，节奏单一、容易疲劳。该结果意味着第 21 节的 `HUMAN_RETEST_REQUIRED` 实际结论为 `HUMAN_RETEST_FAILED / REPAIR_REQUIRED`，P0-2 继续保持单一 WIP。

本轮产品返工不是继续增加解释，而是把黄金路径压缩为可行动节奏：Day 0 只要求新人先选一个真实问题，再从第一份材料找一条线索；所有学习材料显式呈现“带着问题 → 找到一条线索 → 立即返回”，并把按钮改为“我找到 1 条线索”；材料的原始时长只作为边界信息，不再暗示新人必须一次通读。当前修改只发生在 Learner Web 与本地浏览器合同，不改变已发布 Journey、任务正文、身份、角色或其他业务事实。

验收仍需两层独立证据：先由 Computer Use 在隔离数据上走通八站、Reviewer 要求修订、Learner 再次提交、通过和最终结果，并检查桌面与 390px 画面；只有该版本不存在明显体验阻断后，才交给三名未接受口头提示的新人复验。真人复验仍必须分别记录 10 秒定位、60 秒首材料、是否需要提示、继续意愿和原话；在三名独立样本通过前不得关闭 P0-2。
