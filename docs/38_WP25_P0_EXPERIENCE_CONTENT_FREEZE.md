# 38｜WP-25 P0 Experience & Content Freeze 执行包

状态：`CONTENT_SOURCE_FROZEN / REVIEWER_REVIEW_OWNER_REPORTED / RESULT_COPY_DRAFTED / OPERATOR_APPROVAL_PENDING`

版本：V0.2

日期：2026-08-09

本轮授权边界：允许把已确认的唯一内容源、Reviewer 复核陈述和结果文案草案写入施工文档，并完成 Journey V3 发布准备；不发布 Journey V3、不创建邀请、不发送消息、不修改身份、既有业务事实或外部环境。

## 1. 开工事实

- 基线 main：`1c9fbaa91f52e4916f50d1b606ceb7375e062ad6`；
- 工作分支：`codex/wp25-wp30-docs`；
- latest release evidence snapshot：本地存在文档/原型变更，候选仍为 `0589fc825e41dc0c536b3bf87ac284c9a50013fd`，完整 release gate 保持 `NO_GO`；
- 产品事实源：《MUCHEN新人启航探索营 V1.0》、DEC-024/025/026、WP-17/18/24 与 37 号工作包；
- 原型为零网络写入的本地设计工件，不是产品实现、发布候选或真人 UAT 证据。
- 2026-08-09 发布准备基线：主线 `a7d6a86f07efbcf2f8e9771108b19dbe1a15026f`，施工分支 `codex/journey-v3-release-prep`；staging 当前运行候选为 `3b7d7573cd70b72868e427b523ff630b732f0603`，Journey V3 尚未发布。

## 2. 正式内容盘点

2026-08-09，Owner 指定下列飞书表格为本轮唯一正式内容源，并明确其取代此前 Base、Wiki、PDF 和本地映射中的冲突版本：

- [Muchen Journey 正式内容表](https://zx6w57w0j34.feishu.cn/sheets/LpnOsAMGth34BVtzRdXcq96Unwh?from=from_copylink&sheet=0HnpkV)

该表把内容组织成**八个站点、十六条材料记录**：其中十五条提供可发布的 HTTPS 材料，`TRE-002` 的第 2 条明确为“无，自行观看”且没有 URL，不计为独立学习材料，也不得由工程师补造第二内容源。`DAY-0` 含“给 Muchener 的一封信”和“公司介绍与培训流程”两份开营材料；其后为四个宝藏和三项能力评测，每站至少有一份真实材料。`DAY-1` 是 `DAY-0` 站内材料标签，不是第九个 Journey 节点。代码合同继续固定 `DAY-0 + 四宝藏 + 三评测`，不得因表格行名改变路线结构。

2026-08-13 只读复核确认：已发布 Journey V3 暴露十五个外部材料动作，与正式表十五条有效 URL 一一对应；当前登录浏览器逐项打开结果为 `15/15 PASS`。该证据只关闭材料可达性，不替代三名真实新用户的无引导理解测试。

Reviewer 复核完成由 Owner 于 2026-08-09 明确陈述。本记录可以作为发布准备输入，但不能替代 Operator 在产品界面选择 Reviewer、确认八个不可变 TaskVersion、填写复核记录并提交发布命令后的机器读回。

| 阶段 | 正式方案已经锁定 | 仍需 Content Editor 提供/确认 | 当前状态 |
| --- | --- | --- | --- |
| Day 0 | 《给 Muchener 的一封信》、公司介绍与培训流程 | 按唯一正式内容源导入两份 required materials，并由 Operator 核对预览 | `SOURCE_FROZEN / IMPORT_NOT_READ_BACK` |
| 宝藏一 | 公司认知与 Muchener 价值理解；对应主题小任务 | 按正式表格导入文档、视频/外链、小任务和自检 | `SOURCE_FROZEN / IMPORT_NOT_READ_BACK` |
| 宝藏二 | AI 数据与模型基础；对应主题小任务 | 按正式表格导入文档、视频/外链、小任务和自检 | `SOURCE_FROZEN / IMPORT_NOT_READ_BACK` |
| 宝藏三 | 项目认知与项目管理流程；对应主题小任务 | 按正式表格导入脱敏材料、小任务和自检 | `SOURCE_FROZEN / IMPORT_NOT_READ_BACK` |
| 宝藏四 | 关键角色、新人责任边界与交付适配；对应主题小任务 | 按正式表格导入脱敏材料、小任务和自检 | `SOURCE_FROZEN / IMPORT_NOT_READ_BACK` |
| 评测一 | 规则拆解题面、交付格式和 Rubric | Operator 发布时绑定已完成复核的 Reviewer 与不可变版本 | `REVIEWER_REVIEW_OWNER_REPORTED / PUBLISH_NOT_READ_BACK` |
| 评测二 | 模型判断题面、交付格式和 Rubric | Operator 发布时绑定已完成复核的 Reviewer 与不可变版本 | `REVIEWER_REVIEW_OWNER_REPORTED / PUBLISH_NOT_READ_BACK` |
| 评测三 | 数据构造题面、交付格式和 Rubric | Operator 发布时绑定已完成复核的 Reviewer 与不可变版本 | `REVIEWER_REVIEW_OWNER_REPORTED / PUBLISH_NOT_READ_BACK` |
| 结果 | Operator 人工准入的 `ADMIT / DEFER / NOT_ADMIT` | Owner/Operator 审阅本节草案；产品发布后保持版本化、不可原地改写 | `COPY_DRAFTED / OPERATOR_APPROVAL_PENDING` |

允许进入 Journey V3 的内容只能来自上述唯一正式内容源。正文、URL、题面、Rubric 或状态存在冲突时必须停止并回到该表核对；工程师不得自行补写公司事实，也不得把旧 PDF/Base 内容静默混入 V3。

### 2.1 Learner 可见结果文案 V0.1

以下为 Owner 授权先行拟定的版本。它们只描述本轮证据与下一步，不把系统建议写成自动录用或永久能力判断。发布前仍需 Operator 在产品内确认。

| 结果 | 标题 | Learner 可见说明 | 唯一下一步 | 责任人 |
| --- | --- | --- | --- | --- |
| `ADMIT` | 通过，进入下一阶段 | 你已完成本轮探索与三项能力评测，当前证据达到准入要求。通过不是终点，下一阶段将进入真实任务与协作验证。 | 等待运营确认下一阶段安排 | Operator |
| `DEFER` | 需要补充一次 | 当前提交已展示部分能力，但证据尚不足以作出最终准入判断。请只补充反馈中指出的内容；原提交和评审记录会保留。 | 按评审反馈补充并重新提交 | Learner |
| `NOT_ADMIT` | 本次暂不进入下一阶段 | 基于本轮探索材料与三项能力评测，当前证据未达到本次准入要求。该结果只针对本轮岗位匹配与提交表现，不代表对个人能力的永久判断。 | 阅读最终反馈并结束本轮探索 | Learner |

结果页必须同时保留：已完成的学习事实、三项能力证据、Reviewer 结论、系统非决定建议和 Operator 人工决定；不得只显示上表一句文案。

## 3. P0 页面与状态矩阵

| 页面/状态 | Learner 第一眼必须看见 | 唯一主操作 | 不允许出现 |
| --- | --- | --- | --- |
| 邀请/首次进入 | 探索营身份、一天旅程、本人即将开始 | `进入旅程` | 长篇产品说明、多个入口 |
| 旅程地图 | 当前节点、已完成、下一站、四宝藏＋三评测 | `进入当前站` | 节点脱线、固定说明书、假进度百分比 |
| Day 0 | 全旅程结构、答疑/停止边界 | `我已看清路线` | 一上来要求作答 |
| 宝藏学习 | 当前材料、材料序号、来源、完成状态 | `完成本材料` | 作答区、自动计时完成、无来源内容 |
| 宝藏小任务 | 题面、交付边界、自检、保存状态 | `提交这一站` | 重复材料正文、多个同级按钮 |
| 等待反馈 | Reviewer 角色、真实状态、处理预期 | `返回旅程` | 虚构在线/已读/送达 |
| 要求修订 | 原提交保留、唯一修订重点、Reviewer 原始反馈 | `带着反馈继续` | “失败”羞辱、要求全部重写 |
| 宝藏完成 | 完成痕迹、下一站 | `前往下一站` | 积分、抽奖、无意义庆祝 |
| 能力评测 | 固定题面、交付物、Rubric 摘要、草稿状态 | `提交评测` | 学习宝藏式游戏包装、自动答案 |
| 最终结果 | 学习事实、三项能力证据、人工结论、下一步 | `查看旅程记录` | 自动录用/淘汰、重复整段说明 |
| 可恢复错误 | 业务事实未回滚、可恢复动作、参考编号 | `重试` 或 `重新登录` | 死路、技术堆栈、重复品牌文案 |

## 4. 视觉与语言冻结项

- 品牌暗线使用 `It's a long game.`，不与页面行动争夺注意力；
- 路径和节点由同一组 SVG 坐标生成，桌面横向、移动端纵向均保持节点中心在线；
- 当前/完成/锁定/评测同时用形状、图标和文字语义，不只用颜色；
- 每屏一个主状态、一个主操作；同一含义不在标题、说明、按钮和页脚重复；
- 路线节点默认短标签，hover/focus/touch 后只展示一句意义说明；
- Reviewer 陪伴感只来自真实角色、反馈状态和 SLA，不伪造聊天或在线状态；
- 动效只解释状态变化，支持 `prefers-reduced-motion`。

## 5. 完整原型路径

本地工件：[WP-25 完整 Learner 体验原型](../prototypes/wp25/index.html)

原型覆盖：首次进入 → 地图 → Day 0 → 宝藏材料 → 小任务 → 等待 → 要求修订 → 安全重新进入 → 宝藏完成 → 能力评测 → 通过 → 最终结果。所有内容为 PII-free，零 API、零身份、零网络写入。

## 6. 真人验证脚本

对象：至少 3 名未参与设计、符合 Learner 画像的体验者；不得由 Owner、Content Editor、Reviewer 或实现者替代。

主持人开场只说：“请把它当成你第一次收到的探索营链接，按你理解完成。”之后不解释入口、路线、术语或下一步。

| 检查点 | 记录方式 | P0 通过条件 |
| --- | --- | --- |
| 首屏 10 秒 | 问“你在哪里、接下来做什么？” | ≥90% 回答正确；WP-25 最小 3 人时必须 3/3 |
| 60 秒首动作 | 观察是否自主进入第一份材料 | 3/3，无口头提示 |
| 路线理解 | 问“这一天有几段、你在第几段？” | 能区分 Day 0、四宝藏、三评测 |
| 输入先于输出 | 观察进入宝藏后的第一反应 | 不询问“为什么现在就要写”；能先看到材料 |
| 恢复/修订 | 切到等待、修订和重新进入状态 | 能说出谁反馈、补什么、原事实是否保留 |
| 结果 | 问“你证明了什么、下一步是什么？” | 能区分系统建议与人工准入 |
| 体验评分 | 只问两题，1–5 分 | “进度清楚”“愿意继续下一站”中位数均 ≥4 |

原始观察进入私密证据。Public Git 只记录参与人数、通过/失败、问题编号和无 PII 的聚合结果。任何主持人解释都记为一次支持介入，不能从分母中删除。

## 7. 机器复验证据

使用现有固定 `chromium-1232` 和 Playwright CLI 对本地零写入原型复验：

- 自然点击完成“首次进入 → 地图 → Day 0 → 三份材料 → 小任务 → 等待 → 反馈 → 修订 → 宝藏完成 → 评测 → 最终结果”；
- 12 个关键状态 × 390/768/1280，共 36 个页面/视口组合均无横向溢出且恰好一个主操作；
- 桌面、平板、手机的八个节点均与同一组路线坐标精确一致，节点数量为 8；
- 路线热点可由鼠标、键盘 focus/Enter 和触摸 click 渐进披露同一短说明；
- `prefers-reduced-motion` 可识别，控制台为 0 error / 0 warning；
- 代表截图保存在本地 `output/playwright/wp25/`，不进入 Public Git，也不构成真人 UAT。

以上只证明原型结构和浏览器行为，不证明内容正确、目标 Learner 看得懂或愿意继续。

## 8. 当前退出差距

- `AT-WP25-001`：`CONTENT_SOURCE_FROZEN / IMPORT_AND_OPERATOR_READBACK_PENDING`，唯一正式内容源、四宝藏小任务、三评测和结果文案草案已齐；产品内导入、预览、不可变版本与 Operator 读回尚未发生；
- `AT-WP25-002`：`MACHINE_PASS / HUMAN_REVIEW_NOT_RUN`，完整原型已经覆盖正常、等待、修订、恢复、通过和错误恢复合同；
- `AT-WP25-003`：`NOT_RUN`，三名目标用户尚未执行；
- `AT-WP25-004`：`MACHINE_PASS / CONTENT_DESIGN_QA_SIGNOFF_NOT_RUN`，三视口、路线坐标、唯一主操作、键盘提示和 reduced-motion 已通过；
- `AT-WP25-005`：`MAPPING_FROZEN / RUNTIME_READBACK_PENDING`，八站映射已经与代码 stable key 合同核对；发布 TaskVersion/JourneyVersion 后仍须读取摘要证明运行态与本文一致。

因此本轮内容缺失不再是阻塞，但 WP-25 真人体验门禁仍未完成，只能记 `IN_PROGRESS`，不得伪造 `P0_EXPERIENCE_CONTENT_APPROVED`。Journey V3 可以进入受控发布准备，但“发布成功”不能替代 WP-25～WP-29 的真人通过。

## 9. 下一项人工输入

下一步不再向 Content Editor 索取另一份材料包，而是执行一次可审计的产品内读回：

1. Content Editor 只从唯一正式内容源导入八站内容，`DAY-0` 内含两份开营材料；
2. 独立 Reviewer 的复核人和复核记录由 Operator 在发布动作中显式绑定；
3. Operator 精确发布八个新的不可变 TaskVersion，禁止修改 V1/V2 或在途 Learner；
4. 只读核对每个 stable key、版本号、required material 数量和摘要；
5. 另行取得 Journey V3 发布授权后，才组合并发布固定 JourneyVersion；发布后只读核对八站顺序与摘要，不创建邀请。
