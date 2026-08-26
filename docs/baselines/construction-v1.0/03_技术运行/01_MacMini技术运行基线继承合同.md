# 技术运行 01｜Mac mini 技术运行基线继承合同

> 唯一技术运行宿主：`/Users/liumowen/Documents/Muchen Journey2.0`（Mac mini）  
> 当前观察分支：`codex/full-module-development@b7597edfdf7d`（2026-08-26只读核验）  
> 当前状态：工作树大量未提交变更；不是冻结候选，不允许据此声明 Release GO。

## 1. 核心裁决

保留 Mac mini 上 `Muchen Journey2.0` 的全部有价值技术底座，暂停其继续发明产品逻辑。技术底座继续承担唯一开发、数据库、测试、打包、部署和运行职责；产品行为由本施工总包控制。

“Greenfield”只解释没有旧系统运行依赖，不表示产品行为可以从零设计。仓库 README 的旧前提必须补充为：

> 代码/数据库/部署可Greenfield；探索营、新手村和批准治理规则必须行为继承；旧系统不作为运行依赖，但作为产品行为证据。

## 2. 必须保留的运行资产

| 技术资产 | 当前载体 | 继承方式 |
| --- | --- | --- |
| Web | Next.js 16 / React 19 | `KEEP_CORE`，页面信息架构按本包重构 |
| API | FastAPI / Pydantic / SQLAlchemy | `KEEP_CORE`，业务命令按Requirement ID约束 |
| Worker | Outbox/Notification worker | `KEEP_CORE` |
| Database | PostgreSQL 18 + Alembic | `KEEP_CORE`，旧表不迁移 |
| 身份 | 邀请、会话、飞书OAuth、RoleAssignment | `KEEP_CORE` |
| 任务 | Journey/Task版本、Enrollment、Assignment | `KEEP_CORE / ADAPT_SEMANTICS` |
| 提交 | Draft、SubmissionVersion、Attachment | `KEEP_CORE` |
| 审核 | Review、Evaluation、Reviewer工作台 | `KEEP_CORE` |
| 结果 | Outcome、Handoff、formal result候选 | `KEEP_CORE / ADAPT_RESULT_SEMANTICS` |
| 治理 | Audit、Data Rights、Import ledger、权限裁剪 | `KEEP_CORE` |
| 运维 | Compose、健康检查、备份/恢复、release gate | `KEEP_CORE` |
| 共享domain候选 | Evidence/HumanGate/Appeal/GrowthPlan contracts | `KEEP_AND_PERSIST_BY_CONTRACT` |

## 3. 必须改写/隔离的语义

| 当前/候选语义 | 裁决 |
| --- | --- |
| 八站作为用户产品结构 | 改为四宝藏＋三实操；技术stage可存在但不主导UI |
| `JourneyAdmissionDecision ADMIT/DEFER/NOT_ADMIT` | 不得对用户呈现招聘准入；适配为下一训练阶段决定，保留旧表兼容只读 |
| 点击/自证推动正式进度 | 删除或降级为草稿/学习事实 |
| 五地图/BOSS/未批准跨图入口 | 归档或延期，不进9/1导航 |
| 机器READY/HUMAN候选文案 | 只作内部状态，不能展示成业务通过 |
| 公会/AI学院合成原型 | 复用交互候选，重绑真实内容和共享写入 |
| Legacy migration Gate | 对9/1发布标记 `SUPERSEDED_FOR_RELEASE`，不篡改历史报告 |

## 4. 当前工作树收口

禁止 `reset --hard`、整分支盲合或覆盖用户改动。Mini 应生成逐文件台账：

- `KEEP`：已经符合机器合同，可直接纳入；
- `ADAPT`：技术有用但语义需改；
- `ARCHIVE`：保留证据/原型，不进候选；
- `DROP_FROM_CANDIDATE`：不删除文件，只从构建/路由/发布范围排除。

每项记录：文件、当前hash、Requirement IDs、结论、测试、Owner、候选commit。未跟踪文件必须先审计再加入；不得把大量 `outputs/audits` 和历史包混入运行镜像。

## 5. 代码结构约束

- 共享核心在 API/domain 层维护，模块只提供配置/策略/视图组合；
- Web 不在客户端自行推断 formal status；只消费服务端 allowed actions；
- 正式 mutation 必须经API命令、幂等、expected revision、授权和审计；
- 数据库约束承载关键不变量，测试同时覆盖服务层和DB层；
- OpenAPI 与前端类型/合同同步；
- 所有新模块 route 先检查组织/人员/对象scope；
- 配置生成文件必须由权威配置生成并校验hash，不手工双写。

## 6. 技术基线 DoD

1. 当前工作树全部变更完成处置；
2. 本施工包和机器合同同步进仓库 `docs/baselines/construction-v1.0/` 或等价受控目录；
3. 所有P0 requirement有实现与测试映射；
4. 分支合并后工作树干净；
5. 空库升级到唯一 migration head；
6. API、Web、Worker全量测试和生产构建通过；
7. candidate package绑定完整Git SHA、OpenAPI hash、migration、配置、内容包hash和镜像digest；
8. 创建不可移动候选tag；
9. 候选部署后与manifest逐项对账；
10. 未经Release GO不执行production mutation或扩大名单。

## 7. 已知技术风险

- 当前分支为脏工作树，无法生成可信候选；
- 当前migration目录只见到0019，历史审计曾出现main到0021，必须以实际候选空库升级结果确认唯一head；
- `AssignmentStatus.COMPLETED` 与产品 `PASSED` 需统一外部语义；
- `JourneyAdmissionDecision` 仍有招聘式枚举，需兼容隔离；
- Compose 本地默认凭据只限 local，不得进入staging/production；
- 附件、飞书通知、外部告警曾处于禁用/未验证，首发必须明确启用范围；
- 现有 `nanoid` override/依赖审计和完整供应链扫描需在固定候选重跑。

