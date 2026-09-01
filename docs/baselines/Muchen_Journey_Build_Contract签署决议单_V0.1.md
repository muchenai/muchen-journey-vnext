# Muchen Journey Build Contract 签署决议单 V0.1

> 状态：`ALL_ROLES_APPOINTED / 6_OF_14_ACCEPTED / ZERO_CONTRACTS_FULLY_SIGNED / DEVELOPMENT_ACTIVE_BY_DECIDER_OVERRIDE / NO_RELEASE`  
> 日期：2026-08-23  
> 关联文件：`Muchen_Journey_Owner任命与接受记录_V0.1.md`、`Muchen_Journey_Build_Contract签署包_V0.1.md`

## 1. 当前签署结论

14项角色已由刘默文全部任命。刘默文本人承担的产品、技术、数据、安全、发布和业务裁决6项角色已明确接受；郑田源1项、屠元琦3项、段超群4项共8项仍待本人接受。六份合同仍未完成全体签署，但刘默文已直接授权全模块开发；该例外不替代模块内容、独立QA、数据安全、真人Gate和正式发布签署。

## 2. 统一业务不变量签署

| 决议 | 结论 | 证据状态 | 裁决人 |
| --- | --- | --- | --- |
| 探索营采用V1.0四宝藏，个人成长基线为结果包 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| 学习可异步，能力结果来自实操、证据和人工Gate | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| 允许受控真实任务，但Journey不直接执行生产作业 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| 正式任务必须提交、审核、返工/通过；自证不产生正式状态 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| 积分不能单独产生人才结论 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| Day1只决定下一训练阶段 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| 历史数据先审计再分类处理 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| 第一发布含AI学院、公会、竞技场和Career Map | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |
| AI只做自查、初评和摘要；高影响结论真人签署并可申诉 | `APPROVED_DIRECTION` | 用户直接裁决 | 刘默文 |

## 3. 六份合同签署状态

| Contract | 产品Owner | 模块Owner | Tech | Data/Security | QA/UAT/Reviewer | 当前结论 | 最短解锁动作 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BC-001 探索营 | 刘默文 `ACCEPTED_ROLE` | 郑田源 `APPOINTED_PENDING_ACCEPTANCE` | 刘默文 `ACCEPTED_ROLE` | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | `OWNER_ASSIGNED / CONTENT_PENDING / NO_BUILD` | 郑田源、屠元琦接受＋四宝藏/三实操版本和执行Reviewer签署 |
| BC-002 新手村 | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | 刘默文 `ACCEPTED_ROLE` | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | `OWNER_ASSIGNED / DATA_AND_SOD_BLOCKED` | 23表全量导出＋首个真实任务六项前置＋独立Reviewer/UAT见证人 |
| BC-003 AI学院 | 刘默文 `ACCEPTED_ROLE` | 段超群 `APPOINTED_PENDING_ACCEPTANCE` | 刘默文 `ACCEPTED_ROLE` | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | `OWNER_ASSIGNED / FIRST_UNIT_BLOCKED` | 段超群、屠元琦接受＋首个单元、Content Owner、练习和Rubric |
| BC-004 公会 | 刘默文 `ACCEPTED_ROLE` | 段超群 `APPOINTED_PENDING_ACCEPTANCE` | 刘默文 `ACCEPTED_ROLE` | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | `OWNER_ASSIGNED / GUILD_SELECTION_BLOCKED` | 第一公会业务线Owner、导师Owner和任务包 |
| BC-005 认证竞技场 | 刘默文 `ACCEPTED_ROLE` | 段超群 `APPOINTED_PENDING_ACCEPTANCE` | 刘默文 `ACCEPTED_ROLE` | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | `OWNER_ASSIGNED / GOVERNANCE_BLOCKED` | 实际考官/Panel、独立申诉复核人和首个认证合同 |
| BC-006 Career Map | 刘默文 `ACCEPTED_ROLE` | 段超群 `APPOINTED_PENDING_ACCEPTANCE` | 刘默文 `ACCEPTED_ROLE` | 刘默文 `ACCEPTED_ROLE` | 屠元琦 `APPOINTED_PENDING_ACCEPTANCE` | `OWNER_ASSIGNED / MODEL_BLOCKED` | 目标角色、能力内容子Owner、Growth Plan确认人与可见性规则 |

## 4. 签署顺序

### S0｜接受任命

郑田源、屠元琦、段超群填写《Owner任命与接受记录》的接受表。刘默文的六项角色已经接受，但必须补齐独立技术/数据复核人和职责分离Gate。

退出 Gate：三名团队Owner本人接受；所有责任有时间投入、首个结果和升级人；G-SOD-01—03的独立复核人/子Owner落实。

### S1｜先签BC-001

BC-001是最接近可签署的合同，但仍需以下附件：

- 四宝藏正式名称、材料、顺序、版本和Content Owner；
- 三项实操的输入、产出、Rubric、Reviewer和返工规则；
- “进入下一训练阶段/补强复测/暂缓”的签署人、SLA和申诉人；
- 3名目标学员、2名Reviewer和负向测试名单。

附件齐全并完成产品、模块、Tech、Security、QA签署后，BC-001才可标记 `APPROVED_FOR_BUILD`。

### S2｜再签BC-002

BC-002在S1之后签署，但不等待BC-001开发完成。必须先补：

- 23张历史表全量只读导出及数量/语义对账；
- 首个受控真实任务的授权、数据、隔离、Reviewer、保留和退出六项前置；
- 技术Data Owner、Security/Privacy和Release/Ops；
- 任务队列、逾期、替补Reviewer、通知失败和申诉演练。

### S3｜BC-003—006逐份签

这些模块仍属于第一发布，但按首批对象逐份授权，不接受“先做占位页面，之后再补业务”的方式。

## 5. 单合同签署记录

每份合同复制一份本表，不得用口头“没问题”代替。

| 字段 | 值 |
| --- | --- |
| Contract / Version |  |
| 正式来源 / MAP-ID |  |
| 首批对象 |  |
| 产品 Owner | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| 模块业务 Owner | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| Tech Lead | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| Data Owner | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| Security/Privacy | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| QA/UAT | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| Reviewer/Panel Owner | 姓名／`APPROVE-REVISE-REJECT`／日期 |
| 已接受的风险例外 |  |
| 开发授权范围 |  |
| 禁止开发范围 |  |
| 重签触发 |  |

## 6. 当前允许和禁止

### 允许

- 郑田源、屠元琦、段超群阅读任命记录与对应合同，并明确接受或拒绝任命；
- 补齐内容版本、首批任务、Reviewer名单和数据只读导出；
- 继续W0测试隔离、备份恢复、权限审计和PR Gate；
- 制作不写业务状态的技术Spike，但不得合入产品主线。

### 禁止

- 在没有实名Owner的模块继续发明页面、地图、状态或自动判断；
- 把组织任命写成本人已接受，把待评审合同写成已签署；
- 让同一人同时生成内容、唯一评分、独立复核和发布；
- 创建正式基线tag、导入历史数据、开放真实任务或部署生产。

## 7. 签署完成定义

单份合同只有同时满足以下条件才算签署完成：

1. 每个必需角色均由自然人接受；
2. 首批对象、范围、证据、状态、指标和禁止项明确；
3. 负向测试、真人UAT、申诉、数据保留和回滚可执行；
4. 每位签署人写明 `APPROVE` 和日期；
5. 文件状态由产品Owner改为 `APPROVED_FOR_BUILD`，并在PR中绑定合同版本。

目前完成数：`0/6`。
