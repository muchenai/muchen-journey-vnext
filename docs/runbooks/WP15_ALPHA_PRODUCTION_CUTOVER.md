# WP-15｜`journey.muchenai.com` 受控 Alpha 切换手册

状态：`APPROVED_EXECUTION_PATH / NOT_FULL_PRODUCTION_GO`

本手册是受保护主线中唯一允许操作 `journey.muchenai.com` 受控 Alpha 运行面的入口。它不把尚未完成的 WP-13 全量签署、WP-14 真实 14 天、WP-11 外部告警/真实通知、WP-12B 原 1 秒性能失败或独立灾备故障域改写为通过。

## 1. 固定范围

- 候选：`8f77ceec570e2ec5e9c52861fcdc27748d7bb44a`，Candidate Gate run `30709982868`；
- region：火山引擎华北 2（北京）；不新增付费 ECS/RDS；
- 正式 Alpha 域名：`journey.muchenai.com`；staging 保留 `staging-vnext.muchenai.com`；
- 数据库：从当前 `journey_next_staging` 只读备份；原 `journey_next_production` 保留为失败现场，已完整验证的 `journey_next_restore_20260803` 提升为 Alpha production runtime 数据库；三者不得混用；
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

1. `WP-15 Database Tool Mirror`：确认词 `MIRROR_POSTGRES_17_6_DBTOOL`；client-only Dockerfile 从固定 PostgreSQL 17.6 amd64 manifest 只提取 `psql`、`pg_dump`、`pg_restore` 及动态库闭包。发布工作流采用已审查、已生成的 GHCR manifest digest，不重复压缩构建层；仅以 `--prefer-index=false` 复标同一 manifest，并核验三个客户端版本及压缩层总量不超过 6 MB。
2. `WP-15 Controlled Alpha Production / preflight`：确认词 `PREFLIGHT_WP15_ALPHA_PRODUCTION`；只读。
3. `bootstrap-db`：确认词 `CREATE_EMPTY_JOURNEY_NEXT_PRODUCTION_DB`；使用签名 RDS API 只创建或核验精确的 `journey_next_production`，随后导入加密 Terraform state；不执行 plan/apply，不触碰六项冻结基础设施资源。
4. `schema-audit`：确认词 `AUDIT_JOURNEY_NEXT_PRODUCTION_SCHEMA`；以 `default_transaction_read_only=on` 读取 `public` schema Owner、ACL、表数及 migrator 的 USAGE/CREATE 判定。目标库非空立即停止；无论成功或失败都清理 owner-only audit bundle 并关闭临时 SSH。
5. `schema-owner-repair`：确认词 `REPAIR_EMPTY_PRODUCTION_PUBLIC_SCHEMA_OWNER`。同一次作业必须先再次证明 `public` 表数为 0、Owner=`pg_rds_superuser` 且 migrator CREATE=false；随后只调用一次官方 `ModifySchemaOwner`，把 `journey_next_production.public` Owner 改为 `journey_next_migrator`。完成后再次只读证明 Owner、空库和 CREATE=true；不得改变其他账号、表或数据库事实。
6. `backup-restore`：确认词 `BACKUP_STAGING_RESTORE_ISOLATED_PRODUCTION`；只允许在 schema 修复验证通过后执行一次。先在 600 秒内预取并校验固定 client-only 镜像，超时则在访问数据库前停止。目标库非空或 ACTIVE 通知接收人非 0 即拒绝。输出加密 dump 到现有私有 TOS `production-backups/<run-id>/`，并比较源/目标 migration、schema hash、逐表计数和逐表内容指纹；最终加密工件必须实际解密并与原 dump SHA-256 相等。无论成功或失败，都清理当次 owner-only bundle；修复路径同时清理已取消 run `30735084290` 的遗留 bundle。
7. `restore-artifact-inventory`：确认词 `INVENTORY_TWO_PLAINTEXT_RESTORE_ARTIFACTS_NO_DELETE`。只对备份根目录做文件类型、目录时间戳和字节数盘点，并读取失败时已经保存的 PII-free source/target facts；不得打开 dump、连接数据库或删除文件。必须恰好发现两个安全的普通明文文件；facts 完整时输出差异，任一侧未生成时显式记录 `MISSING_SOURCE_FACTS` 或 `MISSING_TARGET_FACTS`，不得猜测或补查业务库。最后清理 inventory bundle 并关闭临时 SSH。
8. `cleanup-known-plaintext`：确认词 `DELETE_INVENTORIED_PLAINTEXT_DUMPS_20260802`。仅当备份根目录的全部明文 dump 精确等于 inventory 已证明的 `20260802T104651Z/6838622 bytes` 与 `20260802T150149Z/6838889 bytes` 两项时，删除这两个 `journey-next.dump`；目录、facts 和数据库保持不变。任何第三项、尺寸变化、verify dump 或符号链接均在删除前拒绝。
9. `restore-drill-temp`：确认词 `CREATE_AND_RESTORE_JOURNEY_NEXT_RESTORE_20260803`。在同一 RDS 实例内只创建允许名单中的 `journey_next_restore_20260803`，Owner 固定为 migrator，并把 `public` Owner 修正为 migrator；不修改或清理 `journey_next_production`。恢复摘要排除易变运行态表 `worker_heartbeats`，但 schema 仍覆盖该表；dump 前后分别生成业务摘要且必须完全一致，再恢复到空白临时库并比较 migration、schema、逐表计数、逐表业务指纹和 ACTIVE 通知接收人数。任何失败均由 EXIT trap 删除明文 dump；成功后只保留加密且已解密校验的工件。
10. run `30760806984` 已完成数据库备份、临时库恢复、源/目标摘要比对和加密解密校验；仅在向现有 FNS TOS 的未授权 `production-backups/` 路径归档时收到 `InvalidPathAccess`。不得重做已通过的数据库恢复。`archive-temp-restore` 使用确认词 `ARCHIVE_TEMP_RESTORE_20260802T181906Z_TO_GITHUB`，只从精确目录读取加密工件、HMAC manifest 与 PII-free facts，确认不存在明文 dump、摘要相等且密文 SHA-256 匹配后，归档至私有 GitHub Actions artifact（30 天）；不连接数据库、不修改 TOS、不部署。
11. 失败恢复诊断仅用于 run `30753376010`：`restore-diff-cleanup`，确认词 `COMPARE_FAILED_RESTORE_30753376010_AND_REMOVE_PLAINTEXT`。它使用只读事务重新生成源库/目标库的 PII-free migration、schema、逐表计数、逐表内容指纹和 ACTIVE 通知接收人数；只输出相等性、差异表名和计数，不输出业务正文。仅当授权时间窗内恰有一个“存在 `journey-next.dump` 且不存在加密 dump/manifest”的目录、并且备份根目录不存在其他明文 dump 时，才删除该目录内的 `journey-next.dump` 和可选 verify dump；保留 PII-free facts，不修改数据库、不恢复、不上传该失败备份。无论成功或失败都清理诊断 bundle 并关闭临时 SSH。
12. `deploy`：确认词 `DEPLOY_8F77CEE_CONTROLLED_ALPHA_PRODUCTION`；不修改 DNS。Web/API/Worker 只连接已验证并提升的 `journey_next_restore_20260803`；禁止引用保留现场 `journey_next_production`；Caddy 预装正式 host 路由。
    - run `30761268308` 在容器启动前被 bundle 门禁拒绝：workflow 仍把 migration/backup target 设为保留现场库；没有启动 production runtime、没有修改数据库、Caddy 或 DNS。修复只把 owner-only bundle 的默认 target 与已提升运行库对齐，失败 run 不直接重试。
13. 在飞书开放平台新增并发布正式回调，保留原 staging 回调；不扩大应用权限和可用人员范围。
14. 在阿里云 DNS 把 `journey` 的 A 记录从私有证据中的旧站值改为当前 vNext ECS 公网地址，TTL 保持 600。只改这一条记录。
15. TLS 签发后验证：正式根页 200、`/health/ready` 精确候选、匿名 `/ops` 和 `/review` 为 401、飞书 OAuth 回跳仍为正式域名；同时确认 staging 根页/readiness 继续可用。

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
