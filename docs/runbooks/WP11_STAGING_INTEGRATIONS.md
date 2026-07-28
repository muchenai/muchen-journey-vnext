# WP-11 Staging 真实通知与外部可观测最小实施手册

状态：`STAGING_DEPLOYED / HOST_AUDIT_PASS / EXTERNAL_LOG_INGESTION_BLOCKED`

本手册只服务当前 Alpha staging，目标是证明“真实结果通知可送达，失败能被发现”。它不创建第二条部署路径，不扩大冻结 IaC，不读通讯录，不订阅消息事件，不把业务正文或人员标识写入日志。

## 1. 不可改变的边界

- Region 只能是火山引擎华北2（北京）`cn-beijing`；所有新的 TLS/Cloud Monitor 对象必须属于已有 IAM 项目 `journey-next-staging`。
- 不改 Terraform state/provider，不为 `journey-next-staging-ci` 增加 TLS、Cloud Monitor、IAM 或全局权限。Alpha 的一次性建置由 Owner 在控制台完成并留存私有证据。
- 通知应用必须与 WP-09 登录应用独立；不得复用身份 App ID/Secret。飞书 `open_id` 是应用级标识，不得把 WP-09 应用下的 `open_id` 复制给通知应用。
- 候选 `172c9f62…` 已部署并完成通知接线；当前没有业务接收人、通知尝试或外部回执。未取得新的精确授权时，不配置接收人、不发消息、不修改应用/云资源、不再次部署。
- 通知是异步副作用；无论投递成功或失败，都不得回滚 Outcome、Evaluation、Handoff 或既有历史。

## 2. 飞书通知应用的最小配置

1. 创建企业自建应用 `Muchen Journey vNext Staging Notifications`。
2. 只添加“机器人”能力和 `im:message:send_as_bot`（“以应用的身份发消息”）权限。不开启获取/发送全部消息的宽权限，不增加通讯录权限，不配置事件回调或消息读取订阅。
3. 发布一个明确版本，可用范围初始只包含一名经授权的 Alpha 接收人。扩大范围是新的外部变更，必须重新授权。
4. 通过飞书官方 API 调试台在该通知应用下获取接收人的 app-specific `open_id`；不调用全量通讯录 API，不把值写入 Git、文档、聊天或 Actions 日志。
5. 将 App ID/Secret 分别写入 GitHub `staging` Environment secrets `WP11_FEISHU_APP_ID` / `WP11_FEISHU_APP_SECRET`。
6. 在密码管理器中生成独立 32-byte 随机值，以 URL-safe Base64 存入 `WP11_NOTIFICATION_RECIPIENT_KEY`。不得复用 session、identity、invite、import 或数据库 secret。

部署包必须同时证明通知 App 与身份 App 不同、密钥解码后精确为 32 bytes、API/Worker 同钥、`NOTIFICATION_RESULT_URL=https://staging-vnext.muchenai.com/app/result`。任意一项不合格时在部署前停止。

参考：飞书官方的[发送消息教程](https://open.feishu.cn/document/introduction)明确要求机器人能力与“以应用的身份发消息”；官方权限表中的最小权限 key 为 `im:message:send_as_bot`。

## 3. 火山引擎 TLS/Cloud Monitor 最小配置

### 3.1 日志资源

- TLS Project：`journey-next-staging-logs`，Region=`cn-beijing`，IAM 项目=`journey-next-staging`。
- Topic：`journey-next-staging-runtime`，1 shard，关闭自动分裂，保留 7 天，默认 `SSE-TLS`；不为 Alpha 额外创建 KMS key。
- Host group：`journey-next-staging-ecs`，只选择已有 staging ECS。通过官方 Cloud Assistant 安装 LogCollector，必须看到正常 heartbeat 后才继续。
- Collection：`journey-next-staging-json-stdout`，只采集 API 和 Worker 的 container stdout JSON lines。不采集 env、Docker inspect、数据库日志、Caddy access query、secret 目录或业务文件。

官方文档确认 TLS Project 可关联 IAM 项目，ECS host group 可通过 Cloud Assistant 安装 LogCollector，`SSE-TLS` 为无需额外配置的默认加密方式：[日志项目](https://www.volcengine.com/docs/6470/72005?lang=en)、[Host group](https://www.volcengine.com/docs/6470/93978?lang=en)、[数据加密](https://www.volcengine.com/docs/6470/2036123?lang=en)。

### 3.2 解析与索引

只开启 JSON 键值索引，禁止全文索引。字段和类型以 `config/wp11_observability.json -> log_source.indexed_fields` 为唯一机器合同。不得索引或保留合同中 `forbidden_fields` 列出的字段。

先发生一次无业务数据的 readiness 请求，再在 TLS 中确认 `api/http.request` 和 `worker/runtime.snapshot` 各有新记录；只记录布尔结果、时间窗口和私有证据引用，不复制原始日志。

### 3.3 仪表盘与告警

创建 Dashboard `journey-next-staging-alpha`，最少包含：

- API route 成功率和 p95 延迟；
- `outbox_backlog`、`oldest_pending_seconds`、`notification_retry_wait`、`notification_dead`；
- 最后一条 `runtime.snapshot` 时间；
- `permission_denials_24h`。

按 `config/wp11_observability.json` 创建四条策略：DEAD > 0、最老积压 > 900 秒、5 分钟内 `runtime.snapshot` 数量为 0、24 小时权限拒绝 >= 10。查询窗口必须纳入 TLS 写入/索引延迟，不使用“有数据”代替数值表达式。告警策略本身再启用官方“执行失败告警”。

Cloud Monitor 只使用现有 ECS 的基础监控，告警对象精确选择单个 staging ECS（不选“全部资源”）：

- `journey-next-staging-ecs-cpu`：带外 CPU 利用率平均值 > 85%，连续 10 个 1 分钟周期，P2；
- `journey-next-staging-ecs-no-data`：基础指标连续 5 个 1 分钟周期无数据，P1。

不为 Alpha 开启全账号预置模板，不安装第二套主机监控 agent。官方文档确认 ECS 已接入[基础监控](https://www.volcengine.com/docs/6408/79324?lang=en)，告警中心支持对精确资源配置阈值和连续无数据告警，见[使用告警中心](https://www.volcengine.com/docs/6408/68815?lang=zh)。

通知组的真实邮箱/飞书 Webhook/IAM 用户目前为 `UNAUTHORIZED_TARGET`。未获得接收目标和告警测试的当轮精确授权前，只能保存策略草稿，不发测试通知。

参考：火山引擎官方[通知组](https://www.volcengine.com/docs/6470/103033)、[告警策略监控](https://www.volcengine.com/docs/6470/1387164)和[告警查询注意事项](https://www.volcengine.com/docs/6470/1359420)。

## 4. 唯一执行顺序

1. 合入 WP-11 工程 PR，等待 Mainline Candidate Gate 生成新的候选 SHA 与三个不可变镜像摘要。
2. 通过独立的候选绑定 PR 更新 staging workflow/deploy 合同；候选必须包含本手册和全部修复。
3. 获得当轮精确授权后，按第 2、3 节完成独立飞书应用、GitHub secrets 和 TLS/Cloud Monitor 建置；先不配置业务接收人。
4. 执行一次只读 preflight，只输出 secret 存在/格式/独立性布尔值和 TLS 资源类别存在性，不输出值、ID、IP 或 endpoint。
5. 只有在 Owner 为精确候选、主线、Region 和冻结基础设施授权后，才执行一次 `phase=deploy`；失败不重试。
6. 部署后先确认无接收人的历史通知仍为 PENDING，再由 Operator 为一名明确受控 Learner 写入新通知应用下的 `open_id`。这是身份数据变更，需单独授权。
7. 只在授权一条明确的合成 Alpha 结果事实后触发成功送达；核对接收人手机实收、私有 provider receipt、结果页 `external_delivery_confirmed=true` 与 TLS 脱敏日志。
8. 错误接收人、限流/凭据、DEAD 和告警测试都会产生外部/业务事实，须另行精确授权；不与首次成功送达合并执行。

## 5. 停止条件与证据

出现以下任一情况立即停止：候选/镜像不匹配、通知 App 复用身份 App、请求通讯录或消息读权限、TLS 对象未转入 staging IAM 项目、LogCollector 超过 1 分钟无 heartbeat、索引出现禁止字段、通知链接不是 `/app/result`、未配接收人的历史事件被消费、或月度预测超过现有 ¥800 上限。

公开证据只记录 PR/run/candidate、资源类别、布尔门禁、时间窗口和结论。App ID/Secret、`open_id`、provider message ID、云资源 ID/IP/endpoint、原始日志和截图只能进入私有证据库，不进 Git/Actions artifact/聊天。

## 6. 当前执行记录与停止点（2026-07-28）

- 飞书独立通知应用、三项 staging secrets、TLS project/topic/host group/collection/index 已完成最小配置；未配置业务接收人，未发送消息；
- 部署 run `30351059075` 成功，migration head 为 `0013_wp11_notify_observability`；
- 有界审计 run `30358231823`、`30359621278` 证明主机本地 API/Worker JSON 日志、LogCollector 服务、heartbeat、Docker socket 与 `json-file` 均正常；
- TLS topic 仍为 0 条；精确 API 容器正则的临时验证未改变结果，原配置已恢复；
- 停止继续调整应用、部署、数据库、IAM 或 TLS collection。后续仅接受“厂商/人工关闭 LogCollector 容器采集路径”或“批准 Alpha 延期并保持 production NO_GO”之一。
