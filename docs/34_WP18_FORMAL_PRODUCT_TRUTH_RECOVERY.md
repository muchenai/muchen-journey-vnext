# 34｜WP-18 正式产品真相恢复与 vNext 重接合同

状态：`APPROVED_FOR_BUILD`

恢复结论：`PRODUCT_TRUTH_RECOVERED / IMPLEMENTATION_NOT_STARTED`

版本：V0.1

日期：2026-08-03

文档 Owner：Product Owner + Content Owner + Design Owner + Tech Lead

适用范围：正式探索营产品目标、内容架构、vNext 领域扩展和 WP-17 后续实现

## 1. 本次恢复关闭什么问题

当前 vNext 已证明邀请、独立身份、唯一当前行动、不可变提交、主管评审、要求修订、再次提交、通过和结果可以形成真实闭环；但 `DEC-004/016` 为 walking skeleton 把内容收缩为单个 `TSK-001` 后，这个验证切片逐渐被误当成正式探索营本身。

旧正式方案的产品事实不是“一个任务加一次评审”，而是：

```text
Day 0 启程
  → 四个认知宝藏
  → 三个能力评测
  → 综合结果与后续去向
```

因此本次恢复只纠正产品目标和后续构建合同，不回滚 vNext、不复用旧运行时、不导入旧业务事实，也不改变当前受控 Alpha 的已产生事实。

## 2. 证据与四/五宝藏歧义

旧归档中存在两种表述：

- 后端正式评审门禁要求 `day-0`、四个认知宝藏和三道实操全部完成；
- 部分旧前端把“四个认知宝藏”与“能力准入容器”并列成五个模块，并进一步写成“五个宝藏”。

本次统一口径：

1. `entry-assessment` 是三个能力评测的容器，不是第五个宝藏；
2. 正式产品结构固定为“四个宝藏 + 三个能力评测”；
3. 旧仓库只作为需求发现证据，旧代码、路由、状态和数据库均不是实现来源；
4. 旧文案、材料和评分阈值必须重新经过内容、版权、敏感度和 Reviewer 校准，不因结构恢复而自动批准原文上线。

## 3. 正式探索营唯一结构

| 顺序 | 稳定键 | 类型 | 对 Learner 的真实问题 | 必需证据 | 完成责任 |
| --- | --- | --- | --- | --- | --- |
| 0 | `DAY-0` | 启程 | 我为什么来到这里，接下来会经历什么？ | 最小确认与当前行动理解 | Learner |
| 1 | `TRE-001-COMPANY-VALUES` | 认知宝藏 | 这家公司在解决什么问题，期待怎样的 Muchener？ | 价值理解反思 | Learner |
| 2 | `TRE-002-AI-DATA-BASICS` | 认知宝藏 | 模型为什么会出错，人的判断为什么重要？ | AI 数据认知证据 | Learner |
| 3 | `TRE-003-PROJECT-AWARENESS` | 认知宝藏 | AI 数据项目怎样为客户和模型产生价值？ | 项目认知证据 | Learner |
| 4 | `TRE-004-DELIVERY-FIT` | 认知宝藏 | 在真实交付中，我负责什么，何时必须提报？ | 交付与边界证据 | Learner |
| 5 | `ASM-001-RULE-BREAKDOWN` | 能力评测 | 我能否把规则拆成目标、维度、红线和提报点？ | 不可变实操作答 | Reviewer |
| 6 | `ASM-002-MODEL-JUDGEMENT` | 能力评测 | 我能否比较模型回答并给出可复核理由？ | 不可变实操作答 | Reviewer |
| 7 | `ASM-003-BOUNDARY-ESCALATION` | 能力评测 | 我能否识别不确定边界并提出有效问题？ | 不可变实操作答 | Reviewer |
| 8 | `JOURNEY-OUTCOME` | 结果 | 我证明了什么，还需要发展什么，下一步去哪里？ | 三项评测的人工结论与完整旅程事实 | System + Reviewer |

四个宝藏不是装饰性关卡，而是让 Learner 获得完成能力评测所需的认知基础；三个能力评测不是知识问答，而是产生可由 Reviewer 复核的行为证据。

## 4. 与 vNext 基座的重接方式

### 4.1 保留不变的基座

以下现有能力继续作为唯一事实源，不建立第二套探索营实现：

- `Invite / User / ExternalIdentity / RoleAssignment / Session`；
- `Enrollment` 的组织、Learner、Reviewer 和生命周期；
- `TaskDefinition / TaskVersion / Assignment` 的版本化执行；
- `Submission / SubmissionVersion` 的不可变证据；
- `Review / Evaluation` 的授权、修订和人工结论；
- `Outcome / Handoff` 的结果与后续去向；
- Current Action Resolver 的“任何时刻只有一个有效行动”；
- 幂等、组织隔离、审计、通知降级、备份恢复与发布合同。

### 4.2 必须新增的产品编排合同

后续实现只补足当前基座缺失的“多阶段旅程”层：

| 新合同 | 责任 | 不允许承担 |
| --- | --- | --- |
| `JourneyDefinition` | 探索营的稳定身份 | Learner 当前进度或提交正文 |
| `JourneyVersion` | 固定四宝藏、三评测、顺序和发布版本 | 运行时随意改序 |
| `JourneyStageVersion` | 绑定稳定阶段键、类型、顺序、前置条件、TaskVersion 和完成策略 | 复制 Assignment 状态机 |
| `Enrollment.journey_version_id` | 让参与者固定进入一个不可变旅程版本 | 自动迁移在途 Learner |
| `JourneyOutcomeEvidence` | 让正式 Outcome 不可变引用三个能力评测的有效 Evaluation | 复制评价正文或制造第二结论 |
| Journey Progress Projection | 从 Enrollment、Assignment、Submission、Evaluation 推导旅程位置 | 成为可写的第二状态源 |

每个阶段仍由现有 `TaskVersion + Assignment` 执行：

- 宝藏使用 `LEARNER_EVIDENCE` 完成策略：提交必需认知证据后完成，不产生能力 PASS，也不需要 Reviewer 逐关审批；
- 能力评测使用 `REVIEW_REQUIRED` 完成策略：完整复用现有提交、开始评审、要求修订、再次提交与通过路径；
- `Outcome` 只有在 Day 0、四个宝藏和三个评测全部完成，且三个评测均存在有效人工结论后才能产生；
- 能力画像是三份 `Evaluation` 的可追溯投影，不新增不可解释的总分作为事实源。

若实现发现 `LEARNER_EVIDENCE` 无法在不破坏 Assignment 不变量的情况下成立，必须先回到领域合同评审；禁止用前端 localStorage、隐藏布尔值或自动伪造 Reviewer 结论完成宝藏。

## 5. Current Action 与页面合同

`/app` 继续是 Learner 唯一首页；不恢复旧版 map/dashboard/learning 等平行入口。Current Action Resolver 按以下顺序工作：

1. 身份或 Enrollment 未完成时，返回现有恢复动作；
2. 返回 JourneyVersion 中第一个未完成且前置条件满足的阶段；
3. 宝藏阶段进入认知材料与证据提交；
4. 评测阶段进入现有任务、提交、等待评审和修订闭环；
5. 全部完成后才返回正式结果与后续去向。

WP-17 的视觉语言可以保留，但正式地图必须表达：

```text
启程 ─ 宝藏 1 ─ 宝藏 2 ─ 宝藏 3 ─ 宝藏 4
                                  ↓
                         评测 1 ─ 评测 2 ─ 评测 3 ─ 结果
```

- 首屏命题继续使用“这里，没有标准答案。”；
- 四个宝藏以可探索节点呈现，三个评测以能力验证节点呈现，视觉语义必须不同；
- 默认先用位置、路线、状态和可操作热点表达，悬停、键盘聚焦或触摸后补充一句必要说明；
- `/review` 与 `/ops` 继续保持专业工具界面；
- “宝藏”只能作为 Learner 叙事层名称，同时展示清楚的业务含义，不能掩盖交付、证据与人工判断。

## 6. TSK-001 的重新定位

`TSK-001 问题洞察与行动建议` 已完成真实修订闭环，证明了 vNext 基座可用，因此历史 TaskVersion、Assignment、Submission、Review、Evaluation 和 Outcome 全部保留。

但 TSK-001 不等同于四个宝藏中的任意一个，也不等同于三个正式能力评测。它的正式定位改为：

`ALPHA_VALIDATION_TASK / OUTSIDE_FORMAL_EXPLORATION_JOURNEY`

除非后续 Product + Content + Reviewer 通过新决策证明它测量某一正式能力，否则不得为了复用现有页面而把它强行改名或塞进四加三结构。

## 7. 对现有决策和 WP-17 的影响

- `DEC-004/016` 继续解释为什么首个 Alpha 只实现 TSK-001，并继续约束已产生的 Alpha 证据；
- `DEC-024` 从本文件生效后，正式产品目标不再由单任务 Alpha 切片代表；
- WP-17 只关闭视觉方向与三状态原型，不关闭正式探索营信息架构；
- 当前 WP-17 原型中的三个路线点是视觉交互样例，不是正式阶段数量，不得直接接入生产路由；
- 正式 Learner 页面实现必须等待多阶段 Journey 合同和四加三内容版本完成。

## 8. 新需求与验收

| ID | 要求 | 最小验收 |
| --- | --- | --- |
| `REQ-BR-011` | 一个 Enrollment 固定引用一个不可变 JourneyVersion | 新版本不改变在途 Learner；顺序与前置条件由服务端强制 |
| `REQ-BR-012` | 正式探索营恰好包含四个认知宝藏 | 四个稳定键、目的、证据、内容版本与 audience 均可追溯 |
| `REQ-BR-013` | 正式探索营恰好包含三个能力评测 | 三项独立提交、人工评审、修订与通过均绑定固定版本 |
| `REQ-BR-014` | 只有完整四加三事实才能产生正式 Journey Outcome | 缺任一阶段或人工结论时服务端拒绝完成 |
| `AT-PRODUCT-001` | 产品结构唯一 | 页面、配置、API 和测试均只出现 Day 0 + 四宝藏 + 三评测 + 结果 |
| `AT-DATA-009` | 多阶段顺序与不可变性 | 跳关、重复完成、跨版本、跨组织和并发完成均被拒绝 |
| `AT-CONTENT-009` | 宝藏内容有效 | 目标 Learner 无口头解释能说出每个宝藏为何存在、需留下什么证据 |
| `AT-CONTENT-010` | 能力评测可校准 | 至少三类样本由独立 Reviewer 校准并得到可解释结论 |
| `AT-UX-010` | 旅程理解 | 首次使用者 5 秒内识别当前位置、下一个节点和四加三总体结构 |
| `AT-UAT-009` | 真人完整旅程 | 真实 Learner 完成四宝藏、三评测、至少一次修订并获得最终结果 |

## 9. 单一 WIP 与实施顺序

本文件完成 WP-18 的“产品真相恢复”，不授权直接重写全部页面。后续保持单一 WIP：

1. `WP-19 Journey Composition`：只实现 JourneyDefinition/Version/Stage、顺序、Current Action 和迁移，不制作完整视觉页面；
2. `WP-20 Four Treasures Content`：逐个发布四个宝藏的批准 TaskVersion 与 Learner 证据路径；
3. `WP-21 Three Ability Assessments`：接入三项评测、Rubric 和 Reviewer 修订闭环；
4. `WP-22 Formal Learner Experience`：把 WP-17 视觉语言接到真实四加三状态；
5. `WP-23 Full Journey UAT`：由真实 Learner/Reviewer 完成不可替代的完整旅程验证。

WP-19 开工前必须补齐 API/数据迁移设计和失败矩阵；不得同时铺开 WP-20～WP-23。

## 10. WP-18 关闭条件

- [x] 四/五宝藏歧义已解释并锁定为四宝藏 + 三能力评测；
- [x] 七个正式阶段的稳定身份、目的和证据责任已定义；
- [x] TSK-001 已从“正式产品全部内容”重新定位为 Alpha 验证任务；
- [x] vNext 可复用基座和必须新增的 Journey 编排层已分开；
- [x] UI、Current Action、领域不变量和 UAT 影响已定义；
- [x] 后续单一 WIP 顺序已定义；
- [ ] 四个宝藏的最终正文、材料来源、敏感度和版权完成 Content Review；
- [ ] 三个能力评测题面、Rubric、边界样本和 Reviewer 校准完成批准；
- [ ] WP-19 的 schema/API/迁移合同通过工程评审。

未勾选项属于后续构建 DoR，不改变 `PRODUCT_TRUTH_RECOVERED`，也不得被误写成正式内容已实现或已上线。
