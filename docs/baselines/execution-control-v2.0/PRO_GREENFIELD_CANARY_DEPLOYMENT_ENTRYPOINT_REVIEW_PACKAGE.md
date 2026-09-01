# Muchen Journey Greenfield Production Canary 入口 Pro 审查包

状态：`READY_FOR_PRO_GREENFIELD_CANARY_DEPLOYMENT_ENTRYPOINT_RE_REVIEW`  
正式部署：`NOT_RUN`  
`RELEASE_GO=false`

## 冻结对象

- 应用候选：`1633ec4eabe381da3b56500c323005c0f363c0d9`
- 待独立审查的运维实现：本文件所在最终 clean commit；完整 SHA 由外部 Pro Review Bundle manifest 绑定
- 分支：`codex/production-canary-closed-prep-20260827`
- 镜像包 workflow run：`33141698913`，结论 `success`
- registry-bound manifest SHA-256：`566f6a60baf6cb2e8e279503489b70036edb071fc891d0653f77abd04f2f7db5`
- 外部证据目录：`/Users/liumowen/Documents/Muchen Journey2.0-evidence/release-control/simplified-release-v1.0/gates/g4-canary-entrypoint/package-run-33141698913-1633ec4eabe381da3b56500c323005c0f363c0d9`

三镜像均为 `linux/amd64`、commit-tag 防覆盖并经 registry digest 回读：

- API：`sha256:df6df5ca835f33697c84c8d2566d317cc538658a0b21a292051f2eb12fd12332`
- Web：`sha256:56fc8f6f9d37960c9a39a1e209c44df19221536bc1208dca9fa60f1df9e040d6`
- Worker 仅作构建证据，Canary 不启动：`sha256:5465f34aa030b2de7a071faeb5b2f0115cbb90aba37fdd3c5fbf47fa370ac5af`

## 入口与边界

单一入口仍为 `.github/workflows/wp15-wartime-production.yml`，新增以下互斥 phase：

1. `greenfield-package`：仅构建、推送和归档，不读取生产环境。
2. `greenfield-preflight`：只读核验当前 `ff530528…` 回滚目标及 Canary 不存在。
3. `greenfield-backup-restore`：加密备份当前生产库并恢复到显式隔离库 `journey_next_canary_20260828_1633ec4`。
4. `greenfield-deploy`：只在隔离库升级到 `0027_next_stage_review`，启动独立 API/Web Compose，并切换 Edge。
5. `greenfield-inspect`：验证公网 release、远端服务集合和容器状态。
6. `greenfield-rollback`：Edge 切回 `production-web:3000` 并停止 Canary Compose；当前生产数据库不变。

任何 production phase 在 Terraform、SSH 或 RDS 访问前依次校验：候选 SHA、包 manifest、真实 Pro evidence 文件及其 SHA-256、精确 reviewed ops commit/tag，以及独立受保护的短期 Owner execution authorization。当前没有 Pro PASS evidence 或 Owner execution authorization，因此所有 production phase 均失败关闭。

运行边界：最多 8 个 Learner UUID、`ALLOW_FIXTURE_IDENTITY=false`、`RELEASE_MARKER=PRODUCTION_CANARY_UAT`、不启动 Worker、通知接收关闭、不导入 Legacy、不运行生产作业、不是 Release GO。若未配置 `WP31_CANARY_LEARNER_USER_IDS`，Learner allowlist 为 0；这允许基础部署但不能记为 Learner 真人 UAT。

## 架构修复证据

历史 run `33061535318` 保留为 `failure`：旧冻结候选 Dockerfile 固定 `aarch64` APK，在 amd64 Runner 上因包签名/架构不匹配退出 99，未推送镜像；旧候选后续成功 run `33062342289` 已被最终候选取代。派生脚本没有改动业务字段：`scripts/wp31_prepare_amd64_dockerfiles.py` 仅接受三个冻结 Dockerfile 的已知源 hash，并只替换 `aarch64 → x86_64` 及三个对应 APK SHA-256，派生 manifest 记录 `semantic_change=false`。最终候选 run `33141698913` 重新执行完整 Gate、构建、推送和 digest 回读并成功。

## 已执行验证

- Runner `33141698913`：候选 preflight、`make ci-main`（API `664 passed`、Web `68 passed`）、amd64 build、task versions、SBOM、registry absence check、push、digest verify、artifact upload 全部成功；`operate`、`greenfield_authorize`、`greenfield_execution_authorize`、`greenfield_canary` 全部 skipped。
- 最终重绑入口定向回归：`30 passed in 0.44s`。
- 精确 detached 候选派生：`WP31_EXACT_CANDIDATE_DERIVATION=PASS`。
- 合同：`WP31_GREENFIELD_CANARY={"authorization_model":"EXTERNAL_PRO_EVIDENCE_PLUS_PROTECTED_OWNER_EXECUTION_EVIDENCE","status":"PASS"}`。
- 包绑定：manifest hash `566f6a60baf6cb2e8e279503489b70036edb071fc891d0653f77abd04f2f7db5`，PASS。
- 未签 Pro evidence 负向：退出码 `2`，在任何基础设施读取前失败关闭。
- Compose 合成验证：服务严格为 `api,web`，`worker_started=false`。
- Python compile、四个 Shell `bash -n`、YAML parse、`git diff --check`：PASS。
- gitleaks：`no leaks found`。

## 文件 SHA-256

```text
e6284a693b0f9d40c9e8d45c45f745f192d66c1e8478a8a751b143db95741341  .github/workflows/wp15-wartime-production.yml
6d739e6c2d9e453fb42ef78fffa4f2ea1a958b6c1d4d60e020008fa980cdc2ee  config/wp31_greenfield_canary.json
d61d3004076110c9d29cf132b21cac9ff81129bc9981b7bcf753e24b6a20c840  deploy/production/Caddyfile.greenfield-canary
039ecaa6b54295f7a6d8b1cb262d2eca6e30b07e62d58bbb525a0048b7d8902c  deploy/production/compose.greenfield-canary.yaml
929b2694d396a04cab69beb49d3da1a025598ec787d070f4c5eb766ba9251679  deploy/production/compose.greenfield-canary.migrate.yaml
51584aee7c64ec75a8ba0e60c1aeae15225f6ac2306179dc73eb81fc17d0c7ba  deploy/production/greenfield_canary_backup_restore.sh
55cf94a65f1ed498b14a140c15d4d82f44a5f64c528c9233b78a0343ad509d32  deploy/production/greenfield_canary_deploy.sh
253d7412e46668e37127b3c5162f3585a66bd0052372c828234dca8412a87323  deploy/production/greenfield_canary_edge.sh
6046c6b13e7eef42f6655af0cc0a71bba83a1ca761f792a2644742eda5d1d636  deploy/production/greenfield_canary_rollback.sh
aa6a5fe249f554af9c4771fc09008269d94c195d34ec3481e44a120d911f5292  scripts/wp15_rds_database.py
3827fa2c4e60dc0959ba763b99981ae51161a0b93c5f80bd3838823d8a5220dc  scripts/wp15_rds_schema_owner.py
1a5174e854fe001f79d9f64eba0981573f33db86a3879d7715a551c71c620fa1  scripts/wp31_greenfield_canary.py
fd492ec6bd6b90bd43a3f6bdb9a1a87a1b444df9b0f3c29d0f1d517920b2a2e7  scripts/wp31_prepare_amd64_dockerfiles.py
6bf4c4b7a4f204df20aae2e1addaf9ed7d0f3a5ab781fdbf24f836040f899e5f  scripts/wp31_prepare_greenfield_canary.py
532a28fcfe7f44b98f736b0c9d7f3992a79dce9d9c573cc0973761ac9e7fb019  tests/test_greenfield_canary_entrypoint.py
1fc64ed340dd4d1a11d65518a8c47df433384963351ce43e52a10405a9804fd8  tests/test_wp31_prepare_amd64_dockerfiles.py
69ac2e3c23c29b4d7d8ebe76509ac31578bfa0f95acf506c611c434e01ae6f74  tests/test_wp31_greenfield_canary.py
```

## Pro 必审与 evidence 合同

Pro 必须独立核对：固定 SHA、构建派生边界、独立数据库创建/非空拒绝、备份 HMAC 与 off-host artifact、零 Worker、Edge 自动恢复、回滚目标 `ff530528…`、allowlist hash、临时 SSH 关闭以及旧 Wartime 路径未被降级复用。

最终候选尚未 dispatch 任何 production phase；`production-canary-uat` environment、secrets、allowlist 和真实基础设施访问均为 `NOT_RUN`。独立 Pro PASS 后仍须使用精确 reviewed tag，并由 Owner 为每个 phase 提供独立、短期、hash-bound execution authorization；不得由 Mini 修改 environment policy 或绕过 secrets Gate。

若且仅若通过，Pro 提供单行 UTF-8 JSON evidence，至少含：

```json
{"review_status":"PASS","reviewer":"CODEX_PRO_REVIEW_MACBOOK_PRO","reviewed_at_utc":"<RFC3339>","application_candidate_sha":"1633ec4eabe381da3b56500c323005c0f363c0d9","reviewed_ops_commit_sha":"<full reviewed ops commit sha>","package_manifest_sha256":"566f6a60baf6cb2e8e279503489b70036edb071fc891d0653f77abd04f2f7db5"}
```

随后仅允许新增该真实 evidence 并把合同中的 `pro_review` 绑定为 PASS；不得改动以上入口文件，否则原 Pro review 失效。先运行 `greenfield-preflight`，再单独执行 backup/restore，最后才能执行 deploy。CVE Gate 仍按 Owner 裁决延期到生产发布前，Canary 不得被解释为 `RELEASE_GO`。

## 当前生产影响

- 生产部署：false
- 生产数据库写入：false
- DNS/云资源变更：false
- Edge 切换：false
- 历史数据迁移：false
- Release GO：false

下一 Gate：`PRO_GREENFIELD_CANARY_DEPLOYMENT_ENTRYPOINT_RE_REVIEW`
