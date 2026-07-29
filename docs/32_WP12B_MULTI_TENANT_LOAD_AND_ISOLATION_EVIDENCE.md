# WP-12B｜多租户容量与隔离门禁证据

状态：`LOCAL_HARNESS_PASS / REVIEW_PERFORMANCE_CANDIDATE_READY / WP12B_NOT_CLOSED`

日期：2026-07-29
Owner：Tech Lead + QA/UAT Owner + Release/Ops

## 1. 结论与边界

WP-12B 是 WP-12 的候选门禁，不是 WP-13 真人名册扩展。它使用无真实个人信息的合成组织证明同一候选在多组织并发下仍满足性能预算、组织隔离和事实唯一性；WP-13 继续用一个真实组织验证人能否理解并完成闭环。

当前已完成负载合同、合成身份生命周期、真实 HTTP runner、数据库不变量审计、失败后强制身份退役和独立 staging workflow。本地 smoke 已通过；旧候选 `9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6` 已部署并完成五次有界 WP-12B 尝试，最近一次得到 Reviewer 写路径真实性能 FAIL。最小优化已由 PR #86 合入，新候选 `674e51d8ed67f9c29c3d04693376c9ba6f1114e5` 经 Mainline Candidate Gate `30489417625` 验证并推送三镜像，但尚未部署或执行负载；因此不得把本文件记为 `WP12B_CLOSED`。

## 2. 固定负载合同

`config/wp12b_multitenant_load.json` 固定：

- 20 个合成组织；
- 每组织 25 名 Learner、2 名 Reviewer、1 名 Operator，共 500 名 Learner；
- 峰值并发 50；
- 稳态 10 req/s × 600 秒；突发 25 req/s × 60 秒；
- readiness、Current Action、提交、Reviewer 队列、评审完成、结果和运营运行状态均纳入；
- 常规读取和核心同步命令 p95 ≤1 秒；
- HTTP 5xx、意外响应、409 状态冲突、跨组织泄漏、重复事实全部为 0；
- 附件继续关闭；runner 不创建通知接收人、不调用飞书、不读取通讯录、不新增云资源；
- `99.5%` 可用性仍由 WP-14 真实 14 天窗口证明，不能由 11 分钟负载替代。

## 3. 安全执行模型

| 组件 | 职责 | 失败边界 |
| --- | --- | --- |
| `journey_api.wp12b_synthetic prepare` | 仅在 local/test/staging 创建明确标记的合成组织、角色、任务和两小时会话；staging 要求运行中 release 与完整 candidate SHA 相等及精确确认词 | production 拒绝；run id 不可重放；不创建 ExternalIdentity 或通知接收人 |
| `scripts/wp12b_load.py run` | 从 owner-only 私有 bundle 经 local HTTP 执行开始、提交、评审、读取和跨组织 404 探测；canonical staging HTTPS 只做一次可达性与精确 release 核对 | local smoke 只接受 loopback；staging runner 以非特权进程在现有北京 ECS API 容器内访问固定 `127.0.0.1:8000`；公开 readiness 不进入性能指标；不打印/记录 token |
| `journey_api.wp12b_synthetic audit` | 核对组织/用户/Assignment/Submission/Review/Evaluation/Outcome 数量、固定 scope 和一事实不变量 | 任一漏单、重复或跨组织 FK 不一致即失败 |
| `journey_api.wp12b_synthetic retire` | 无论负载/审计成功与否，撤销全部合成会话并禁用合成用户 | 不删除已经产生的业务事实，保留可审计历史 |
| `scripts/wp12b_load.py verify` | 只在 load/audit/retire 同一候选、同一 run 且全部 PASS 时输出 `WP12B_CLOSED` | 不部署、不修改 staging/production |

GitHub workflow 只从加密 Terraform state 读取现有 ECS/安全组，临时开放 runner 单一 `/32` SSH，核对 `/srv/journey-next-staging/DEPLOYED_CANDIDATE` 后执行；不运行 `terraform plan/apply`、DNS、迁移、部署或通知。SSH 规则在 `always()` 中关闭，合成身份在 `always()` 中退役。公开 artifact 只含计数、延迟和布尔结果，不含 session bundle、UUID、正文或基础设施标识。

## 4. 本地真实 HTTP smoke

2026-07-29 使用隔离测试库和临时 API 容器完成：

- 2 个组织、4 名 Learner、2 名 Reviewer、2 名 Operator；
- 峰值并发 8；稳态 10 req/s ×2 秒；突发 20 req/s ×1 秒；
- 69 次真实 HTTP 请求；
- start、submission、review start/finalize、result 全闭环；
- Learner 跨组织 Assignment 与 Reviewer 跨组织 Review 均返回 404；
- HTTP 5xx=`0`、409=`0`、cross-org leak=`0`、unexpected response=`0`；
- 最慢端点本地 p95 <0.1 秒；
- 数据库审计 PASS；临时 session 全撤销、用户全禁用；
- 报告：`artifacts/wp12b/multitenant-load-20260729T012211Z-a64ff401.json`（本地私有证据，不关闭 staging 门禁）。

## 5. 首次 staging 执行与修复

2026-07-29，Owner 授权候选 `9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6` 基于主线 `c0743c3ca44be76a6c9dee5ebea97ffe64e7c3e2` 执行唯一一次 WP-12B；GitHub Actions run `30422068110` 在准备合成身份前失败。根因是远端 `docker compose exec` 未先加载发布目录的 `.deployment.env`，Compose 在解析 `API_IMAGE` 时 fail closed。该次运行未创建合成组织、用户、会话或业务事实，公开负载和数据库审计均未开始；独立 `always()` SSH 关闭步骤成功，未部署、未新增资源、未发送消息，也未重试。

本修复让 prepare/audit 在任何 Compose 调用前显式加载已有 `.deployment.env`；retire 不再解析 Compose 文件，而是用既有 Compose project/service 标签解析唯一运行中的 API 容器，再通过直接 `docker exec` 撤销身份并删除容器内会话材料。runner 侧用 `EXIT` trap 清除 ECS 上的临时私有文件，即使证据复制失败也执行。合同测试明确拒绝 prepare/audit 环境加载顺序倒置，以及 retire 再次依赖 `docker compose`。

本节只关闭首次失败的根因分析和代码修复，不关闭 staging 负载门禁。新的 WP-12B staging 运行必须由 Owner 对精确候选另行授权，失败运行 `30422068110` 不得重跑。

## 6. 第二次 staging 执行与传输边界修复

PR #82 合入后，Owner 授权同一候选基于主线 `50dbf155d57449599b61ddd6bf56bb8d9b562498` 执行一次新的 WP-12B。GitHub Actions run `30433586481` 完成 20 个合成组织、500 名 Learner 的 prepare，但 load 在 Reviewer 队列核对处得到 `expected=500 / actual=0`，audit 因 load 失败未执行。`retire` 随后 PASS，确认 active sessions=`0`、active users=`0`；SSH `/32` 入站也成功关闭。该次运行未部署、未新增资源、未发送消息，且未重试。

只读核对显示 canonical staging Web readiness 返回 200 且 release 与候选一致，而公开 `/api/v1/reviews` 返回 404。Caddy 合同仅代理 Web 容器，未公开 API；因此该结果证明 load runner 错把 Web origin 当作 API origin，不证明 20 组织或 500 Learner 容量失败，也不证明 Reviewer 队列业务逻辑失败。

本次代码修复保持公网合同不变：工作流通过已有有界 SSH 连接解析唯一 API 容器及其内部 IPv4，只在 GitHub runner 的 `127.0.0.1:38000` 建立临时 SSH 转发，所有业务压测请求走该 loopback origin；canonical HTTPS 继续独立验证用户可见 Web readiness 和精确 release。隧道进程由 `EXIT` trap 清理，不新增安全组端口、不公开 `/api`。runner 对业务阶段失败写出 owner-only、PII-free 的固定聚合报告；workflow 在 retire PASS 后无论 load/audit 是否成功均组装并上传已有的 load/audit/retired/closure 文档，永不上传 session bundle。

本修复和证据回写不构成新的 staging 执行授权。run `30433586481` 保持失败，WP-12B 仍为 `WP12B_NOT_CLOSED`。

## 7. 第三次 staging 执行与测量位置修复

PR #83 合入后，Owner 授权候选 `9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6` 基于主线 `7b3815cec6e806a3c1e0f359ac9a43d0820162e0` 执行一次 WP-12B。GitHub Actions run `30482295111` 完成 20 组织、500 Learner、500/500 Reviewer 队列和 10,562 次真实请求；HTTP 5xx、409、cross-org leak、unexpected response 均为 0，公开 readiness 及精确 release 核对 PASS。load 因 7 个端点 p95 超过统一 1 秒预算而 FAIL，数据库 audit 按旧顺序被跳过；retire PASS，active sessions/users 均为 0，PII-free 失败证据上传和 SSH 关闭 PASS。未部署、未新增资源、未发消息，也未重试。

该次 GitHub runner 位于美国西部、staging 位于北京。API/readiness 基线 p50 已约 0.58–0.69 秒，因此 p95 同时包含跨境网络抖动和应用处理时间，不能单独归因为 API/RDS 容量不足，也不能通过放宽预算将其改记为 PASS。

本次代码修复保持 1 秒应用预算不变，并改变测量位置而非结果：主线 runner/config 临时复制到北京 ECS 现有 API 容器的 `/tmp`，以非特权应用用户启动独立 load 进程；不修改应用目录/镜像，不重启服务、不拉取镜像、不创建云资源，进程结束即删除临时文件。私有 session bundle 始终留在 API 容器，不再复制到 ECS 主机文件或 GitHub runner。canonical public readiness 只核对 HTTP 200 与候选 release，明确排除在应用 p95 指标之外。数据库 audit 改为 prepare 成功后 `always()` 执行，即使性能门禁失败也保留事实唯一性/组织隔离证据；随后 retire 与 SSH close 继续无条件收尾。

本修复不构成新的 staging 执行授权。run `30482295111` 保持失败，WP-12B 仍为 `WP12B_NOT_CLOSED`。

## 8. 第四次 staging 执行与长连接修复

PR #84 合入后，Owner 授权候选 `9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6` 基于主线 `d7bc8372f0a047a24a568b09d1055758f5d5ce5b` 执行一次 WP-12B。GitHub Actions run `30486354070` 在北京 ECS API 容器内完成 20 组织、500 Learner 的真实业务事实；数据库 audit PASS：500 Assignment/Submission/Review/Evaluation/Outcome 全部闭环，cross-org mismatch、duplicate fact、incomplete flow 均为 0。retire PASS：560 个会话全部撤销、560 个合成用户全部禁用，active session/user 均为 0；PII-free 证据上传和 SSH 关闭 PASS。未部署、未新增资源、未发消息，也未重试。

load 运行约五分钟后，GitHub runner 到 ECS 的控制连接报 `client_loop: send disconnect: Broken pipe` 并以 255 退出；没有生成 `load.json`，因此该 run 不是性能 PASS/FAIL 证据，WP-12B 仍为 `WP12B_NOT_CLOSED`。事实闭环和 audit 证明应用进程已工作，但不能替代完整 600 秒稳态、60 秒突发和 p95 预算证据。

根因是长时间无标准输出的 SSH 会话未配置 client keepalive，而不是 API/RDS 容量结论。本次最小修复仅为 performance SSH 会话增加固定 `ServerAliveInterval=15`、`ServerAliveCountMax=4` 和 TCP keepalive；不改变负载规模、性能预算、应用、数据库、基础设施或失败不重试边界。合同测试要求 keepalive 不得被移除。

本修复不构成新的 staging 执行授权。run `30486354070` 保持失败，任何后续执行必须基于合入后的精确主线重新获得一次性授权。

## 9. 第五次 staging 执行与 Reviewer 写路径诊断

PR #85 合入后，Owner 授权候选 `9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6` 基于主线 `379edf82ef941b5a0bc1a50df058c380a02a349d` 执行一次 WP-12B。GitHub Actions run `30487668744` 完整运行 13 分 17 秒，证明 keepalive 修复有效并首次得到北京容器内完整性能报告：20 组织、500 Learner、50 峰值并发、600 秒 × 10 rps 稳态、60 秒 × 25 rps 突发，共 10,561 请求；canonical public readiness/release PASS 且未计入性能指标。HTTP 5xx、409、cross-org leak、unexpected response 均为 0，500/500 Reviewer 队列完整。

容量门禁仍 FAIL，且失败已收敛为两条真实 Reviewer 写路径：`reviewer.review_start` p50=`0.930194s`、p95=`1.364579s`；`reviewer.review_finalize` p50=`1.007398s`、p95=`1.502132s`。其余全部端点 p95 低于 1 秒，其中 submission create=`0.900642s`、assignment start=`0.822677s`，稳态读取与 readiness p95 均低于 `0.025s`。因此不得放宽统一 1 秒预算，也不得把该结果解释为网络或读取容量问题。

同 run 数据库 audit PASS：500 Assignment/Submission/Review/Evaluation/Outcome 全部闭环，cross-org mismatch、duplicate fact、incomplete flow 均为 0。retire PASS：560 个合成会话全部撤销、560 个合成用户全部禁用，active session/user 均为 0；PII-free 证据上传和 SSH 关闭 PASS。未部署、未新增资源、未发消息，也未重试。

代码诊断显示两条失败路径共享事务往返放大：原实现依次锁定 Review、锁定 Assignment、再读取完整组织范围上下文；finalize 还为复合外键依赖执行三次中间 flush。本次最小应用修复将可变 Review/Assignment 与完整 scoped context 合并为一次 `FOR UPDATE OF reviews, assignments` 查询，并在保留即时复合外键检查的前提下把 Outcome/Handoff/Outbox 的 flush 边界从三次降为两次。测试固定单条 scoped lock 查询和两次依赖 flush；不修改数据模型、业务事实、并发规模或性能预算。

PR #86 已将本修复合入主线；自动 Mainline Candidate Gate `30489417625` 对精确候选 `674e51d8ed67f9c29c3d04693376c9ba6f1114e5` 完成 `ci-main`、SBOM、三镜像 GHCR push、registry digest 验证和候选 artifact 上传。该事实只证明候选可部署，不构成部署或 staging 负载授权。run `30487668744` 保持真实性能 FAIL，WP-12B 仍为 `WP12B_NOT_CLOSED`。

## 10. 关闭条件

WP-12B 只有同时满足以下条件才关闭：

1. 工具 PR 合入，主线生成包含工具的完整候选 SHA 和三镜像摘要；
2. 通过独立候选绑定 PR 更新 staging 部署合同；
3. Owner 明确授权该精确候选在冻结 staging 基础设施执行一次 deploy；
4. deploy 成功后，Owner 再授权相同候选执行一次 WP-12B workflow；
5. load、数据库 audit、身份 retire 均 PASS，PII-free closure artifact 输出 `WP12B_CLOSED`；
6. 将精确 run、候选和聚合结果回写本文件及追溯矩阵。

在此之前：WP-13 真人 UAT 不启动，WP-12 仍为 `IN_PROGRESS`，production 继续 `NO_GO`。
