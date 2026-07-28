# WP-11 真实通知与外部可观测构建证据

状态：`STAGING_DEPLOYED / HOST_OBSERVABILITY_VERIFIED / EXTERNAL_LOG_INGESTION_BLOCKED`

结论：`ENGINEERING_VERIFIED / STAGING_RUNTIME_VERIFIED / INTEGRATIONS_AND_OBSERVABILITY_NO_GO`

## 1. 本工作包关闭的问题

WP-11 的工程目标是让通知成为可恢复、可审计、不会污染业务事实的异步副作用，并为外部日志与告警建立可执行数据源。它不以“代码中存在飞书调用”替代真实收件、外部日志采集或告警演练证据。

本次实现追溯 `REQ-BR-009`、`REQ-NFR-007/009`、`AT-SEC-008/010`、`AT-API-006`、`AT-ARCH-004/005`，以及 `AT-UAT-006` 的技术前置部分。

## 2. 已实现事实

- migration head `0013_wp11_notify_observability` 新增加密通知接收人、外部 provider receipt、投递 revision、重驱次数和 attempt offset；重驱保留全部历史尝试，不清零或覆盖旧事实；
- API 配置合同升级为 V3。`local/test` 只允许 `LOCAL_TEST`，非本地结果事实使用 `FEISHU`；production 必须启用接收人密钥，staging 可保持禁用；
- Operator 可按同组织有效 Learner 配置、替换和撤销一个飞书 `open_id`。原值使用独立 256-bit URL-safe Base64 密钥和 AES-GCM 加密，AAD 固定组织、用户、渠道和接收类型；幂等比较只使用密钥化指纹，撤销会销毁原密文与指纹；列表、审计、日志与 OpenAPI 响应不返回原值、密文、指纹或 provider message ID；
- Worker 的 FEISHU 适配器固定 `open.feishu.cn`，使用独立 `FEISHU_NOTIFICATION_APP_ID/SECRET`、默认 10 秒超时、稳定 UUID provider 幂等键和最小文本模板；模板只提示结果已更新并给出真实用户页 `/app/result`，不含结论、反馈、正文、附件名或无关 PII；
- 网络、超时、限流、凭据、接收人和响应合同错误转换为安全错误码。可重试错误指数退避，最终进入 DEAD；非重试错误直接 DEAD；任一通知失败都不回滚或改写 Outcome、Evaluation 或 Handoff；
- provider 接受消息后只在私有表记录 message ID。结果页只有在该回执存在时才返回 `external_delivery_confirmed=true`；
- Web 结果页按 `LOCAL_TEST_ONLY/FEISHU` 和真实 provider receipt 分别展示“本地不代表送达”、“尚无回执”或“飞书已接受”；时间线不再把 FEISHU 投递误标为本地测试；
- DEAD 只允许 Operator 带幂等键、理由和 expected revision 人工重驱，最多三次。已有外部回执或无有效 FEISHU 接收人时拒绝；
- API/Worker 输出 allowlist JSON 日志。API 记录 release/request ID/method/route/status/duration，Worker 记录 release/event type/attempt/dedupe/error code，不记录 URL query、请求正文、cookie、token、接收人或 provider 响应正文；
- Worker 每 60 秒输出一条无组织/用户/对象标识的 `runtime.snapshot`，仅含 backlog、retry/dead、最旧积压秒数、24 小时权限拒绝计数和存活布尔值；这为 TLS 仪表盘和“5 分钟无快照” Worker 失联告警提供真实数据源，不暴露受保护 metrics 端点；
- `/api/v1/ops/runtime-status` 提供 backlog、retry wait、DEAD、最老待处理秒数、权限拒绝和 Worker heartbeat；`config/wp11_observability.json` 固定 TLS 四条应用告警、Cloud Monitor 单 ECS 带外 CPU/无数据两条告警、Owner 和时限。
- 下一次 staging 部署包不再接受“有代码但硬编码禁用”的半接线状态：必须同时提供独立于身份 App 的通知 App ID/Secret、独立 32-byte URL-safe Base64 接收人密钥，API 与 Worker 使用同一密钥，Worker 使用 `FEISHU` adapter、10 秒 provider timeout 和唯一 canonical `/app/result` URL；缺失、复用、格式错误或 bundle 内不一致均在部署前 fail closed；
- 修正 Worker 领取边界：`DISABLED` 模式不领取 `notification.requested.v1`，不会把尚未发送的历史事件误写成 DEAD；`FEISHU` 模式只领取已经存在活动接收人的通知，允许 Operator 在部署后安全配置接收人，再由 Worker 自然消费。非通知 Outbox 事件仍按原合同处理；领取后接收人被并发撤销的竞态继续 fail closed 并保留失败事实。

安全实现使用 `security-best-practices` 约束加密、出站目标、超时、日志脱敏与 fail-closed；Ops 页面遵循 `vercel-react-best-practices`，数据在服务端并行读取，所有写操作仍由服务端 Action 重新鉴权。

## 3. 机器证据

本地干净 PostgreSQL 迁移与全 API/Worker 套件：

```text
make api-test
171 passed
```

覆盖的新增矩阵包括：

- AES-GCM 正常解密、跨用户 AAD 拒绝、密文篡改拒绝；
- 固定飞书路径、最小模板、稳定 provider UUID、限流分类；
- Operator 配置/审计/撤销、Reviewer 拒绝、列表不泄露；
- DEAD 重驱保留 attempt 1/2 后以 attempt 3 成功，Outcome/Evaluation/Handoff 不变；
- FEISHU Worker 写入唯一私有回执，结果页据真实回执切换外部确认；
- 外部观测合同明确 `external_collection=NOT_RUN`、`external_route=UNCONFIGURED`、`drill_evidence=NOT_RUN`。
- staging bundle 的三项新 secret、通知 App 与身份 App 分离、32-byte key、API/Worker 同钥、canonical URL 与 `FEISHU` adapter 均由自动化锁定；新增 DISABLED/无活动接收人两组历史不消费矩阵。

Web 门禁：

```text
cd apps/web && npm run lint && npm run typecheck
PASS
```

完整 `ci-fast`、迁移升降级、生产 Web build、依赖/secret 扫描和 OpenAPI 同步在候选提交前重新执行并记录最终结果。

## 4. Staging 物理证据（2026-07-28）

- 已创建与 WP-09 身份应用分离的飞书通知应用，仅启用机器人和发消息权限；独立 App ID/Secret 与 32-byte recipient key 已写入 GitHub `staging` Environment。公开证据只记录存在性与独立性，不记录值；
- 候选 `172c9f62ffdcd4fce31fb4900fdca46b3405ab89` 已由唯一授权部署 run `30351059075` 成功部署到冻结 staging 基础设施；migration 已从 `0011_wp09_feishu_identity` 升级至 `0013_wp11_notify_observability`，部署 readiness 通过；
- 部署后没有配置业务接收人、没有发送飞书消息。两次有界主机审计均确认活动接收人、外部回执和通知尝试为 0，业务事实未因观测复验而改变；
- 火山引擎 TLS project/topic、staging ECS host group、JSON stdout collection 与索引已存在并归属 staging 项目；LogCollector heartbeat 正常、服务运行、Docker socket 可访问，Docker 使用 `json-file`；
- 主机审计 run `30358231823` 与脱敏修复后的 run `30359621278` 均通过：最近 10 分钟可见 API/Worker 本地 JSON 事件，安全错误计数不含配置、容器运行时、Docker 连接或权限拒绝；后者在导出 runner CIDR 前完成掩码；
- TLS topic 在同一窗口仍返回 0 条日志。将 collection 临时收窄为精确 API 容器后结果仍为 0，随后已恢复原 API/Worker 合同；因此可排除“候选未部署、容器无日志、LogCollector 未运行、host group 未绑定、复合容器正则或索引缺失”作为当前主因，但不能宣称外部日志采集通过；
- 当前证据将剩余问题限定在 LogCollector 容器采集/传输/provider 路径。继续修改应用、部署、数据库、IAM 或业务事实不会增加诊断价值，因此停止该方向的自动修补。

## 5. 仍未运行且不得伪记通过

- 未登记真实业务接收人，未执行真实飞书发送，因此没有 provider message receipt，也没有错误收件人、限流或凭据轮换物理证据；
- TLS 外部日志采集未通过；Dashboard、Cloud Monitor 策略、外部路由和告警送达没有在本轮重新核验；
- 未执行外部告警演练，也未证明 DEAD 在真实外部系统中 4 小时内被发现；
- WP-11 仍不得记为 `INTEGRATIONS_AND_OBSERVABILITY_VERIFIED`。进入 WP-12 前必须由 Owner 选择：修复外部日志采集并完成真实通知/告警证据，或以新的 Alpha 范围决策明确延期并继续保持 production `NO_GO`。

## 6. 已验证候选

- PR #64 将 WP-11 工程接线合入主线 `172c9f62ffdcd4fce31fb4900fdca46b3405ab89`；
- Mainline Candidate Gate `30302594972` 完成 `ci-main`、候选打包、三镜像 SPDX SBOM、GHCR 推送和 registry digest 二次验证；
- canonical manifest 精确记录 migration `0013_wp11_notify_observability`、config V3、TSK-001 V1/V2 内容摘要；
- 候选绑定合同使用 API `sha256:9fd8ac58…10094`、Web `sha256:029cdc66…0b19`、Worker `sha256:6a2fe4c7…f4b79`；run `30351059075` 已把该候选部署到 staging。

## 7. 下一次外部动作所需授权

唯一执行顺序、最小权限、资源命名、停止条件和私有证据边界见 `docs/runbooks/WP11_STAGING_INTEGRATIONS.md`。

工程接线、候选锁定、独立应用/secret、staging 部署和主机侧审计已经完成。下一次外部动作只能是以下两条之一，不再把它们与应用部署混在同一轮：

1. 由 Owner/厂商支持在不改应用、不部署的前提下关闭 TLS 容器采集/传输问题；通过后再为一个明确受控接收人执行真实送达与告警演练；或
2. 由 Product/Engineering/Security 共同批准一条新的 Alpha 延期决策，承认外部日志、真实通知和告警演练尚未关闭，保留主机有界审计作为临时手段，并保持 production `NO_GO`。

未获得上述选择前，不继续修改 TLS 配置、应用、云资源或部署，也不产生外部消息或业务接收人事实。
