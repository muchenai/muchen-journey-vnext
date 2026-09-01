# Muchen Journey Greenfield Production Canary 入口复审包（c72fea57）

状态：`READY_FOR_INDEPENDENT_PRO_REVIEW`  
正式部署：`NOT_RUN`  
`RELEASE_GO=false`

## 冻结对象

- 应用候选：`c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f`
- 候选分支：`main`
- 应用 package workflow run：`33489482777`，结论 `success`
- registry-bound release manifest SHA-256：`c9c1ac639e7b4b1ed963b6b9e31b777456784b3aa560816123afdaf6bb20cc8b`
- artifact：`wp07-candidate-c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f`
- artifact ID：`9793338215`
- artifact digest：`sha256:f5d413266fbe2da41b64edd9f6b79f159d63c74165712abbd5c9ab2965fd48dc`
- 待审 Ops 对象：本文件所在的最终 clean commit；完整 SHA 与 tag 必须由外部 Pro evidence 精确绑定。

新候选镜像均位于组织命名空间并完成 registry digest 回读：

- API：`ghcr.io/muchenai/muchen-journey-vnext-api@sha256:d7131d5e8af5cf0a7cef6e4aa4cd6a8a2e6eec0816424f7010efad86224da74c`
- Web：`ghcr.io/muchenai/muchen-journey-vnext-web@sha256:fcfd637bef0e6722d45494c7e4b0099270e41046c356eaa981d702935a0a6fc3`
- Worker（仅构建证据，Canary 禁止启动）：`ghcr.io/muchenai/muchen-journey-vnext-worker@sha256:26e2a9f1826b506c3cd1f0171e694a0a209f721569f8b1102971217312dad340`

## 本次重绑范围

- Canary 应用候选、package run、manifest、migration head 和三镜像 digest 全部绑定到新候选。
- 隔离数据库固定为 `journey_next_canary_20260901_c72fea5`；生产源数据库仍为 `journey_next_cutover_20260810`。
- API 与 Web 均要求 `RELEASE_MARKER=PRODUCTION_CANARY_UAT`。
- Dockerfile 已在应用候选内支持 `amd64`/`arm64` 自动选择；Ops 构建验证器只接受三个冻结 Dockerfile 的精确 hash，不再派生修改产品字节。
- 历史 wartime 入口、`ff53052847a268d025bceb93c3eab37986d50219` 回滚目标、旧数据库和旧镜像记录均未改写。

## 强制边界

- 最多 8 名具名 Learner UUID；未配置 allowlist 时 Learner 数为 0。
- `ALLOW_FIXTURE_IDENTITY=false`，不允许 fixture、模拟用户或 Codex 操作冒充真人 UAT。
- 仅启动 API/Web；Worker、真实通知、附件和生产作业保持关闭。
- `release_go=false`；本 Canary 不是正式发布。
- 未取得独立 Pro PASS evidence、精确 reviewed Ops tag 和刘默文逐 phase 短期授权前，所有生产 phase 必须失败关闭。

## 已完成的只读验证

- Mainline run `33489482777`：CI、package、GHCR push/digest verify、SBOM 和 image archive 全部通过。
- package 合同检查：PASS。
- WP31/Ops 定向测试：`30 passed`。
- Canary 应用边界、WP31/Ops、入口和架构构建四组数据库回归：`36 passed`。
- RDS 数据库目标白名单：`11 passed`。
- Ops closure：31 个发现依赖、32 个 manifest 绑定文件、0 缺失，PASS。
- gitleaks：`no leaks found`。
- 四个 Greenfield shell 脚本 Bash syntax：PASS。
- `git diff --check`：PASS。

## 独立 Pro 必审项

1. 新应用 SHA、package manifest、三镜像 digest 与 GHCR 命名空间是否逐字一致。
2. Ops manifest 是否覆盖完整 Greenfield 执行闭包，且所有 hash 与 reviewed commit 一致。
3. 独立数据库创建、非空拒绝、备份 HMAC、恢复事实一致性和源库只读边界。
4. API/Web 双 release marker、服务端 allowlist、零 Worker、通知关闭和附件关闭。
5. Edge 自动恢复、失败清理、临时 SSH 收口及回滚目标未发生语义漂移。
6. 旧 Wartime 历史入口未被本次新候选重绑误改。

本文件只是复审请求，不是 PASS evidence，也不包含生产授权。复审通过后，外部 evidence 必须符合 `config/wp31_greenfield_canary_pro_review_evidence.schema.json`，并绑定最终 Ops commit、精确 reviewed tag、应用 SHA、package manifest SHA-256 和 Ops manifest SHA-256。任何 Ops 字节变化都会使该 evidence 失效。

## 当前生产影响

- 生产部署：false
- 生产数据库写入：false
- DNS/云资源变更：false
- Edge 切换：false
- Worker 启动：false
- Release GO：false

下一 Gate：`INDEPENDENT_PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW`
