# UAT与发布 03｜PRODUCTION_CANARY_UAT 合同变更 V1.0.1

> 决策日期：`2026-08-27`  
> 决策人：刘默文（Product Owner / Tech Lead / Security & Privacy / Release & Ops / Business Decider）  
> 合同状态：`CANARY_UAT_MODE_APPROVED / CANDIDATE_NOT_FROZEN / CANARY_DEPLOYMENT_NOT_AUTHORIZED / RELEASE_NOT_AUTHORIZED`

## 1. 决策

四模块真人 UAT 改在最终生产基础设施上执行，发布态定义为
`PRODUCTION_CANARY_UAT`。它不是 staging，也不是正式生产发布，而是同一生产运行面上的受控
Canary：仅 8 名具名白名单学员可见、明确标注“受控内测”、使用准确冻结候选并保留一键冻结和
回滚能力。

本变更只改变 UAT 的运行环境，不降低候选、内容、安全、恢复、真人或独立复核 Gate。旧合同中
“真人 UAT 只能在 staging/uat 环境执行”与本文件冲突的部分，以本文件为准。

## 2. 状态边界

| 状态 | 可做 | 不可做 |
| --- | --- | --- |
| `CANDIDATE_FROZEN` | 对准确 SHA 完成扫描、备份、恢复、回滚和 Canary 预检 | 对真人开放 |
| `PRODUCTION_CANARY_READY` | 等待准确 SHA 的 Canary 部署授权 | 推断 UAT 已通过或发布已放行 |
| `PRODUCTION_CANARY_UAT_ACTIVE` | 仅 8 名白名单学员执行四模块真人 UAT；写入受控 Journey UAT 事实 | 扩大名单、外部生产作业、历史迁移、高影响自动结论 |
| `INDEPENDENT_REVIEW` | 冯宇汀复核同一候选、UAT、恢复、回滚和职责边界 | 用角色接受替代候选签署 |
| `CONTROLLED_RELEASE_ACTIVE` | 在 `RELEASE_GO` 后把同一候选扩大到最多 25 人 | 自动全量开放 |

`CANARY_DEPLOYMENT_GO` 与 `RELEASE_GO` 是两个不同签署。前者只允许 8 人 UAT；后者才允许扩大至
最多 25 人。任何 Canary 部署、UAT 或角色任命都不能自动生成 `RELEASE_GO`。

## 3. Canary 部署前置

以下全部满足后，Business Decider 才能对准确候选签署 `CANARY_DEPLOYMENT_GO`：

1. 工作树干净，完整 Git SHA、不可移动 tag 和 candidate manifest 已固定；
2. 四模块 UAT 所需内容、Task、Rubric、Reviewer、替补和 SLA 已由对应 Owner 绑定 hash；
3. 所有 P0 机器测试、负向合同、生产构建和当前镜像安全扫描通过；
4. migration 为唯一 head，空库升级、生产兼容检查和 schema hash 通过；
5. 对同一候选完成新鲜加密备份、隔离恢复、应用回滚和具名真人告警回执；
6. 8 名具名参与者、角色、模块覆盖、邀请有效期、同意与隐私规则形成不可变名单 hash；
7. 非白名单访问失败关闭，fixture 身份、搜索引擎索引和公开一级入口关闭；
8. `release_marker=PRODUCTION_CANARY_UAT`、停邀请开关、值守人、回滚人和观察窗口就绪；
9. Journey 不持有外部生产写凭证，不执行生产作业，不迁移历史数据，不产生自动高影响结论。

缺任一项时只能保持 `CANDIDATE_FROZEN` 或 `NO_GO`，不能用“生产环境更真实”代替前置 Gate。

## 4. 运行隔离

- 使用与 9 月 1 日受控发布相同的域名、镜像、配置形态、身份系统和数据库运行面；
- 通过服务端白名单/组织或 cohort scope 隔离，不以只隐藏按钮作为访问控制；
- 8 名参与者产生的 Assignment、SubmissionVersion、Review、Evaluation、Outcome 和审计事实可在
  `RELEASE_GO` 后继续保留，不需要重新导入；
- UAT 数据必须带 `canary_uat_id`、candidate SHA、content hash、participant ref 和时间；
- 普通访客继续看到稳定公开页；非白名单不得进入新四模块运行路径；
- 页面持续显示“受控内测 / 反馈不自动形成人才结论”，不得制造正式开放或通过预期。

## 5. UAT 与放行

8 名参与者必须覆盖四个模块，每模块至少 2 名真实目标用户，并在同一候选完成提交、返工、通过、
结果查看和负向权限场景。UAT 通过后：

1. 不重建、不换 SHA、不静默改内容；
2. 冯宇汀执行独立 QA 与独立 Release Review；
3. 刘默文对同一候选显式签署 `RELEASE_GO`；
4. Release/Ops 只扩大白名单至明确名单且总人数不超过 25；
5. 任何代码、内容、配置、迁移或镜像变化都形成新候选并使旧 UAT/签署失效。

## 6. 停止线

出现任一项立即冻结新邀请和新 mutation，保留证据并回滚或进入维护页：

- 非白名单、跨用户或跨组织访问成功；
- 提交、评审、结果或审计事实丢失、覆盖或无法对账；
- AI、积分、阅读或自证生成正式状态；
- Journey 写入外部生产系统或持有生产写凭证；
- 敏感数据泄露、当前镜像安全结论失效或候选 hash 漂移；
- backup/restore/rollback 无法证明，或 P0 核心路径失败且无安全替代；
- 运行人数超过 8、Canary 标识消失或非白名单入口被公开。

停止线触发后不得用人工口头说明继续运行；恢复必须形成新证据和重新授权。

## 7. 必备证据

`candidate_manifest_hash, canary_deployment_authorization_hash, allowlist_hash, release_marker,
deployed_image_digests, migration_head, configuration_hash, content_package_hashes,
backup_restore_rollback_evidence_hash, vulnerability_scan_hash, uat_run_ids,
participant_refs, module_coverage, defect_ledger_hash, independent_review_hash,
release_go_hash`。

## 8. 明确未授权

本文件不是 `CANARY_DEPLOYMENT_GO`，也不是 `RELEASE_GO`。截至本变更生效时：

- `candidate_sha=null`；
- `canary_deployment_authorized=false`；
- `release_authorized=false`；
- `production_deployment_executed=false`。

