# Muchen Journey Greenfield Production Canary 入口 Pro 审查包

状态：`READY_FOR_PRO_GREENFIELD_CANARY_DEPLOYMENT_ENTRYPOINT_REVIEW`  
正式部署：`NOT_RUN`  
`RELEASE_GO=false`

## 冻结对象

- 应用候选：`1bccbbf1706a8216892f5b9b512b1e27ce784101`
- 待独立审查的运维实现：`a2bc5ce4a5696f6bdc1f41a21de4fc884249df91`
- 分支：`codex/production-canary-closed-prep-20260827`
- 镜像包 workflow run：`33062342289`，结论 `success`
- registry-bound manifest SHA-256：`49f95c33131932e113cc8bcdf252ff647a4d21782ce353d1b2038ffc75960eb1`
- 外部证据目录：`/Users/liumowen/Documents/Muchen Journey2.0-evidence/production-canary/1bccbbf1706a8216892f5b9b512b1e27ce784101/package-run-33062342289`

三镜像均为 `linux/amd64`、commit-tag 防覆盖并经 registry digest 回读：

- API：`sha256:772ea55221ab07fdec746c9098542c2e627a658239b2769cc214c969e1ed1a85`
- Web：`sha256:743d441ef04c1d23e7cc77c34c4216028ec2b8f2499260a98283428803b6cdbb`
- Worker 仅作构建证据，Canary 不启动：`sha256:ec9aa9f3975db8349e8439990bc98d6740fff5cf763496a174b1cf0b33b00e5d`

## 入口与边界

单一入口仍为 `.github/workflows/wp15-wartime-production.yml`，新增以下互斥 phase：

1. `greenfield-package`：仅构建、推送和归档，不读取生产环境。
2. `greenfield-preflight`：只读核验当前 `ff530528…` 回滚目标及 Canary 不存在。
3. `greenfield-backup-restore`：加密备份当前生产库并恢复到显式隔离库 `journey_next_canary_20260827_1bccbbf`。
4. `greenfield-deploy`：只在隔离库升级到 `0027_next_stage_review`，启动独立 API/Web Compose，并切换 Edge。
5. `greenfield-inspect`：验证公网 release、远端服务集合和容器状态。
6. `greenfield-rollback`：Edge 切回 `production-web:3000` 并停止 Canary Compose；当前生产数据库不变。

任何 production phase 在 Terraform、SSH 或 RDS 访问前依次校验：候选 SHA、包 manifest、真实 Pro evidence 文件和调用参数中的 evidence SHA-256。当前 `config/wp31_greenfield_canary.json` 明确为 `pro_review.status=PENDING`、`entrypoint_execution_granted=false`，因此所有 production phase 当前均失败关闭。

运行边界：最多 8 个 Learner UUID、`ALLOW_FIXTURE_IDENTITY=false`、`RELEASE_MARKER=PRODUCTION_CANARY_UAT`、不启动 Worker、通知接收关闭、不导入 Legacy、不运行生产作业、不是 Release GO。若未配置 `WP31_CANARY_LEARNER_USER_IDS`，Learner allowlist 为 0；这允许基础部署但不能记为 Learner 真人 UAT。

## 架构修复证据

首轮 package run `33061535318` 保留为 `failure`：冻结候选 Dockerfile 固定 `aarch64` APK，在 amd64 Runner 上因包签名/架构不匹配退出 99，未推送镜像。修复没有改动业务字段：`scripts/wp31_prepare_amd64_dockerfiles.py` 仅接受三个冻结 Dockerfile 的已知源 hash，并只替换 `aarch64 → x86_64` 及三个对应 APK SHA-256；派生 manifest 记录 `semantic_change=false`。第二轮 run `33062342289` 完成完整 Gate、构建、推送和 digest 回读。

## 已执行验证

- Runner `33062342289`：候选 preflight、`make ci-main`、amd64 build、task versions、SBOM、registry absence check、push、digest verify、artifact upload 全部成功；旧 `operate` job skipped。
- 本机候选回归：在部署入口施工前 `526 passed`。
- 新入口定向回归：`28 passed in 0.43s`。
- 精确 detached 候选派生：`WP31_EXACT_CANDIDATE_DERIVATION=PASS`。
- 合同：`WP31_GREENFIELD_CANARY={"pro_review_status":"PENDING","status":"PASS"}`。
- 包绑定：manifest hash `49f95c…`，PASS。
- 未签 Pro evidence 负向：退出码 `2`，在任何基础设施读取前失败关闭。
- GitHub 负向 dispatch `33064145301`：`failure`、`steps=[]`、`runner_name=""`，三个业务 job 中仅 Greenfield job 失败，旧 `operate` 与 package 均 skipped；没有 Runner、Terraform、SSH 或 RDS 执行。该现象与 environment/branch 的 pre-run policy Gate 一致，但 GitHub 未提供日志，故不冒充为入口内部 review-check 的远端 PASS。
- Compose 合成验证：服务严格为 `api,web`，`worker_started=false`。
- Python compile、四个 Shell `bash -n`、YAML parse、`git diff --check`：PASS。
- gitleaks：`no leaks found`。
- 一次完整套件替代执行因绕过 Compose 测试环境注入产生 401/BusyBox 工具差异，不计 PASS；原始候选的真实 Runner 完整 Gate 仍为上述 run `33062342289`。

## 文件 SHA-256

```text
5d41b18f0e3cef9b41915a19dc719dbbfb6072b25124a3edcace09793c53fb3d  .github/workflows/wp15-wartime-production.yml
bf1c02003af83a9ab43776b87b5279c8bdd35cee5efcdbec47c25fe1e65965bb  config/wp31_greenfield_canary.json
d61d3004076110c9d29cf132b21cac9ff81129bc9981b7bcf753e24b6a20c840  deploy/production/Caddyfile.greenfield-canary
039ecaa6b54295f7a6d8b1cb262d2eca6e30b07e62d58bbb525a0048b7d8902c  deploy/production/compose.greenfield-canary.yaml
929b2694d396a04cab69beb49d3da1a025598ec787d070f4c5eb766ba9251679  deploy/production/compose.greenfield-canary.migrate.yaml
2236dd0cf219179f3b683733a8cee728b1ddf621aaa69f99d35eca40057a7e3d  deploy/production/greenfield_canary_backup_restore.sh
3aa8d61f87b4dd7e2d7e8bceaed5f69d68c63bd6b13be3d05d3c32f438b3eb77  deploy/production/greenfield_canary_deploy.sh
82039197ca52864db0753e12d84a73feba4c07c1918e03c72e144b8b71996699  deploy/production/greenfield_canary_edge.sh
818dc57b61ef872bff8faa8b70d89b4befd30bc60edabb149bd906704bdd86db  deploy/production/greenfield_canary_rollback.sh
458ee5b951cebfff64622c0be1c40af502d50752cbf778a050ad8dc2d4981955  scripts/wp15_rds_database.py
c4eeda0af0ad9e502ea45aabf0d2309209528184e3d143480e5b4d34ca6a8325  scripts/wp15_rds_schema_owner.py
01768cead42c4e2500c810e04fe810db8e2a9314cd5f63105151c563fa2977c0  scripts/wp31_greenfield_canary.py
5c37aa1057f06ccf85101d6f59d1ad4027da937be28dd6379e04c4a6f355ced1  scripts/wp31_prepare_amd64_dockerfiles.py
53b7c39b87aaec41aa2681fd20ebe7472e2ce07d934ca071eb08266d318c7d76  scripts/wp31_prepare_greenfield_canary.py
45499e659c920f3967ef40138e0184c770bbb4eb0ad64f846ca7e16e83e0a2bb  tests/test_greenfield_canary_entrypoint.py
1fc64ed340dd4d1a11d65518a8c47df433384963351ce43e52a10405a9804fd8  tests/test_wp31_prepare_amd64_dockerfiles.py
01afd984b30fcd2bbe16fe84dc5887d049470a0f4e4b5575d654212ebc33e173  tests/test_wp31_greenfield_canary.py
```

## Pro 必审与 evidence 合同

Pro 必须独立核对：固定 SHA、构建派生边界、独立数据库创建/非空拒绝、备份 HMAC 与 off-host artifact、零 Worker、Edge 自动恢复、回滚目标 `ff530528…`、allowlist hash、临时 SSH 关闭以及旧 Wartime 路径未被降级复用。

当前分支尚不能取得 `staging` environment 中复用的生产运维 secrets：run `33064145301` 在分配 Runner 前即失败。独立 Pro PASS 后，还必须由获批流程让固定运维提交使用该 environment，或将已审查入口合入 environment 允许的受保护分支；不得由 Mini 修改 environment policy 或绕过 secrets Gate。

若且仅若通过，Pro 提供单行 UTF-8 JSON evidence，至少含：

```json
{"review_status":"PASS","reviewer":"<independent reviewer>","reviewed_at_utc":"<RFC3339>","application_candidate_sha":"1bccbbf1706a8216892f5b9b512b1e27ce784101","reviewed_ops_commit_sha":"a2bc5ce4a5696f6bdc1f41a21de4fc884249df91","package_manifest_sha256":"49f95c33131932e113cc8bcdf252ff647a4d21782ce353d1b2038ffc75960eb1"}
```

随后仅允许新增该真实 evidence 并把合同中的 `pro_review` 绑定为 PASS；不得改动以上入口文件，否则原 Pro review 失效。先运行 `greenfield-preflight`，再单独执行 backup/restore，最后才能执行 deploy。CVE Gate 仍按 Owner 裁决延期到生产发布前，Canary 不得被解释为 `RELEASE_GO`。

## 当前生产影响

- 生产部署：false
- 生产数据库写入：false
- DNS/云资源变更：false
- Edge 切换：false
- 历史数据迁移：false
- Release GO：false

下一 Gate：`PRO_GREENFIELD_CANARY_DEPLOYMENT_ENTRYPOINT_REVIEW`
