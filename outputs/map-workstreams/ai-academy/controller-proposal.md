# AI 学院 → 总控集成提案

状态：`PROPOSAL_ONLY`  
当前候选：`READY_FOR_HUMAN`、冻结、未获集成或发布授权

## 学员需求

AI 学院第一条路径需要在未来正式集成时连续读取“个人能力目标”和“岗位 AI 能力需求”，并在完成一次有意义练习后，把可解释的练习事实交回共享 Evidence Ledger。学员应能分辨共享事实、本人原文、确定性完成检查与人/模型判断。

当前隔离候选只用合成只读夹具和会话内记录验证这一体验，不建立第二套 Person、Capability、Evidence、Progress 或 Identity 事实源。

## 请求总控评审的共享能力

1. 一个由总控所有的只读投影：提供获授权学员的当前个人能力目标、岗位 AI 能力需求、来源与版本。
2. 一个由总控所有的 Evidence Ledger 写入契约：接受练习 ID、内容版本、本人原文、公开完成检查、用途和限制说明；不得接受能力评分或用人结论作为本路径输出。
3. 一个由总控所有的进度转场：在证据写入成功后决定 AI 学院下一动作；地图本身不维护跨地图进度。

这三项均未在本工作流中实现。

## 兼容性影响

- Person / Capability：只读，不改变共享 schema；需要稳定 ID、展示文本、来源和版本。
- Evidence：建议新增或映射为“learner-authored-practice”证据类型，并区分原文、确定性检查与后续人工/模型判断。
- Progress：只请求一次幂等的完成事件，不直接解锁其他地图。
- Identity / privacy / audit：沿用总控会话、权限、最小必要访问、审计与保留策略。
- Content：合成夹具必须替换为经 Owner 批准、带版本的正式学习输入后才可形成集成候选。
- 其他地图与全局导航：无直接修改需求。

## 迁移要求

1. 内容 Owner 批准正式课程与练习版本，保留“合成/正式”来源标记。
2. 总控定义只读能力目标投影与 Evidence Ledger 契约，并完成隐私、权限、审计和幂等检查。
3. 用适配层替换 `synthetic-fixture.json`，但保持四步体验合同与证据边界不变。
4. 对 Person、Capability、Evidence、Progress 的跨地图连续性执行总控契约测试。
5. 仅在本冻结候选真人门槛通过后，创建新的总控集成候选；重新执行 390/768/1280 与跨地图回归。

## 现有证据

- 地图合同：`outputs/map-workstreams/ai-academy/contract.json`
- 独立判定：`outputs/map-workstreams/ai-academy/evaluator-report.json` → `READY_FOR_HUMAN`
- 浏览器证据：`outputs/map-workstreams/ai-academy/browser-evidence/manifest.json`
- 真人计划：`outputs/map-workstreams/ai-academy/human-validation-plan.md`

## 总控当前可做的动作

只做合同与兼容性评审，确认未来共享投影、证据与进度接口的归属和约束。当前不得合入正式 Journey、替换正式内容、写入共享事实、发布或声称 AI 学院通过真人验收。
