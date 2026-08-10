# WP-15 上线战时模式：受控生产切换

状态：`APPROVED_FOR_CONTROLLED_ALPHA_CUTOVER / FULL_PRODUCTION_NO_GO`

## 目标

用已在 staging 验收的候选 `ff53052847a268d025bceb93c3eab37986d50219` 替换当前受控 Alpha 运行态，同时保留当前生产应用和数据库作为可执行回退点。整个过程不修改 DNS、不运行 Terraform、不发送消息、不创建邀请。

## 冻结事实

- 候选门禁：GitHub Actions run `31340959377`。
- staging 部署：run `31342063864`；九项公开检查首次全部通过。
- staging inventory：run `31342539916`；API/Web/Worker/heartbeat 均为 `ff530528…`，migration 为 `0019_wp30_invitation_control`。
- 当前生产回退基线：API/Worker=`8f77ceec…`，Web=`8e56e759…`，数据库=`journey_next_restore_20260803`，migration=`0014_wp12_data_lifecycle`。
- 当前 DNS/TLS/飞书 OAuth 回调已正确指向 `journey.muchenai.com`，因此本次不做 DNS 或飞书控制台变更。
- 新生产数据库固定为 `journey_next_cutover_20260810`。它是同一 RDS 内的新逻辑库，不新增 ECS/RDS/网络资源。

## 唯一允许的顺序

1. `phase=preflight`：只读核对当前生产回退基线、staging 源候选和公开生产表面。
2. `phase=backup-restore`：仅创建白名单内的新空逻辑库；从 staging 生成自定义格式备份，恢复到新库，比较 PII-free 摘要，加密并复制到私有 TOS。
3. `phase=deploy`：必须引用第 2 步成功的 run ID；再次核对备份 HMAC、恢复摘要和零通知接收人，然后部署冻结候选。
4. 部署内置 12 次、每次间隔 5 秒的九项公开验收；成功后再执行容器、镜像、版本、migration、数据库、Worker heartbeat、Caddy 上游和通知状态 inventory。
5. 真实飞书 Operator 登录由当前 Operator 在同一浏览器完成；之后只创建受控小名单邀请。

任一步失败即停止，不自动重新执行工作流。部署脚本内部或公开验收失败时，只执行确定性的旧应用+旧数据库回退；若回退也失败，自动切维护页。

## 操作确认词

- `preflight`: `PREFLIGHT_FF53052_WARTIME_PRODUCTION`
- `backup-restore`: `BACKUP_RESTORE_FF53052_WARTIME_PRODUCTION`
- `deploy`: `DEPLOY_FF53052_WARTIME_PRODUCTION`
- `inspect`: `INSPECT_FF53052_WARTIME_PRODUCTION`
- `rollback`: `ROLLBACK_FF53052_TO_CONTROLLED_ALPHA_BASELINE`
- `maintenance`: `MAINTENANCE_JOURNEY_PRODUCTION`
- `live`: `LIVE_JOURNEY_PRODUCTION`

所有阶段只接受候选 `ff53052847a268d025bceb93c3eab37986d50219`，最终无条件关闭临时 SSH。

## 数据边界

- staging 只作为只读备份源；备份前后摘要必须完全一致。
- 新库必须为空；非空时立即拒绝，不清理、不覆盖。
- `journey_next_production` 继续保留为历史失败现场，不访问正文、不清理。
- 旧生产数据库不迁移、不修改；回退重新启用旧 release 目录及其旧数据库。
- 明文 dump 由 `trap` 无条件删除；仅保留 AES-256-CBC/PBKDF2 加密包、HMAC manifest 和 PII-free 摘要。
- active notification recipients 必须为 0；否则拒绝备份和上线。

## 九项公开验收

每次尝试逐项输出结果，不输出 OAuth state、cookie、身份或业务正文：

1. `/` 返回 200。
2. `/health/ready` 返回候选 `ff530528…`。
3. 匿名 `/ops` 返回 401。
4. 匿名 `/review` 返回 401。
5. 匿名 `/content` 303 到 `/content/login`。
6. `/content` 含 `Cache-Control: no-store`。
7. `/content/login` 返回 200。
8. 登录页存在“使用飞书进入”。
9. 飞书 OAuth 只指向 `accounts.feishu.cn`，回调精确为 `https://journey.muchenai.com/auth/feishu/callback`。

## 一键回退

`phase=rollback` 从 `/srv/journey-next-production/PREVIOUS_RELEASE` 读取受控基线，严格核验旧 API/Worker/Web 镜像、三组件 release 和旧数据库后重建 Compose。成功标准为公开 readiness=`8e56e759…`。它不改 DNS，也不接触新库。

若仅需阻止业务访问，使用 `phase=maintenance`；恢复当前 production Web 使用 `phase=live`。两者都保留 staging 上游为 `journey-next-staging-web-1:3000`。

## 仍然延期

本次仅允许 `CONTROLLED_ALPHA_LIVE`，不宣称 full production GO。以下项目继续延期：TLS 外部日志采集、真实通知、告警演练、独立灾备故障域、广泛邀请和正式全员开放。
