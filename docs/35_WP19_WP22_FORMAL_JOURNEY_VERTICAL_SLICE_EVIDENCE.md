# 35｜WP-19～WP-22 正式探索营最小纵向切片 As-Built

状态：`AS_BUILT`

实现结论：`MINIMAL_VERTICAL_SLICE_COMPLETE / ENGINEERING_SLICE_VERIFIED / CONTROLLED_BETA_CONTENT / STAGING_RUNTIME_DEPLOYED / PUBLIC_ROUTE_VERIFIED / RUNTIME_CONTENT_PUBLICATION_VERIFIED / MACHINE_READBACK_VERIFIED / HUMAN_GATES_NOT_RUN`

版本：V0.2

日期：2026-08-04

适用范围：WP-19 Journey Composition、WP-20 Four Treasures Content、WP-21 Three Ability Assessments 与 WP-22 Formal Learner Experience 的首个端到端工程切片。

发布边界：API/Worker 精确基线 `ef0a512…` 已在 staging 完成 migration `0015` 与运行面部署，Edge 修复 run `30826160950` 连续证明公开 staging 只路由到预期运行态。Web 修复候选 `12bc627…` 经唯一 run `30875911123` 部署成功并保持 API/Worker、数据库与业务事实不变。Operator 随后发布 Journey V1，并通过一条绑定该 JourneyVersion、刷新后状态为“待使用”的受控邀请完成最小机器读回。这只关闭 WP-19～WP-22 的最小纵向切片，不声称内容真人有效、独立 Reviewer 校准、WP-23 或 production GO 已通过。

## 1. 为什么按一个纵向切片收口

WP-18 恢复了正式产品真相，但仅按数据层、内容层和页面层分别搭空框架，无法证明真实 Learner 能走完产品。此次最小切片因此从一次受控 Operator 发布开始，贯通：

```text
发布不可变 Journey V1
  → 创建绑定 JourneyVersion 的邀请
  → Learner 依序完成 Day 0 + 四宝藏证据
  → 三项能力评测均由 Reviewer 人工结论
  → 至少一项要求修订并再次提交
  → 仅在 8 个阶段完整且 3 项评测均 PASS 后生成 Outcome
  → /app/result 展示三项可追溯能力证据
```

旧 `TSK-001` 的 Assignment、Submission、Evaluation 和 Outcome 保持原样，继续属于 `ALPHA_VALIDATION_TASK / OUTSIDE_FORMAL_EXPLORATION_JOURNEY`。此次没有把旧 Alpha 在途 Learner 自动迁入正式旅程。

## 2. 四个工作包的最小交付

| 工作包 | 已接通的最小真实能力 | 此次明确未声称完成 |
| --- | --- | --- |
| WP-19 | `JourneyDefinition / JourneyVersion / JourneyStageVersion`、组织级复合约束、发布后不可变、Enrollment 固定版本、8 个 Assignment、服务端顺序锁和 Current Action 投影 | 多版本升级 UI、在途版本迁移、通用旅程编辑器 |
| WP-20 | Day 0 与四个宝藏各自固定 TaskVersion；Learner 提交不可变证据后完成阶段；不伪造 Review、Evaluation 或 PASS | 最终材料版权签署、目标 Learner 的 `AT-CONTENT-009` 真人理解验证 |
| WP-21 | 三个稳定能力评测、三套独立四维 Rubric、现有提交/评审/修订/通过闭环；最终 Outcome 不可变引用三份 Evaluation | 独立 Reviewer 真人边界样本校准、自动人事判断、总分排名 |
| WP-22 | `/`、`/join`、`/app`、任务页与结果页接入真实 8 节点状态；悬停/聚焦/触摸渐进说明；键盘与 reduced-motion 合同；`/review`、`/ops` 保持工具界面 | WP-23 真人 5 秒理解率、完整视觉 UAT、游戏经济或装饰性积分 |

最小内容是新的 vNext 受控内测文本，来源标记固定引用 `DEC-024` 与 34 号产品合同。旧归档只用于恢复意图，不复制旧正文。候选 TaskVersion 工件同时绑定：

- 已 seed 的兼容 `TSK-001` 数据库版本及完整内容摘要；
- 8 个正式阶段的确定性内容摘要，状态为 `RUNTIME_OPERATOR_PUBLISH_REQUIRED`；
- 正式 Journey 只允许 Operator 选择同组织、已绑定且已完成线下复核的独立 Reviewer，并显式确认“发布后正文不可原地修改”后发布一次 V1；运行时生成的物理 UUID 不改变候选绑定的内容摘要。

## 3. 数据与安全不变量

迁移 `0015_wp19_formal_journey` 在现有 `0014_wp12_data_lifecycle` 之后新增编排层，不复制运行状态。数据库强制：

- JourneyDefinition、JourneyVersion、JourneyStageVersion、Invite、Enrollment、Assignment 和 JourneyOutcomeEvidence 的组织范围不能跨绑；
- 一个 Journey V1 恰好按位置 `0..7` 固定 Day 0、四个 Treasure 和三个 Assessment；
- Day 0/宝藏只能使用 `LEARNER_EVIDENCE`，评测只能使用 `REVIEW_REQUIRED`；
- JourneyVersion、JourneyStageVersion 和 JourneyOutcomeEvidence 发布后拒绝更新或删除；
- 同一 Enrollment 不得重复绑定同一阶段，也不得跳过前置阶段操作后续 Assignment；
- 宝藏提交只完成 Learner 证据，不创建虚假 Reviewer 事实；
- 中间评测 PASS 只推进下一阶段，不提前完成 Enrollment 或生成 Outcome；
- 最后一项评测通过时，若任一阶段未完成、任一评测无有效 PASS 或组织/版本不匹配，服务端拒绝生成正式结果。

## 4. 接口与页面

新增或扩展的合同包括：

- Operator 读取/发布同组织正式 Journey V1；
- Invite 在 `task_version_id` 与 `journey_version_id` 之间显式选择一个目标，运行时仍固定第一个 TaskVersion 以兼容既有加入合同；
- `GET /api/v1/me/current-action` 返回服务端推导的 JourneyProgress 与唯一当前阶段；
- Assignment detail 返回固定 JourneyStage 身份和完成策略；
- Result 返回按旅程位置排序的三项 Evaluation 证据；
- `/app` 只显示投影，不保存可写进度；任务页依据完成策略给出“留下旅程证据”或“提交主管评审”；结果页只在服务端完整结果存在时展示。

首页主命题保持“这里，没有标准答案。”，`It's a long game.` 只作为低权重品牌暗线。正式地图用不同视觉语义区分启程、四个宝藏和三项评测；必要文字只在热点被悬停、键盘聚焦或触摸时出现。

## 5. 自动化证据

本地在干净 PostgreSQL 18 测试库执行了 `0001 → 0015 → 0014 → 0015` 迁移往返；随后从空库 seed 并运行完整 API 测试：

| 检查 | 结果 |
| --- | --- |
| migration static | 唯一 head `0015_wp19_formal_journey`；15 个线性 revision |
| 空库升级、降级、再升级 | PASS |
| 既有 `0014` Alpha facts 升级 | 使用上一候选代码建立 `0014` seed 后升级至 `0015`；organization/user/task/enrollment/assignment/outcome 计数逐项不变，新增 Journey 表保持空白，PASS |
| API/领域/权限/旧 Alpha 回归 | `266 passed / 2 skipped`；跳过项为既有外部条件测试 |
| 正式旅程端到端 | 发布、邀请、8 阶段顺序、5 个 Learner 证据阶段、3 个评测、一次修订、最终结果 PASS |
| Web lint / TypeScript / contract tests | PASS；10/10 |
| Next.js production build | PASS；全部正式路由可构建 |
| 真实浏览器纵向检查 | Firefox 桌面与 390px 窄视口完成邀请、加入、地图、热点提示、进入任务、提交 Day 0 和 `0/8 → 1/8` 推进；无产品 console error |
| OpenAPI runtime equality | 由 source-mounted API 与 `contracts/openapi.json` 精确比较 |
| 候选追溯 | migration/config/OpenAPI 与 8 个正式内容摘要进入候选检查 |
| 依赖与仓库安全 | Python 与 Web 固定锁文件均无已知漏洞；Gitleaks 无泄漏 |

Docker 首次重建期间曾在 build isolation 拉取 Python setuptools 时遇到外部 PyPI TLS 失败；这不是产品测试失败。源代码挂载到既有固定依赖镜像后，迁移和完整测试均通过。远端 Mainline Candidate Gate `30806515651` 随后重新构建三镜像、生成不可变候选 `ef0a512…` 并复验 registry digest；发布证据没有复用本地镜像。

## 6. 当前发布状态与剩余门槛

“先完成切片、再发布”的前四个工程步骤已完成：PR 已合入受保护主线，mainline 已生成绑定 migration `0015` 和 8 个正式阶段摘要的候选 `ef0a512…`，该候选已在单次精确授权下部署到现有 staging，并经内部 runtime inventory 与公开 Edge 连续路由验收。

候选发布后，Owner 于 2026-08-04 报告：当前 Operator 已在 staging 选择完成线下复核的独立 Reviewer，确认正文不可原地修改，并发布受控内测 Journey V1。刷新 `/ops` 后，固定旅程下拉框从服务端列出 `Muchen Journey 探索营 · V1 · 8 站`，因此发布事实由“仅 Owner 陈述”升级为运行态机器读回。

此前通用 Next 错误无法证明请求进入 API；唯一只读诊断 run `30872474226` 在固定窗口内没有找到发布请求并失败关闭，SSH 已关闭且未重跑。PR #142/#143 修复发布错误呈现并增加有界诊断后，PR #144 将 Web 候选 `12bc627d4310cdba9eba4c67050dc875994ceb31` 绑定到 API/Worker 基线 `ef0a512cf357001cfd8cb6803f65cc17ae697325`。唯一 Web-only deploy run [`30875911123`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30875911123) 成功：公开 readiness 返回 Web `12bc627…`，根页面 200，匿名 `/ops` 与 `/review` 为 401；数据库、migration、业务事实、消息、Terraform 和云资源均未改变，临时 SSH 已关闭。

Operator 只生成一次绑定上述固定 Journey V1 的 24 小时受控邀请。页面刷新后，一次性链接正文消失，最近邀请仍由服务端读回并显示“待使用”。这同时证明 JourneyVersion 可被邀请引用、邀请事实已持久化、一次性链接不会在后续读取中重复暴露；未读取或记录邀请 token。

后续顺序固定为：

1. 由 Learner 使用受控邀请加入，验证 Enrollment 固定到该 JourneyVersion 且首个 Current Action 为 Day 0；
2. 小范围学员、NPC、直培班班主任和人才发展主管使用真实路径；这些反馈属于 WP-23，不反写已发布 V1，只能形成 V2 决策；
3. 未经新的精确授权和生产门禁通过，不把此候选切到 `journey.muchenai.com`。

WP-19～WP-22 的“最小纵向切片”现记为 `MINIMAL_VERTICAL_SLICE_COMPLETE / MACHINE_READBACK_VERIFIED`：代码、数据库编排、正式内容目录、正式 Learner 页面、staging 运行态、Journey V1 发布和受控邀请持久读回已在同一路径闭合。`AT-CONTENT-009`、`AT-CONTENT-010`、`AT-UX-010` 真人部分和 `AT-UAT-009` 仍为 `NOT_RUN`，所以这不是完整 WP-20、WP-21、WP-22 退出签署，也不关闭 WP-23 或 production `NO_GO`。
