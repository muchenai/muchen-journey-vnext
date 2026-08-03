# 13｜需求追溯矩阵

状态：`APPROVED_FOR_BUILD`  
版本：V0.7
日期：2026-07-28
文档 Owner：Product Owner + QA Owner  
规则：P0 任一行缺少设计、数据/API 或验收引用，不得进入开发；实现 PR 必须引用对应 ID。

## 1. 业务需求追溯

| 需求 | 用户旅程/页面 | 领域/数据 Owner | API/事件 | 安全/权限 | 验收 | 当前状态 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-BR-001 邀请与加入 | JRN-001/003；`/join` | Invite、Enrollment | `POST /join/exchange`；invite.* | token hash/expiry/replay | AT-SEC-001；身份邀请矩阵；AT-UAT-003 | WP-01 已实现并自动化；真人 AT-UAT-003 `NOT_RUN`；见 17 |
| REQ-BR-002 身份与会话 | JRN-001/003；`/join` | User、ExternalIdentity、RoleAssignment | identity/session endpoints | session、CSRF、旧凭证拒绝 | AT-SEC-004/012；AT-ISO-003 | WP-01 逻辑身份已自动化；WP-09 独立 staging 飞书应用、真实 Operator/Reviewer 绑定、轮换与撤销矩阵已通过，明确失效提示待候选部署；production 身份仍 `NOT_RUN`；见 17/27 |
| REQ-BR-003 当前行动 | JRN-001/002；`/app`、task understanding | Enrollment、TaskDefinition、TaskVersion、Assignment；Resolver | `GET /me/current-action`、`GET /me/assignments/{id}`、task definition publish | Learner owner + org；Operator content owner；server allowed commands | AT-UX-001/002；resolver/权限/版本矩阵；AT-CONTENT-005 | WP-02 已实现并自动化；真人理解率/UAT `NOT_RUN`；见 18 |
| REQ-BR-004 任务与提交 | JRN-001/004；task page | Assignment、Submission、SubmissionVersion、SubmissionDraft、Attachment | start/draft/submissions/attachments/history；submission.created | org + owner + assignment + purpose；hash/type/size/name/scan；复合 FK | AT-DATA-003/005；AT-SEC-002/003/005/007；AT-UX-008；AT-UAT-001/004 | WP-03 本地闭环已自动化；DEC-017 将当前 Alpha/RC 固定为无附件 `TSK-001 V1`，staging 页面/API fail closed。TOS/ClamAV 工程路径保留但不激活；五项物理证据转为未来附件启用前置门禁，见 19/28 |
| REQ-BR-005 主管评审 | JRN-001/005；review pages | Review、Evaluation | reviews/start/finalize；review.* | explicit reviewer + organization/object scope；GET 无副作用；DB 不可变 | AT-UX-004/005；权限/并发矩阵；AT-UAT-005 | WP-04 本地实现并自动化；真人 Reviewer 独立性/校准与 AT-UAT-005 `NOT_RUN`；见 20 |
| REQ-BR-006 修订闭环 | JRN-002；result/task | Assignment、Submission、SubmissionVersion、Review、Evaluation | 同一 submissions 命令按 allowed command 追加版本；history；revision_requested | 本人 + org + object；expected revision；旧版本/附件关联 DB 只读 | AT-DATA-002/003/005；AT-API-002；AT-UX-008；AT-UAT-002 | WP-03 本地实现并自动化；真实 Learner/Reviewer UAT `NOT_RUN`；见 19 |
| REQ-BR-007 通过与交接 | JRN-001；`/app/result` | Evaluation、Outcome、Handoff | `GET /me/result`；assignment.completed/outcome.created/handoff.ready | Learner owner + org/object；固定 Evaluation/Enrollment；DB 不可变 | AT-DATA-006；AT-UAT-001/006 | WP-05 本地实现并自动化；真人 AT-UAT-001/006 `NOT_RUN`；见 21 |
| REQ-BR-008 运营处理 | JRN-003/005；`/ops` | Invite、Enrollment、TaskDefinition/TaskVersion、Audit、ImportBatch/ImportRecord、WorkerHeartbeat | task definition publish；`GET /api/v1/ops/enrollments|audit|runtime-status`；`PUT /api/v1/ops/enrollments/{id}/reviewer`；`POST /api/v1/ops/enrollments/{id}/cancel`；离线 import CLI | Operator role + organization/object scope + reason + expected revision + idempotency；审计 allowlist/裁剪；无通用状态编辑器 | 运营命令/权限/并发/重放矩阵；AT-UAT-008；AT-SEC-011；AT-ISO-006；AT-DATA-007 | WP-06 本地实现并自动化；真人 Operator UAT、真实旧系统导入和发布运行 `NOT_RUN`；见 22 |
| REQ-BR-009 通知 | JRN-006；`/app/result` | OutboxEvent、NotificationDelivery、NotificationAttempt、LocalNotificationReceipt | notification.requested；本地 worker | organization + recipient + outcome 复合 scope；最小 payload/log；lease/retry/dedupe；非 local/test fail closed | AT-SEC-008；故障/崩溃/并发注入；AT-UAT-006 | WP-05 本地适配器实现并自动化；真实 Feishu/邮件收件 `NOT_RUN`，通知不阻塞核心结果；见 21 |
| REQ-BR-010 不可变历史 | 全旅程；`/app/result` timeline/history | SubmissionVersion、Review/Evaluation、Outcome/Handoff、OutboxEvent/NotificationAttempt | submission history；`GET /me/timeline`；所有写事件 | role + organization + owner + object 裁剪；事件/日志最小化；历史事实 DB 不可覆盖 | AT-DATA-005；审计结构测试 | WP-05 完成跨域时间线与 Outcome/Handoff/NotificationAttempt 不可变证明；早期 Task/Submission/Review 历史证据仍见 18/19/20；见 21 |

## 2. Greenfield 隔离追溯

| 要求 | 架构/交付控制 | 自动/人工验收 | 发布证据 |
| --- | --- | --- | --- |
| ISO-MUST-001 独立源码 | 新 Git repo；无 submodule/workspace 引用 | AT-ISO-001；dependency/import scan | WP-07 候选 commit、CODEOWNERS、clean-tree preflight 与 legacy/isolation scan；无 `rg` 时以严格 `grep` fallback 且扫描错误 fail closed；Public `main` 保护已由 API 验证；见 24 |
| ISO-MUST-002 独立依赖 | 公开依赖 + vNext 自有模块 | lockfile/SBOM/forbidden import | WP-07 固定 runtime/base/扫描器摘要，npm/pip audit、secret scan、三镜像 SPDX SBOM 与 canonical GHCR SHA-tag/digest 合同；见 24 |
| ISO-MUST-003 独立 DB | 新 DB/role；0001..0010 migration | AT-ISO-005；DB ACL/空库重建 | 空库 0001→0010 与既有事实 0009↔0010 本地 PASS；物理 ACL `NOT_RUN`；见 22 |
| ISO-MUST-004 无旧运行时 | egress allowlist；无旧 SDK/URL | AT-ISO-002；network deny | egress policy/report |
| ISO-MUST-005 独立身份 | vNext user/session/secret | AT-ISO-003；AT-SEC-004/012 | WP-01 逻辑隔离与配置 fail-closed 已自动化；WP-09 staging 使用独立飞书应用与独立 secrets，真人轮换/撤销矩阵通过；production 物理 identity config 仍 `NOT_RUN`；见 27 |
| ISO-MUST-006 无兼容路由 | 04 号唯一 route manifest | AT-ISO-004；AT-UX-009 | route scan |
| ISO-MUST-007 独立环境 | 资源清单与命名空间 | environment audit | signed env manifest |
| ISO-MUST-008 独立部署 | vNext CI/image/runtime | AT-ISO-001/007 | WP-07 run 29804468895 在实现 SHA `eb4035e…` 完成 mainline、三个精确 SHA GHCR 镜像、远端 digest 二次验证与 manifest/SBOM/TaskVersion 上传；`registry_push=VERIFIED`，protected main/deployment 仍 `NOT_RUN`；见 24 |
| ISO-MUST-009 独立可观测 | vNext log/APM/revision | AT-ARCH-005；告警演练 | WP-06 暴露 release/health/worker/backlog/dead 并完成本地告警模拟；外部 APM/告警 `NOT_RUN`；见 22 |
| ISO-MUST-010 vNext 内回滚 | N ↔ N+1 compatible rollout | AT-ISO-007 | WP-06 隔离恢复后 0010→0009→0010 与事实指纹本地 PASS；生产回滚 `NOT_RUN`；见 22 |
| ISO-MUST-011 离线导入 | signed export + importer | AT-ISO-006；AT-DATA-007 | WP-06 HMAC/checksum/dry-run/幂等/冲突隔离/不可变 ledger 本地 PASS；真实旧系统包 `NOT_RUN`；见 22 |
| ISO-MUST-012 旧系统只读 | no fallback/writeback | AT-ISO-002/007；UAT | importer 仅接受合成 vNext fixture，报告 `source_writeback_executed=false`；真实 cutover signoff `NOT_RUN`；见 22 |

## 3. 非功能需求

| ID | 要求 | 设计来源 | 验收 |
| --- | --- | --- | --- |
| REQ-NFR-001 | Greenfield 物理独立 | 02、06、10、11 | AT-ISO-001..007；AT-ARCH-002/003/006 |
| REQ-NFR-002 | 服务端状态与 allowed commands 权威 | 04、05、07 | resolver/状态矩阵；AT-UX-003；AT-API-002 |
| REQ-NFR-003 | 幂等、并发与安全重试 | 05、07 | AT-DATA-003；AT-API-002；AT-UAT-004 |
| REQ-NFR-004 | 不可变历史与审计 | 05、07、08 | AT-DATA-005；AT-SEC-011；审计测试 |
| REQ-NFR-005 | 身份、权限、隐私与文件安全 | 08 | AT-SEC-001..013；权限矩阵 |
| REQ-NFR-006 | 可访问性与响应式 | 04、09 | AT-UX-006/007；AT-UAT-007 |
| REQ-NFR-007 | 外部依赖可降级 | 06、07、11 | AT-ARCH-004；AT-API-006；故障演练 |
| REQ-NFR-008 | 性能与可用性预算 | 06、11；DEC-013 | benchmark、load、SLO dashboard |
| REQ-NFR-009 | 可观测与可诊断 | 06、11 | trace/revision/request id；告警演练 |
| REQ-NFR-010 | 部署、备份、恢复和回滚 | 11 | AT-DATA-008；AT-ISO-007；发布演练 |
| REQ-NFR-011 | 离线、可审计、幂等导入 | 05、11 | AT-ISO-006；AT-DATA-007 |
| REQ-NFR-012 | 真实角色 UAT | 09 | AT-UAT-001..008；签字证据 |

## 4. 页面到合同追溯

| 页面 | 主要需求 | 服务端读取/命令 | 核心状态 | 体验验收 |
| --- | --- | --- | --- | --- |
| `/join` | BR-001/002 | join exchange、identity confirm | Invite + Enrollment | UX-001/003；SEC-001/004 |
| `/app` | BR-003/007 | current-action、result | Enrollment/Assignment/Outcome | UX-001/002/003 |
| `/app/tasks/{id}` | BR-004/006 | assignment、start、submit、attachments | Assignment/Submission | UX-002/003/006/007 |
| `/app/result` | BR-006/007/009/010 | `GET /me/result`、`GET /me/timeline` | Evaluation/Outcome/Handoff/NotificationDelivery + immutable facts | UX-003；UAT-002/006；SEC-008 |
| `/review` | BR-005 | review list | Review | UX-004；SEC-002/003 |
| `/review/{id}` | BR-005 | detail/start/finalize | Review/Evaluation | UX-004/005/007 |
| `/ops`（Invites 仍由 API 命令创建） | BR-001/008 | ops invite commands；版本化 Task/config 读取；enrollment list/reviewer/cancel；audit/runtime-status | Invite、Enrollment、TaskDefinition/Version、Audit、WorkerHeartbeat | UAT-008；SEC-003/011；config/revision/negative HTTP tests；见 22 |

## 5. 状态迁移到测试追溯

| 聚合 | 迁移 | 必测风险 | 测试类型 |
| --- | --- | --- | --- |
| Invite | DRAFT→ACTIVE→CONSUMED | 过期、撤销、并发消费、重放 | Domain + DB + API + Security |
| Enrollment | PENDING_IDENTITY→ACTIVE；PENDING_IDENTITY/ACTIVE→CANCELLED | 半成品、重复 active、身份错误、原因/幂等/revision、存在 Review 时拒绝改写历史 | Domain + DB + API + Permission |
| TaskDefinition/Version | DRAFT→PUBLISHED；V1→V2 | content owner、reviewer scope、发布不变性、在途 Assignment 固定 V1 | DB + API + Permission + Migration |
| Assignment | AVAILABLE→IN_PROGRESS | 越权、重复 start、revision 冲突 | Domain + API |
| Assignment | IN_PROGRESS→SUBMITTED | 重复事实、附件、超时 | DB + API + Browser |
| Assignment | SUBMITTED→IN_REVIEW | GET 副作用、错误 reviewer | Domain + Permission |
| Assignment | IN_REVIEW→NEEDS_REVISION | Evaluation 原子、旧版本不变 | DB + API + Browser |
| Assignment | NEEDS_REVISION→SUBMITTED | version 递增、历史追溯 | DB + API + Browser |
| Assignment | IN_REVIEW→COMPLETED | 并发 final、Outcome 一次、通知降级 | DB + API + Worker + UAT |
| Notification | PENDING→SENDING→DELIVERED；PENDING/SENDING→RETRY_WAIT→SENDING；→DEAD | 租约、退避、并发、崩溃重放、重复投递、错组织/收件人/Outcome、核心结果独立 | Worker process + DB + API + Security |
| OfflineImport | VERIFIED→APPLIED/REPLAYED；冲突→QUARANTINED | 签名/checksum/schema、包与 source key 重放、并发应用、跨包冲突、零写回、报告脱敏 | CLI + DB + Concurrency + Security |

## 6. 决策到受影响文档

| DEC | 影响 |
| --- | --- |
| DEC-001/002 | 02、06、09、10、11、13；全部 ISO 验收 |
| DEC-003 | 02 资源清单、06 拓扑、10 WP-00、11 环境/发布 |
| DEC-004 | 03 范围、04 IA、05 模型、10 工作包 |
| DEC-005 | 06 技术栈、10 工程规则、11 工件 |
| DEC-006 | 03 BR-002、04 JRN、07 身份 API、08 session、09 测试 |
| DEC-007 | 03 用户/试点、09 UAT、11 试点切换 |
| DEC-008 | 05 保留、08 隐私、11 导入/归档 |
| DEC-009 | 05/11 导入、09 数据测试 |
| DEC-010 | 03 KPI、09 退出、11 观察/Go-No-Go |
| DEC-011 | 03 BR-007、04 结果页、05 Outcome、07 result API |
| DEC-012 | 03 非目标/范围、06 worker、07 AI、08 隐私、09 降级 |
| DEC-013 | 06 NFR、09 benchmark、11 备份/观察 |
| DEC-014 | 02 资源、08 密钥、11 发布/事故 |
| DEC-015 | 04 体验、14 UI token/组件、09 可访问性验收 |
| DEC-016 | 03 P0 范围、05 TaskVersion、07 配置 API、09 UAT、15 内容/Rubric |

## 7. PR 与发布使用规则

每个 PR 描述必须包含：

```text
Requirement IDs:
Decision IDs:
Acceptance IDs:
State/API/Data changes:
Isolation impact:
Test evidence:
Known risks/non-scope:
```

CI 后续应验证：

- 引用的 ID 在本目录存在且未 `SUPERSEDED`；
- P0 需求至少有一个自动化和一个适用的 UAT/人工验收；
- API/migration/route 变化更新对应矩阵；
- 新 route/command 无需求映射时失败；
- `BLOCKED_BY_DECISION` 需求不得进入产品实现。

## 8. G0 完成项与后续证据边界

以下构建输入已锁定；需要真人、物理环境或发布窗口的证明继续保留到 G4/G5，不以文档批准替代执行证据：

- [x] DEC-003..016 的最终构建选项、初始 Owner 和批准日期；
- [x] BR-002、BR-007 的明确产品合同；
- [x] KPI 阈值与试点样本规模；
- [x] 数据保留与 P0 不导入旧业务数据的边界；
- [x] API 路由、错误、事件与幂等机器实现初稿；OpenAPI 固化随本次基座验证生成；
- [x] 逻辑模型、0001 migration 与 walking-skeleton 权限 scope；
- [x] 低保真状态已实现为可运行页面，不另造一次性原型；
- [ ] G4：受控登记真实 UAT 名册、排期与签字证据；
- [ ] G4/G5：建立物理独立资源并由发布/事故 Owner 验证；
- [x] UI token、组件约束与实际 P0 任务/Rubric/SLA。

## 9. G4 候选基线追溯

| 工作包 | 需求/验收 | 本地机器证据 | 外部边界 | 当前结论 |
| --- | --- | --- | --- | --- |
| WP-07 候选基线与软件供应链 | ISO-MUST-001/002/008；REQ-NFR-001/010；AT-ISO-001；AT-ARCH-005/007 | `make ci-fast`、`make ci-main`、`make candidate-package`、`make candidate-registry-check`；完整 SHA/OpenAPI/migration/config/TaskVersion、三镜像 local digest/SPDX SBOM，以及 CI-only canonical GHCR push + remote digest verify 合同；见 24 | run 29804985537 PASS；GHCR 三镜像与 registry-mode artifact 已交叉复验。Public `main` 强制 PR + `WP-07 / quick`，管理员受约束，禁止 force-push/删除；部署仍 `NOT_RUN` | `CANDIDATE_BASELINE_READY`；可进入 WP-08，整体发布仍 `NO_GO` |
| WP-08 物理独立 Staging | ISO-MUST-003/004/007/008/009/012；DEC-003/013/014；AT-ISO-002/003/005；AT-ARCH-002/003/005 | `make wp08-staging-readiness`、`make wp08-staging-apply-check`、`make wp08-workflow-check`、Terraform validate、saved-plan destroy/replacement guard、独立 Web `/health/ready` runtime check、匿名 `/ops = 401`、生产 CSP nonce/hydration、三档视口 browser smoke、首次失败容器清理、候选源码 Web 合同门禁，以及 Worker database-only 配置/完整 API secret 双向负测；DoR 与路径证据见 25/26 | 唯一 deploy run 30161121353 在冻结基础设施上部署精确候选 14c9ba0…；migration/runtime grant/seed、API/Web/Worker/Edge、TLS/readiness、匿名 `/ops=401` 和 SSH 关闭均通过。2026-07-27 控制台人工复验确认非默认 AllowList 仅含预期安全组派生的单一非空主机地址、关联 ECS IP 模式、预期实例和 staging VPC；公开证据不记录物理标识 | `STAGING_ISOLATION_VERIFIED / PHYSICAL_ACL_EVIDENCE_CLOSED`；以控制台当前事实、冻结 state 身份核对和成功 ECS→RDS TLS 数据面连接关闭供应商不再展示 `IsLatest` 的证据缺口；整体发布仍 `NO_GO` |
| WP-09 真实身份与权限 | REQ-BR-002；DEC-006/014；AT-SEC-001/003/004/012；AT-ISO-003 | Feishu OAuth、HMAC subject、state/browser binding、session rotation/revoke、角色/组织负测和日志抑制；见 27 | 候选 `2ab2658…` 唯一 deploy run `30242231558` 成功，release/readiness、匿名拒绝和飞书入口机器复验通过；指定真实 Reviewer 在替换绑定后进入 `/review`，身份撤销后原会话显示明确 `SESSION_EXPIRED`/重新登录指引，Reviewer=`REVOKED`、Operator=`LINKED` 且审计脱敏 | `IDENTITY_AND_ACCESS_VERIFIED / HUMAN_SESSION_UX_PASS`；整体发布仍 `NO_GO` |
| WP-10 真实附件与文件安全 | REQ-BR-004；REQ-NFR-005；AT-SEC-002/003/005/006；AT-CONTENT-004/008；AT-ARCH-003/004 | migration `0012_wp10_file_security`、TOS 对象级短时 PUT/GET、ECS role provider、size/type/SHA/魔数复核、ClamAV INSTREAM、扫描失败隔离、Reviewer 固定版本授权、禁用门禁；`tests/test_submission_attachments.py`、`tests/test_wp10_file_security.py`、`tests/test_wp08_prepare_deploy.py`、OpenAPI/config V2；见 28 | Alpha/RC Assignment 固定无附件 `TSK-001 V1`，部署合同固定 `ATTACHMENTS_ENABLED=false`；不创建文件 IAM/CORS/扫描资源、不部署。V2 仅保留为未激活工程能力；启用前必须重开五项物理门禁 | `SECURELY_DISABLED_FOR_ALPHA`；当前范围关闭，但不得记 `FILE_SECURITY_VERIFIED` |
| WP-11 真实通知与外部可观测 | REQ-BR-009；REQ-NFR-007/009；AT-SEC-008/010；AT-API-006；AT-ARCH-004/005；AT-UAT-006 技术前置 | migration `0013_wp11_notify_observability`、config V3、AES-GCM recipient、独立 FEISHU adapter、稳定 provider UUID/receipt、错误分类/退避/DEAD/有界重驱、JSON logs、runtime metrics、观测与告警合同；部署 secret 独立性/API-Worker 同钥/canonical URL fail-closed；DISABLED 与无接收人 FEISHU 安全领取；`tests/test_wp11_notifications_observability.py`、完整 API/Worker 回归、OpenAPI/Web 门禁；见 29 | 独立通知应用与 secret 已配置；候选 `172c9f6…` 已由 run `30351059075` 部署并升级至 migration `0013`；无业务接收人、消息、尝试或回执。主机审计 run `30358231823`/`30359621278` 通过，但 TLS topic 仍为 0；真实收件、provider receipt、外部告警与演练仍 `NOT_RUN`。DEC-018 仅允许 Alpha 延期并以有界主机审计临时观测 | `ENGINEERING_VERIFIED / STAGING_RUNTIME_VERIFIED / ALPHA_DEFERRED_BY_DEC_018 / INTEGRATIONS_AND_OBSERVABILITY_NO_GO`；production 仍 `NO_GO`，不得记 `INTEGRATIONS_AND_OBSERVABILITY_VERIFIED` |
| WP-12 候选硬化与灾备 | DEC-008/013/014/019/020；REQ-NFR-005/008/010；AT-DATA-008；AT-ISO-007；AT-ARCH-001/007 | 非本地 fail closed；最小权限与 source map/依赖/secret audit；threat model；DEC-008 policy、migration `0014`、PII-free plan；Operator 数据权利登记/查询/legal hold/受限拒绝与脱敏审计；loopback-only benchmark；WP-12B 20 组织/500 Learner/50 并发真实 HTTP 负载与数据库隔离审计；加密本地备份、空白恢复、事实指纹和 `0013↔0014` 零新增事实回滚拒绝；`tests/test_wp12_*`；见 30/32 | 候选 `02863d0b670ee9b00b9def3e75bc6699827f555a` 已由 Mainline run `30511897160` 验证并由 deploy run `30519669770` 部署。唯一 WP-12B run `30525165474` 完成 20 组织/500 Learner、50 峰值并发和 10,561 请求；HTTP 5xx/409、跨组织泄漏、意外响应、数据库 cross-org mismatch/duplicate/incomplete 均为 0，500 条完整业务闭环、560 个会话/用户退役、证据上传和 SSH 关闭均 PASS。原 1 秒性能门禁仍 FAIL：submission create p95=`1.012s`、review finalize=`1.097s`，其余端点通过。DEC-020 仅按 ≤1.2 秒为同一候选开放 WP-13，物理删除、真实 RPO/RTO、真实故障卡、异机恢复仍未执行 | `IN_PROGRESS / WP12B_FAIL_NO_RETRY / ALPHA_UAT_CONDITIONAL_PASS / DATA_RIGHTS_LEDGER_READY_APPLY_DISABLED / OFF_HOST_RESTORE_NOT_RUN / PRODUCTION_NO_GO`；不得记 `WP12B_CLOSED` 或 `RC_TECHNICALLY_READY` |
| WP-13 内容校准与真人 UAT | DEC-007/010/016/020/021/022/023；AT-UAT-001..008；AT-CONTENT-001..008；AT-UX-001/002/004/005/007 | 候选 `8f77ceec…` 绑定 Mainline run `30709982868` 和 staging deploy run `30729705773`；Web/API/Worker、migration 与 schema 已核对。`UAT-WP13-002` 安全重新进入保持同一 Learner/Enrollment/Assignment 与不可变历史，只轮换 session；见 31 | 真人已完成邀请、首次提交、`REQUEST_REVISION`、安全重新进入、查看反馈、再次提交与最终 `PASS` 的一条真实闭环；原失败保留。完整 5 Learner/2 Reviewer/签署矩阵仍未完成 | `ONE_REAL_REVISION_LOOP_PASS / UAT-WP13-002_SCENARIO_REVERIFIED / FULL_UAT_UNSIGNED` |
| WP-14 14 天独立试点 | DEC-010/013/016；KPI-001..007 | 强制同一候选、真实 14 日、D+1/3/7/14 不可提前、原始分子分母和七项批准阈值；见 31 | WP-13 尚未签署，观察窗未启动；机器测试仅证明验证器拒绝提前/失败证据 | `NOT_STARTED / REAL_TIME_REQUIRED` |
| WP-15 生产切换与观察 | DEC-003/010/013/014/019/023；ISO-MUST-007/008/009/010/012 | 完整 release gate 保持 18 项检查与双人批准；DEC-023 另建受保护的受控 Alpha 路径，锁定候选、独立 production DB/Compose/secrets、加密异机备份+空库恢复、双域名 Caddy、正式 OAuth/canonical URL 和维护页；见 31 与 WP15 runbook | 备份/恢复 run `30760806984`、加密归档 `30761088830`、维护/TLS `30779397520`、live `30779441351` 已通过；正式域名 root/readiness=200、候选精确、匿名受限路由=401、正式 OAuth 与 staging 回归通过。共享 ECS/RDS/Caddy 物理故障域仍延期 30 日 | `CONTROLLED_ALPHA_LIVE / FULL_RELEASE_GATE_NO_GO / MUTATION_TRUE` |
