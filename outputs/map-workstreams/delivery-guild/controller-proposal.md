# delivery-guild 总控集成提案

状态：`PROPOSAL_ONLY`

地图候选：`delivery-guild-first-bounded-evidence-draft`

地图判定：`READY_FOR_HUMAN`（仅机器验收）

## 学员需要

真人门槛通过后，正式体验需要让学员从共享平台只读取得当前角色准备度与 AI 能力档案，进入一个已授权且边界完整的交付任务，并把经本人确认的项目证据或复盘输入送入共享 Evidence Ledger 的“待导师复核”状态。正式集成必须保持当前候选已经验证的四个区分：合成/平台事实、学员输入、人工判断、系统状态。

## 请求总控拥有并实现的共享能力

1. 只读输入适配器：从共享 Person/Capability 权限上下文提供最小必要的 `role-and-collaboration-readiness` 与 `ai-capability-profile` 快照；地图不得缓存成第二事实源。
2. 任务边界契约：由共享 API 提供已授权任务的目标、非目标、允许数据、时间盒、完成条件、升级条件与内容版本；没有完整边界时拒绝进入。
3. Evidence Ledger 待审写入：接受学员显式确认的 `project-evidence` 或 `retrospective-input`，默认状态为 `PENDING_HUMAN_REVIEW`，保留来源、版本、本人声明、不确定性与审计记录。
4. 权限与隐私：真实任务入口必须验证身份、项目最小权限、数据用途与保留策略；禁止外部发送和自动人员决定。
5. 导师复核转场：由总控路由到正式人工复核，不把“本地草稿已形成”表达为“证据已认可”。

## 兼容性影响

- 不改变现有 Person、Capability、Evidence、Progress、Identity 领域模型的所有权。
- 不要求 delivery-guild 拥有全局导航、跨地图解锁或共享视觉 Token。
- 正式输入字段需映射到现有来源与内容版本；地图仅消费快照，不持久化副本。
- 正式证据写入是新增的受控状态转移，不能复用会被理解为“已通过”的完成状态。
- 当前本地存储键 `muchen-journey.delivery-guild.v1` 只属于隔离原型，正式集成不得迁移为业务事实。

## 迁移要求

1. 总控先定义只读快照与 `PENDING_HUMAN_REVIEW` 写入契约、鉴权、审计和错误语义。
2. 用合成 fixture 做契约测试，确认无真实客户、项目或个人数据进入测试。
3. 由总控创建 controller-assigned runtime module，并把地图四步状态机接入；地图任务不直接修改 `/` 或全局导航。
4. 先做只读集成候选；共享写入必须单独安全评审并显式授权。
5. 真人门槛与跨地图回归通过后，仍由总控创建唯一发布候选；本地图不发布。

## 验证证据

- 独立验收：[evaluation-report.md](evaluation-report.md)
- 三档终点截图：`browser-evidence/evaluator-{390,768,1280}-end.png`
- 契约测试：5/5 通过
- 运行观察：三档无水平溢出，控制台 0 error/0 warning，网络仅本地静态 HTML
- 治理观察：界面持续说明未发送、未写共享 Evidence Ledger、未发生导师反馈或真人验收

## 总控决策点

在真人验收前，只审阅契约可兼容性并保持候选隔离。真人通过后，总控再决定是否分配运行时模块与共享 API 适配工作；若共享状态或权限语义不满足上述要求，不得以本地存储实现替代。
