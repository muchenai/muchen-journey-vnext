# G6｜独立 QA/UAT 与发布复核合同 V0.1

> 状态：`G6A_READINESS_CONTRACT / CURRENT_NO_GO / HUMAN_SIGNOFF_AND_CANDIDATE_BLOCKED`  
> 日期：2026-08-24  
> Owner：`muchen-journey-program-control`  
> 上游合同：BC-001—006、G1—G5、WP-06、WP-07、WP-13/15、WP-29/30

## 1. 本阶段保护的人结果

全模块机器测试通过，不等于真实员工理解、真实任务有效、Reviewer 独立或产品可以发布。G6 建立一个只读、失败关闭的总控复核合同，把候选冻结、六份 Build Contract、G1—G5、六模块真人 UAT、历史数据 Data Owner 审批、Panel/申诉职责分离和既有 WP-06 发布 Gate 绑定到同一候选。

该合同只回答“当前还缺什么”。它不能创建 WP-07 候选、记录真人行为、批准发布、调用部署入口或执行生产变更。

## 2. 唯一发布路径

- 候选冻结和供应链继续由现有 `scripts/wp07_candidate.py` 与 Make targets 负责；
- WP-13/15 继续验证真人 UAT、试点和发布证据；
- WP-29/30 继续承担受控 RC 和 launch 合同；
- WP-06 `release-gate-check` 继续是完整发布 NO_GO/GO 事实源；
- `journey_api.program_release_readiness` 只聚合以上证据并输出 PII-free 裁决，不建立第二套打包、部署或生产入口。

## 3. 输入合同

输入必须精确包含：

1. 当前分支、完整 HEAD、工作树冻结状态和 WP-07 manifest；
2. G1—G5 五个总控组件的机器、Pro 复核、真人验证和 operationalization 状态；
3. BC-001—006 六份合同及其合同版本哈希；
4. 六模块 UAT，且 PASS 必须有真实目标参与者、完整场景、真实 QA 签署和固定候选 SHA；
5. 14 项 Owner 接受状态；
6. 真实历史 inventory 审计和 Data Owner 批准；
7. Builder、Owner、Reviewer、Panel、UAT、申诉和发布角色的匿名职责集合；
8. WP-06 的 17 项发布检查和显式双人发布批准。

每个来源都使用仓库相对路径和 SHA-256 绑定。报告拒绝绝对路径、路径逃逸、符号链接、超大文件、checksum 漂移、额外字段和范围缺失。

## 4. 真人与职责分离规则

- AI、合成脚本、自证、积分和机器测试不能填充真人 UAT 或签署；
- UAT PASS 必须绑定真实目标参与者、固定场景、非零参与人数、全部场景通过和 `REAL_HUMAN_SIGNATURE`；
- 至少一名 QA/UAT 签署人必须独立于 Candidate Builder、模块 Owner、正式 Reviewer 和 Panel；
- Panel 成员不能充当同一高影响结论的独立申诉复核人；
- Release Owner 与独立 Release Reviewer 必须是不同自然人；独立 Reviewer 不能同时属于 Builder、产品 Owner、模块 Owner 或 Release Owner 集合；
- 每份签署绑定固定合同 SHA-256 或完整候选 SHA；候选漂移后旧签署失效；
- BC-005 除通用六角色外，还必须有 Panel Owner 和独立 Appeal Owner。

## 5. 裁决语义

| 裁决 | 含义 | 是否允许执行 |
| --- | --- | --- |
| `NO_GO` | 候选、合同、治理、机器或运营前置仍缺失 | 否 |
| `READY_FOR_INDEPENDENT_UAT` | 非真人前置齐备，可安排真实独立 UAT | 否 |
| `READY_FOR_EXPLICIT_RELEASE_DECISION` | UAT 和全部前置齐备，等待独立发布签署 | 否 |
| `RELEASE_REVIEW_APPROVED_NO_EXECUTION` | 输入中的独立发布复核完整，但仍须通过授权运维入口执行 | 否 |

无论裁决为何，报告固定：`candidate_package_created=false`、`release_execution_authorized=false`、`production_mutation_executed=false`。

## 6. 当前事实

- 当前 HEAD 为开发基线，工作树包含继承的未提交全模块代码；历史 WP-07 manifest 不绑定当前 HEAD；
- G1—G5 机器合同通过，但 Pro 复核、真人验证和 operationalization 均未完成；
- Owner 接受 `6/14`，Build Contract 完整签署 `0/6`；
- 当前产品合同仍保留探索营旧 `MACHINE_FAIL` controller review，与后续 R4 `READY_FOR_HUMAN` 证据存在待复核差异；不能由 G6 自动改写；
- 六模块真人 UAT、独立 QA、实际 Panel/申诉人、真实历史 Data Owner 审计均未完成；
- WP-06 的真人 UAT、真实通知、production preflight、异机恢复、发布批准和观察窗口为 `NOT_RUN`；
- 因此当前裁决必须是 `NO_GO`，不能生成 release candidate。

## 7. 机器验收

- `AT-G6A-001`：五组件、六合同、六模块和 17 个 release check 必须精确齐全；
- `AT-G6A-002`：候选必须 clean、完整 SHA 且与 WP-07 manifest 一致；
- `AT-G6A-003`：所有来源路径和 SHA-256 失败关闭；
- `AT-G6A-004`：AI、合成或自证 UAT 不能 PASS；
- `AT-G6A-005`：合同签署绑定合同版本，UAT/发布签署绑定候选版本；
- `AT-G6A-006`：独立 QA、Panel/Appeal 和 Release 四眼职责分离；
- `AT-G6A-007`：BC-005 具备 Panel 与独立申诉签署；
- `AT-G6A-008`：报告不输出 actor ref、姓名或业务正文；
- `AT-G6A-009`：报告不可覆盖，权限 `0600`；
- `AT-G6A-010`：任何状态都不创建候选、不授权迁移或发布、不执行生产 mutation。

## 8. 当前未做与下一 Gate

2026-08-24 本地机器证据：

- G6 定向合同 `24 passed in 0.10s`；API 全量 `443 passed, 5 skipped in 13.75s`；
- Web `38/38`，TypeScript、ESLint、Next.js production build 均通过；
- source-bound readiness report 为 `NO_GO`，45 个 blocker，且 `contains_actor_identifiers=false`；
- readiness report 权限 `0600`，输入和报告 SHA-256 已登记；
- Product Doctor PASS；Ops V0.4 因 schema 1/2 工具兼容债务保持 FAIL；
- WP-06 release gate 11/17 PASS，六个真人/生产/发布 Gate 保持 NOT_RUN；
- `git diff --check` 与 JSON 解析通过。

本阶段未记录真人 UAT、未签署合同、未接受 Owner 任命、未创建 WP-07 候选、未执行 backup/restore、未连接 staging/production、未发送通知、未部署、未迁移、未提交或合并。

下一 Gate：`G6_PRO_INDEPENDENT_QA_ROSTER_AND_CONTRACT_SIGNOFF_REVIEW`。MacBook Pro 需要先确认当前 Golden Path 证据差异、G1—G5 退回项、独立 QA/Release Reviewer 名单和六份合同签署计划；没有这些真人输入，当前候选继续冻结为 `NO_GO`。
