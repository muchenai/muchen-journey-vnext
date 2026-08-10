# WP-15 上线战时模式生产切换证据

状态：`CONTROLLED_ALPHA_LIVE / FULL_PRODUCTION_NO_GO`

## 已完成的只读与 staging 证据

- 候选：`ff53052847a268d025bceb93c3eab37986d50219`
- 候选门禁：`31340959377`
- staging 部署：`31342063864`
- staging inventory：`31342539916`
- staging 公开验收：九项检查全部在 attempt 1 通过。
- 旧生产只读基线：run `31343429264`；生产 marker=`8f77ceec570e2ec5e9c52861fcdc27748d7bb44a`，API/Worker/Web 均健康，作为回退事实保留。
- 当前生产只读公开核验：根页与 readiness 均为 200，readiness=`ff53052847a268d025bceb93c3eab37986d50219`；匿名 `/ops`、`/review` 为 401，匿名 `/content` 303 到 `/content/login`，飞书 OAuth 回调精确为 production 域名。

## 本 PR 增加的受控能力

- 新鲜 staging 备份恢复到 `journey_next_cutover_20260810`。
- 加密备份、HMAC manifest、PII-free 源/目标摘要一致性和 GitHub Actions 加密工件离机归档。
- 生产 API/Web/Worker/heartbeat/migration/database/image/Compose/Caddy/notification inventory。
- 九项逐条可观测公开检查和最多 12 次、每次 5 秒的有界重试。
- 部署失败或验收失败时自动回到旧应用+旧数据库；回退失败时进入维护页。
- 手动一键 `rollback`、`maintenance`、`live` 阶段。

## 运行证据与剩余人工门禁

以下字段只能在对应单次工作流成功后填写：

- production preflight run：`31346327113`，`PASS`；旧应用/旧库基线、staging 候选和公开表面一致，SSH 已关闭。
- backup/isolated restore run：`31346697068`，数据库备份、隔离恢复、摘要、加密解密和零接收人均 `PASS`；随后仅在 TOS 新前缀归档被 `InvalidPathAccess` 拒绝，部署未开始，SSH 已关闭。
- encrypted GitHub Actions archive：run `31355813108`，现有密文恢复证明的校验与 30 天私有 Actions artifact 上传均 `PASS`，SSH 已关闭；未重做恢复。
- production deploy run：`31356099600`，候选 `ff530528…`、数据库 `journey_next_cutover_20260810`、migration `0019_wp30_invitation_control` 和零有效通知接收人均 `PASS`，SSH 已关闭。
- production post-deploy inventory：run `31356099600` 与 live run `31407779768` 均 `PASS`；API/Web/Worker/heartbeat 全部为 `ff530528…`，Compose 三服务各一实例、Worker 非 stale、Caddy 上游为 `production-web:3000`。
- notification safety：`active_notification_recipients=0`，因此未发送消息；恢复库保留 `pending_outbox_events=2501`，未来配置真实接收人前必须单独审计和处理，不得直接启用发送。
- production Feishu Operator login：`PENDING`
- maintenance/live drill：maintenance run `31373093204` 返回 503 且 SSH 关闭；首次 live run `31373410985` 因工作流先验收后切流而失败且未执行 live 路由。PR #172 修正顺序后，live run `31407779768` 在主线 `be8159e6a011aa1c82e3e76c75d9b5792d33dd33` 成功，Edge=200、九项公开验收 attempt 1 全部通过、runtime inventory 通过、临时 SSH 已关闭。此前 noexec 与 env path 失败 run `31358449822`、`31363231719` 继续作为失败证据保留。
- controlled small-cohort activation：`PENDING`

`journey.muchenai.com` 已恢复候选 `ff530528…` 的受控 Alpha 访问；本记录不替代真人 Operator 登录、小名单激活、完整 WP-13/WP-14 或双人 production 批准，因此 full production 继续 `NO_GO`。
