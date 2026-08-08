# WP-08 火山引擎独立 Staging 运维手册

状态：`CONTENT_EDITOR_ANONYMOUS_ENTRY_CANDIDATE_BOUND_PENDING_AUTHORIZATION / LAST_DEPLOYED_API_WEB_WORKER_2223FC1 / PRODUCTION_NO_GO`。本文仍是 Greenfield vNext 唯一 staging 资源与部署入口；不复用旧 P1 脚本。Provision 已收敛并冻结。最近一次成功部署证据为 API/Web/Worker=`2223fc1…`、migration=`0019_wp30_invitation_control` 的 run `31147474464`；该候选的唯一部署已消费。PR #154/#156 依次修复 `/content` OAuth 回调 cookie 转发和无会话安全重新进入；PR #157 只关闭候选生成时新出现的 `nanoid` 公告。新主线 `3b7d757…` 的 Mainline Gate 已远端复验三镜像，当前只建立其部署合同，尚未部署。候选绑定不替真人提供材料、复核或签署，不发布 Journey V3、不创建邀请、不发送消息；production 继续 `NO_GO`。

2026-07-30 本地隔离诊断复现默认 15 连接池的约 `0.750s` checkout wait p95，并完成 API `20+5`、Worker `2+1` 的有界修复及 submission 两次冗余 flush 删除。候选已部署并完成唯一 WP-12B；原 1 秒性能结果保持 FAIL，隔离、事实审计和强制退役 PASS，DEC-020 仅建立 WP-13 Alpha 条件入口。

## 1. 已锁定授权

- Provider：火山引擎；Region：华北2（北京），ID=`cn-beijing`；
- 计费：全部按量计费（`PostPaid`）；月度硬上限：`¥800`；
- 历史候选：`670661865f708a835997596ed5b74904809564a5`；已验证 Next.js 16.2.11 / sharp 0.35.3，但不含 Web readiness 修复，禁止再次 deploy；
- 已消费候选：`d407b5f4a32fd68b1a8b08ac5a461aa04aa29fff`；唯一 deploy run `30138363837` 已失败且禁止重试；
- 已消费候选：`dad44cc679184a1978b0f69e3632cb95de7f1b8e`；canonical run `30139385352` 的 `registry_push=VERIFIED`，唯一 deploy run `30157449832` 已实际部署但浏览器 CSP/hydration 复验失败，禁止重试；
- 已消费候选：`14c9ba073c293da1d4c6b615ea1f07c6c50688fa`；唯一 deploy 已成功消费；
- 历史身份候选：`26d56010125024ca2dbc6e85f7dfeb59857f93dd`；唯一 deploy run `30181022690` 成功，真实 Operator 完成绑定与会话；随后已由 OAuth 同源回跳修复候选 `2ea51c0…` 成功部署并取代，不得再次 deploy；
- 历史已消费候选：`2ab2658fc0341d11bc1434524d86128e23da9170`；canonical run `30237677350` 的 `registry_push=VERIFIED`，唯一 deploy run `30242231558` 已成功，后续已由 WP-11 候选替代；
- 历史已消费候选：`172c9f62ffdcd4fce31fb4900fdca46b3405ab89`；Mainline Candidate Gate `30302594972` 与唯一 deploy run `30351059075` 均成功，该候选不得再次部署；
- 历史已消费候选：`9e1cdb280e47ecb5b2571a4f4bedb05a7c9f22f6`；Mainline Candidate Gate `30416410890` 和部署均成功，WP-12B run `30487668744` 给出真实性能 FAIL，该候选不得再次部署或重跑；
- 历史已消费候选：`674e51d8ed67f9c29c3d04693376c9ba6f1114e5`；Mainline Candidate Gate `30489417625`、唯一 deploy run `30506961105` 均成功；唯一 WP-12B run `30508873351` 完成 20 组织/500 Learner/10,561 请求，正确性、数据库 audit、560 会话/用户退役、证据上传和 SSH 关闭均 PASS，但 submission/review start/review finalize p95 超过 1 秒，性能门禁 FAIL；该候选不得再次部署或重跑；
- 当前 API/Worker 性能基线：`02863d0b670ee9b00b9def3e75bc6699827f555a`；PR #90、Mainline Candidate Gate `30511897160` 和唯一 deploy run `30519669770` 均成功；唯一 WP-12B run `30525165474` 完成 20 组织/500 Learner/10,561 请求，隔离、事实审计、560 会话/用户退役、证据上传和 SSH 关闭均 PASS，但 submission/finalize p95=`1.012/1.097s` 超过原 1 秒预算。该基线不得再次部署或重跑 WP-12B；DEC-020/021 仅允许其与 Web=`222096db…` 的已验证组合按 ≤1.2 秒边界启动 WP-13，不能视为 WP-12B 或 production 性能门禁通过；
- Web 邀请入口修复候选：`222096db506e95db887a8705b22ca4a439d0545d`；Mainline Candidate Gate `30550010916` 已完成完整 CI、候选工件、三镜像 GHCR push 与 digest 验证。full deploy run `30556851235` 超时取消后形成 Web 新、API/Worker 旧的混合状态，未被接受为部署成功。`config/wp08_web_only.json` 现建立有界 Web-only 合同：只允许候选单提交中的 Web/指定证据路径；API、Worker、migration 与 OpenAPI 必须和基线 `02863d0…` 完全兼容；运行时必须先证明 API/Worker=`02863d0…`、migration=`0014_wp12_data_lifecycle`、config schema=3、Worker 非 stale，否则在 Web 写入前停止；
- 历史 Web-only/runtime-repair dispatch 已随受控 Alpha 候选绑定退役；`config/wp08_web_only.json` 仅保留为不可变历史合同并明确 `RETIRED`。PR Fast Gate 继续验证其原候选、父提交、路径和兼容性事实，但 `.github/workflows/staging.yml` 的 job guard 不再允许 `provision`、`deploy-web` 或 `repair-runtime`；
- 历史受控 Alpha 候选：`8f77ceec570e2ec5e9c52861fcdc27748d7bb44a`；唯一 deploy run `30729705773` 已成功消费，不得再次部署；
- WP-19～WP-22 最小纵向切片候选：`ef0a512cf357001cfd8cb6803f65cc17ae697325`；Mainline Candidate Gate `30806515651` 已完成 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验。migration head 为 `0015_wp19_formal_journey`；候选清单包含 10 个 TaskVersion，其中 8 个正式旅程任务保持 `RUNTIME_OPERATOR_PUBLISH_REQUIRED`，部署不会替 Operator 发布业务内容。唯一 deploy run `30808632624` 已在 `.deployment.env` 缺少 `PRODUCTION_HOST` 时 pre-start fail closed：没有 pull、migration、grant、seed、容器替换或 `current` 切换，SSH 已关闭。该部署授权已消费；修复与失败目录清理不构成新部署授权；
- WP-24 Formal Exploration Camp V2 staging 候选：`0589fc825e41dc0c536b3bf87ac284c9a50013fd`；Mainline Candidate Gate `30909355182` 已完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验，migration head 为 `0016_wp24_formal_camp_v2`。该部署只安装运行能力和前向 schema，不替 Operator 发布 Journey V2、不创建邀请、不发送消息；
- WP-26～WP-30 staging 候选：`a2312b269b1806cd3d5ce7d26fbc693466399035`；Mainline Candidate Gate `30958975566` 已完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验，migration head 为 `0019_wp30_invitation_control`。该部署只允许从现有 `0016` 前向迁移到 `0019`、同步 runtime DML 权限并替换 API/Web/Worker/Edge；不运行 Terraform、DNS、云资源、WP‑12B，不发布 Journey V3、不创建邀请、不发送消息；
- `/content` 身份入口修复候选：`e61cb3af80baef389157ead79fc91ebf89e52adc`；Mainline Candidate Gate `30960806357` 与唯一 staging deploy run `31006041324` 均成功，migration head 保持 `0019_wp30_invitation_control`，临时 SSH 已关闭。该候选已经消费，不得再次部署；
- Content Editor 历史身份迁移候选：`2223fc1589d772e5397e43357fc5682f27c1c3a8`；Mainline Candidate Gate `31137770622` 与唯一 staging deploy run `31147474464` 均成功，migration head 保持 `0019_wp30_invitation_control`，临时 SSH 已关闭。Operator 随后完成受控迁移和新链接生成，账号持有人本人完成 OAuth，机器读回确认 Content Editor 为 `LINKED`；该候选已经消费，不得再次部署；
- Content Editor OAuth 回调修复候选：`c0765eb625fc3c99205dc3d05abf9fad0475d81d`；PR #154 把 `/content` 加入 Web callback 的精确同源安全入口，并增加 cookie 响应转发合同。Mainline Candidate Gate `31171640166` 已完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验，migration head 保持 `0019_wp30_invitation_control`；候选尚未部署；
- Content Editor 无会话重新进入候选：`3b7d7573cd70b72868e427b523ff630b732f0603`；PR #156 为匿名 `/content` 增加同源 `/content/login` 与“使用飞书进入”，保持 `/ops`、`/review` 匿名 401；PR #157 仅固定 `nanoid 3.3.17` 以关闭候选门禁公告。Mainline Candidate Gate `31259643008` 已完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与摘要复验，migration head 保持 `0019_wp30_invitation_control`；候选尚未部署；
- 入口：`https://staging-vnext.muchenai.com`；
- 资源：独立 IAM 项目/CI 子用户、VPC、子网、安全组、ECS、RDS PostgreSQL、TOS、委派 DNS 子区与 TLS；
- Owner：Liu Mowen。上述授权不包含 production、旧系统变更、真实飞书消息、真人 UAT 或将月预算扩大到 ¥800 以上。

`config/wp08_staging.json` 是机器合同。官方价格计算器同日总额未写入 `approved_monthly_estimate_cny` 时，`make wp08-staging-apply-check` 必须失败；合计高于 ¥800 时同样失败。

2026-07-22 的首次 ¥500 尝试已停止且未创建资源。用户随后将上限提高为 ¥800 并保留托管 RDS。新候选与同日报价均已关闭：PostgreSQL 17 高可用 1C2G 主备 20 GiB ¥396/月、ECS ¥177.26/月、TOS 20 GiB 保守 ¥3/月、EIP 出流量 100 GiB ¥80/月、RDS 备份 ¥0、DNS/ACME TLS ¥0，合计预测 ¥656.26/月，预算余量 ¥143.74。

## 2. 资源边界

- 新建项目与资源统一使用 `journey-next-staging-*`；禁止使用旧账号 AK/SK、旧 VPC/安全组、旧 ECS/RDS、旧 TOS bucket/prefix、旧部署脚本、旧 Sentry 项目或旧飞书应用。
- `staging-vnext.muchenai.com` 建为独立 DNS 子区；主域 `muchenai.com` 只增加该子区的 NS 委派，不把根区凭证交给 staging CI。
- ECS 只公开 80/443；Terraform 中 22 端口始终只接受 `127.0.0.1/32`。部署期间由同一 workflow 直接调用 VPC API 临时添加当前 GitHub runner 的单一 `/32`，`always()` 步骤按完全相同的 CIDR/协议/端口/优先级/描述撤销并反向确认；不得让 CloudControl 重写安全组嵌套集合。
- Alpha 应用发布冻结现有基础设施：`phase=deploy` 只做 backend init、`terraform output -raw`、临时 SSH、发布包、Compose 与 TLS smoke，不运行 provider refresh、DNS import、plan 或 apply。基础设施变化只能显式使用 `phase=provision` 并继续通过 saved-plan 破坏性门禁。
- `phase=deploy-web` 复用同一 workflow、同一冻结 state、同一临时 SSH 开关和同一 `deploy.sh`，不是第二条部署路径。它只拉取固定 Web digest，并仅执行 `docker compose up ... web`；API/Worker 镜像、环境、迁移、seed、DNS 和基础设施不得改变。Web pull 最长 8 分钟、启动最长 4 分钟；失败或取消只回滚 Web。成功证据必须同时包含 Web target revision、API/Worker baseline revision、migration、config schema、Worker 新鲜心跳及三个公开 HTTP 合同。
- `phase=repair-runtime` 只处理已审查运行态：Web 必须先为 `222096db…`；API/Worker 与 heartbeat release 只能是 inventory 已证明的 `222096db…`，或先前已审查的 `172c9f62…` / `02863d0…`；migration 只能是 `0013` 或 `0014`。它不拉取、不重启 Web；只拉取固定 `02863d0…` API/Worker digest，必要时前向升级到 `0014`、同步 runtime DML 权限并依次替换 API/Worker。API/Worker pull 各最长 8 分钟，migration 5 分钟、授权 2 分钟、两个服务各 4 分钟，所有 timeout 另有 30 秒强制终止。应用失败回滚到容器实际 Compose working directory；`0014` 是加表型前向 migration，不伪造数据库回滚。禁止 seed、业务事实、DNS、Terraform、云资源、Web 或 WP-12B 改写。
- `phase=inspect-runtime` 是修复前的 PII-free 只读盘点。它从冻结 state 仅读取 ECS 地址与安全组，临时开放当前 runner 的单一 SSH `/32`，在现有容器内读取 Web/API/Worker release、API readiness release、Alembic revision、config schema 与 Worker heartbeat release/freshness；同时对白名单内的 API/Worker/Web/Edge 容器输出运行状态、实际 image ID、配置的不可变镜像摘要、Compose project/service、release 目录 basename、Compose 文件 basename、网络名称与 DNS alias，并只从容器内现行 Caddyfile 提取 staging/production upstream。额外输出同一 Compose project 的各 service 运行容器计数，用于发现重复 Web backend；不得输出容器 IP、环境变量、挂载内容、网络/容器 ID、账号、数据库连接、身份、业务事实或消息内容。盘点后无条件关闭临时 SSH；禁止镜像拉取、Compose 变更、容器重启/停止/删除、网络连接变更、migration、grant、seed、Terraform plan/apply/import、DNS、消息和 WP-12B。
- `phase=diagnose-publication` 是一次性正式 Journey 发布失败诊断。它只接受候选 `ef0a512…` 与确认词 `DIAGNOSE_FORMAL_JOURNEY_EF0A512_STAGING`，固定读取 `2026-08-04T01:20:00Z` 至 `01:30:30Z` 的现有 Web/API Docker 日志；原始日志只在内存解析，输出严格限于 HTTP 状态、request ID、异常类、应用文件/行号、数据库表/约束标识与预定义错误分类。不得输出原始日志、请求正文、业务数据、IP、环境变量、凭据或数据库值；不得连接数据库、在容器内执行命令、写文件、部署或重启服务。无论结果如何都关闭 runner 单一 SSH `/32`，失败不重试。
- 该一次性诊断 run `30872474226` 已失败关闭：固定窗口没有正式 Journey 发布请求到达 API，不能把此前 Next 通用错误误判为 API/数据库根因；临时 SSH 已关闭且不得重跑。主线 `12bc627d…` 的 Mainline Candidate Gate `30872461375` 已生成并验证 Web digest `sha256:21e22f…`。`config/wp19_publication_web_only.json` 与 `WP-19 Publication Web-only Staging` 只建立待授权的 staging Web-only 合同：API/Worker 固定 `ef0a512…`、migration 固定 `0015_wp19_formal_journey`，不包含 production、数据库、Terraform apply、seed、消息或业务事实写入。合同存在不代表部署授权；只有取得新的明确授权后才能 dispatch 一次，失败不得重试并必须关闭临时 SSH。
- Owner 随后精确授权候选 `12bc627d4310cdba9eba4c67050dc875994ceb31` 基于主线 `dffb68ce84c6468ad913e6413ece19914f193c3d` 执行一次 staging Web-only 部署。唯一 run [`30875911123`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30875911123) 成功且未重试：API/Worker 固定 `ef0a512…`，migration 固定 `0015_wp19_formal_journey`；公开 readiness=`12bc627…`、根页面 200、匿名 `/ops`/`/review`=401。数据库、业务事实、消息、Terraform、DNS、云资源和 WP-12B 均未改变，临时 SSH 已关闭。
- 运行态随后从 `/ops` 服务端读回固定旅程 `Muchen Journey 探索营 · V1 · 8 站`。Operator 只生成一次绑定该 JourneyVersion 的 24 小时受控邀请；刷新后最近邀请仍显示“待使用”，一次性链接正文不再展示且未进入证据。该事实将 WP-19～WP-22 最小纵向切片升级为 `MACHINE_READBACK_VERIFIED`，不替代内容真人理解、Reviewer 校准、WP-23 或 production 门禁。
- `phase=repair-edge-route` 是上述 inventory 根因的单次、fail-closed 修复。它只接受候选 `ef0a512…` 与确认词 `REPAIR_EDGE_ROUTE_EF0A512_STAGING`，从冻结 state 临时开放一个 runner `/32`，先核验 staging/production Web 既有 release、共享 `web` 冲突、唯一 staging alias、当前 Edge digest、Compose project/release 和旧 Caddyfile，再用运行中的同一 Caddy binary 校验新 Caddyfile。应用时只原位替换当前 release 的 Caddyfile并以 `--no-deps --force-recreate --pull never edge` 重建 Edge；不重启 Web/API/Worker。成功必须连续 12 轮命中 staging=`ef0a512…`、production=`8e56e759…`，两个根页面可达且 staging `/ops`、`/review` 匿名均为 401。任何应用或公开核验失败都恢复备份并再次只重建 Edge；成功才删除 root-only 临时状态。SSH 最终无条件关闭；禁止 pull、migration、grant、seed、Terraform、DNS、云资源、消息和 WP-12B。
- `phase=audit` 只从加密 remote state 读取 ECS、RDS、AllowList 与安全组身份，并用北京地域 `DescribeAllowListDetail` 核对 `AssociateEcsIp` 的有效主网卡 IP；日志只输出计数和一致性布尔值，不输出 IP/资源 ID。结构、身份、IP 或 VPC 不一致立即失败；仅当这些字段全部匹配而实例 `IsLatest=false` 时，允许在同一次 audit 内每 10 秒重读、最多 7 次（总等待不超过 60 秒），窗口耗尽仍 fail closed。该 phase 不运行 refresh/plan/apply/import、不开放 SSH、也不连接数据库。
- ECS `stopped_mode` 固定为实例当前且该规格支持的 `KeepCharging`；预算按整月运行估算，不在 deploy 时尝试切换计费停止模式。
- 每条安全组规则只声明实际使用的来源选择器；CIDR 规则不得同时传入空 `prefix_list_id` 或 `source_group_id`，否则 CloudControl 会把空 PrefixList TRN 纳入 IAM 鉴权并越出项目边界。
- 安全组及规则描述只使用火山引擎允许的中英文、数字、空格、逗号、句号、下划线、等号和连字符；禁止分号等未支持标点。
- 自定义安全组创建时平台会自动加入允许 `0.0.0.0/0`、ALL 协议/端口的默认出站规则；Terraform 不得重复声明同一规则，否则 CloudControl 以 `InvalidSecurityRule.Conflict` 拒绝。出站收敛继续由主机 denylist 与隔离复验负责。
- RDS 只绑定 staging ECS 安全组，无公网地址；`AssociateEcsIp` 绑定不得配置 `ip_list`，且 AllowList 必须等 ECS 主网卡加入该安全组后才能创建。`volcenginecc` 0.0.57 会在更新既有 `SetNestedAttribute` 时把 computed `IpList` 序列化为空值，因此该嵌套绑定仅在创建时配置，后续由精确 `ignore_changes = [security_group_bind_infos]` 保持不可变；安全组本身继续由 Terraform 管理。既有 AllowList 是否已导入 ECS 私网 IP 必须从控制面只读核验，不能由 Terraform 依赖关系倒推。`journey_next_migrator` 拥有 schema，`journey_next_runtime` 禁止 DDL，只获 DML/sequence 权限；强制 TLS。
- 若只读 audit 返回 `RDS security-group IP list is missing`，停止 deploy；只允许在当轮精确授权后对同一 AllowList 执行一次控制台“同步安全组”，不得新建/删除 AllowList、手工扩大 CIDR、改安全组或运行 provision。同步后先运行 `phase=audit`，只有 `allowlist_match=true`、`instance_association=true`、`vpc_match=true`、`allowlist_latest=true` 全部通过，才可另行申请新的 deploy 授权。
- RDS SSL 启用与 DBAccount 更新都会让实例进入独占操作状态，Terraform 必须显式串行这些资源，禁止并发提交；若平台返回 `instance is in exclusive status`，保留 partial state 并停止，不能自动重试。
- DNS API 返回 `AlreadyExists` 时，先只读核验记录内容与归属，再把唯一目标记录精确 import 到同一 remote state；禁止先删记录、扩大 DNS 权限或用第二条部署路径绕过。
- DNS 精确纳管固定使用项目限定的 `dns:ListRecords` 读取现有子区：同时匹配 `@`、A、默认线路、TTL 600、已启用、`vNext staging` 备注和当前 ECS EIP，必须且只能得到一个 RecordID。RecordID 先加入 Actions mask，只用于同一 workflow 的 `terraform import`；不得写入 Git、artifact、公开证据或新增 Environment secret。已有 state 地址则必须核对完整 import identity，不允许覆盖或重绑。
- TOS bucket 私有、版本化、默认 SSE-TOS AES-256；WP-08 只创建物理隔离资源，应用接入、presign 与扫描属于 WP-10。
- WP-08 基线曾以 `APP_ENV=staging` + `NOTIFICATION_ADAPTER=DISABLED` 运行并上报 heartbeat。WP-11 合入后，部署包要求独立通知 App、32-byte 接收人加密密钥、`NOTIFICATION_ADAPTER=FEISHU` 与 canonical result URL；缺任一 secret、复用身份 App 或 API/Worker 密钥不一致均在部署前 fail closed。`LOCAL_TEST` 在 staging 始终启动失败；未经精确授权不得执行真实发送。
- staging secret 的权威存储是 GitHub `staging` Environment；部署时经单次 SSH 加密通道落盘，密码和环境文件为 `0600`。RDS CA 是公开信任证书，以容器只读 `0444` 落盘，且必须在 migration 前由 UID 10001 的 API 容器成功读取；所有内容均不进入 Git、Actions artifact、Terraform CLI 参数或日志。Terraform 加密 TOS state 会保存 RDS account 的敏感属性，因此 state bucket 必须私有、版本化、仅 CI 子用户可读。
- ECS 创建所需的 bootstrap password 由 Terraform `random_password` 一次生成，仅保存在上述私有、版本化、SSE 加密的 remote state，并且不声明 output、不进入 GitHub secret、Actions 日志或 cloud-init。实例用它满足创建 API 的必填凭据合同；cloud-init 写入 staging-only deploy 公钥后立即将 SSH 收敛为 key-only。密码遗失不恢复、不用于日常登录，实例替换时生成新的随机值。

## 3. 一次性主账号 Bootstrap

Bootstrap 必须由主账号 Owner 在火山引擎控制台完成，不能使用旧系统子用户：

1. 创建资源项目 `journey-next-staging`；
2. 创建私有、版本化、SSE 加密的 TOS state bucket，名称使用 `journey-next-staging-tfstate-<random>`；
3. 创建无控制台登录能力的 IAM 子用户 `journey-next-staging-ci`；全局 CloudControl 自定义策略只允许 CreateResource/GetResource/UpdateResource/DeleteResource/GetTask 五项生命周期动作，不得使用 `CloudControlFullAccess`；RDS PostgreSQL AllowList 因资源创建前没有可用项目属性，额外使用全局自定义策略 `journey-next-staging-rdspg-allowlist-cn-beijing`，正文只允许 Create/Associate/DescribeDetail/Upgrade/Delete/Disassociate/Describe/Modify 八项 AllowList 动作，并以 `volc:RequestedRegion=cn-beijing` 限定地域；RDS SSL 两项与 EBS Describe 一项同样使用华北2最小自定义策略；DNS/ECS/RDS/VPC/TOS 服务权限只授权 `journey-next-staging` 项目及 state bucket 必需读写。CloudControl 创建 DNS Record 时会额外以 `project/*` 调用只读 `dns:QueryRecord`，因此只允许为 CI 身份增加这一项无项目限制的全局只读动作，不得增加其他全局 DNS 动作；不授予 `TagFullAccess`、旧项目或 IAM 管理权限；
4. 创建一次 AK/SK，并直接写入 GitHub repo 的 `staging` Environment secrets `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY`；不得复制到聊天、shell history、文档或本地 `.env`；
5. 创建 `staging-vnext.muchenai.com` 独立 DNS 子区，将控制台分配的 NS 记录委派到 `muchenai.com`，并把该子区转入 `journey-next-staging` 项目；把子区 ID 写入 Environment secret `WP08_DNS_ZONE_ID`；
6. 创建 staging-only Ed25519 deploy key；私钥/公钥分别写入 `WP08_DEPLOY_SSH_PRIVATE_KEY` / `WP08_DEPLOY_SSH_PUBLIC_KEY`。Terraform 通过 ECS cloud-init 把公钥写入实例，不创建账号级 ECS KeyPair，避免为 KeyPair 的创建后读取扩大 ECS 全局权限；
7. 建立费用预算 ¥800/月并设置 50%、80%、100% 告警。预算告警不是强制停机，Terraform 的报价门禁仍必须执行。

GitHub `staging` Environment 还需设置：

- Secrets：`WP08_TF_STATE_BUCKET`、`WP08_DNS_ZONE_ID`、`WP08_TOS_BUCKET_NAME`、两项 deploy key、两项 RDS password、`WP08_SESSION_SECRET`、`WP08_INVITE_SECRET`、`WP08_IMPORT_SIGNING_KEY`、`WP08_RDS_CA_PEM_B64`、`WP08_ACME_EMAIL`；
- Variables：`WP08_PRIMARY_ZONE_ID`、`WP08_SECONDARY_ZONE_ID`、`WP08_ECS_IMAGE_ID`、`WP08_ECS_INSTANCE_TYPE`。

密码/secret 均须由密码管理器独立生成。RDS password 为 20–32 字符且满足火山引擎复杂度；三个应用 secret 至少 32 字符且互不相同。

## 4. 报价与 Apply 前置

使用火山引擎价格计算器，在 `cn-beijing` 对同一组库存可用规格逐项记录 ECS 计算、系统盘、EIP 流量、RDS 两节点与 20 GiB、TOS、快照/备份和 DNS/TLS的月估算。将总额写入 `config/wp08_staging.json`；不得以促销首月价或未含流量/备份的数字通过门禁。

执行：

```bash
make wp08-staging-readiness
make wp08-staging-apply-check
```

唯一 Terraform 写路径执行 fail-closed 顺序：生成 saved plan → `terraform show -json` 直接管道到 `scripts/wp08_plan_guard.py` → 仅在没有任何 `delete` action 时 apply 同一个 saved plan。`delete/create` 与 `create/delete` 都视为 replacement 并拒绝；不得把 plan JSON 保存为 artifact、提交到 Git 或打印其中的敏感值。ECS 另有 `prevent_destroy`，不得为了通过计划而关闭。deploy 的 SSH 开关不再经过 Terraform/CloudControl；`scripts/wp08_security_group.py` 只允许一个公网 IPv4 `/32`，请求不得包含 `PrefixListId` 或 `SourceGroupId`，并在每次开关后只读确认精确规则数量。

当前 workflow/config 原子绑定 Content Editor 无会话重新进入候选 `3b7d757…`、Mainline run `31259643008`、API `sha256:009be6c7…b9a`、Web `sha256:b8073419…2e5`、Worker `sha256:9796479e…323`、artifact name 和唯一确认词；绑定只描述部署合同，不授予部署。最近一次成功部署证据仍是 run `31147474464` 的 `2223fc1…`。真人输入与签署仍须真实完成，任何前置门禁失败都停止后续步骤。workflow 必须从 Git 历史核验候选源码本身包含 readiness、Compose 探针、`/ops`/`/review` 匿名 401、`/content` 匿名 303 同源登录恢复、请求 CSP nonce 传播、动态渲染、root-relative OAuth redirect、OAuth callback 安全入口与 cookie 响应转发、真实 standalone 失效会话响应测试、WP-11 通知/可观测接线合同、WP-12B 合成多租户工具，以及 API `20+5`/Worker `2+1` 连接池环境：

1. 仅在基础设施确有审查过的变更时运行 `phase=provision`；现有 Alpha 资源已冻结，不得为候选升级重复 provision；
2. 复验 GitHub staging Environment 中的 `WP08_RDS_CA_PEM_B64` 仍对应现有 RDS；只有实例或 CA 发生受审轮换时才重新下载，不从旧服务器复制；
3. 所有历史确认词均不得复用；本候选只接受 `DEPLOY_3B7D757_TO_VOLCENGINE_STAGING`。绑定 PR 合入且 required check 通过仍不等于部署授权；只有 Owner 再明确授权完整候选 `3b7d7573cd70b72868e427b523ff630b732f0603` 和绑定 PR 的合入后主线 SHA，才能消费一次冻结基础设施 staging 部署，失败不重试。任何前置状态漂移必须零业务写入停止，不得退化为 provision、Web-only、runtime-repair 或修改期望基线。

这条 workflow 仍是唯一写入口；两阶段不改变候选、预算或环境授权边界，本地个人机器不执行 `terraform apply` 或直连部署。

WP-09 首个 Operator 绑定链接已由 run `30181942549` 成功生成并消费；`.github/workflows/wp09-operator-bootstrap.yml` 只保留为该次受控流程的历史合同。它仍绑定已消费候选 `26d5601…`，而当前 staging 部署合同必须绑定不同的新候选，因此执行前的 candidate/config 等值检查必然 fail closed。机器门禁明确拒绝把当前候选回退为 bootstrap 候选，禁止为新候选更新该 workflow 或重复生成“首个 Operator”链接。后续 Reviewer/Operator 链接只能由已绑定 Operator 在 `/ops` 的受权 UI 中生成。

## 5. 部署顺序与证据

Workflow 顺序固定：provision 阶段执行合同检查 → TOS remote state init → Terraform validate → DNS 只读精确匹配与 state import/identity 核对 → Terraform saved plan → 破坏性门禁 → 关闭态 apply；Alpha deploy 阶段执行候选源码 Web 合同检查 → remote state 仅读取既有输出 → VPC API 临时 runner `/32` → 私有 bundle → GHCR digest pull → UID 10001 容器读取 CA → migration → runtime grant → PII-free seed → API/Worker → Web `/health/ready` → edge/TLS → 匿名 `/ops = 401` → VPC API 撤销精确 SSH 规则。

三镜像必须使用 WP-07 已核验 digest，不能只用 tag。公开证据只记录 GitHub run ID、候选 SHA、门禁结果和非敏感资源类别；账号 ID、IP、DNS zone ID、RDS/TOS endpoint、SSH fingerprint、ACL 明细和截图只进入 `evidence/private/wp08` 或 90 天受控外部证据。

服务端部署步骤成功后必须立即运行真实 staging browser smoke；公开 `/` 承担三档视口、hydration、console、overflow 与键盘焦点检查，受保护 `/ops` 单独断言匿名 401，不能用 401 JSON 页面代替 UI 验证。主任务还要复验 Web/API/Worker revision、migration head、fixture/LOCAL_TEST fail-closed、旧凭证拒绝、旧私网不可路由、RDS/TOS/secret ACL 和空库合成路径。全部通过前退出词仍不是 `STAGING_ISOLATION_VERIFIED`。

## 6. 回滚与停止

- 应用失败：`deploy.sh` 尝试重新启动 `PREVIOUS_RELEASE`；不回滚已接受业务事实，不自动 downgrade migration。
- Terraform plan/apply 失败：保留 state 和不含敏感值的精确错误引用；此时尚未添加临时 SSH 规则。VPC API、bundle、部署或验证失败时，`always()` 必须撤销并确认当前 runner `/32`；不得无审查重复。plan 出现任何 destroy/replacement 时必须在 apply 前停止，并由独立 PR 修复 drift 或重新取得破坏性操作授权；不得关闭 ECS deletion protection/`prevent_destroy` 绕过。
- CloudControl 长耗时 state refresh 若仅以精确 `InvalidTimestamp: The Signature of the request is expired` 失败，workflow 只允许重新签名并重跑一次只读 `terraform plan`；`apply` 不自动重试，其他错误继续 fail closed。
- 预算预测或实际成本超过 ¥800、候选/digest 不一致、CA/域名/ACL 不合格、旧资源引用出现：立即 `STOPPED / NO DEPLOY`。
- 首次部署无 previous release；失败时停止新容器，保留 RDS/TOS 供诊断。删除付费资源属于单独破坏性操作，需用户再次明确授权并先保留必要证据。
- run `30808632624` 的 pre-start 失败目录仅可由 `phase=cleanup-failed-release` 处理，确认词固定为 `CLEANUP_FAILED_RELEASE_EF0A512_30808632624`。脚本必须同时证明候选/run 精确匹配、目录不是符号链接、`current`/`PREVIOUS_RELEASE`/`DEPLOYED_CANDIDATE` 均未引用、没有任何 Docker 容器以该目录为 Compose working directory，且目录内容与审查过的 bundle 完全一致；随后先安全擦除 release-local 环境文件，再删除该精确目录。该 phase 不运行 Compose、migration、seed、Terraform、DNS、消息或业务写入，并始终关闭临时 SSH。
