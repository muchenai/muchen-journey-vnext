# 26｜WP-08 火山引擎 Staging 实施路径证据

日期：2026-07-27
状态：`STAGING_ISOLATION_VERIFIED / PHYSICAL_ACL_EVIDENCE_CLOSED`
当前候选：`14c9ba073c293da1d4c6b615ea1f07c6c50688fa`
已消费候选：`d407b5f4a32fd68b1a8b08ac5a461aa04aa29fff`（唯一 deploy 失败，禁止重试）；`dad44cc679184a1978b0f69e3632cb95de7f1b8e`（唯一 deploy 已落地但浏览器复验失败，禁止重试）；`14c9ba073c293da1d4c6b615ea1f07c6c50688fa`（唯一 deploy 成功，授权已消费）
历史候选：`670661865f708a835997596ed5b74904809564a5`（已退役）
整体发布：`NO_GO`

## 已关闭

- 用户明确锁定火山引擎、华北2（北京）/`cn-beijing`、按量计费、¥800/月和上述完整候选；
- 独立资源命名、子域、VPC/SG/ECS/RDS/TOS、migration/runtime role、GitHub Environment secret、remote state、CI-only deploy 和回滚边界已形成仓库唯一受审路径；
- Terraform 使用官方推荐的 `volcengine/volcenginecc` 0.0.57，而非已停止维护的旧 provider；
- `wp08_staging.py` 将 provider/region/budget/candidate/origin 和同日报价设为 fail-closed 合同；
- staging Worker 使用显式 `DISABLED` adapter，只跳过 notification event，保留真实进程/heartbeat，且 production/LOCAL_TEST 继续拒绝；
- 候选三镜像部署引用固定为 WP-07 已核验 GHCR digest；Caddy 镜像固定 digest；
- deploy bundle 的密码与环境文件为 `0600`，私有目录为 `0700`；公开 CA 信任证书为容器只读所需的 `0444`，旧域名/旧部署标识和 `LOCAL_TEST` 被拒绝。

## 当前事实（2026-07-25）

- 独立 staging 项目中的部分 IAM、VPC、安全组、ECS、RDS/TOS 与 DNS 资源已由唯一受审 workflow 创建或纳管；资源和 remote state 的逐项事实以私有证据为准，公开仓库不记录账号、资源 ID、endpoint、IP、凭据或人员信息；
- 第二次 provision run `29945430858` 在无 destroy/replacement 的门禁通过后停止；RDS AllowList 与 DNS 查询权限的代码侧修复已由 PR #17 合并到主线 `1791ea6d89a290cf4ff41e5c4a9e27fb64d7213c`，required check 通过；
- 用户明确授权后已创建并附加全局只读策略 `journey-next-staging-dns-query-record-global`：正文仅允许 `dns:QueryRecord`，资源范围为 `*`，只附加给 `journey-next-staging-ci`，不受项目限制；授权页已反向核验。原 DNS/ECS/RDS/VPC/TOS 服务权限继续限定 `journey-next-staging`，本次未修改其他策略；
- 第三次 provision run `29974201816` 失败后没有自动重试；DNS state 精确纳管与 RDS 串行修复已由 PR #20 通过 required check 并合入主线 `af6443d9f4d3b25513c840557c9755e78758e092`，没有扩大 IAM；
- 本轮唯一新 provision run `29994013611` 已成功：DNS 精确 import、`0 add / 4 change / 0 destroy` saved plan、无破坏性门禁和 apply 均通过；应用部署步骤按 phase 正确跳过；
- 新实例 RDS CA 已取得并写入 GitHub `staging` Environment；Alpha deploy 已移除 DNS/provider/plan/apply 耦合。run `30062128087` 使用已修复路径通过冻结 state、精确 runner `/32`、私有 bundle、release-local secret 与 Compose 校验，但 ECS 访问 Docker Hub 拉取固定 Caddy digest 时以网络超时停止；全镜像 pull 位于 migration 前，因此未观察到 migration、seed 或容器启动。TLS/browser smoke 被跳过，SSH 已确认关闭且未重试；真实身份和真人 UAT 仍为 `NOT_RUN`，整体发布为 `NO_GO`。
- mirror run `30063385826` 已将固定 Caddy 2.10.2 源 digest 复制到项目 GHCR；PR #31 把 Compose 固定到验证后的项目 digest。唯一后续 deploy run `30063847635` 已成功拉取四个 GHCR 镜像，但 Alembic 首次连接 RDS 时超时；migration 未开始，runtime grant、seed、应用、TLS 与浏览器 smoke 均未运行，SSH 已关闭且没有重试。
- PR #33 已修复 Terraform 创建图，使 RDS AllowList 必须等待 ECS 主网卡加入目标安全组；该修复只防止新环境复发，不能倒推既有 AllowList 已同步。PR #34 在唯一 staging workflow 增加脱敏 `phase=audit`，PR #35 修复其 runner 模块入口；两者均通过 required check 和主线门禁。
- 首次 audit run `30066549563` 在任何火山引擎 API 调用前因 Python 模块入口不可解析而停止，没有产生云状态证据或外部写入。修复后的只读 run `30066942906` 成功读取冻结 remote state 并调用北京地域 `DescribeAllowListDetail`：目标 AllowList ID 和 `AssociateEcsIp` 安全组绑定均匹配，但其有效 `IpList` 缺失，因此 fail closed。run 未执行 provider refresh、plan、apply、import、SSH 规则变更、数据库连接或部署，也未输出 IP、资源 ID 或 secret。
- 该缺口与 AllowList 先于 ECS 成员创建的历史竞态一致，并能解释 migration 连接超时；但同步后的数据库/TLS/应用结果当时仍未知。当时唯一下一动作是对现有 AllowList 执行一次原生“同步安全组”，范围只刷新当前绑定的 ECS 主网卡 IP；该云端写入必须取得当轮精确授权。同步后先重跑只读 audit，不直接部署。
- 用户精确授权后，主任务已在华北2（北京）对同一 AllowList 执行一次控制台“同步安全组”。控制台差异只把当前安全组关联 ECS 的主网卡 IP 纳入既有绑定，没有新增/删除 AllowList、实例、安全组或网络规则；同步后的只读详情已显示相同安全组、相同 `AssociateEcsIp` 模式和非空派生 IP。
- 随后唯一只读 audit run `30067829879` 读取同一冻结 state；AllowList、安全组绑定、派生 IP、实例关联和 VPC 均已匹配，但 `AssociatedInstances[].IsLatest=false`，因此仍 fail closed。DNS、Terraform apply、SSH、数据库与 deploy 全部跳过，没有重试。火山引擎把“同步安全组”定义为取得最新安全组 IP，并用 `IsLatest` 表示最新白名单是否已同步到实例；这说明 IP 缺口已关闭，但实例侧传播尚未被证实，不能据此部署。
- 现有 audit 只在控制台确认后的数秒内读取一次详情，不能区分异步传播窗口和持续失败。后续实现保留 `IsLatest=true` 硬门禁，同时在**同一次只读 audit** 内最多轮询 60 秒；任一结构、身份、IP、VPC 不一致立即失败，只有单独的 `IsLatest=false` 可等待，窗口耗尽仍失败。该修复不调用同步 API、不改变云资源，也不构成新的 audit 或 deploy 授权。官方参考：[同步安全组](https://docs.volcengine.com/docs/6438/1742797?lang=zh)、[DescribeAllowListDetail](https://docs.volcengine.com/docs/6438/1257389?lang=zh)。
- 后续 deploy run `30116863700` 已越过 CA 门禁并建立 RDS TLS 连接，但因 `journey_next_migrator` 当时没有 `public` schema 的 ownership/`CREATE` 权限，在创建 Alembic version table 前停止；精确 schema ownership 修正后，唯一 deploy run [`30117658292`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30117658292) 已成功执行 `0001` 至 `0010` migration、runtime grant 与 seed，API 达到 healthy，SSH `/32` 已关闭。
- run `30117658292` 的 Web 容器把需要身份的 `/ops` 当作 Compose healthcheck；staging 正确关闭 fixture identity 后，匿名探针被拒绝，Web 因而持续 unhealthy，edge/TLS 未启动。这是健康合同错误，不是数据库、网络或授权错误。首次部署没有 previous release 时，旧 rollback trap 也没有停止本轮已创建容器。
- 修复新增不访问 API/数据库、返回当前 `APP_RELEASE` 且 `no-store` 的 `/health/ready`；Compose 与外部验证改用该路由，匿名 `/ops` 明确要求 HTTP 401；首次失败执行 `docker compose down --remove-orphans`，不删除卷。deploy 另从 Git 历史核验候选源码本身包含 readiness、Compose 探针和 `/ops` 拒绝合同，防止新发布脚本与旧 Web 镜像混合发布。
- PR #39 已通过 required check 并合入受保护主线 `d407b5f4a32fd68b1a8b08ac5a461aa04aa29fff`。Mainline Candidate Gate [`30120441674`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30120441674) 完成完整 CI、候选打包、三镜像 SBOM、GHCR push 与远端 digest 验证；canonical artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`。
- 新候选固定摘要为 API `sha256:b51fc66a…368ab`、Web `sha256:c6b26024…7f631`、Worker `sha256:979cbfa5…2b75a`。机器合同、Terraform candidate、deploy preflight、bundle、workflow artifact run/name 与确认词同步绑定；旧候选 `670661…` 不能再进入 deploy。
- 本轮用户授权范围是生成候选、镜像摘要和候选绑定 PR，不包含 staging deploy。绑定 PR 合入前不得 dispatch；合入后仍需一次新的、指名完整候选与 `phase=deploy` 的明确授权。staging TLS、真实身份与真人 Alpha UAT 继续为 `NOT_RUN`，整体发布保持 `NO_GO`。

## 2026-07-25 14c9ba0 候选成功部署与运行面复验

- 用户精确授权候选 `14c9ba073c293da1d4c6b615ea1f07c6c50688fa` 基于主线 `73cf07f2ec6849036611cd2ba75772b7f94da5de`，在华北2（北京）冻结基础设施上只执行一次 `phase=deploy`。唯一 run [`30161121353`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30161121353) 成功，没有重试；
- 候选/artifact/四镜像固定摘要、冻结 state、精确 runner `/32`、私有 bundle、RDS TLS migration、runtime grant、PII-free seed、API/Web/Worker/Edge 健康、外部 TLS/readiness、匿名 `/ops = 401` 全部通过；`always()` 输出 `WP08_SSH_INGRESS=CLOSED`；
- 真实 Chromium 随后在 1440/768/390 三档视口复验公开根页：无 console error/warning、无水平 overflow、hydration 与键盘焦点正常；受保护 `/ops` 匿名访问仍为 401，readiness 返回精确 release 且 `no-store`；
- 部署证明 Alpha staging 运行面及 ECS→RDS 实际 TLS 路径可用。但随后唯一只读 audit run [`30162196135`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30162196135) 在 AllowList 结构、精确安全组/IP、实例和 VPC 均匹配后，因 API 响应未返回可用的 `IsLatest` 字段而 fail closed；该 run 没有部署或云写入，不重试；
- 本记录不把缺失字段篡改为 `true`，也不把它误判为已证实的网络故障。当前决策是停止继续修补 provider/audit 路径，将其作为正式发布前必须关闭的物理 ACL 证据债；阶段结论为 `ALPHA_STAGING_RUNTIME_VERIFIED / PHYSICAL_ACL_EVIDENCE_OPEN`，不是 `STAGING_ISOLATION_VERIFIED`，整体发布继续 `NO_GO`。

## 2026-07-27 物理 ACL 人工复验与证据关闭

- 用户在华北2（北京）的 RDS PostgreSQL 控制台打开现有应用 AllowList 详情并提供截图证据 `PEV-WP08-20260727-ACL-CONSOLE`；本仓库不保存截图，不记录其中的 IP、资源 ID 或 endpoint；
- 控制台显示该 AllowList 不是默认白名单，当前全部地址恰好由一个已绑定安全组派生；绑定模式为关联 ECS IP，AllowList 地址与该安全组派生地址一致且非空；
- 同一详情页只显示预期的 staging PostgreSQL 实例，并显示其位于预期 staging VPC。此前只读 audit 已用冻结 state 核对同一安全组、实例和 VPC，成功 deploy 又证明 ECS→RDS 的真实 TLS 数据面路径可用；
- 控制台不展示 `IsLatest`，API 在后续响应中也不再返回可用字段。本次不把缺失字段伪造为 `true`，而是以“控制台当前派生事实 + 冻结 state 身份核对 + 成功 TLS 数据面连接”的组合证据替代不可取得的供应商内部标志；
- 本轮只读查看，没有刷新、编辑、同步安全组、绑定/解绑实例、修改 IP 或部署。物理 ACL 证据债据此关闭，WP-08 退出结论升级为 `STAGING_ISOLATION_VERIFIED`；其他真人、文件、通知、灾备和发布门禁仍保持原状态，整体发布继续 `NO_GO`。

## 2026-07-22 路径设计时未发生（历史快照）

- 火山引擎控制台已登录并只执行只读报价核验；未创建 IAM、VPC、安全组、ECS、RDS、TOS、DNS、证书或预算；
- 同日总报价已写入机器合同，但新的候选绑定变更仍须通过 PR 与受保护主线后才能 dispatch；
- GitHub `staging` Environment 的火山引擎身份与 vNext secrets 尚未配置；
- 没有运行 migration、seed、TLS、browser smoke、旧凭证拒绝或物理 ACL 审计；
- candidate manifest 的 deployment 仍须保持 `NOT_RUN`。

因此该状态不代表 physical staging、发布 GO 或 WP-08 关闭。首次报价触发的停止事实保持不变；后续预算重授权作为新的执行尝试单独记录。

## 2026-07-22 首次物理 Provision 与最小权限复盘

- GitHub staging run `29929929570` 使用完整候选和已批准确认词执行 `phase=provision`；候选合同、远端加密 state 初始化均通过，并创建了首批项目隔离资源；未运行 migration、seed、应用部署或外部 TLS 验证；
- 原先项目作用域的 `CloudControlFullAccess` 被 CloudControl API 拒绝。按用户明确授权，仅将该控制面策略改为全局；DNS/ECS/RDS PostgreSQL/Tag/VPC/TOS 六项服务策略逐项复核后仍限定 `journey-next-staging`；
- 重试 run `29929929570` 已越过 CloudControl 403，但在安全组创建冲突以及 ECS KeyPair 创建后的 `DescribeKeyPairs` 项目权限检查处停止；该 run 不得原样重试；
- 为保持 ECS 最小权限，不把 `ECSFullAccess` 扩大为全局。部署公钥改由 ECS cloud-init 写入 root `authorized_keys`，取消账号级 ECS KeyPair 资源；安全组、ECS、RDS、TOS 和 DNS 仍显式绑定 staging 项目或 staging 子区；
- 失败 run 产生的 Terraform partial state 和可能的孤立 KeyPair/安全组必须在下一次 apply 前完成精确核对；不得删除付费资源或扩大权限来绕过收敛。
- PR #8 合并后，run `29931062181` 已确认 KeyPair 全局读取不再出现；安全组创建仍因规则显式传入空 `prefix_list_id` 而把空 PrefixList TRN 纳入 `vpc:AuthorizeSecurityGroupIngress` 鉴权并停止。修复只删除未使用的空来源选择器，不扩大 `VPCFullAccess` 项目范围。
- PR #9 合并后，run `29931436619` 已越过 KeyPair 与安全组 IAM 鉴权；长耗时 refresh 最终仅在 TOS encryption `GetResource` 处返回 `InvalidTimestamp`。官方 provider 0.0.59 未包含该路径修复，因此 workflow 只为该精确错误增加一次只读 plan 重签重试；apply 与其他错误不重试。
- PR #10 合并后，run `29933251955` 的 plan 与 TOS refresh 正常完成，apply 在安全组出站规则描述的分号处以 `InvalidDescription.Malformed` 停止；修复仅把未支持的分号替换为允许的逗号。
- PR #11 合并后，run `29933635861` 确认描述已通过，但平台自动创建的默认全放行出站规则与 Terraform 重复声明冲突；根据火山引擎 VPC 官方行为，删除重复 IaC 出站项，不改变实际出站策略。
- PR #12 合并后，run `29934422323` 已创建并纳管 staging 安全组，随后在两个独立边界停止：RDS PostgreSQL AllowList 没有项目属性，因此项目限定的 `RDSPGFullAccess` 无法授权其创建；ECS 创建 API 同时缺少 Password 和 KeyPair。该 run 未创建 ECS、RDS，未执行 migration、seed 或应用部署，不得原样重试。
- 用户明确授权后，新建全局自定义策略 `journey-next-staging-rdspg-allowlist-cn-beijing`：仅含 RDS PostgreSQL AllowList 的 Create/Associate/DescribeDetail/Upgrade/Delete/Disassociate/Describe/Modify 八项动作，并以 `volc:RequestedRegion=cn-beijing` 限定地域。授权后反向核验其项目限制为“无”，原 `RDSPGFullAccess` 仍限定 `journey-next-staging`，未扩大其他 RDS 权限。
- ECS 不恢复账号级 KeyPair，也不扩大 `ECSFullAccess`。Terraform 改为一次生成 30 位 bootstrap password，仅保存在私有、版本化、SSE 加密的 TOS remote state且不输出；cloud-init 写入 deploy 公钥后关闭 SSH password、keyboard-interactive 和 challenge-response 登录，root 仅允许公钥登录。

## 2026-07-22 预算门禁

- 火山引擎官方价格计算器核验：华北2（北京）、按量计费、共享型 ECS `ecs.e-c1m2.large`（2C4G）、Linux、40 GiB PL0、EIP 按流量计费，按 720 小时估算为 ¥177.26/月；
- 火山引擎 PostgreSQL 创建页核验：当前最小高可用配置为 1C2G 主节点 + 1C2G 备节点，配置费用 ¥0.75/小时，即 ¥540/月；
- 两项小计已达 ¥717.26/月，尚未计入 TOS、备份和实际公网出流量，比授权上限 ¥500 高 ¥217.26；
- `approved_monthly_estimate_cny` 继续保持 `null`，`make wp08-staging-apply-check` 必须失败；
- 私有截图和失败记录引用：`PEV-WP08-20260722-BUDGET_GATE`。不含账号 ID、资源 ID、endpoint、凭据或 PII。

预算门禁触发后，本次执行状态为 `STOPPED / NO DEPLOY`。未创建 IAM、项目、VPC、安全组、ECS、RDS、TOS、DNS、证书或预算；未配置云凭据，未 dispatch staging workflow，WP-09 不得启动。后续只能由用户开启新的、范围明确的执行尝试：提高预算，或重新批准不使用托管 RDS 的架构变更。

## 2026-07-22 预算重授权与安全候选要求

- 用户将月预算上限提高到 ¥800，并明确保留火山引擎托管 PostgreSQL RDS；Region 与按量计费不变；
- 已核 ECS + RDS 固定基线仍为 ¥717.26/月，低于新上限，理论余量约 ¥82.74；TOS、备份和公网流量属于用量型费用，创建前必须刷新同日总报价并保持在 ¥800 内；
- 用户同时授权把 Next.js 固定到 16.2.11，并通过 npm override 将 sharp 固定到 0.35.3，完成兼容性和安全复验；
- 旧候选 `ff07ce47d20f3f6eb09d633b09292628fbb58e2a` 不再作为实际部署版本。必须等待包含安全修复的新完整候选 SHA、远端 required check 与 GHCR digest 验证后，再更新机器合同并启动物理 staging；
- 在此之前 `approved_monthly_estimate_cny` 保持 `null`，apply 门禁继续 fail closed，云端仍不写入。

本地兼容性与安全复验结果：

- `npm ls next eslint-config-next sharp --all`：Next.js 16.2.11、eslint-config-next 16.2.11、sharp 0.35.3 overridden；
- `npm audit --audit-level=low`：0 vulnerabilities；固定 Python 锁文件审计：No known vulnerabilities found；
- `make web-check`：lint、TypeScript、Next.js 16.2.11 production build 全部通过；
- `make ci-fast` 与 `make ci-main`：96 tests passed，OpenAPI、隔离、gitleaks、迁移、HTTP 权限负向和发布 NO_GO 合同全部通过；
- `make wp08-staging-readiness`：PASS，预算合同已为 ¥800；`make wp08-staging-apply-check` 按设计以“重授权后须刷新同日总报价”失败，不构成部署失败。

远端 required check 证据：PR #5 在包含依赖修复的提交 `43973cbcf9953b893cdee58ec1d5bcf9f70a5155` 上运行 [GitHub Actions 29888061258](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29888061258)，`WP-07 / quick` 于 1m57s 内通过。

## 2026-07-22 新候选授权与同日报价刷新

- PR #5 已合并到受保护主线，候选完整 SHA 为 `670661865f708a835997596ed5b74904809564a5`；[Mainline Candidate Gate 29888300206](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29888300206) 于 4m23s 内通过，三镜像 registry digest 均为 `VERIFIED`；
- 用户在当前对话明确授权该候选在火山引擎华北2（北京）、按量计费、月上限 ¥800 范围内创建独立 staging 资源并部署；
- RDS 控制台同日刷新：PostgreSQL 17、高可用 1C2G 主备、20 GiB、按量计费为 ¥0.55/小时，即按 720 小时估算 ¥396/月；ECS 既有同日报价为 ¥177.26/月，固定基线 ¥573.26/月；
- 预算模型保守计入单 AZ TOS 20 GiB ¥3/月、EIP 公网出流量 100 GiB ¥80/月；RDS 备份当前 0 折，DNS 子区与 ACME TLS 按 ¥0 计，月预测为 ¥656.26，距上限余 ¥143.74；
- 私有报价证据引用 `PEV-WP08-20260722-QUOTE_REFRESH`，不含凭据、账号 ID、资源 ID、endpoint 或 PII；
- 机器合同、Terraform、deploy bundle、工作流确认词及三镜像 digest 已重新绑定新候选；staging workflow 在门禁前从 run `29888300206` 下载精确候选 artifact，不依赖本地忽略目录。首次创建的新 RDS CA 只能在实例启用 SSL 后下载，因此唯一 workflow 使用 `provision` → 写入新实例 CA → `deploy` 的两阶段输入；两阶段共享同一 state、候选、预算和授权边界，不构成第二条部署路径。物理资源和 deployment 仍为 `NOT_RUN`，须待该绑定变更进入受保护主线后才允许执行。

## 2026-07-23 State 对账与破坏性计划修复

- 资源/state 对账已将既有 ECS 精确导入远端 state；对账 workflow 随后删除，长期入口仍只有 `.github/workflows/staging.yml`。远端 state 当前 serial 为 13，既有 ECS 保持 deletion protection，未被删除；
- IAM 已收敛为全局 CloudControl Create/Get/Update/Delete/GetTask 五项生命周期动作、华北2 RDS AllowList 八项、RDS SSL 两项和 EBS Describe 一项；DNS、ECS、RDS、VPC、TOS 服务权限继续限定 `journey-next-staging` 项目。`CloudControlFullAccess` 与 `TagFullAccess` 已删除，DNS 子区已转入该项目；
- 唯一 provision run `29942799357` 在 apply 前生成 `3 add / 4 change / 1 destroy`。CloudControl import 无法回读 ECS 的 EIP、镜像安全增强、Cloud Assistant、系统盘、bootstrap password 与 user-data 等创建期/write-only 属性，provider 因而错误提出替换；ECS deletion protection 阻止删除。RDS AllowList 同时因 `AssociateEcsIp` 绑定仍显式发送空 `ip_list` 被平台拒绝。TOS 发生一次就地更新，SSL、DNS 和应用部署均未开始；该 run 没有重试；
- 修复仅对官方 provider 标注为 write-only/创建期且实测不可回读的 ECS 属性使用精确 `ignore_changes`，同时增加 Terraform `prevent_destroy`；可回读的实例类型、区域、VPC/子网/安全组、项目、标签和 deletion protection 仍由 Terraform 管理。AllowList 的 `AssociateEcsIp` 绑定改为完全省略 `ip_list`；
- 所有 apply 路径（主基础设施与关闭 SSH）现在都必须先生成 saved plan，再把 `terraform show -json` 直接管道交给 `wp08_plan_guard.py`。任一 action 含 `delete`，包括两种 replacement 顺序，立即 fail closed；plan 值不写日志、不提交也不进入 artifact；
- 本节只代表代码修复与本地机器门禁通过，未授权或执行新的 provision。候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 第二次 Provision 与精确阻塞

- 用户明确授权后仅执行一次 `phase=provision`：run `29945430858`，workflow HEAD `bc76d1d813b193c18f96a4da364732f7af2b0967`，候选仍为 `670661865f708a835997596ed5b74904809564a5`；没有自动重试；
- saved plan 为 `2 add / 5 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`。apply 完成 ECS 与 TOS 的原地收敛后，在两个并行资源处失败：RDS AllowList 把 computed `IpList` 作为空值发送并被 `InvalidAllowListIPList.InvalidIPList` 拒绝；DNS Record 因 CI 缺少 CloudControl 所需的全局只读 `dns:QueryRecord` 而被拒绝；
- DNS 子区、`DNSFullAccess`、ECS、RDS、VPC、TOS 仍限定 `journey-next-staging` 项目。待授权的 IAM 增量必须只有全局 `dns:QueryRecord` 一项，不得扩大为全局 `DNSFullAccess`；
- AllowList 修复把 `security_group_bind_infos` 明确设为创建期不可变嵌套集合，禁止配置 `ip_list`，并由机器检查锁定；安全组资源仍受 Terraform 管理。官方 provider 对 SetNestedAttribute 的已知限制决定了不能通过补齐空字段来更新该绑定；
- deploy 失败清理同步收窄：只要 remote state 初始化成功，`always()` 清理即运行，并只 target staging 安全组；清理 plan 仍须通过无 destroy/replacement 门禁，避免失败路径继续修改其他资源；
- 本轮未执行 migration、seed、应用容器、TLS 或 browser smoke。候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 DNS 最小权限与第三次 Provision

- 用户明确授权创建并附加全局只读策略 `journey-next-staging-dns-query-record-global`。控制台创建结果、策略语法和授权结果已核验：唯一 action 为 `dns:QueryRecord`，resource 为 `*`，只附加 `journey-next-staging-ci`，项目限制为“否”；项目限定的 DNS/ECS/RDS/VPC/TOS 权限均未改动；
- 权限完成后只触发一次 `phase=provision`：run [`29974201816`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29974201816)，workflow HEAD `6dbcb80de9639d3f9adf650c31d549f3e3964e07`，候选仍为 `670661865f708a835997596ed5b74904809564a5`；没有第二次 dispatch 或自动 apply 重试；
- saved plan 为 `2 add / 4 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`，因此不是破坏性计划门禁失败。RDS SSL 在 apply 中成功启用；两个 DBAccount 更新与 SSL 独占操作并发，被平台以 `instance is in exclusive status` 拒绝；
- DNS Record 创建返回 `AlreadyExists`，说明目标记录已经存在但当前 Terraform remote state 未完整收录。后续必须先以只读事实核验并精确 import/纳管该记录，禁止删除记录后重建；RDS SSL 与两个账号更新必须显式串行，避免同一实例上的独占操作并发；
- 本轮未执行 migration、seed、应用容器、TLS、browser smoke 或旧凭证拒绝。当前状态为 `PROVISION_PARTIAL_APPLY_RECONCILIATION_REQUIRED`，候选 deployment 仍为 `NOT_RUN`，整体发布继续为 `NO_GO`；任何新的 provision 都需要独立授权，不得原样重试。

## 2026-07-23 DNS State 纳管与 RDS 串行修复

- 用户以“按下一步推进”授权完成 DNS 精确纳管、RDS 独占操作串行化、受保护主线复验，并在全部门禁通过后只执行一次新的 provision；该授权不包含自动重试、production 部署或新增 IAM 权限；
- 唯一 staging workflow 新增只读 DNS 事实核验：复用项目限定的 `DNSFullAccess` 执行 `ListRecords`，按 host/type/line/TTL/status/remark/当前 ECS EIP 全字段匹配且要求唯一结果；RecordID 只在 run 内 mask 后用于同一 remote state 的精确 import/identity 核对，不落 Git、artifact、公开文档或新 secret；
- Terraform 将 RDS 变更锁定为 `SSL → migration account → runtime account`，避免平台独占状态下并发更新；DNS 导入之后仍必须生成 saved plan，并由现有 destroy/replacement 拒绝门禁检查后才允许 apply；
- 修复由 PR #20 合入受保护主线，required check 与主线 Candidate Gate 均通过；本地私有证据引用为 `GH_RUN_29994013611`。
- 合入后只触发一次 `phase=provision`：run [`29994013611`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29994013611)，workflow HEAD `af6443d9f4d3b25513c840557c9755e78758e092`；DNS import 成功，saved plan 为 `0 add / 4 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`，apply 为 `0 added / 4 changed / 0 destroyed`；
- `Prepare private deploy bundle`、镜像部署、外部 TLS 验证和 SSH 清理均按 provision phase 跳过，没有 migration、seed、容器或域名发布；当前状态为 `PROVISION_CONVERGED_RDS_CA_REQUIRED`。下一步需取得该 RDS 实例当前 CA 并写入 GitHub staging Environment；deploy 需要新的明确授权，候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 RDS CA 与首次 Deploy

- 火山引擎控制台反向核验目标 staging RDS 已启用 SSL、强制加密并允许 TLS 1.2/1.3；下载的新 CA bundle 只含一张可解析的 `CA:TRUE` PEM 证书，剩余有效期超过 30 天。证书正文未写入日志、Git 或公开证据；
- CA 已通过 stdin 以 base64 PEM 写入 GitHub `staging` Environment secret `WP08_RDS_CA_PEM_B64`，随后只按名称与更新时间确认 secret 存在，没有读回 secret 内容；
- 写入前重新执行候选、仓库、workflow、secret presence、最新 provision 与并发运行复验；候选 `670661865f708a835997596ed5b74904809564a5` 的受保护主线门禁和三镜像 registry digest 保持通过，最新 provision run `29994013611` 成功，且 dispatch 时没有其他 staging run；
- 用户明确授权后只触发一次 `phase=deploy`：run [`29997923817`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/29997923817)，workflow HEAD `936502fe75213250e0d91e6fe789e8cd127ea269`；没有自动重试；
- deploy 的候选合同、remote state 初始化和 DNS 精确对账均通过；saved plan 为 `0 add / 5 change / 0 destroy`，`WP08_TERRAFORM_PLAN_GUARD=PASS`。apply 在打开当前 runner 单一 `/32` 的临时 SSH 路径时停止：CloudControl 的安全组更新请求再次把空 PrefixList 引用纳入 `vpc:AuthorizeSecurityGroupIngress` 鉴权，越出项目限定资源边界；
- 该失败与预期的项目限定 VPC 权限模型不一致，不得通过授予全局 `VPCFullAccess` 或空 PrefixList 权限绕过。后续必须修正安全组嵌套集合/provider 更新模型或改用等价的最小、可清理临时访问路径，并重新通过代码、计划和权限复验后取得新的单次 deploy 授权；
- `Prepare private deploy bundle`、migration、镜像部署与外部 TLS 验证均被跳过；`always()` 关闭 SSH 步骤生成 `0 add / 1 change / 0 destroy` plan、再次通过破坏性门禁并成功 apply。当前未留下 runner SSH 放行，候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 最小部署通道修复

- 为避免继续扩大 IAM 或重构基础设施，Terraform 中 22 端口保持 `127.0.0.1/32` 关闭态，不再用 CloudControl 更新整个安全组嵌套集合；
- 同一 staging workflow 在关闭态 Terraform plan/apply 及破坏性门禁通过后，直接调用火山引擎 VPC API 添加当前 GitHub runner 的单一公网 `/32`；请求只包含 CIDR、TCP/22、accept、优先级和固定描述，不包含 `PrefixListId`、`SourceGroupId`，复用现有项目限定 VPC 权限；
- `always()` 清理按完全相同的规则属性撤销，并在添加和撤销后分别调用只读安全组查询确认精确规则数量为 1 和 0；不新增 provider、长期资源、Environment secret 或 IAM 策略；
- 本节只代表最小代码修复与本地复验，尚未触发新的 deploy。候选 deployment 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-23 最小修复后的 Deploy 尝试

- PR #23 通过 required check 并合入受保护主线后，只触发一次 `phase=deploy`：run [`30006425732`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30006425732)，没有自动重试；
- 首次 plan 因精确 `InvalidTimestamp` 按既定合同只重签并重跑一次只读 plan；第二次得到 `0 add / 4 change / 0 destroy`，破坏性门禁通过；
- apply 中 RDS 账号与 TOS 原地收敛成功，ECS 因 Terraform 试图把实例当前 `KeepCharging` 改为 `StopCharging` 而被 CloudControl 以枚举校验失败拒绝。临时 SSH 规则尚未添加，因此 bundle、migration、容器、TLS 与清理均未运行；
- 月度预算本来按 ECS 整月运行估算；最小修复只把 `stopped_mode` 配置改为实例当前且该规格支持的 `KeepCharging`，不新增忽略项、权限、资源或费用假设。新的 deploy 仍需独立授权。

## 2026-07-23 硬停止与 Alpha 试点路径

- 安全组真实响应修复提交 `d20f263215f3abbd60e22d3c9d9529295085c063` 通过 PR #25 合入主线 `5e700afaeac6ef2bddcc83e6359e15e6f4bc1133`，required check 与 Mainline Candidate Gate 均通过；
- 按用户“一次且失败不重试”的边界，只触发 run [`30020569136`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30020569136)。候选合同、remote state、DNS、无破坏性基础设施收敛、精确 runner `/32`、私有 bundle 均通过；
- `Deploy exact registry digests` 在 migration 和容器启动前以 `expected candidate marker is missing` 停止。原因是标记只由 ECS 创建期 cloud-init 写入，而既有导入实例按受审模型忽略 `user_data` 变化；TLS 验证被跳过，`always()` 已确认 SSH 入口关闭，没有第二次 dispatch；
- 根据硬停止条件，不再修补当前 provider/apply 链。仍复用同一 `.github/workflows/staging.yml`：`provision` 保留唯一 IaC 写路径；Alpha `deploy` 只读取冻结 state 输出，不运行 DNS import、provider refresh、plan 或 apply；
- 发布脚本直接核对授权候选和三个 GHCR digest，不再依赖 ECS 创建期标记；每次发布使用带 run ID 的新目录，失败不覆盖旧目录，GHCR 登录通过退出 trap 清理；
- 本节仅表示新路径代码与机器门禁就绪，尚未执行新的 Alpha deploy。真实身份与真人 Alpha UAT 仍不得提前标记为通过，整体发布继续为 `NO_GO`。

## 2026-07-24 Alpha Secret 路径失败与最小修复

- 用户精确授权候选 `670661865f708a835997596ed5b74904809564a5` 在 staging 只执行一次 Alpha `phase=deploy`，失败不重试；唯一 run [`30026998583`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30026998583) 使用主线 `d393321aa24c3b5b7b04b49559af2f1686fcd729`；
- 候选合同、加密 state 初始化和冻结输出读取通过；DNS、Terraform plan/apply 与 CloudControl 步骤按设计跳过。精确 runner `/32`、私有 bundle 和 GHCR 登录通过；
- `deploy.sh` 在 migration 前以 `secret file api.env is missing` 停止。bundle 实际把六个 `0600` secret 放在本次 release 的 `secrets/`，Compose 也使用相对路径；脚本却固定读取 `/srv/journey-next-staging/secrets`，因此是单一发布包路径错误，不是 IAM、provider、RDS 或候选失败；
- 外部 TLS 被跳过，`always()` 已确认 runner SSH 规则为关闭态；未运行 migration、seed 或容器，未自动重试。失败 release 目录可能保留 root-only bundle，后续清理属于新的受控操作；
- 最小修复只把 `SECRETS` 指向当前 release 的 `$PWD/secrets`，并由 staging 校验测试锁定该合同；不新增 workflow、资源、IAM、secret 或依赖。新的 Alpha deploy 仍需独立精确授权。
- 合入修复后的离线审计进一步发现原顺序会在确认 Web、Worker 与 Edge 镜像可拉取前执行数据库迁移；发布脚本现先运行 Compose 合并配置校验并拉取全部固定 digest，再允许 migration。该调整没有云端写入，也没有消费新的 deploy 授权。

## 2026-07-24 Alpha Registry Egress 失败

- 用户重新精确授权候选 `670661865f708a835997596ed5b74904809564a5` 在 staging 只执行一次 Alpha `phase=deploy`，失败不重试；唯一 run [`30062128087`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30062128087) 使用主线 `a4bf1775e0de25d10dc17b678421e2dae500101c`；
- 候选合同、预算、加密 state 初始化、冻结基础设施输出、精确 runner `/32`、私有 bundle、release-local secret 与 Compose 合并校验均通过；DNS reconcile 与 Terraform plan/apply 按 deploy phase 跳过；
- 预迁移 `docker compose pull` 在解析 Docker Hub 上固定 Caddy digest 时因 HTTPS 连接超时失败。该失败不是候选 GHCR 三镜像、IAM、CloudControl、RDS 或应用运行错误；
- 日志未观察到 migration、runtime grant、seed、容器启动或部署成功标记；外部 TLS 验证被跳过。`always()` 步骤输出 `WP08_SSH_INGRESS=CLOSED`，run 终态为 failure，随后没有活动 staging run；
- 本次授权已消费且没有重试。状态保持 `ALPHA_PILOT_REGISTRY_EGRESS_BLOCKED`，候选 deployment、真实身份和真人 UAT继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-24 项目 GHCR Edge Mirror

- PR #30 以手动触发、固定确认词和 `packages: write` 最小权限加入受控 mirror；源固定为 Caddy 2.10.2 Alpine 的既定 Docker Hub digest，工作流本身不修改 staging 或云资源；
- 主线 `96368ca97b2a975d781fb35f7a036593f69d9944` 的 Candidate Gate run `30063177897` 通过后，只执行一次 mirror run [`30063385826`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30063385826)；
- GHCR 推送与 `target@digest` 回读验证均通过，目标固定为 `ghcr.io/muchenai2024-creator/muchen-journey-vnext-edge@sha256:b7c239fee65c44ac1dccfa76f88253f87e4d7a8ca27b92e419c86a967ecff171`；staging Compose 不再依赖 Docker Hub Caddy；
- 本节仅关闭已知 edge registry egress 阻塞。新的候选 deployment、migration、容器、TLS、真实身份和真人 UAT 仍为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-24 GHCR 修复后的唯一 Deploy

- PR #31 把 staging Compose 固定到已验证的项目 GHCR edge digest，并加入拒绝 Docker Hub Caddy 的机器合同；required check 和主线 `93635e336bb47836a8326068df84ff113253a748` 的 Candidate Gate run `30063625181` 均通过；
- 部署前候选 `670661865f708a835997596ed5b74904809564a5`、预算、冻结 state 路径、Environment secret/变量名称、成功 provision 与无活动 staging run 均已复验；随后只触发一次 `phase=deploy`：run [`30063847635`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30063847635)，没有重试；
- DNS reconcile 与 Terraform plan/apply 按 deploy phase 跳过。四个 GHCR 镜像全部拉取成功，已知 Docker Hub 阻塞关闭；Compose 创建了 release network 和空附件 volume，随后第一次 Alembic 连接 RDS 即以 `psycopg ConnectionTimeout` 停止；
- 未观察到 migration 执行、runtime grant、seed、应用容器启动、部署成功标记、TLS 或 browser smoke。本次 release 目录、缓存镜像、Compose network 和空附件 volume 可能保留在 ECS，清理或复用需要新的受控操作；
- `always()` 清理输出 `WP08_SSH_INGRESS=CLOSED`，运行后没有活动 staging run。当前必须先只读核验 ECS 与 RDS 的 VPC/子网、私网 endpoint、有效 AllowList/安全组绑定及 TCP 5432 路径；不得把连接超时误判为凭据或 TLS 错误，也不得自动重试 deploy。真实身份、真人 UAT 与 WP-09 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-25 人工网络核验与 CA 容器权限修复

- 主任务在火山引擎控制台只读核验现有 staging 资源：AllowList 的派生 IP、活动安全组、RDS 实例与 VPC 均一致；该 IP 与 staging ECS 主网卡一致。RDS 公网地址为空，SSL、强制加密与 TLS 1.2/1.3 已启用；活动安全组的 SSH 关闭态仍只允许 loopback `/32`，公网仅保留 80/443。公开证据不记录 IP、资源 ID 或 endpoint；
- 用户授权“人工核验 + 现有资源最小部署”后，只触发一次 `phase=deploy`：run [`30109954801`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30109954801)，workflow HEAD `08f6b728f6f03e15ac53d78272db29ff1c7e85e7`，候选仍为 `670661865f708a835997596ed5b74904809564a5`；没有重试；
- `audit`、DNS reconcile 与 Terraform plan/apply 按 phase 跳过；冻结 state、精确 runner `/32`、私有 bundle 与四个 GHCR 镜像拉取均通过。首次 Alembic 连接前，非 root API 容器无法读取 `/run/secrets/volcengine-rds-ca.pem`，因此未建立数据库连接、未执行 migration、runtime grant、seed、应用启动或 TLS smoke；`always()` 输出 `WP08_SSH_INGRESS=CLOSED`；
- 根因是公开 CA 证书与密码文件共用 root-only `0600` 策略，而 API/Worker 镜像固定以 UID 10001 运行。修复仅把 CA 文件设为只读 `0444`，密码、环境文件和部署元数据继续为 `0600`；镜像、候选、IAM、网络、RDS 和 Terraform 均不改变；
- 发布脚本在镜像 pull 后、migration 前增加真实 API 容器 CA 读取检查。定向测试 15 项、完整 API/迁移测试 126 项、workflow、traceability、isolation、gitleaks 与 UID 10001 容器读取复验均通过。本节只代表修复就绪；新的 deploy 仍需在修复合入受保护主线后取得独立授权，当前 deployment、TLS、真实身份与真人 UAT 继续为 `NOT_RUN`，整体发布继续为 `NO_GO`。

## 2026-07-25 d407 候选 Deploy 与 Worker 配置边界

- PR #40 已把候选 `d407b5f4a32fd68b1a8b08ac5a461aa04aa29fff`、canonical artifact run `30120441674` 与三项 registry digest 原子绑定到受保护主线 `82cac3b771a48985a4f5d7195aabdaef9b1f274e`；PR required check 与合入后 Mainline Candidate Gate `30122196338` 均通过；
- 用户精确授权后只派发一次 `phase=deploy`：run [`30138363837`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30138363837)，没有重试。候选合同、artifact、预算、冻结 TOS state、四个 GHCR 镜像、CA 容器读取、migration `0010`、runtime grant、合成 seed、API 与 Web health 均通过；DNS、Terraform plan/apply/import 和 CloudControl 按 deploy phase 跳过；
- Worker 容器在写 heartbeat 前退出，Compose 因而将其判为 unhealthy；外部 TLS 步骤未执行。首次发布失败清理移除了 API/Web/Worker/Edge 容器与 release network，`always()` 输出 `WP08_SSH_INGRESS=CLOSED`，没有遗留 runner SSH 放行；
- 本地使用同一 staging 配置复现：Worker 导入 `journey_api.db` 时会加载完整 API `Settings`，而最小权限 `worker.env` 不含 `SESSION_SECRET`、`INVITE_SECRET`、`IMPORT_SIGNING_KEY`，因此在数据库连接和 heartbeat 之前被 API secret 校验拒绝；
- 修复不把三个无关高权限 secret 扩散给 Worker。数据库层改用只含 `DATABASE_URL` 的 `DatabaseSettings`；API 入口继续加载完整 `Settings` 并在 staging 缺少独立身份 secret 时 fail closed。新的子进程测试同时锁定这两个边界，真实 `APP_ENV=staging` + `NOTIFICATION_ADAPTER=DISABLED` Worker 启动路径已在本地 PostgreSQL 通过；
- 本次 `d407…` 部署授权已消费且禁止重试。当次状态为 `ALPHA_PILOT_WORKER_CONFIG_FIX_PENDING_CANDIDATE`；修复必须经 PR、主线 Candidate Gate、新候选与新的候选绑定后，才可另行申请一次 staging deploy。WP-09、真实身份、真人 UAT 与整体发布继续为 `NOT_RUN/NO_GO`。

## 2026-07-25 Worker 修复候选绑定

- PR #41 已通过 required check 并合入受保护主线 `dad44cc679184a1978b0f69e3632cb95de7f1b8e`。Mainline Candidate Gate [`30139385352`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30139385352) 完成完整 CI、候选打包、三镜像 SBOM、GHCR push 与远端 digest 验证；artifact 未过期且标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`；
- 新候选固定摘要为 API `sha256:6ccc4bdb…d886`、Web `sha256:44d3fa66…30c5`、Worker `sha256:77c611d1…95bf`。机器合同、Terraform candidate、deploy preflight、bundle、workflow artifact run/name 与确认词 `DEPLOY_DAD44CC_TO_VOLCENGINE_STAGING` 原子绑定；
- 绑定变更不包含 staging dispatch、云资源写入或旧候选重试。只有绑定 PR 合入受保护主线后，才能另行取得指名完整候选 `dad44cc679184a1978b0f69e3632cb95de7f1b8e`、基于届时绑定主线、冻结基础设施、失败不重试的精确 `phase=deploy` 授权。当前 deployment、真实身份、真人 UAT 与整体发布继续为 `NOT_RUN/NO_GO`。

## 2026-07-25 dad44 候选部署与浏览器 CSP 复验

- 用户精确授权候选 `dad44cc679184a1978b0f69e3632cb95de7f1b8e` 基于主线 `58b2428a45fa4d848d8438dcc24dfc2c0a79fc5c`，在华北2（北京）冻结基础设施上只执行一次 `phase=deploy`，失败不重试。唯一 run [`30157449832`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30157449832) 已消费该授权，没有第二次 dispatch；
- 唯一 job `89677528525` 的候选/artifact 合同、冻结 state、精确 runner `/32`、私有 bundle、固定 GHCR digest、migration/runtime grant/seed、API/Worker/Web/Edge、外部 TLS/readiness、匿名 `/ops = 401` 与 SSH 撤销步骤全部为 success。公开只读复验再次得到 root 200、readiness 200、release 精确匹配、匿名 `/ops = 401`、`Cache-Control: no-store` 与 TLS verified；PII-free 物理部署证据写入私有引用 `evidence/private/wp08/physical-deployed.json`；
- GitHub workflow run 与 check suite 顶层结论却为 failure，而唯一 job/check-run 为 success，且所有 job steps 均成功；唯一 annotation 是 Node 20 deprecation。本记录把它保留为 GitHub 聚合异常，不把顶层 failure 擅自改写成成功，也不以此触发重试；
- 发布后真实 Chromium 打开公开 `/` 时返回 200 且存在可聚焦控件，但控制台出现 15 条 CSP 错误，Next.js framework/page scripts 因缺少匹配 nonce 被浏览器拒绝，页面未 hydration。根因是 proxy 只把 nonce 写入 `x-nonce` 与响应 CSP，没有把 CSP 传给 Next.js 请求头；RootLayout 同时可静态渲染，无法为每个请求给 framework scripts 注入 nonce；
- 最小修复把同一 CSP 写入请求头，并以 `connection()` 强制请求时渲染；生产 runtime test 锁定 root 脚本 nonce 与响应 CSP 一致且每请求变化。canonical browser smoke 改为在公开 `/` 检查三档视口、console、overflow、focus/键盘，并单独对匿名 `/ops` 断言 401；本地隔离生产构建与真实 Chromium 已通过；
- 当前 staging 仍运行 `dad44…`，因此只能记为“应用已部署、发布验证失败”，不是 `STAGING_ISOLATION_VERIFIED`。CSP 修复必须经 PR、主线 Candidate Gate、新候选和候选绑定后，再取得新的精确 deploy 授权；`dad44…` 禁止重试，WP-09、真实身份与真人 UAT 不得提前启动或转绿。

## 2026-07-25 CSP 修复候选绑定

- PR #43 已通过 required check 并以仓库允许的 squash 方式合入受保护主线 `14c9ba073c293da1d4c6b615ea1f07c6c50688fa`；PR Fast Gate run `30158813946` 与 Mainline Candidate Gate [`30158877647`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30158877647) 均通过；
- canonical artifact 未过期且标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`。修复候选固定摘要为 API `sha256:4f205e46…c949`、Web `sha256:ce05e4d4…8ff6`、Worker `sha256:25451ac5…48cc`；机器合同、Terraform candidate、deploy preflight、bundle、workflow artifact run/name 与确认词 `DEPLOY_14C9BA0_TO_VOLCENGINE_STAGING` 原子绑定；
- 本候选绑定不包含 staging dispatch、云资源写入或 `dad44…` 重试。只有绑定 PR 合入受保护主线后，才能另行取得指名完整候选 `14c9ba073c293da1d4c6b615ea1f07c6c50688fa`、届时绑定主线、冻结基础设施、失败不重试的精确 `phase=deploy` 授权；当前 staging 仍运行 `dad44…`，WP-09、真实身份、真人 UAT 与整体发布继续为 `NOT_RUN/NO_GO`。

## 2026-07-31 运行态只读盘点与 Repair 前置事实

- repair run [`30595486997`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30595486997) 在镜像拉取、migration、grant 和容器替换前 fail closed；精确失败项为 API release 不在旧审查集合，SSH 已关闭，没有应用或数据库写入；
- PR #98 增加同一 WP-08 workflow 的 `phase=inspect-runtime`，只允许读取固定容器的 Web/API/Worker release、API readiness、Alembic revision、config schema 与 Worker heartbeat release/freshness；禁止镜像、Compose、migration、grant、seed、Terraform plan/apply/import、DNS、消息和 WP-12B；
- 主线 `16c50e4a0164193569fd96a59cb75229dad6906d` 的唯一 inventory run [`30598785077`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30598785077) 成功：Web/API/Worker/heartbeat 全部为 `222096db506e95db887a8705b22ca4a439d0545d`，migration=`0014_wp12_data_lifecycle`、config schema=3、API ready、Worker 非 stale；部署相关步骤全部 skipped，SSH 已关闭；
- 本事实只允许把 `222096db…` 加入 repair prestate。repair 目标仍固定为 API/Worker=`02863d0…`，Web 不变；本记录不构成部署授权，不把未完成的 deploy 追认为成功，不激活 UAT，也不改变 production `NO_GO`。

## 2026-07-31 有界 Runtime Repair 成功

- PR #99 合入受保护主线 `100e89494b8c42a6b04a86f5bdc26c06ab690fa7`，Mainline Candidate Gate [`30615645332`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30615645332) 通过；
- 用户随后精确授权一次 `phase=repair-runtime`。唯一 run [`30616573615`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30616573615) 成功，未重试：Web=`222096db506e95db887a8705b22ca4a439d0545d`，API/Worker/heartbeat=`02863d0b670ee9b00b9def3e75bc6699827f555a`，migration=`0014_wp12_data_lifecycle`；
- workflow 内部组件合同、公开 readiness、root=200、匿名 `/ops`/`/review`=401 与 SSH 撤销全部通过；Terraform、DNS、云资源、seed、消息发送和 WP-12B 未执行；
- 本记录只恢复 WP-13 技术入口。原 UAT 失败、WP-12B 1 秒性能失败、真人签署缺失、WP-14 真实 14 天与 WP-15 production 门禁继续保持，production 仍为 `NO_GO`。

## 2026-08-03 WP-19～WP-22 候选绑定

- 精确候选 `ef0a512cf357001cfd8cb6803f65cc17ae697325` 的 Mainline Candidate Gate [`30806515651`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30806515651) 已通过完整 CI、候选打包、SBOM、三镜像 GHCR push 和远端 digest 复验；artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`；
- staging 合同固定 API `sha256:045bc1eb…3281`、Web `sha256:ba24dc10…99b6`、Worker `sha256:1a767577…efc5`，并绑定唯一 artifact 名、run ID、Terraform candidate、部署 bundle、脚本 preflight 与确认词 `DEPLOY_EF0A512_TO_VOLCENGINE_STAGING`；
- 候选 migration head 为 `0015_wp19_formal_journey`。10 个 TaskVersion 中 8 个正式旅程任务保持 `RUNTIME_OPERATOR_PUBLISH_REQUIRED`；部署只建立可运行能力，不替 Operator 发布业务内容；
- Owner 已授权绑定 PR 合入且 required check 通过后，在冻结 staging 基础设施执行一次部署；失败不重试。Terraform plan/apply、DNS、云资源、消息发送、业务接收人和 WP-12B 均不在范围，production 继续 `NO_GO`。

## 2026-08-03 ef0a512 部署 pre-start 失败与精确清理合同

- 绑定 PR #138 已合入主线 `80c3e7e9050b8c69c411e42a99ac6d6e7c07b1b3`。用户授权的唯一 deploy run [`30808632624`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30808632624) 没有重试；候选、artifact、冻结 state 和临时 runner `/32` 均通过，随后 `deploy.sh` 在第一组环境合同检查以 `WP08_DEPLOY_ERROR: unexpected production host` fail closed；
- 根因是 `scripts/wp08_prepare_deploy.py` 已把 `PRODUCTION_HOST=journey.muchenai.com` 写入 edge 环境，却漏写到 `deploy.sh` 实际 source 的 `.deployment.env`。失败发生在 `docker compose pull`、migration、runtime grant、seed、容器替换和 `current` symlink 更新之前；外部 staging 继续运行旧 Web-only release，匿名 `/ops` 与 `/review` 仍为 401，临时 SSH 已输出 `WP08_SSH_INGRESS=CLOSED`；
- 失败仅留下 root-only 目录 `/srv/journey-next-staging/releases/ef0a512cf357001cfd8cb6803f65cc17ae697325-30808632624`。修复 PR 增加 `.deployment.env` 的生产 host、单元回归测试和一次性 `cleanup-failed-release`。清理脚本精确绑定候选/run，并在删除前拒绝 `current`、回退标记、部署标记、Docker working directory、符号链接、硬链接或 bundle 内容漂移；release-local 环境文件先安全擦除；
- 清理不是部署，不读取业务表正文、不修改数据库、DNS、Terraform、云资源、消息、接收人或 WP-12B。清理通过后 staging 仍应保持旧 release；新的 deploy 必须由用户基于合入后的完整主线 SHA 单独授权，production 继续 `NO_GO`。

## 2026-08-03 ef0a512 内部部署完成与公开路由根因

- 修复后的唯一 deploy run [`30817611873`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30817611873) 已完成 migration `0015_wp19_formal_journey`、Web/API/Worker/Edge 启动与内部 readiness；部署标记和四个运行组件均为候选 `ef0a512…`。该 run 的单次公开 readiness 命中候选，但没有覆盖共享 Docker DNS 的非确定性。
- PR [#140](https://github.com/muchenai2024-creator/muchen-journey-vnext/pull/140) 将 `phase=inspect-runtime` 扩为 PII-free 拓扑 inventory；唯一只读 run [`30823210293`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30823210293) 确认 staging 四服务各只有一个运行容器、均属于同一 candidate release 和 Compose project，API ready、Worker heartbeat 新鲜，临时 SSH 已关闭。
- inventory 同时确认 staging Web 在共享网络拥有 `web` 与 `journey-next-staging-web-1` 两个别名，Caddy staging upstream 为 `web:3000`，production upstream 为 `production-web:3000`。production Compose 的 `web` 服务也加入该共享网络，Docker Compose 自动注册通用服务名 `web`；随后 20 次独立公网 readiness 全部返回旧 production Web release `8e56e759…`。因此根因是共享网络 DNS alias 冲突，不是候选镜像、应用启动、数据库或 DNS 失败。

## 2026-08-03 Edge-only 确定性路由修复合同

- staging Caddyfile 仅把 upstream 从通用 `web:3000` 改为 inventory 已验证的唯一 `journey-next-staging-web-1:3000`；production upstream `production-web:3000`、TLS、域名、安全头和日志策略保持不变。官方 Caddy 合同说明当前 `admin off` 不支持管理 API reload，因此首次应用必须重建一次 Edge，不能把未受支持的“热加载”当作零中断证据。
- 新 `phase=repair-edge-route` 固定候选、确认词、旧 production release 与 Edge digest，先验证两个 Web 的直接 readiness 和共享 alias prestate，再用现行 Caddy binary validate。唯一变更命令为 `docker compose ... up -d --no-deps --force-recreate --pull never edge`；禁止 image pull、Web/API/Worker、migration、grant、seed、Terraform、DNS、云资源、消息和 WP-12B。
- 公开验收要求 12 轮连续新连接均得到 staging 候选、production 既有 release、两个根页面 200 与 staging 两个受保护路由 401，避免单次探针再次掩盖 Docker DNS 轮询。应用或验收失败时，root-only 备份原位恢复并只重建 Edge；成功后删除临时状态。临时 SSH 仍由 `always()` 无条件关闭。本合同本身不构成 mutation dispatch 授权，production 继续 `NO_GO`。

## 2026-08-03 Edge-only 修复应用与公开 staging 验收

- Owner 精确授权候选 `ef0a512cf357001cfd8cb6803f65cc17ae697325` 基于主线 `36e80e6a6d783dba0417c88612794b0c1e105db0` 在现有 staging 执行一次 `phase=repair-edge-route`。唯一 run [`30826160950`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30826160950) 成功，未重试。
- run 在修复前证明 staging Web=`ef0a512…`、production Web=`8e56e759…`、共享 alias 冲突、Edge 固定摘要、Compose project/release 和旧 Caddyfile；随后用现行 Caddy binary 校验新配置，仅以 `--no-deps --force-recreate --pull never edge` 重建 Edge。
- workflow 内 12 轮连续新连接和主任务独立 12 轮复验均证明 staging readiness=`ef0a512…`、production readiness=`8e56e759…`、两个根页面 200、staging 匿名 `/ops` 与 `/review` 401。回退步骤未触发，成功状态已清理，SSH 关闭步骤输出 `WP08_SSH_INGRESS=CLOSED`。
- 本证据只关闭公开 staging Edge 路由债务；正式 Journey V1 的 Operator/Reviewer 发布事实仍待生成，内容真人理解、独立 Reviewer 校准、WP-23 完整旅程与 production GO 均不因此转绿。

## 2026-08-04 正式 Journey V1 发布的 Owner 陈述

- Owner 报告当前 staging Operator 已选择完成线下复核的独立 Reviewer，确认发布后正文不可原地修改，并发布一次受控内测 Journey V1；未同时创建邀请或发送消息。
- 这是合格的真人 Operator 操作陈述，不是应用或数据库机器读回。发布事实暂记为 `RUNTIME_CONTENT_PUBLICATION_OWNER_REPORTED / MACHINE_READBACK_PENDING`；下一步只允许以一条绑定正式 JourneyVersion 的受控邀请关闭最小读回，不因此改写真人内容门禁、WP-23 或 production `NO_GO`。

## 2026-08-04 正式 Journey V1 发布与邀请机器读回

- PR #142/#143 修复发布错误呈现并增加只读有界诊断；唯一诊断 run `30872474226` 在固定窗口未找到发布请求并失败关闭，未连接数据库或重跑，SSH 已关闭。
- PR #144 将 Web 候选 `12bc627d4310cdba9eba4c67050dc875994ceb31` 绑定到 API/Worker 基线 `ef0a512cf357001cfd8cb6803f65cc17ae697325`。唯一 Web-only deploy run [`30875911123`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30875911123) 成功：公开 readiness 返回 `12bc627…`，根页面 200，匿名 `/ops` 与 `/review` 401；数据库、migration、业务事实、Terraform、DNS、云资源、消息和 WP-12B 未改变，临时 SSH 已关闭。
- 刷新 `/ops` 后，固定旅程下拉框从服务端列出 `Muchen Journey 探索营 · V1 · 8 站`。Operator 只生成一次绑定该 JourneyVersion 的受控邀请；再次刷新后，一次性链接正文消失，最近邀请仍显示“待使用”。未读取、输出或记录 token。
- 上述证据关闭发布事实的最小机器读回，并将 WP-19～WP-22 最小纵向切片记为 `MINIMAL_VERTICAL_SLICE_COMPLETE / MACHINE_READBACK_VERIFIED`。内容真人有效性、独立 Reviewer 校准、WP-23 完整旅程与 production `NO_GO` 不变。

## 2026-08-04 WP-24 候选与单次 staging 授权

- PR #146 合入主线 `0589fc825e41dc0c536b3bf87ac284c9a50013fd`；Mainline Candidate Gate [`30909355182`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30909355182) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验。artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 为 `0016_wp24_formal_camp_v2`；
- staging 合同固定 API `sha256:18f0e6fc…2d46`、Web `sha256:10db6534…0dd4`、Worker `sha256:2a98da14…bd14`，并绑定唯一 artifact 名、run ID、Terraform candidate、部署 bundle、脚本 preflight 与确认词 `DEPLOY_0589FC8_TO_VOLCENGINE_STAGING`；
- Owner 已明确授权以该主线生成新候选并在冻结 staging 执行一次部署。部署允许 migration 从 `0015` 前向升级至 `0016`、同步 runtime DML 权限并替换 API/Web/Worker/Edge；不运行 Terraform plan/apply、DNS、云资源、WP-12B，不发布 Journey V2、不创建邀请、不发送消息。失败不重试，临时 SSH 必须无条件关闭；
- 本节只记录候选与授权边界；绑定 PR 未合入和唯一 workflow 未成功前，不得把 staging 记为已部署，production 继续 `NO_GO`。

## 2026-08-05 WP-26～WP-30 候选与 staging 绑定

- PR #148 合入主线 `a2312b269b1806cd3d5ce7d26fbc693466399035`；Mainline Candidate Gate [`30958975566`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30958975566) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验。artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 为 `0019_wp30_invitation_control`；
- staging 合同固定 API `sha256:a2dea31e…6ad4`、Web `sha256:646e7965…30bc`、Worker `sha256:d8a1cbc7…31b4`，并绑定唯一 artifact 名、run ID、Terraform candidate、部署 bundle、脚本 preflight 与确认词 `DEPLOY_A2312B2_TO_VOLCENGINE_STAGING`；
- Owner 已授权文档 39 的待授权事项按顺序执行。该授权允许本候选在冻结 staging 进行一次完整部署；部署只允许 migration 从现有 `0016` 前向升级至 `0019`、同步 runtime DML 权限并替换 API/Web/Worker/Edge，不运行 Terraform、DNS、云资源、WP‑12B，不发布 Journey V3、不创建邀请、不发送消息；失败不重试，临时 SSH 必须无条件关闭；
- 真实 Content Editor 身份、材料导入、独立 Reviewer 复核、八版本发布、Journey V3、真人门禁和 UAT 仍是部署后的独立业务事实；候选绑定不得替代这些步骤，production 继续 `NO_GO`。

## 2026-08-05 WP-26～WP-30 staging 部署与身份入口停止点

- 绑定 PR #149 通过 Fast Gate 后合入主线 `987a3d4d7ba1f92c63a34b76b5445865ab827fba`。唯一 staging deploy run [`30959911465`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30959911465) 成功且未重试：固定三镜像摘要，migration 依次完成 `0016→0017→0018→0019`，公开 readiness 返回候选 `a2312b2…`，临时 SSH 已关闭；Terraform、DNS、云资源、WP‑12B、Journey V3、邀请和消息均未执行；
- workflow 内 `/ops` 与 `/review` 匿名 401 通过。主任务随后独立核对新增 `/content`，发现匿名请求因未被 Next.js proxy 提前拦截而进入服务端数据请求并返回 500；这是身份入口合同缺口，不是数据库或材料事实失败；
- 按“只修 P0 blocker”边界停止 Content Editor 创建与绑定。修复仅把 `/content` 及子路由加入现有身份前置 401，并把该路由加入 Web 静态回归和 staging 外部验收；修复 PR 合入不等于获得第二次部署授权，production 继续 `NO_GO`。

## 2026-08-05 `/content` 身份入口修复候选绑定

- PR #150 通过 Fast Gate 后合入主线 `e61cb3af80baef389157ead79fc91ebf89e52adc`。修复把 `/content` 及子路由纳入与 `/ops`、`/review` 相同的匿名 401 前置，增加独立 identity route contract，并把候选源码核验和 staging 外部验收扩展到 `/content`；没有修改业务事实、角色、材料、Journey 或邀请；
- Mainline Candidate Gate [`30960806357`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30960806357) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验。artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 保持 `0019_wp30_invitation_control`；
- 修复候选固定 API `sha256:98f9ab54…8db9`、Web `sha256:242070d6…03dc`、Worker `sha256:5574f0ee…6d63`。虽然应用变更仅涉及 Web 身份入口与部署验收合同，仍选择既有完整原子部署和自动回退路径，不新增临时 Web-only 分支；
- 本绑定不消费部署授权。`a2312b2…` 的首次授权已由 run `30959911465` 消费；只有绑定 PR 合入并取得完整候选 `e61cb3af80baef389157ead79fc91ebf89e52adc` 与合入后主线 SHA 的新精确授权，才允许执行一次冻结基础设施 staging 部署。此前 Content Editor 创建与绑定继续停止，production 继续 `NO_GO`。

## 2026-08-07 Content Editor 历史身份迁移候选绑定

- `/content` 修复绑定 PR #151 合入主线 `b91969faa2b6cac501f2aa6f3d94cca757376e4a` 后，唯一 staging deploy run [`31006041324`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31006041324) 成功部署 `e61cb3af80baef389157ead79fc91ebf89e52adc`；migration 保持 `0019_wp30_invitation_control`，部署完成并关闭临时 SSH。该候选已消费，不得再次部署；它是本节最近一次成功部署证据，不代表对当前运行态进行了新的在线盘点；
- 真实 Content Editor 随后使用绑定链接时命中历史已撤销 Reviewer 飞书身份。只读核验确认目标 Content Editor 尚未绑定、历史身份无有效会话、现任 Reviewer 已有另一条有效身份；Owner 另行确认历史账号确属目标 Content Editor 本人。处理边界因此固定为“转移仍保持撤销的历史身份归属，再由本人使用撤销后新链接重新绑定”，禁止清除撤销标记、直接改库或复用旧链接；
- PR #152 以受控、可审计、fail-closed 的方式实现上述迁移合同，并合入主线 `2223fc1589d772e5397e43357fc5682f27c1c3a8`。Mainline Candidate Gate [`31137770622`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31137770622) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验；artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 保持 `0019_wp30_invitation_control`；
- 新候选固定 API `sha256:69ab50c2…c393`、Web `sha256:2d36bcd6…8ac`、Worker `sha256:d16cc5d0…a89b`。本绑定只建立下一次部署的候选、摘要、artifact、确认词和回归合同，不执行 staging 部署，不迁移身份，不生成链接，不修改角色或业务事实；
- 只有本候选绑定 PR 合入并取得完整候选 `2223fc1589d772e5397e43357fc5682f27c1c3a8` 与合入后主线 SHA 的新精确授权，才允许执行一次冻结基础设施 staging 部署。部署成功后仍须由当前 Operator 分两步执行身份转移和新链接生成，并由郑田源本人完成 OAuth；production 继续 `NO_GO`。

## 2026-08-07 Content Editor OAuth callback 修复候选绑定

- 身份迁移绑定 PR #153 合入后，唯一 staging deploy run [`31147474464`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31147474464) 成功部署 `2223fc1589d772e5397e43357fc5682f27c1c3a8`；migration 保持 `0019_wp30_invitation_control`，readiness 与匿名拒绝通过，临时 SSH 已关闭。该候选已经消费，不得再次部署；
- Operator 随后按受控流程转移仍保持撤销的历史身份、生成一次新的 30 分钟 Content Editor 链接，账号持有人本人完成 OAuth。机器读回确认身份重新激活且服务端创建了 Content Editor 会话；但 Web callback 的安全入口仅包含 `/review`、`/ops`，拒绝 `/content` 后未转发 API 的 cookie 响应，浏览器因此继续得到 `AUTH_REQUIRED`；
- PR #154 仅把 `/content` 加入精确同源安全入口，并增加未知入口拒绝、成功回跳和 cookie 响应转发合同；没有修改数据库、身份、角色或业务事实。PR 合入主线 `c0765eb625fc3c99205dc3d05abf9fad0475d81d`，Mainline Candidate Gate [`31171640166`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31171640166) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验，migration head 保持 `0019_wp30_invitation_control`；
- 新候选固定 API `sha256:49f2412e…8b37`、Web `sha256:9369885d…f0f8`、Worker `sha256:bd9686fb…d95e`。本绑定只建立候选、摘要、artifact、确认词和回归合同，不执行 staging 部署，不修改身份或业务事实；
- 只有本绑定 PR 合入并取得完整候选 `c0765eb625fc3c99205dc3d05abf9fad0475d81d` 与合入后主线 SHA 的新精确授权，才允许执行一次冻结基础设施 staging 部署。部署失败不重试，production 继续 `NO_GO`。

## 2026-08-08 Content Editor 无会话重新进入候选绑定

- PR #156 为匿名访问 `/content` 增加同源 `/content/login` 与“使用飞书进入”，并以真实浏览器端到端合同覆盖登录入口；`/ops` 与 `/review` 对匿名访问继续返回 401。该变更没有修改数据库、身份、角色或业务事实；
- PR #156 合入后的 Mainline Candidate Gate [`31258836950`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31258836950) 在候选打包前被新披露的 `GHSA-2v37-7h3g-55p8` 拒绝，因此没有候选 artifact 或镜像 push。PR #157 只把既有 Web override 中的 `nanoid` 固定为 `3.3.17`，没有扩大依赖或产品范围；
- PR #157 合入新主线 `3b7d7573cd70b72868e427b523ff630b732f0603` 后，Mainline Candidate Gate [`31259643008`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31259643008) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验。artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 保持 `0019_wp30_invitation_control`；
- 新候选固定 API `sha256:009be6c7…6b9a`、Web `sha256:b8073419…f2e5`、Worker `sha256:9796479e…7323`。机器合同同时要求匿名 `/content` 返回 303、`Location: /content/login`、`Cache-Control: no-store`，且登录页展示“使用飞书进入”；
- 本绑定只更新候选、artifact run、三镜像摘要、唯一确认词与外部 smoke，不执行 staging 部署，不修改身份或业务事实。只有绑定 PR 合入并取得完整候选 `3b7d7573cd70b72868e427b523ff630b732f0603` 与合入后主线 SHA 的新精确授权，才允许执行一次冻结基础设施 staging 部署；失败不重试并必须关闭临时 SSH。production 继续 `NO_GO`。

## 2026-08-09 Content Editor 无会话重新进入候选部署

- Owner 精确授权候选 `3b7d7573cd70b72868e427b523ff630b732f0603` 基于主线 `a7d6a86f07efbcf2f8e9771108b19dbe1a15026f`，在华北2（北京）的冻结 staging 基础设施执行一次 `phase=deploy`；
- 唯一 run [`31261406217`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31261406217) 完成候选校验、既有 `0019_wp30_invitation_control` migration 核对、API/Web/Worker/Edge 替换和临时 SSH 关闭。没有 Terraform、DNS、云资源、WP-12B、Journey V3、邀请、消息、身份或业务事实变更，也没有重试；
- 工作流末尾外部验证发生竞态并使 run 最终状态为失败，原始失败保持不变；随后同一运行态 exact public contract 立即通过且连续三次通过：根页 `200`、readiness 精确返回 `3b7d757…`、匿名 `/ops` 和 `/review` 为 `401`、匿名 `/content` 为 `303` 且只转向 `/content/login`、登录页展示“使用飞书进入”；
- 因部署授权已消费且运行态合同稳定通过，不允许以工作流红色结论为由再次部署。当前下一项是八个不可变 TaskVersion 与 Journey V3 的受控业务发布准备，production 继续 `NO_GO`。

## 2026-08-09 Journey V3 邀请标签修复候选绑定

- Operator 已从唯一正式内容源发布八个不可变 TaskVersion，并以独立 Reviewer 与复核记录组装 Journey V3。机器读回确认 `formal_journey.v3_published=SUCCESS`、固定旅程列表新增 V3、八站顺序正确，发布前后邀请均为 4 条；没有创建 V3 邀请、发送消息或修改 production；
- 机器读回同时发现邀请下拉框把已含 `V3` 的标题再次追加版本，显示为 `V3 · V3 · 8 站`。PR #160 只在标题末尾已包含对应版本时停止重复追加，并增加回归测试；V1/V2 显示合同不变；
- PR #160 合入主线 `3445b5784d735fad2af4cd9a3568221b4aef7e19` 后，Mainline Candidate Gate [`31317525199`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31317525199) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端摘要复验。artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 保持 `0019_wp30_invitation_control`；
- 新候选固定 API `sha256:2b67a095…ca8b`、Web `sha256:0e1cbd1b…777d`、Worker `sha256:ce63089b…b447`。本绑定只更新候选、artifact run、三镜像摘要、唯一确认词与回归合同；不执行 staging 部署，不创建邀请，不修改 Journey V3、Enrollment、身份或消息事实；
- 只有绑定 PR 合入并取得完整候选 `3445b5784d735fad2af4cd9a3568221b4aef7e19` 与合入后主线 SHA 的新精确授权，才允许执行一次冻结基础设施 staging 部署。部署成功且标签机器读回正确后，仍需单独授权创建首条 Journey V3 受控邀请；production 继续 `NO_GO`。

## 2026-08-10 staging 外部表面门禁可观测化候选绑定

- Journey V3 标签修复候选 `3445b5784d735fad2af4cd9a3568221b4aef7e19` 的唯一 deploy run [`31325490856`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31325490856) 已完成三服务与 Edge 替换并关闭临时 SSH；最后的外部 smoke 在短暂切换窗口标红。随后只读核对确认实际运行态 release=`3445b57…`、migration=`0019_wp30_invitation_control`、API/DB READY、Worker release 正确，公开根页/readiness、匿名受保护路由及 Journey V3 标签均满足合同。该 run 原始失败记录保留，候选不得重跑；
- PR #162 将部署后的九项外部合同改为逐项输出 `WP08_SURFACE_CHECK`，只记录检查名、轮次、PASS/FAIL、HTTP 状态与经过白名单清洗的 readiness 字段，不输出响应正文、地址、身份、业务数据或凭据；
- 同一 workflow 最多执行 12 轮只读外部核验，每轮间隔 5 秒，单请求连接时限 2 秒、总时限 3 秒。任一轮九项全通过即结束；窗口耗尽仍 fail closed。该重试不拉取镜像、不重启容器、不重复 migration、grant、seed 或业务写入，也不等于第二次部署；
- PR #162 合入主线 `ff53052847a268d025bceb93c3eab37986d50219` 后，Mainline Candidate Gate [`31340959377`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31340959377) 完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端摘要复验。artifact 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 保持 `0019_wp30_invitation_control`；
- 新候选固定 API `sha256:2a053bad…a6a6c`、Web `sha256:a3335542…e2aee`、Worker `sha256:2ef3cd1b…9f38`。本绑定只更新候选、artifact run、三镜像摘要、唯一确认词和候选源码反查合同；不运行 Terraform、DNS、云资源或 WP-12B，不发布 Journey V3、不创建邀请、不发送消息、不修改身份或业务事实；
- 绑定合入并通过门禁后，只允许按 Owner 本次授权执行一次冻结基础设施 staging 部署验收。部署失败不重试且必须关闭临时 SSH；成功后须核对 exact release、migration、API/DB readiness、Worker revision、匿名路由与 Journey V3 标签。production 继续 `NO_GO`。

## 2026-08-10 staging 可观测表面门禁正式部署验收

- 绑定 PR #163 通过 Fast Gate 并合入主线 `7d2c17a6a6fb2468806731a7879716394df50f38`。候选 `ff53052847a268d025bceb93c3eab37986d50219` 的唯一冻结基础设施 deploy run [`31342063864`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31342063864) 成功：API/Web/Worker/Edge 完成替换，migration 保持 `0019_wp30_invitation_control`，没有 Terraform、DNS、云资源、WP-12B、Journey 发布、邀请或消息写入；
- 九项外部合同均在 attempt 1 通过：根页 `200`，readiness `200/ready` 且 release 精确匹配，匿名 `/ops` 与 `/review` 均为 `401`，匿名 `/content` 为 `303`、只跳转 `/content/login`且 `Cache-Control: no-store`，登录页 `200` 并展示“使用飞书进入”。工作流未触发第二轮，不存在应用重试或二次部署；
- 独立公开接口复验确认 staging readiness release=`ff530528…`，同时 production readiness 仍为 `8e56e759152efcbf17f4373f2132e02a8762af81`；本次 staging 不影响 production。Operator 页可见固定旅程标签 `Muchen Journey 新人启航探索营 · V3 · 8 站`；
- 部署后只读 inventory run [`31342539916`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31342539916) 直接从 ECS 运行容器核对：deployed marker、API readiness/config release、Web release、Worker env/heartbeat release 全部精确为 `ff53052847a268d025bceb93c3eab37986d50219`，Worker 不 stale，migration=`0019_wp30_invitation_control`，config schema=3；API/Web/Worker/Edge 各且仅一个运行容器，镜像摘要与候选 manifest 完全一致，staging/production Caddy 上游仍隔离；
- deploy 与 inventory 两个 run 都记录 `WP08_SSH_INGRESS=CLOSED`。现有 Operator 浏览器标签中的“运行快照”仍保留部署前 `3445b578…` 文本；鉴于公开 readiness 与 ECS 容器内独立 inventory 均一致证明实际运行态已是 `ff530528…`，该观察记为现有标签页的陈旧页面快照，不视为运行态回退。候选的一次部署验收结论为 `PASS`；候选已消费，不得重新部署，production 仍为 `NO_GO`。

## 2026-08-11 P0 真实旅程闭环候选绑定

- P0 邀请、会话连续性、学习材料、修订闭环与 Learner Experience 收敛通过 PR #174 合入主线，候选源码 SHA 为 `1d228f752853728f594245ae9e9904dc5820215e`；
- Mainline Candidate Gate [`31496334555`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31496334555) 成功生成不可变 artifact，并完成完整 CI、SBOM、三镜像 GHCR push 与远端摘要复验。manifest 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 保持 `0019_wp30_invitation_control`；
- staging 合同固定 API `sha256:bf815ca2…d5cdc`、Web `sha256:5de1511a…f7f6`、Worker `sha256:fe889286…df53`，并同步 workflow 候选守卫、artifact run、Terraform candidate、部署脚本和准备脚本；唯一部署确认词为 `DEPLOY_1D228F7_TO_VOLCENGINE_STAGING`；
- 本绑定 PR 只建立候选与 staging 部署合同，不执行部署、不修改数据库、身份、Journey、邀请、消息、DNS、Terraform 或云资源。只有绑定 PR 合入并取得合入后的精确主线 SHA，再由 Owner 明确授权该候选基于该主线执行一次冻结基础设施 staging 部署，才允许派发；失败不重试且必须关闭临时 SSH；
- 自动化浏览器已证明八站、要求修订、重新提交与 Reviewer 完成在隔离环境可执行，但这不是 1 名真实新人 UAT。staging 成功后仍必须先观察 1 名未接触项目的新人独立完成，再决定是否扩大至 3–5 人。

## 2026-08-11 P0 材料链接发布门禁候选绑定

- production 首站材料核对确认：失效 URL 来自易混淆字符的人工抄写，正式源使用数字 `0` 与大写 `I`；旧 TaskVersion/JourneyVersion 不允许原地修改，现有 Enrollment、提交与评审事实继续保留；
- PR #176 为 Operator 发布页增加逐项材料链接清单：正文内 HTTPS URL 与独立外链均被提取、去重并显示为可打开链接，未逐项确认时浏览器不能提交不可变 TaskVersion；该门禁不修改 API、迁移、身份或业务状态机；
- 最新候选源码 `65057e8db306b2dd9830e5047e77376899dcc652` 的 Mainline Candidate Gate [`31566262399`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31566262399) 成功；manifest 标记 registry push verified、deployment not run，migration 仍为 `0019_wp30_invitation_control`；
- staging 合同固定 API `sha256:1d4b8311…a5d3`、Web `sha256:11655ff4…b4c`、Worker `sha256:c7a640d5…4010`，唯一部署确认词为 `DEPLOY_65057E8_TO_VOLCENGINE_STAGING`；本绑定不部署、不修改内容或其他外部事实。该候选同时包含材料链接审计、邀请三态、安全续接、Learner 单目标/单动作信息层级收敛，以及任务目标与交付默认可见的 P0 修复；完整隔离浏览器路径及三档视口回归通过，但正式飞书材料权限和真人 UAT 仍未证明。

## 2026-08-12 P0 任务要求默认可见候选部署验收

- Owner 精确授权候选 `65057e8db306b2dd9830e5047e77376899dcc652` 基于主线 `0d8130be3d99807bf21b7dd26552ecf27a08548f`，在华北2（北京）的现有冻结 staging 基础设施执行一次 `phase=deploy`；派发前本地、远端主线 SHA 一致，工作区干净且无排队或运行中的 staging workflow；
- 唯一 deploy run [`31570449604`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31570449604) 成功完成候选 manifest 校验、冻结 state 只读输出、三服务部署、外部表面复验和临时 SSH 关闭。Terraform plan/apply/import、DNS、云资源、WP-12B、邀请、消息、Journey、身份及其他业务事实写入均未执行；没有重试；
- 部署合同保持 migration `0019_wp30_invitation_control`。公开只读复验确认根页 `200`，readiness=`ready` 且 release 精确为 `65057e8db306b2dd9830e5047e77376899dcc652`，匿名 `/ops` 与 `/review` 均为 `401`，匿名 `/content` 为 `303`、`Location: /content/login`、`Cache-Control: no-store`，登录页 `200` 并展示“使用飞书进入”；

## 2026-08-12 Reviewer 委派候选绑定

- PR #187、#188 分别补齐受控 Reviewer 委派/双角色访问与 migration 0020 既有评审历史升级、空表安全降级；PR #189 为三镜像 GHCR push 和远端摘要复验增加最多三次的逐次可观测重试，失败仍保留已构建的 PII-free artifact；
- 主线 `83bc974e580395c52a36bf242efd18b58f9461de` 的 Mainline Candidate Gate [`31603792594`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/31603792594) 成功；API、Web、Worker 均在首次推送与首次远端不可变摘要复验通过，manifest 标记 `registry_push=VERIFIED`、`deployment=NOT_RUN`，migration head 为 `0020_wp09_reviewer_delegation`；
- staging 合同固定 API `sha256:f3e78192…ce148`、Web `sha256:305d2099…665f6`、Worker `sha256:b812333b…da0c1`，唯一部署确认词为 `DEPLOY_83BC974_TO_VOLCENGINE_STAGING`；本绑定不部署、不授予角色、不转移待评审任务，也不修改 Journey、邀请、消息或其他业务事实。
- workflow 的 `Deploy bounded staging release`、`Verify external TLS and release surface` 与 `Close SSH ingress` 三项均为 `success`。候选的一次 staging 部署授权已经消费，不得重跑；当前结论仅为 `STAGING_DEPLOYED / MACHINE_VERIFIED / HUMAN_UAT_PENDING`，不证明正式飞书材料对新人可访问，也不证明真实新人能理解并完成 Journey V3。
