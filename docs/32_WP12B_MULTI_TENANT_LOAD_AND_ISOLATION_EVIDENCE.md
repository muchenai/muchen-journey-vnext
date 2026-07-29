# WP-12B｜多租户容量与隔离门禁证据

状态：`LOCAL_HARNESS_PASS / STAGING_NOT_RUN / WP12B_NOT_CLOSED`

日期：2026-07-29
Owner：Tech Lead + QA/UAT Owner + Release/Ops

## 1. 结论与边界

WP-12B 是 WP-12 的候选门禁，不是 WP-13 真人名册扩展。它使用无真实个人信息的合成组织证明同一候选在多组织并发下仍满足性能预算、组织隔离和事实唯一性；WP-13 继续用一个真实组织验证人能否理解并完成闭环。

当前已完成负载合同、合成身份生命周期、真实 HTTP runner、数据库不变量审计、失败后强制身份退役和独立 staging workflow。本地 smoke 已通过；主线 `9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6` 经 Mainline Candidate Gate `30416410890` 生成并验证三镜像摘要，但尚未部署，也未在 staging 执行批准规模，因此不得把本文件记为 `WP12B_CLOSED`。

## 2. 固定负载合同

`config/wp12b_multitenant_load.json` 固定：

- 20 个合成组织；
- 每组织 25 名 Learner、2 名 Reviewer、1 名 Operator，共 500 名 Learner；
- 峰值并发 50；
- 稳态 10 req/s × 600 秒；突发 25 req/s × 60 秒；
- readiness、Current Action、提交、Reviewer 队列、评审完成、结果和运营运行状态均纳入；
- 常规读取和核心同步命令 p95 ≤1 秒；
- HTTP 5xx、意外响应、409 状态冲突、跨组织泄漏、重复事实全部为 0；
- 附件继续关闭；runner 不创建通知接收人、不调用飞书、不读取通讯录、不新增云资源；
- `99.5%` 可用性仍由 WP-14 真实 14 天窗口证明，不能由 11 分钟负载替代。

## 3. 安全执行模型

| 组件 | 职责 | 失败边界 |
| --- | --- | --- |
| `journey_api.wp12b_synthetic prepare` | 仅在 local/test/staging 创建明确标记的合成组织、角色、任务和两小时会话；staging 要求运行中 release 与完整 candidate SHA 相等及精确确认词 | production 拒绝；run id 不可重放；不创建 ExternalIdentity 或通知接收人 |
| `scripts/wp12b_load.py run` | 从 owner-only 私有 bundle 经真实 HTTP/HTTPS 执行开始、提交、评审、读取和跨组织 404 探测 | 只接受 loopback HTTP 或 canonical staging HTTPS；不打印/记录 token |
| `journey_api.wp12b_synthetic audit` | 核对组织/用户/Assignment/Submission/Review/Evaluation/Outcome 数量、固定 scope 和一事实不变量 | 任一漏单、重复或跨组织 FK 不一致即失败 |
| `journey_api.wp12b_synthetic retire` | 无论负载/审计成功与否，撤销全部合成会话并禁用合成用户 | 不删除已经产生的业务事实，保留可审计历史 |
| `scripts/wp12b_load.py verify` | 只在 load/audit/retire 同一候选、同一 run 且全部 PASS 时输出 `WP12B_CLOSED` | 不部署、不修改 staging/production |

GitHub workflow 只从加密 Terraform state 读取现有 ECS/安全组，临时开放 runner 单一 `/32` SSH，核对 `/srv/journey-next-staging/DEPLOYED_CANDIDATE` 后执行；不运行 `terraform plan/apply`、DNS、迁移、部署或通知。SSH 规则在 `always()` 中关闭，合成身份在 `always()` 中退役。公开 artifact 只含计数、延迟和布尔结果，不含 session bundle、UUID、正文或基础设施标识。

## 4. 本地真实 HTTP smoke

2026-07-29 使用隔离测试库和临时 API 容器完成：

- 2 个组织、4 名 Learner、2 名 Reviewer、2 名 Operator；
- 峰值并发 8；稳态 10 req/s ×2 秒；突发 20 req/s ×1 秒；
- 69 次真实 HTTP 请求；
- start、submission、review start/finalize、result 全闭环；
- Learner 跨组织 Assignment 与 Reviewer 跨组织 Review 均返回 404；
- HTTP 5xx=`0`、409=`0`、cross-org leak=`0`、unexpected response=`0`；
- 最慢端点本地 p95 <0.1 秒；
- 数据库审计 PASS；临时 session 全撤销、用户全禁用；
- 报告：`artifacts/wp12b/multitenant-load-20260729T012211Z-a64ff401.json`（本地私有证据，不关闭 staging 门禁）。

## 5. 关闭条件

WP-12B 只有同时满足以下条件才关闭：

1. 工具 PR 合入，主线生成包含工具的完整候选 SHA 和三镜像摘要；
2. 通过独立候选绑定 PR 更新 staging 部署合同；
3. Owner 明确授权该精确候选在冻结 staging 基础设施执行一次 deploy；
4. deploy 成功后，Owner 再授权相同候选执行一次 WP-12B workflow；
5. load、数据库 audit、身份 retire 均 PASS，PII-free closure artifact 输出 `WP12B_CLOSED`；
6. 将精确 run、候选和聚合结果回写本文件及追溯矩阵。

在此之前：WP-13 真人 UAT 不启动，WP-12 仍为 `IN_PROGRESS`，production 继续 `NO_GO`。
