# Muchen Journey Owner 任命与接受记录 V0.1

> 状态：`ALL_ROLES_APPOINTED / 8_OF_16_ACCEPTED / DEVELOPMENT_OVERRIDE_ACTIVE / RELEASE_BLOCKED`  
> 任命日期：2026-08-23  
> 任命来源：刘默文在当前任务中的直接裁决  
> 本文件覆盖上一版候选提名；任命决定不等于对应 Build Contract 已批准。
> 2026-08-23 刘默文已另行直接授权全模块开发；见 `Muchen_Journey_全模块开发解锁决议_V0.1.md`。该授权不等于团队本人接受或正式发布批准。

## 1. 权威任命表

“已接受”只用于本人直接接受或 Owner 明确核验并作出接受事实声明的角色。对郑田源、屠元琦、段超群的任命已由业务 Decider 作出，但仍需本人确认可投入时间、首个结果和职责边界。2026-08-26，Owner 明确确认冯宇汀已经接受“独立 QA＋独立 Release Reviewer”；该文字确认为任命与接受证据，不等于任何候选级签署。

| # | 角色 | 任命人 | 任命状态 | 本人接受状态 | 首个责任结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 产品 Owner | 刘默文 | `APPOINTED` | `ACCEPTED` | 六模块范围、顺序、停做清单和合同最终产品签署 |
| 2 | 探索营业务 Owner | 郑田源 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 四宝藏、三项实操与下一训练阶段人工Gate可用 |
| 3 | 新手村运营 Owner | 屠元琦 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 任务队列、Reviewer SLA、异常升级和运营闭环可用 |
| 4 | AI学院 Owner | 段超群 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 首个学习单元转化为实操、证据和人工结论 |
| 5 | 公会 Owner | 段超群 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 第一公会使命、任务包、导师池和短周期实践闭环 |
| 6 | 认证治理 Owner | 段超群 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 首个认证对象、Panel、有效期、重试和申诉规则 |
| 7 | 人才发展 Owner | 段超群 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 首个Career Map目标角色、证据、差距和Growth Plan |
| 8 | Reviewer/Panel Owner | 屠元琦 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | Reviewer/Panel池、校准、排班、替补与申诉复核 |
| 9 | Tech Lead | 刘默文 | `APPOINTED` | `ACCEPTED` | 唯一代码基线、状态机、权限、测试隔离和技术签署 |
| 10 | Data Owner | 刘默文 | `APPOINTED` | `ACCEPTED` | schema、历史迁移、数据质量、备份恢复和数据裁决 |
| 11 | Security/Privacy Owner | 刘默文 | `APPOINTED` | `ACCEPTED` | 数据分级、最小权限、保留、访问审计和风险接受 |
| 12 | QA/UAT Owner | 屠元琦 | `APPOINTED` | `PENDING_PERSONAL_ACCEPTANCE` | 负向合同测试、真人UAT和缺陷关闭证据 |
| 13 | Release/Ops Owner | 刘默文 | `APPOINTED` | `ACCEPTED` | 监控、告警、通知、备份恢复、回滚和发布执行 |
| 14 | 业务 Decider | 刘默文 | `APPOINTED` | `ACCEPTED` | 业务冲突裁决、风险例外、恢复开发和发布终决 |
| 15 | 独立 QA | 冯宇汀 | `APPOINTED` | `ACCEPTED_BY_OWNER_ATTESTATION` | 对固定候选 SHA 复核四模块机器证据、真人 UAT、P0/P1、权限隐私和恢复证据 |
| 16 | 独立 Release Reviewer | 冯宇汀 | `APPOINTED` | `ACCEPTED_BY_OWNER_ATTESTATION` | 对同一固定候选 SHA 完成 Production Preflight 和独立发布复核签署 |

任命完成度：`16/16`。角色接受完成度：`8/16`。完整 Build Contract 签署完成度：`0/6`。

G6 角色阻塞更新：`INDEPENDENT_QA_UAT_NOT_APPOINTED=RESOLVED`；`INDEPENDENT_RELEASE_REVIEWER_NOT_APPOINTED=RESOLVED`。继续保持：`HUMAN_UAT=NOT_RUN`、`INDEPENDENT_QA_SIGNOFF=NOT_RUN`、`RELEASE_REVIEW=NOT_RUN`、`RELEASE_AUTHORIZED=false`。

## 2. 任命的最低界限条件

### G-SOD-01｜刘默文的六角色集中

刘默文同时承担产品、技术、数据、安全、发布和业务终裁。这可以作为资源有限阶段的临时组织设计，但不能形成自审、自签、自发布：

- 任一 Build Contract 除刘默文签署外，必须取得对应模块 Owner 和屠元琦以 QA/UAT 身份的独立签署；
- 任一历史数据导入、生产迁移或发布，必须增加一名未参与执行的独立技术/数据复核人并留下复核记录；
- Security例外必须写明风险、范围、期限和撤销条件，并由模块Owner＋QA/UAT共同确认；
- 刘默文可以作最终风险接受人，但不能把自己的执行记录当成独立验收证据。

未满足上述条件时，状态保持 `NO_BUILD` 或 `NO_RELEASE`。

### G-SOD-02｜屠元琦的运营、Reviewer与QA集中

屠元琦可以管理Reviewer/Panel机制并拥有QA/UAT Gate，但在BC-002中同时是新手村运营Owner，因此：

- 不得作为自己发布任务或自己运营案例的唯一Reviewer；
- 不得同时完成同一案例的评分、独立复核和UAT签署；
- BC-002首个真实任务必须另设执行Reviewer和独立UAT见证人；
- 申诉必须由未参与原结论的Reviewer处理。

### G-SOD-03｜段超群的四模块集中

段超群承担AI学院、公会、认证治理和人才发展四个模块的组合责任。该任命可作为组合Owner，但不能把四个模块变成单人内容生产：

- 每个模块在批准Build前必须各自指定Content/Task/Panel/能力模型子Owner；
- BC-004必须指定第一公会实际业务线Owner和导师Owner；
- BC-005必须指定实际考官/Panel成员，段超群不得单人签发认证；
- BC-006必须指定角色/能力内容Owner及Growth Plan确认人；
- 任一模块连续两个Gate逾期时，触发拆分Owner而不是继续叠加职责。

## 3. 接受确认表

建议本人确认截止：2026-08-25 18:00（Asia/Shanghai）。沉默、参会、收到文件或继续工作不算接受。

| 姓名 | 被任命角色 | 接受/拒绝 | 每周可投入 | 首个交付及日期 | 所需权限/支持 | 本人签名/日期 |
| --- | --- | --- | --- | --- | --- | --- |
| 郑田源 | 探索营业务 Owner | `PENDING` |  | 四宝藏/三实操正式版本表 | 内容Owner、Reviewer池、训练台账 |  |
| 屠元琦 | 新手村运营；Reviewer/Panel；QA/UAT | `PENDING` |  | Reviewer池、BC-001/002校准与UAT名单 | 独立Reviewer、UAT环境、证据访问 |  |
| 段超群 | AI学院；公会；认证治理；人才发展 | `PENDING` |  | 四模块首批对象和子Owner清单 | 内容/业务线/Panel/人才能力来源 |  |
| 冯宇汀 | 独立 QA；独立 Release Reviewer | `ACCEPTED_BY_OWNER_ATTESTATION` | 候选冻结后安排 | 固定候选 SHA 的独立 QA 与 Release Review | 只读候选、UAT、权限、恢复和 Preflight 证据 | Owner 文字确认，2026-08-26 |

刘默文承担的六个角色已由本次直接陈述确认接受，不需要重复填本表；但对应合同、技术基线、数据迁移和发布仍需逐件签署。

## 4. 七日交付 Gate

| Owner | 截止 | 必须形成的可使用结果 | 验收组合 |
| --- | --- | --- | --- |
| 刘默文｜产品 | 2026-08-30 | 六模块首批对象、优先顺序、停做清单和Owner冲突处理 | 模块Owner＋QA/UAT |
| 刘默文｜技术/数据/安全/发布 | 2026-08-30 | 独立复核人名单、测试隔离、备份恢复、数据/安全Gate和发布四眼规则 | 屠元琦＋对应模块Owner |
| 郑田源 | 接受后7日 | BC-001四宝藏、三实操、Reviewer与下一阶段接口版本表 | 刘默文＋屠元琦 |
| 屠元琦 | 接受后7日 | BC-002首个任务运营包；Reviewer/Panel池；BC-001/002负向UAT | 刘默文＋对应模块Owner |
| 段超群 | 接受后7日 | BC-003—006各自首批对象、子Owner、证据与人工Gate清单 | 刘默文＋屠元琦 |
| 冯宇汀 | 候选冻结后、最终 GO 前 | 对同一候选 SHA 分别完成独立 QA 和独立 Release Review | 刘默文＋对应模块 Owner；不得由 Builder 代签 |

## 5. 任命重开条件

本人拒绝；无法说明时间投入；连续两个Gate逾期且未升级；职责冲突未按G-SOD隔离；模块首批对象没有真实使用者；数据/安全或发布风险超出授权。触发任一项时，业务Decider必须拆分、改任或暂停模块。
