# Muchen Journey vNext

本仓库是 Muchen Journey vNext 的独立 Greenfield 代码库。批准文档、产品代码、测试和运行合同在此共同版本化；没有复制旧产品代码、数据库迁移或运行时兼容层。

本轮的不可逆前提是：下一版按 Greenfield 项目从零开发。旧系统可用于业务调研、历史数据盘点和验收对照，但不能成为新系统的代码依赖、运行时依赖、数据库依赖、部署依赖或写入回滚目标。

## 当前交付

- G0：DEC-001–016 与 00–15 号文档构成 Greenfield 基座；DEC-017–024 记录 Alpha 执行边界、正式域名和产品真相恢复；
- WP-00：独立 Web/API/Worker/PostgreSQL 基座、0001 migration、CI 和隔离扫描；
- G2 最小 walking skeleton：fixture 新人开始并提交 TSK-001，fixture 主管评审固定版本，系统生成 `HANDOFF_READY`；
- WP-01：真实一次性邀请、vNext 内部身份、`PENDING_IDENTITY → ACTIVE` Enrollment、独立可撤销会话、CSRF 与旧凭证拒绝；
- WP-02：稳定 TaskDefinition、发布后不可变 TaskVersion、固定版本 Assignment、服务端 Current Action Resolver，以及 Learner 当前行动/任务理解页；
- WP-03：不可变 SubmissionVersion 追加历史、服务端草稿恢复、首次/修订提交的幂等与并发合同，以及按 organization/owner/assignment/purpose 隔离的受控附件路径；
- WP-04：按 explicit reviewer + organization/object scope 裁剪的评审队列与详情、固定材料完整性、四维结构化 Rubric、并发安全的 start/finalize、不可变 Evaluation 历史，以及 Reviewer→Learner 修订/完成状态闭环；
- WP-05：评审通过后原子生成不可变 Outcome 与唯一 Handoff，事务 Outbox、本地 NotificationDelivery worker 的租约/重试/去重/死信合同，按 organization/owner/object 裁剪的跨域时间线，以及完整 Learner 结果页；
- WP-06：版本化 Task/config 只读运营视图，带角色/组织/对象 scope、原因、幂等键与 expected revision 的 reviewer assignment / enrollment cancel 命令，安全裁剪审计，revision/health/worker/observability 状态，签名离线 fixture 导入，以及本地加密备份、隔离恢复、回滚/告警模拟和 fail-closed 发布门禁；
- WP-07：候选基线、CODEOWNERS、分层 CI、固定摘要的基础/扫描镜像、依赖/secret/旧引用扫描、三进程 SPDX SBOM，以及绑定完整 Git SHA、OpenAPI hash、migration head、config schema 和 TaskVersion 清单的 release manifest；远端 mainline 已向三个 canonical GHCR package 推送精确 SHA tag、验证 immutable digest 并上传工件。仓库按用户明确决策设为 Public，`main` 强制 PR、`WP-07 / quick`、线性历史、会话解决并禁止 force-push/删除，管理员同样受约束；
- WP-08：火山引擎华北2（北京）冻结 staging 资源上的 Alpha 运行面、TLS/readiness/API/Web/Worker/匿名权限与真实浏览器 smoke 已通过；控制台当前事实、冻结 state 身份核对和成功 ECS→RDS TLS 数据面连接已关闭物理 ACL 证据债，结论为 `STAGING_ISOLATION_VERIFIED`；
- WP-09：独立飞书应用、首位真实 Operator、Reviewer 绑定及真实权限矩阵已完成；明确会话失效提示候选 `2ab2658…` 已在唯一冻结 staging deploy run `30242231558` 成功上线，readiness、匿名 `/ops`/`/review` 拒绝和飞书入口均通过机器复验。Reviewer 暂时无法继续真人复验，撤销会话提示保留为 `WAITING_FOR_HUMAN_UAT`，不伪记 PASS；
- WP-10：真实 TOS 直传、对象元数据复核、短时授权下载、ClamAV 流式扫描和 fail-closed 隔离的工程路径已完成；当前 Alpha/RC 明确固定无附件的 `TSK-001 V1`，staging 保持 `ATTACHMENTS_ENABLED=false`，结论为 `SECURELY_DISABLED_FOR_ALPHA`。V2 附件能力不进入当前范围，未来启用前必须重新完成五项物理门禁；
- WP-11：独立飞书通知适配器、加密接收人、provider receipt、限流/超时/重试/DEAD/人工重驱、JSON 结构化日志和运行指标的工程路径已完成；配置合同升级为 V3。真实飞书收件、火山引擎 TLS/Cloud Monitor、外部告警与演练保持 `NOT_RUN`，staging 通知适配器继续禁用；
- 候选 `8f77ceec…` 已通过 `journey.muchenai.com` 向单一组织私密名单开放受控 Alpha：独立 production Compose/应用 secret/逻辑数据库、TLS、正式飞书 OAuth 回调、canonical URL、加密备份与隔离恢复均已验证，staging 保持在线；维护页 503 与恢复 live 已实际演练。真实旧系统数据导入、真实飞书通知/外部告警、独立故障域、完整真人 UAT、WP-14 与完整发布签署仍未完成，因此这是 `CONTROLLED_ALPHA_LIVE`，不是完整 `RELEASE_GO`。
- WP-17/18：Learner 视觉方向已关闭；正式产品真相已恢复为 Day 0＋四个认知宝藏＋三个能力评测＋完整结果。当前 TSK-001 保留为已验证 Alpha 任务，不再代表完整探索营。
- WP-19：多阶段 Journey 编排、不可变版本、整版邀请与顺序 Current Action 已进入独立构建候选；正式四宝藏内容、Learner Evidence 与综合结果仍由 WP-20/21 关闭，当前线上 Alpha 不变。

从 [文档地图](docs/00_DOCUMENT_MAP_AND_GOVERNANCE.md) 开始阅读。真人 UAT、物理 staging/production 资源、恢复/回滚演练与发布签署仍是 G4/G5 独立门禁，当前不是发布 GO。

## 本地运行

需要 Docker Compose 与 Node.js 24（仅直接运行 Web 工具时需要）。

```bash
docker compose up --build
```

- Web：<http://localhost:3000>
- API 健康：<http://localhost:8000/health/ready>
- 本地 OpenAPI：<http://localhost:8000/docs>

`/join#token=<invite_token>` 是新人 canonical 加入链接；fragment 不会发送到服务器，Web 在读取后立即从地址栏移除。邀请 token 只由 `POST /api/v1/ops/invites` 的创建响应返回，数据库仅保存 keyed hash。

当前仅在 `local/test` 允许 `X-Fixture-Role` 身份，用于 Operator 创建测试邀请以及保留 walking skeleton 回归。真实新人确认后使用 `journey_next_session` 独立会话；staging/production 配置会拒绝 fixture 身份和默认/复用的身份 secret。

本地附件继续使用隔离目录和确定性测试扫描器；未来非本地附件只允许浏览器通过对象级短时 URL 直传私有 TOS，API 完成时复核 size/type/SHA-256 并通过 ClamAV 后才进入 `READY`。扫描器不可用时文件停留隔离态。当前 Alpha/RC 只使用无附件的 `TSK-001 V1`，staging 固定 `ATTACHMENTS_ENABLED=false`，页面不展示附件入口，结构化文本提交继续可用；任何 V2/附件启用都必须先重开 WP-10 并关闭五项物理门禁。

Reviewer 工作台以服务端 `allowed_commands` 为唯一动作来源。`GET /reviews*` 只查询且按明确 Reviewer、组织和对象裁剪；finalize 要求固定四维 Rubric、每维反馈、总体反馈与 `APPROVE`/`REQUEST_REVISION`，结论写入后由数据库拒绝覆盖。

`APPROVE` 现在在同一数据库事务中写入最终 `Outcome(HANDOFF_READY)`、唯一 `Handoff(READY)`、最小化 Outbox 事件和 `NotificationDelivery`。`GET /api/v1/me/result` 返回服务端最终结论、结构化人工反馈、交接、通知状态与明确的本地范围；`GET /api/v1/me/timeline` 返回授权裁剪的 SubmissionVersion→Review/Evaluation→Outcome/Handoff→Notification 事实。两者都是无副作用读取。

Compose worker 在 `local/test` 使用 `LOCAL_TEST`，并实现仅允许 `staging/production` 的 `FEISHU` 适配器。飞书路径固定官方域名，使用独立通知凭据、加密 `open_id`、10 秒默认超时、稳定 provider UUID、最小无 PII 模板、指数退避、DEAD、最多三次人工重驱与私有 provider receipt；外部失败不会回滚 Outcome/Handoff。下一次 staging 部署包已要求独立通知 App、32-byte 接收人密钥、API/Worker 同钥与 canonical result URL，缺失或复用即 fail closed；禁用模式不再领取通知事件，FEISHU 模式也只领取已有活动接收人的事件。当前运行中的 staging 仍为 `NOTIFICATION_ADAPTER=DISABLED`，因此工程接线不等于真实送达证据；只有存在外部回执时结果页才返回 `external_delivery_confirmed=true`。

`/ops` 是受控 Operator 入口。它不提供通用状态编辑器：TaskVersion 只读且发布后不可变；Enrollment 只能执行服务端返回的 `allowed_commands`，写入必须带原因、幂等键和 expected revision，存在评审事实时拒绝更换主管或取消。身份区只列出同组织有效 Reviewer/Operator 的安全状态；通知区只显示接收人状态与版本，不回显密文、指纹、`open_id` 或 provider message ID。一次性身份链接只显示一次，撤销身份会同步撤销活动会话。`GET /api/v1/ops/audit` 仅返回同组织、最多 31 天/100 行的安全字段；`GET /api/v1/ops/runtime-status` 暴露 release、config schema、migration、API/DB/worker heartbeat、backlog/retry/DEAD/最老待处理时长，并明确 `external_observability_confirmed=false`。

离线导入是本地 CLI 合同，不是 HTTP 上传接口，也不连接旧系统。它只在 `local/test` 接受 HMAC 签名、SHA-256 校验、严格 manifest/NDJSON schema 的 `SYNTHETIC_VNEXT_FIXTURE` 包，先 dry-run，再以 package/source key 幂等应用；重放、跨包冲突和隔离原因写入不可变 ledger，报告不含记录标识符。示例命令：

```bash
mkdir -p artifacts/wp06/import-example
docker compose run --rm --no-deps -v "$PWD/artifacts/wp06/import-example:/import" api python -m journey_api.offline_import create-fixture /import/package
docker compose run --rm --no-deps -v "$PWD/artifacts/wp06/import-example:/import" api python -m journey_api.offline_import dry-run /import/package --report /import/dry-run-report.json
docker compose run --rm --no-deps -v "$PWD/artifacts/wp06/import-example:/import" api python -m journey_api.offline_import apply /import/package --report /import/apply-report.json
```

完整本地运维流程见 [WP-06 Runbook](docs/runbooks/WP06_LOCAL_OPERATIONS.md)：

```bash
make wp06-backup       # 仅 journey_next_dev；加密、签名 manifest
make wp06-drill        # 仅恢复到 db-test 的新隔离数据库并回滚/再升级
make wp06-alert-sim    # 只产生合成告警判定，不发送外部消息
make release-gate-check
make release-gate      # 当前预期非零并输出 NO_GO
```

## 验证

```bash
make verify
```

该命令精确重建测试数据库，执行空库迁移/种子、API 与领域测试、迁移升降级、Web lint/类型/生产构建、Greenfield 隔离扫描、真实 Compose HTTP 权限负向矩阵，并验证发布门禁保持 `NO_GO`。各工作包证据分别见 16–28 号 As-Built。依赖安全审计单独运行：

```bash
cd apps/web && npm audit --audit-level=low
```

Python 漏洞审计使用临时容器运行 `python -m pip_audit -r requirements.lock`，不把审计工具加入产品依赖或改写锁文件。

WP-07 分层门禁和候选工件入口为：

```bash
make ci-fast             # PR 快速层，目标小于 10 分钟
make ci-main             # 主线完整本地门禁
make candidate-package   # 仅对 clean、已有 40 字符 HEAD 的候选生成 digest/SBOM/manifest
make candidate-registry-check  # 只校验三个 canonical GHCR SHA tag；不登录、不 push
```

`candidate-package` 输出到被 Git 忽略的 `artifacts/wp07-candidate/`，本地默认不会 push。mainline workflow 只在 `push main` 且四项显式保护条件满足时，将同一批本地候选镜像推到 `ghcr.io/muchenai2024-creator/muchen-journey-vnext-{api,web,worker}:<full-sha>`；禁止 `latest`，不修改 GitHub 设置或部署环境。完整事实见 [WP-07 As-Built](docs/24_WP07_CANDIDATE_BASELINE_SUPPLY_CHAIN_EVIDENCE.md)。
