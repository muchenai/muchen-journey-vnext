# WP-08 火山引擎独立 Staging 运维手册

状态：`RUNTIME_REPAIRED / WEB_222096D_API_WORKER_02863D0 / WP12B_FAIL_NO_RETRY / HUMAN_UAT_READY / PRODUCTION_NO_GO`。本文仍是 Greenfield vNext 唯一 staging 资源与部署入口；不复用旧 P1 脚本，不授权 production。Provision 已收敛并冻结。主线 `100e89494b8c42a6b04a86f5bdc26c06ab690fa7` 的唯一 repair run `30616573615` 已成功：Web=`222096db…`，API/Worker/heartbeat=`02863d0…`，migration=`0014_wp12_data_lifecycle`、schema=3、API ready、Worker 非 stale；root=200、匿名 `/ops`/`/review`=401，SSH 已关闭。Terraform、DNS、云资源、seed、消息与 WP-12B 未执行。技术 UAT 入口已恢复，真人场景与签署仍未完成。

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
- 当前运行中性能修复候选：`02863d0b670ee9b00b9def3e75bc6699827f555a`；PR #90、Mainline Candidate Gate `30511897160` 和唯一 deploy run `30519669770` 均成功；唯一 WP-12B run `30525165474` 完成 20 组织/500 Learner/10,561 请求，隔离、事实审计、560 会话/用户退役、证据上传和 SSH 关闭均 PASS，但 submission/finalize p95=`1.012/1.097s` 超过原 1 秒预算。该候选不得再次部署或重跑 WP-12B；DEC-020 仅允许其按 ≤1.2 秒边界启动 WP-13，不能视为 WP-12B 或 production 性能门禁通过；
- Web 邀请入口修复候选：`222096db506e95db887a8705b22ca4a439d0545d`；Mainline Candidate Gate `30550010916` 已完成完整 CI、候选工件、三镜像 GHCR push 与 digest 验证。full deploy run `30556851235` 超时取消后形成 Web 新、API/Worker 旧的混合状态，未被接受为部署成功。`config/wp08_web_only.json` 现建立有界 Web-only 合同：只允许候选单提交中的 Web/指定证据路径；API、Worker、migration 与 OpenAPI 必须和基线 `02863d0…` 完全兼容；运行时必须先证明 API/Worker=`02863d0…`、migration=`0014_wp12_data_lifecycle`、config schema=3、Worker 非 stale，否则在 Web 写入前停止；
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
- `phase=inspect-runtime` 是修复前的 PII-free 只读盘点。它从冻结 state 仅读取 ECS 地址与安全组，临时开放当前 runner 的单一 SSH `/32`，在现有容器内只读取 Web/API/Worker release、API readiness release、Alembic revision、config schema 与 Worker heartbeat release/freshness，随后无条件关闭该规则。日志不得包含账号、IP、数据库连接、身份、业务事实或消息内容；禁止镜像拉取、Compose 变更、migration、grant、seed、Terraform plan/apply/import、DNS、消息和 WP-12B。
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

当前 workflow/config 将原子绑定 Web 邀请入口修复候选 `222096d…`、Mainline run `30550010916`、三个 registry digest、artifact name 和唯一确认词；绑定只描述部署合同，不授权 dispatch。workflow 必须从 Git 历史核验候选源码本身包含 readiness、Compose 探针、`/ops`/`/review` 匿名拒绝、请求 CSP nonce 传播、动态渲染、root-relative OAuth redirect、真实 standalone 失效会话响应测试、WP-11 通知/可观测接线合同、WP-12B 合成多租户工具，以及 API `20+5`/Worker `2+1` 连接池环境：

1. 仅在基础设施确有审查过的变更时运行 `phase=provision`；现有 Alpha 资源已冻结，不得为候选升级重复 provision；
2. 复验 GitHub staging Environment 中的 `WP08_RDS_CA_PEM_B64` 仍对应现有 RDS；只有实例或 CA 发生受审轮换时才重新下载，不从旧服务器复制；
3. 历史确认词 `DEPLOY_2AB2658_TO_VOLCENGINE_STAGING`、`DEPLOY_172C9F6_TO_VOLCENGINE_STAGING`、`DEPLOY_9E1CDB2_TO_VOLCENGINE_STAGING`、`DEPLOY_674E51D_TO_VOLCENGINE_STAGING`、`DEPLOY_02863D0_TO_VOLCENGINE_STAGING` 与已消费的 `DEPLOY_222096D_TO_VOLCENGINE_STAGING` 均不得复用。Web-only 合同使用 `DEPLOY_WEB_222096D_ON_02863D0_STAGING`；当前混合状态的恢复合同使用 `REPAIR_RUNTIME_02863D0_FOR_WEB_222096D_STAGING`。两段文本均不构成 dispatch 授权；只有合同 PR 合入、当轮精确主线与一次性授权齐备时才可执行对应 phase。任何前置状态漂移必须零业务写入停止，不得退化为 full deploy 或修改期望基线。

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
