# Muchen Journey Construction V1｜Owner Decision Pack V1.0

> 状态：`SUPERSEDED_BY_V1.1 / DO_NOT_USE_FOR_ACTIVE_BLOCKER_COUNT`
>
> 2026-08-27 起，活动决策包为 `Muchen_Journey_Construction_V1_Owner_Decision_Pack_V1.1.md`。本文件中的 `PENDING_OWNER_INPUT` 仅保留历史审计，不得再计入当前字段缺口；当前只按 V1.1 的精确 hash 签署 Gate 判断。

状态：`TECHNICAL_CHECKPOINT_AUTHORIZED / OWNER_INPUT_PENDING / NO_RELEASE`  
记录日期：2026-08-26  
适用范围：Construction V1 首发四模块的内容、任务、Reviewer 与运营决定  
机器填写边界：仅抄录批准来源已经明确的事实；任何未获 Owner 明确决定的字段均为
`PENDING_OWNER_INPUT`。

## 1. 本次 candidate-prep 授权

刘默文以 Product Owner、Tech Lead、Release/Ops Owner 和业务 Decider 身份授权 Mini：

- 新建隔离的 candidate-prep branch/worktree；
- 从最新受控 stage 纳入 `RELEASE_REQUIRED / IN_SCOPE_CANDIDATE` 的代码、迁移、配置、测试和必要证据；
- 重新生成完整 inventory，要求 `UNKNOWN=0`；
- 创建可审计的本地 Git technical-checkpoint commit，并保存 SHA、diff、测试和回滚证据。

该定向授权仅覆盖 Construction V1 technical checkpoint，并在此范围内取代旧
`config/muchen_journey_product.json` 的通用 `pro_audit_control.commit_authorized=false`。
它不改变以下 Gate：

- `deploy_authorized=false`；
- `release_authorized=false`；
- `production_mutation_authorized=false`；
- `candidate_frozen=false`；
- `ready_for_uat=false`。

不得纳入 Career Map、认证竞技场、Boss Dungeon、自动跨模块准入、历史迁移或其他
`POST_RELEASE_DEFERRED` 内容；不得代替模块 Owner、真人 UAT、独立 QA 或 Release Review。

## 2. 郑田源｜探索营决定表

Owner 任命：郑田源，`APPOINTED / PENDING_PERSONAL_ACCEPTANCE`。  
批准来源：

- `construction-v1.0/02_模块分册/01_探索营_V1.0.md`；
- `build-contracts/BC-001_探索营_V1.0_V0.1.md`；
- `module-content-package.schema.v1.json`。

### 2.1 四宝藏

| 顺序 | 已批准目录名 | 正式材料/链接 | ContentVersion | 时长 | 内容 hash | Owner 决定 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 公司与 Muchener | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |
| 2 | AI 数据行业与模型 | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |
| 3 | 项目认知 | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |
| 4 | 项目交付与组织适配 | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |

固定边界：只使用上述 V1.0 四宝藏；不得改为五宝藏或面向学员的八站结构。Day0 材料、问题收集、
保密说明、未完成处理规则及对应版本同样为 `PENDING_OWNER_INPUT`。

### 2.2 三项实操

| Task key | 已批准实操 | 已批准最低交付结构 | 最终输入/版本 | Rubric/阈值/校准 | 主/备 Reviewer | 时限/SLA | Owner 决定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `EXP-P1` | 规则拆解 | 目标、判断维度、红线、例外、不确定项、需提报问题 | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |
| `EXP-P2` | 模型回答判断 | 选择/无法判断、维度、理由、证据、不确定项 | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |
| `EXP-P3` | 边界与问题提报 | 已知事实、未知项、影响、临时处理建议、需谁裁决 | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` | `PENDING_OWNER_INPUT` |

固定边界：正式结果必须来自不可变 SubmissionVersion、真人 Review/Evaluation 和签署；总分、AI、积分、
材料点击或自证不能自动产生下一训练阶段决定。三种允许的中文决定为“进入下一训练阶段 / 补强后复测 /
暂缓”，不得解释为录用、淘汰或项目准入。

## 3. 屠元琦｜新手村首批任务决定表

Owner 任命：屠元琦，`APPOINTED / PENDING_PERSONAL_ACCEPTANCE`。  
批准来源：

- `construction-v1.0/02_模块分册/02_沐晨新手村.md`；
- `build-contracts/BC-002_新手村受控任务闭环_V0.1.md`；
- `module-content-package.schema.v1.json`。

首发只选择 1—3 条任务；旧任务名仅是候选，未被本包选定。

| 字段 | 决定值 |
| --- | --- |
| 首批任务数量、taskKey、名称与类型 | `PENDING_OWNER_INPUT` |
| 授权项目、Project Owner、授权用途与有效期 | `PENDING_OWNER_INPUT` |
| 固定 TaskVersion 与训练用途 | `PENDING_OWNER_INPUT` |
| execution environment（SIMULATION/CONTROLLED_REAL_TASK） | `PENDING_OWNER_INPUT` |
| 数据等级、允许输入、来源版本及脱敏规则 | `PENDING_OWNER_INPUT` |
| Learner/Reviewer/Operator 可见范围 | `PENDING_OWNER_INPUT` |
| 交付物、格式、示例/反例与截止时间 | `PENDING_OWNER_INPUT` |
| RubricVersion、人工通过标准与不可接受项 | `PENDING_OWNER_INPUT` |
| 主 Reviewer、备 Reviewer 与替补条件 | `PENDING_OWNER_INPUT` |
| 首响/完成 SLA、容量和升级路径 | `PENDING_OWNER_INPUT` |
| 积分/徽章数值、授予权限、重复规则和更正规则 | `PENDING_OWNER_INPUT` |
| 证据保留、删除或封存规则 | `PENDING_OWNER_INPUT` |
| ControlledTaskAuthorization 签署证据 | `PENDING_OWNER_INPUT` |

固定边界：Journey 不持有生产写凭证、不自动发送或写入生产系统、不把未审核产物投递生产；
`production_write_allowed=false`、`raw_customer_data_allowed=false`、
`ai_high_impact_decision_allowed=false`。积分只能引用可验证事实，不能修改能力或人才状态。

## 4. 段超群｜AI 学院首个单元决定表

Owner 任命：段超群，`APPOINTED / PENDING_PERSONAL_ACCEPTANCE`。  
批准来源：

- `construction-v1.0/02_模块分册/03_AI学院.md`；
- `build-contracts/BC-003_AI学院_V0.1.md`；
- 正式方案引用 `GzknwrxybiOAOGkRrKKcjZyqnPb` 对应的
  《AI学院主管_2026下半年执行计划_V0.2》；
- `module-content-package.schema.v1.json`。

| 字段 | 决定值 |
| --- | --- |
| 首个单元名称、目标人群与能力目标 | `PENDING_OWNER_INPUT` |
| 正式材料、source refs、ContentVersion、顺序、时长和 hash | `PENDING_OWNER_INPUT` |
| 练习 TaskVersion、输入、交付物和非目标 | `PENDING_OWNER_INPUT` |
| AI 自查用途、披露要求和禁止行为 | `PENDING_OWNER_INPUT` |
| RubricVersion、人工维度、校准证据和阈值 | `PENDING_OWNER_INPUT` |
| 主/备 Reviewer、容量、SLA 和升级人 | `PENDING_OWNER_INPUT` |
| 组织资产候选的形成与发布政策 | `PENDING_OWNER_INPUT` |
| Owner 批准、有效期和签署时间 | `PENDING_OWNER_INPUT` |

固定边界：阅读、练习、AI自查、提交和人工结论必须区分；组织资产只能成为候选，不能自动发布；
AI 或材料完成不能产生正式能力结论。

## 5. 段超群｜交付线公会首个任务包决定表

Owner 任命：段超群，`APPOINTED / PENDING_PERSONAL_ACCEPTANCE`。  
批准来源：

- `construction-v1.0/02_模块分册/04_交付线公会.md`；
- `build-contracts/BC-004_公会_V0.1.md`；
- `module-content-package.schema.v1.json`。

| 字段 | 决定值 |
| --- | --- |
| 第一发布公会名称、使命、适用人群和业务线 Owner | `PENDING_OWNER_INPUT` |
| 目标能力、能力来源和证据有效期 | `PENDING_OWNER_INPUT` |
| 加入/试炼、暂停、退出和转会规则 | `PENDING_OWNER_INPUT` |
| 首个短周期 TaskVersion、输入、交付物和边界 | `PENDING_OWNER_INPUT` |
| RubricVersion、返工/通过标准和校准证据 | `PENDING_OWNER_INPUT` |
| 导师 Owner、主/备导师、容量、SLA 和升级路径 | `PENDING_OWNER_INPUT` |
| 数据等级、真实任务授权和证据保留规则 | `PENDING_OWNER_INPUT` |
| Owner 批准、有效期和签署时间 | `PENDING_OWNER_INPUT` |

固定边界：公会复用现有身份、Assignment、SubmissionVersion、Review/Evaluation、Evidence、通知、申诉和
审计；不复制第二套任务状态机，不自动认证、入项、岗位定级或执行生产作业。

## 6. 屠元琦｜共享 Reviewer 运营决定表

| 字段 | 决定值 |
| --- | --- |
| Reviewer pool ref 与专业/模块范围 | `PENDING_OWNER_INPUT` |
| 每模块主 Reviewer | `PENDING_OWNER_INPUT` |
| 每模块备 Reviewer | `PENDING_OWNER_INPUT` |
| 替补触发条件与具名升级人 | `PENDING_OWNER_INPUT` |
| 每人每周容量、开放时段和队列上限 | `PENDING_OWNER_INPUT` |
| first-response SLA | `PENDING_OWNER_INPUT` |
| completion SLA | `PENDING_OWNER_INPUT` |
| 超载、超时和通知失败升级路径 | `PENDING_OWNER_INPUT` |
| Reviewer 校准样例、允许差异和证据位置 | `PENDING_OWNER_INPUT` |
| 独立 UAT 见证人与回避关系 | `PENDING_OWNER_INPUT` |
| 本人接受、签署时间和有效期 | `PENDING_OWNER_INPUT` |

职责分离硬约束：屠元琦不得同时成为同一任务的运营者、唯一 Reviewer 和唯一 UAT 签署人；本人发布或运营的
案例必须另设执行 Reviewer 与独立 UAT 见证人；申诉由未参与原结论的 Reviewer 处理。

## 7. Owner 回填与验收格式

每位 Owner 的有效回填必须：

1. 对本包中属于本人范围的所有 `PENDING_OWNER_INPUT` 逐项给出值或明确拒绝首发；
2. 使用不可变版本、来源引用和内容 hash；
3. 给出签署人、签署时间、有效期和替代/撤销规则；
4. 通过 `module-content-package.schema.v1.json` 或对应 ControlledTaskAuthorization 合同；
5. 不以聊天收到、参会、机器测试或 Mini 生成内容代替本人接受与签署。

本包不是 Owner 签署、真人 UAT、独立 QA、候选冻结或发布批准。

## 8. 后续 Gate

`OWNER_CONTENT_BINDING_REQUIRED`  
→ `FINAL_CANDIDATE_FREEZE`  
→ `CURRENT_IMAGE_SECURITY_SCAN`  
→ `FIXED_CANDIDATE_RECOVERY`  
→ `REAL_HUMAN_UAT`

`production_mutation_executed=false`  
`production_deployment_executed=false`  
`external_message_sent=false`  
`legacy_migration_executed=false`  
`human_gate_filled_by_machine=false`
