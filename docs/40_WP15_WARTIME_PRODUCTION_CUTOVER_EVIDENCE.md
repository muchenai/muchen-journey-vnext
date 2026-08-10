# WP-15 上线战时模式生产切换证据

状态：`IN_PROGRESS / PRODUCTION_UNCHANGED`

## 已完成的只读与 staging 证据

- 候选：`ff53052847a268d025bceb93c3eab37986d50219`
- 候选门禁：`31340959377`
- staging 部署：`31342063864`
- staging inventory：`31342539916`
- staging 公开验收：九项检查全部在 attempt 1 通过。
- 当前生产只读公开核验：根页 200，readiness=`8e56e759152efcbf17f4373f2132e02a8762af81`，匿名 `/ops`、`/review` 为 401，飞书 OAuth 回调为 production 域名。
- 当前生产 legacy inventory：`31343429264`；生产 marker=`8f77ceec570e2ec5e9c52861fcdc27748d7bb44a`，API/Worker/Web 均健康，临时 SSH 已关闭。

## 本 PR 增加的受控能力

- 新鲜 staging 备份恢复到 `journey_next_cutover_20260810`。
- 加密备份、HMAC manifest、PII-free 源/目标摘要一致性和 GitHub Actions 加密工件离机归档。
- 生产 API/Web/Worker/heartbeat/migration/database/image/Compose/Caddy/notification inventory。
- 九项逐条可观测公开检查和最多 12 次、每次 5 秒的有界重试。
- 部署失败或验收失败时自动回到旧应用+旧数据库；回退失败时进入维护页。
- 手动一键 `rollback`、`maintenance`、`live` 阶段。

## 待写入运行证据

以下字段只能在对应单次工作流成功后填写：

- production preflight run：`31346327113`，`PASS`；旧应用/旧库基线、staging 候选和公开表面一致，SSH 已关闭。
- backup/isolated restore run：`31346697068`，数据库备份、隔离恢复、摘要、加密解密和零接收人均 `PASS`；随后仅在 TOS 新前缀归档被 `InvalidPathAccess` 拒绝，部署未开始，SSH 已关闭。
- encrypted GitHub Actions archive：`PENDING`；只允许归档 run `31346697068` 的现有密文证明，不重做恢复。
- production deploy run：`PENDING`
- production post-deploy inventory run：`PENDING`
- production Feishu Operator login：`PENDING`
- maintenance/live drill：`PENDING`
- controlled small-cohort activation：`PENDING`

在这些证据完成前，`journey.muchenai.com` 维持当前受控 Alpha，full production 继续 `NO_GO`。
