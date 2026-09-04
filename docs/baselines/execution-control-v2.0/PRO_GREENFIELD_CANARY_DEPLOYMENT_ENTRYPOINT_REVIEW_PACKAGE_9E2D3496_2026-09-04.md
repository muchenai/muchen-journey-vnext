# Muchen Journey Greenfield Production Canary 入口复审包（9e2d3496）

状态：`READY_FOR_INDEPENDENT_PRO_REVIEW`  
正式部署：`NOT_RUN`  
`RELEASE_GO=false`

## 冻结对象

- 应用候选：`9e2d3496f5df80da1291c77bd6f949a5078ef25d`
- 候选分支：`main`
- 应用 package workflow run：`33838169130`，结论 `success`
- registry-bound release manifest SHA-256：`0efb1141903e295f879e4f63bc8172e6c009ebcdd2c06992215e1415db074056`
- artifact：`wp07-candidate-9e2d3496f5df80da1291c77bd6f949a5078ef25d`
- artifact ID：`9924442994`
- artifact digest：`sha256:2f3d55cee8f9992a3970a93cd3df51dedbdc1c097612329ab8c91d007aa117db`
- 待审 Ops 对象：本文件所在的最终 clean commit；完整 SHA 与 tag 必须由外部 Pro evidence 精确绑定。

新候选镜像均位于组织命名空间并完成 registry digest 回读：

- API：`ghcr.io/muchenai/muchen-journey-vnext-api@sha256:850d5b1eb31eda6840fc31cae266af84aa96e5d8b6ed822db6bc03081374117c`
- Web：`ghcr.io/muchenai/muchen-journey-vnext-web@sha256:0d7599796c5eef2f451b50b9a5cfe851b64c76e54b7ba17c1604b25324d85899`
- Worker（仅构建证据，Canary 禁止启动）：`ghcr.io/muchenai/muchen-journey-vnext-worker@sha256:db238460d43e2812f86e6c0c05ca98997efa022bdc09e202bbd94f740361912a`

## 本次重绑范围

- Canary 应用候选、package run、manifest、人工确认口令和三镜像 digest 全部绑定到新候选。
- 隔离数据库固定为 `journey_next_canary_20260901_c72fea5`；生产源数据库仍为 `journey_next_cutover_20260810`。
- migration head 保持 `0028_canary_main_merge`。
- API 与 Web 均要求 `RELEASE_MARKER=PRODUCTION_CANARY_UAT`。
- Dockerfile 源文件 hash 已在新候选上重新核对；Ops 构建验证器不派生修改产品字节。
- 历史 wartime 入口、`ff53052847a268d025bceb93c3eab37986d50219` 回滚目标和旧候选历史证据均未改写。

## 强制边界

- 最多 8 名具名 Learner UUID；未配置 allowlist 时 Learner 数为 0。
- `ALLOW_FIXTURE_IDENTITY=false`，不允许 fixture、模拟用户或 Codex 操作冒充真人 UAT。
- 仅启动 API/Web；Worker、真实通知、附件和生产作业保持关闭。
- `release_go=false`；本 Canary 不是正式发布。
- 未取得独立 Pro PASS evidence、精确 reviewed Ops tag 和逐 phase 短期授权前，所有生产 phase 必须失败关闭。

## 已完成的只读验证

- Mainline run `33838169130`：CI、package、GHCR push/digest verify、SBOM 和 image archive 全部通过。
- package 合同检查：PASS，manifest SHA-256 与三个 registry digest 全部匹配。
- WP31/Ops、入口和架构 Dockerfile 定向测试：`30 passed`。
- Ops closure：31 个发现依赖、32 个 manifest 绑定文件、0 缺失，PASS。
- Ops manifest 的 32 个文件 hash 全部现场复算匹配。
- 当前执行合同中的旧候选 SHA、旧 package run、旧 manifest 和旧镜像 digest 引用为 0。
- 四个 Greenfield shell 脚本 Bash syntax：PASS。
- `git diff --check`：PASS。

## 独立 Pro 必审项

1. 新应用 SHA、package manifest、三镜像 digest 与 GHCR 命名空间是否逐字一致。
2. Ops manifest 是否覆盖完整 Greenfield 执行闭包，且所有 hash 与 reviewed commit 一致。
3. 独立数据库创建、非空拒绝、备份 HMAC、恢复事实一致性和源库只读边界。
4. API/Web 双 release marker、服务端 allowlist、零 Worker、通知关闭和附件关闭。
5. Edge 自动恢复、失败清理、临时 SSH 收口及回滚目标未发生语义漂移。
6. 旧 Wartime 历史入口和旧候选历史证据未被本次重绑误改。

本文件只是复审请求，不是 PASS evidence，也不包含生产授权。复审通过后，外部 evidence 必须符合 `config/wp31_greenfield_canary_pro_review_evidence.schema.json`，并绑定最终 Ops commit、精确 reviewed tag、应用 SHA、package manifest SHA-256 和 Ops manifest SHA-256。任何 Ops 字节变化都会使该 evidence 失效。

## 当前生产影响

- 生产部署：false
- 生产数据库写入：false
- DNS/云资源变更：false
- Edge 切换：false
- Worker 启动：false
- Release GO：false

下一 Gate：`INDEPENDENT_PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW`
