# WP-15｜`journey.muchenai.com` 受控 Alpha 切换手册

状态：`APPROVED_EXECUTION_PATH / NOT_FULL_PRODUCTION_GO`

本手册是受保护主线中唯一允许操作 `journey.muchenai.com` 受控 Alpha 运行面的入口。它不把尚未完成的 WP-13 全量签署、WP-14 真实 14 天、WP-11 外部告警/真实通知、WP-12B 原 1 秒性能失败或独立灾备故障域改写为通过。

## 1. 固定范围

- 候选：`8f77ceec570e2ec5e9c52861fcdc27748d7bb44a`，Candidate Gate run `30709982868`；
- region：火山引擎华北 2（北京）；不新增付费 ECS/RDS；
- 正式 Alpha 域名：`journey.muchenai.com`；staging 保留 `staging-vnext.muchenai.com`；
- 数据库：从当前 `journey_next_staging` 只读备份，首次恢复到空白 `journey_next_production`；两者不得相同；
- 运行时：独立 production Compose project、独立 production 数据库与独立应用 secret；Alpha 暂时共享现有 ECS、RDS 实例和 Caddy 故障域；
- `ATTACHMENTS_ENABLED=false`；不得 seed、发送飞书消息、配置业务接收人、修改 Terraform 中既有资源或自动修改阿里云 DNS；
- 真实开放仅限单一组织私密名单。域名切换不是完整 production release gate 的通过证明。

## 2. 前置证据

切换前必须同时满足：

1. staging Web/API/Worker 均报告精确候选，migration=`0014_wp12_data_lifecycle`、config schema=3；
2. 至少一条真实闭环已经完成：邀请 → 提交 → `REQUEST_REVISION` → Learner 安全重新进入 → 再次提交 → `PASS`；
3. `python3 scripts/wp15_alpha_cutover.py` 与 `make ci-fast` 通过；
4. GitHub `staging` Environment 存在四个彼此独立的 WP-15 secret：session、invite、import signing、backup；
5. 飞书身份应用保留 staging 回调，并新增 `https://journey.muchenai.com/auth/feishu/callback`；
6. 旧站 DNS 记录值、TTL 与截图保存在私有证据中，不写入 Public Git。

## 3. 唯一执行顺序

所有 workflow 都必须从受保护 `main` 手动触发；每个有副作用阶段只执行一次，失败不自动重试。

1. `WP-15 Database Tool Mirror`：确认词 `MIRROR_POSTGRES_17_6_DBTOOL`；只复制固定 PostgreSQL 17.6 digest 到项目 GHCR。
2. `WP-15 Controlled Alpha Production / preflight`：确认词 `PREFLIGHT_WP15_ALPHA_PRODUCTION`；只读。
3. `bootstrap-db`：确认词 `CREATE_EMPTY_JOURNEY_NEXT_PRODUCTION_DB`；Terraform saved plan 只允许创建 `volcenginecc_rdspostgresql_database.production`。
4. `backup-restore`：确认词 `BACKUP_STAGING_RESTORE_ISOLATED_PRODUCTION`；目标库非空或 ACTIVE 通知接收人非 0 即拒绝。输出加密 dump 到现有私有 TOS `production-backups/<run-id>/`，并比较源/目标 migration、schema hash、逐表计数和逐表内容指纹；最终加密工件必须实际解密并与原 dump SHA-256 相等。
5. `deploy`：确认词 `DEPLOY_8F77CEE_CONTROLLED_ALPHA_PRODUCTION`；不修改 DNS。Web/API/Worker 只连接 production DB；Caddy 预装正式 host 路由。
6. 在飞书开放平台新增并发布正式回调，保留原 staging 回调；不扩大应用权限和可用人员范围。
7. 在阿里云 DNS 把 `journey` 的 A 记录从私有证据中的旧站值改为当前 vNext ECS 公网地址，TTL 保持 600。只改这一条记录。
8. TLS 签发后验证：正式根页 200、`/health/ready` 精确候选、匿名 `/ops` 和 `/review` 为 401、飞书 OAuth 回跳仍为正式域名；同时确认 staging 根页/readiness 继续可用。

## 4. 一键止血与旧站回退

### 首选：维护页

触发 `maintenance`，确认词 `ROUTE_JOURNEY_TO_MAINTENANCE`。它只将正式 host 切到 503 维护页；staging 保持可用，production 数据库和容器不删除。恢复当前 production Web 使用 `live`，确认词 `ROUTE_JOURNEY_TO_PRODUCTION_WEB`。

### 旧站 DNS 回退

只有在 vNext 入口持续不可用且维护页不足以止血时，按私有证据把阿里云 `journey` A 记录恢复为原值。旧站不得接收或合并 vNext 已产生的业务事实；回退仅恢复入口展示，不构成数据回滚。DNS 切回后继续保留 staging 与 production DB，等待新候选前滚修复。

禁止用发布前备份覆盖已经承载真实写入的 production DB，禁止 drop database，禁止把 vNext 数据写回旧站。

## 5. 停止条件

出现以下任一项立即切维护页，不继续放量：

- 跨组织访问或角色越权；
- 已接受 Submission/Review/Outcome 事实丢失、回滚或重复；
- OAuth 回调落到 staging/本机或 session 不能撤销；
- backup/restore 事实摘要不一致；
- Web/API/Worker revision 漂移或 migration 不是 `0014`；
- Sev-1，或阻断主闭环且没有可接受手工绕行的 Sev-2。

独立故障域在真实 Alpha 连续稳定 30 个自然日后按 DEC-019 重开；在此之前必须保持共享故障域风险显式、staging 可用和加密异机备份。
