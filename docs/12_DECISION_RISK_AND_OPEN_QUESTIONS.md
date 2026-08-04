# 12｜决策、风险与开放问题台账

状态：`APPROVED_FOR_BUILD`  
版本：V0.9
日期：2026-08-04
文档 Owner：Product Owner（业务）+ Tech Lead（技术）  
规则：`BLOCKS_G0` 未关闭即 No-Go；不得用“先按默认做，后面再调”开始编码。

## 1. 状态定义

| 状态 | 含义 |
| --- | --- |
| `LOCKED_BY_DIRECTION` | 已由本轮明确方向锁定，待责任人补正式签署 |
| `PROPOSED` | 本文给出建议，尚未批准 |
| `NEEDS_DISCOVERY` | 缺事实/原型/业务输入，必须先调研 |
| `APPROVED` | 已批准并可约束开发 |
| `REJECTED` | 已拒绝，记录替代方案 |
| `SUPERSEDED` | 被新 DEC 明确替代 |

## 2. 决策台账

| ID | 决策 | 已批准结论 | 状态 | 门禁 | Owner |
| --- | --- | --- | --- | --- | --- |
| DEC-001 | 项目类型 | vNext 是 Greenfield Replacement，不是止血重构、旁路 V2 或渐进兼容 | `APPROVED` | `BUILD_G0` | Liu Mowen（初始 Product + Tech Owner） |
| DEC-002 | 旧系统边界 | 旧系统仅用于需求调研、只读归档和离线导出；无运行时依赖/写回/回滚 | `APPROVED` | `BUILD_G0` | Liu Mowen（初始 Product + Tech + Data Owner） |
| DEC-003 | 独立资源 | 资源统一使用 `journey-next-*` 命名；本仓库、独立 DB/bucket/identity/CI/CD/secret/observability 不与旧系统共享 | `APPROVED` | `BUILD_G0`；物理生产验证 `G4` | Liu Mowen（初始 Tech + Ops Owner） |
| DEC-004 | P0 范围 | 只做探索营邀请→任务→提交→主管评审→修订/通过→结果/交接；只含 TSK-001 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product Owner） |
| DEC-005 | 技术栈 | Next.js 16 + TypeScript、FastAPI 0.139 + Python 3.14、PostgreSQL、S3-compatible storage；全新初始化 | `APPROVED` | `BUILD_G0` | Liu Mowen（Tech Owner） |
| DEC-006 | 身份方案 | 采用 C：邀请建立 vNext 内部身份与独立会话；Reviewer/Operator 在非本地环境绑定独立飞书身份 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product + Security Owner） |
| DEC-007 | 首批试点 | 5 名新人、2 名独立主管、1 名运营、1 名 QA Recorder；使用专用账号与受控人员名册 | `APPROVED` | 人员名册与真人执行 `G4` | Liu Mowen（Product + QA Owner） |
| DEC-008 | 数据治理 | 身份/提交/评价/结果保留 3 年，附件 1 年，通知元数据 180 天，幂等记录 30 天，审计 3 年；删除请求 30 天内处理，法定保留除外 | `APPROVED` | `BUILD_G0` | Liu Mowen（Privacy + Data Owner） |
| DEC-009 | 历史数据导入 | P0 不导入旧业务事实；所有试点对象在 vNext 新建。未来导入需新 DEC 与离线签名包 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product + Data Owner） |
| DEC-010 | 成功与观察 | 14 天试点；完成率≥80%、当前行动理解率≥90%、90% 评审在 2 个工作日内、重复事实/状态冲突为 0、支持介入率≤20% | `APPROVED` | 实测与观察 `G5` | Liu Mowen（Product + QA Owner） |
| DEC-011 | 通过后的下一步 | 产生 `HANDOFF_READY`，展示责任人和说明；不调用旧新手村 API，不共享会话或状态 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product Owner） |
| DEC-012 | AI Advisor | 不进入 P0；无模型调用、无 AI 数据处理 | `APPROVED` | `BUILD_G0` | Liu Mowen（Product + Security + Tech Owner） |
| DEC-013 | SLO/恢复预算 | 常规 API p95≤1 秒；试点可用性 99.5%；RPO≤24 小时、RTO≤4 小时；每日备份、月度隔离恢复、14 天观察 | `APPROVED` | 演练证据 `G4` | Liu Mowen（Tech + Ops + Data Owner） |
| DEC-014 | 生产控制 | 生产密钥仅在受管 secret store；CI 受限身份发布；个人机器不得直接生产部署；双人批准后开放写入 | `APPROVED` | 物理配置与人员授权 `G4` | Liu Mowen（初始 Security + Ops Owner） |
| DEC-015 | UI Foundations | 系统字体、4px 网格、390/768/1280、WCAG 2.2 AA、单一正式组件与蓝色主操作语义 | `APPROVED` | `BUILD_G0` | Liu Mowen（初始 Design + Frontend Owner） |
| DEC-016 | P0 内容与评审 | 只发布 TSK-001“问题洞察与行动建议”；四维 Rubric 全部达标才 PASS；Reviewer SLA 2 个工作日 | `APPROVED` | 真人校准 `G4` | Liu Mowen（初始 Product + Content + Reviewer Owner） |
| DEC-017 | Alpha/RC 附件边界 | 当前 Alpha/RC 只使用无附件的 `TSK-001 V1`，staging 固定 `ATTACHMENTS_ENABLED=false`；V2 附件能力不进入当前范围，未来启用前必须重开并完成 WP-10 五项物理门禁 | `APPROVED` | 当前范围 `G4`；未来附件启用前置门禁 | Liu Mowen（Product + Security + Tech Owner） |
| DEC-018 | Alpha 可观测与通知延期边界 | Alpha 阶段延期 TLS 外部日志采集、真实通知和告警演练；保留无业务写入的有界主机审计作为临时观测手段，允许启动 WP-12；三项延期证据仍为 `NOT_RUN`，WP-11 不得记为完整验证，production 继续 `NO_GO` | `APPROVED` | Alpha WP-12 激活；production 前置门禁不变 | Liu Mowen（Product + Security + Tech + Ops Owner） |
| DEC-019 | Alpha 灾备故障域延期边界 | Alpha 期间不选择跨地域或其他独立灾备故障域；待真实 Alpha 开放后连续稳定运行 30 个自然日再重开选型。基础备份、恢复可用性、数据完整性与 RPO/RTO 工程工作不取消；异机/独立故障域恢复继续 `NOT_RUN`，WP-12 不得记 `RC_TECHNICALLY_READY`，production 继续 `NO_GO` | `APPROVED` | Alpha 可继续非故障域 WP-12 与真人 UAT；production 恢复门禁不变 | Liu Mowen（Product + Data + Tech + Ops Owner） |
| DEC-020 | Alpha 性能条件放行 | 候选 `02863d0b670ee9b00b9def3e75bc6699827f555a` 的 WP-12B run `30525165474` 保持原 1 秒合同 `FAIL`；仅为启动 WP-13 真人 UAT，接受核心同步命令 p95 ≤1.2 秒的候选级条件边界。该 run 的隔离、正确性、数据库审计、身份退役和 SSH 关闭必须全部保持 PASS；候选漂移立即失效。DEC-013 的 production p95≤1 秒不变，WP-12B 不记 `CLOSED`，production 继续 `NO_GO` | `APPROVED` | 允许该候选启动 WP-13；不授权 WP-14、production、重跑负载或再次部署 | Liu Mowen（Product + Tech + QA/UAT Owner） |
| DEC-021 | WP-13 Web 修复候选重绑定 | 主线 `222096db506e95db887a8705b22ca4a439d0545d` 相对已测候选仅改变 Web 运行代码；API、Worker、迁移、OpenAPI、Python/Web 锁文件及 Compose 内容保持一致。允许沿用 WP-12B run `30525165474` 的原始 FAIL 与 DEC-020 的 Alpha ≤1.2 秒条件证据来准备新候选 UAT 绑定，不重跑 WP-12B。Mainline run `30550010916` 生成并验证三镜像；在该候选完成一次独立授权的 staging 部署、readiness/版本核对和部署 run 绑定前，真人 UAT 不得恢复，production 继续 `NO_GO` | `APPROVED` | 仅批准影响核对、候选生成和 pending UAT 重绑定；不授权部署、UAT 恢复、WP-14 或 production | Liu Mowen（Product + Tech + QA/UAT Owner） |
| DEC-022 | 2026-08-03 受控 Alpha 上线 | 停止把完整 production 门禁作为 Alpha 使用前置。候选 `8f77ceec570e2ec5e9c52861fcdc27748d7bb44a` 仅在一次冻结基础设施 staging 部署成功，并完成 readiness/revision、真实邀请、提交、要求修订、安全重新进入和越权拒绝的 20 分钟最小核验后，向单一组织私密名单开放真实使用。附件、真实通知、WP-12B 重跑、灾备故障域和 production 切换继续延期；正式 UAT 未完成、production 继续 `NO_GO` | `APPROVED` | 仅允许受控 Alpha 使用；部署仍需候选、主线、环境和次数的当轮精确授权 | Liu Mowen（Product + Tech + QA/UAT + Release Owner） |
| DEC-023 | 受控 Alpha 正式域名切换 | 候选 `8f77ceec…` 已完成一条真实“提交→要求修订→安全重新进入→再次提交→通过”闭环。允许以 `journey.muchenai.com` 作为单一组织私密名单的正式 Alpha 入口：production Compose/DB/application secrets 与 staging 逻辑隔离，现阶段共享北京 ECS/RDS/Caddy 故障域；先完成加密异机备份和空库隔离恢复，再配置 TLS/OAuth/canonical URL；维护页为一键止血，旧站 DNS 仅作入口级回退，禁止回写或覆盖 vNext 新事实；staging 永久保留。该决定不把 WP-13 全量签署、WP-14、WP-11 延期项、WP-12B 原 FAIL 或完整 production release gate 记为通过 | `APPROVED` | 授权本手册三项最小切换动作；仍限单组织 Alpha，30 日后重开故障域 | Liu Mowen（Product + Data + Security + Tech + Ops + Release Owner） |
| DEC-024 | 正式探索营产品真相恢复 | 当前 TSK-001 是验证 vNext 闭环的 Alpha 切片，不代表正式探索营全部产品。正式目标固定为 Day 0、四个认知宝藏、三个能力评测和完整结果；旧前端所谓“第五个宝藏”是能力准入容器，不是独立宝藏。后续只在 vNext Identity/Enrollment/Task/Submission/Review/Outcome 基座上增加版本化 Journey 编排，不复用旧代码、路由、状态、数据库或运行时 | `APPROVED` | WP-18 产品合同生效；当前 Alpha 历史不变；WP-19 实现前需 schema/API/迁移评审 | Liu Mowen（Product + Content + Design + Tech + Data + QA Owner） |
| DEC-025 | 正式探索营 V2 内容、评分与准入 | 以完整正式方案而非最小技术切片为内容事实源：10:00–19:00 先完成 Day 0 与四个学习宝藏，再完成规则拆解、模型回答判断和通用数据构建三项真实题面；边界识别与提报是横向能力，不是第三项独立评测。固定 100 分只形成 A/B/C/D 建议，最终下一阶段准入必须由授权 Operator 基于证据人工决定；覆盖建议必须记录理由，系统不得自动淘汰或录用。V1 与既有事实不可变，V2 以新版本发布 | `APPROVED` | 授权 WP-24 本地实现和 PR；不授权业务发布、邀请、部署或现有 Enrollment 迁移 | Liu Mowen（Product + Content + Design + Tech + Data + QA Owner） |
| DEC-026 | 探索营 P0 真人体验优先与受控上线 | 不再按视觉/数据/后台/页面的技术层顺序建设；先冻结真实材料和完整可点击体验，每个工作包均以真人可感知结果退出，只在单宝藏闭环通过后扩展四宝藏和三评测。路线节点共享坐标、Learner 页面执行文字预算；最小权限 Content Editor 导入结构化文本/HTTPS 链接，经 Operator 发布不可变 Journey V3；WP-10 附件保持关闭。P0 上线仅指 `journey.muchenai.com` 单组织私密 cohort，不等同完整 production GO | `APPROVED` | 2026-08-04 只开放 WP-25 内容/原型/真人验证；产品代码、外部写入、WP-26 及以后仍未授权 | Liu Mowen（Product + Content + Design + Security + Tech + QA Owner） |

> Owner 说明：仓库使用操作系统账号对应的项目发起人标识 `Liu Mowen` 作为初始责任人。真实试点参与者采用受控名册，不把姓名或外部身份标识提交到 Git。真人 UAT、Reviewer 独立性和生产双人批准必须在 G4 以独立证据确认，当前均为 `NOT_RUN`。

## 3. 决策说明与选择框架

### DEC-004｜为什么推荐只做探索营

上一轮同时承载探索营、新手村、AI 学院、Talent OS 和旧后台，导致路由、权限、状态和验收呈乘法增长。探索营具备清晰的真实新人 + 真实主管闭环，足以验证 Identity、Assignment、Submission、Review、Outcome、Notification 和运维基础，不需要先建立多空间平台。

若 P0 加入第二空间，Product Owner 必须证明它是同一闭环不可缺的步骤，而不是“既然重做顺便一起做”。

### DEC-005｜同栈不等于同系统

继续使用相同公开技术栈可降低团队学习成本，但必须通过新 repo、空白配置、新迁移、独立资源和禁止源码复用证明独立。如果技术 discovery 发现当前栈本身无法满足团队能力/部署/性能，再用小原型比较，而不是通过换栈掩盖边界问题。

### DEC-006｜身份选择标准

比较：用户进入阻力、是否必须企业飞书身份、非员工/候选人适用性、主管授权来源、安全与运营成本。无论选择哪一项，vNext 内部 UUID 和独立 session 不变。

### DEC-011｜交接不应重新耦合旧系统

P0 可以输出“handoff ready + 明确责任人/说明/外部链接”，但不能为了自动进入旧新手村而在 vNext 引入旧 API、旧 session 或共享状态。未来后续系统集成需独立 ADR/API 合同。

### DEC-017｜为什么 Alpha/RC 不启用附件

当前种子 Assignment 固定 `TSK-001 V1`，该版本的附件类型为空、大小上限为 0；结构化文本已能完成真实学习与评审闭环。为可选附件新增扫描运行时、IAM/CORS、对象生命周期和恢复证明，会消耗当前预算与工程 WIP，却没有真实用户阻塞证据。Alpha/RC 因此把附件作为明确的未激活能力：页面和 API 同时 fail closed，不能把“禁用”表述为 `FILE_SECURITY_VERIFIED`。若真实试点证明文件是完成任务的必要条件，必须先重开 WP-10，完成其五项物理门禁，再发布和分配新的 TaskVersion；不得修改在途 V1 Assignment。

### DEC-018｜为什么 Alpha 延期外部日志与真实通知

当前候选已证明通知失败不会改写业务事实、无接收人时 Worker 不会错误消费通知，并能通过无业务写入的有界主机审计确认 API/Worker 运行与脱敏日志。继续修补 TLS provider 采集路径、配置真实接收人或发送测试消息，不会更快验证新人提交与主管评审的核心用户问题，反而会继续占用单一 WIP。

因此 Alpha 只延期 TLS 外部日志采集、真实通知和告警演练，并允许 WP-12 进入候选硬化与灾备开发。延期不是豁免或通过：三项证据继续标记 `NOT_RUN`，WP-11 结论继续包含 `INTEGRATIONS_AND_OBSERVABILITY_NO_GO`；临时主机审计必须有界、只读、脱敏且不得配置接收人或发送消息。进入 production 前，必须由后续明确决策恢复并关闭这些门禁，或提出经 Security/Ops/Release 批准的等效生产观测方案；在此之前 production 始终 `NO_GO`。

### DEC-019｜为什么延后灾备故障域选型但不取消基础恢复

当前 Alpha 的首要问题是证明新人提交、主管评审和结果交接能稳定解决真实用户问题。此时提前选择跨地域、跨账号或其他独立故障域，会引入持续费用、KMS/复制权限、保留策略和恢复编排，但还没有一个月真实运行数据用于判断需要保护的实际数据量、恢复频率和运营能力。

因此 Alpha 暂不选择灾备故障域。重新开启条件定义为：真实 Alpha 实际开放并由 Owner 登记起始日后，连续 30 个自然日没有 Sev-1/Sev-2、不可逆数据丢失或核心闭环长时间不可用；任一上述事件会中断并重新开始计时。30 日成熟检查点只能触发选型评审，不能自动把门禁改为通过。

延期只覆盖跨地域/独立故障域副本和相应隔离恢复演练。数据库受管备份事实核对、备份可读性、schema/计数/约束/业务指纹校验、恢复脚本的本地或临时隔离测试，以及 RPO/RTO 预算分析仍属于 WP-12。异机恢复证据继续为 `NOT_RUN`，release gate 的 `off_host_backup_restore` 阻塞保持不变；在独立故障域选定并完成真实隔离恢复前，WP-12 不得记 `RC_TECHNICALLY_READY`，production 继续 `NO_GO`。

### DEC-020｜为什么允许 Alpha 真人 UAT 但不改写性能失败

run `30525165474` 在北京现有 ECS 内完整执行 20 组织、500 Learner、50 峰值并发和 10,561 个请求。HTTP 5xx、409、跨组织泄漏、意外响应、数据库重复/缺失/跨组织错配均为 0；560 个合成会话和用户全部退役，SSH 已关闭。原 1 秒合同仅有 `learner.submission_create=1.011632s` 与 `reviewer.review_finalize=1.097447s` 两项 p95 失败，其余端点通过。

把该 run 追认成 `PASS` 会破坏证据真实性，继续为约 0.1 秒差距重复部署和合成负载又不能更快验证真实用户问题。因此本决策保留 WP-12B=`FAIL/NOT_CLOSED`，只为同一已部署候选建立 p95≤1.2 秒的 `CONDITIONAL_PASS_FOR_ALPHA`，允许启动 WP-13。该边界不是 DEC-013 的替代品：WP-14 不自动启动，RC/production 仍须满足原 1 秒 SLO 或由新的生产级决策明确替代；任何候选、部署或规模变化都必须重新评估。

### DEC-021｜为什么 Web 修复不重跑后端负载

`UAT-WP13-001` 的根因是 `/ops` 缺少邀请入口。候选差异核对证明 `apps/api`、`apps/worker`、`migrations` 的 Git tree，以及 OpenAPI、Python/Web 锁文件与 Compose blob 均和候选 `02863d0…` 完全一致；运行态新增只包含邀请入口的 Web UI/Server Action，并复用既有 scoped invite API。重新执行 20 组织/500 Learner 的后端负载不会增加与该缺陷相关的证据，反而会消耗试点时间。

因此 DEC-021 允许为候选 `222096db…` 继承 run `30525165474` 的原始结果：1 秒合同仍为 `FAIL`，仅 Alpha ≤1.2 秒条件边界可继续使用。full deploy run `30556851235` 和首个 repair run `30595486997` 的失败事实保持不变；只读 inventory run `30598785077` 证明实际 prestate 后，主线 `100e8949…` 的唯一 repair run `30616573615` 成功将 API/Worker/heartbeat 恢复为 `02863d0…`，Web 保持 `222096db…`、migration=`0014`、schema=3、API ready、Worker 非 stale，公开 root=200、匿名 `/ops`/`/review`=401 且 SSH 已关闭。该 run 现绑定为 WP-13 技术入口；不追认 WP-12B 通过、不替代真人 UAT，也不改变 production `NO_GO`。

### DEC-022｜为什么受控 Alpha 不再等待全部 production 门禁

真实用户闭环已经能够完成邀请、任务、提交和主管评审，当前最高信息价值来自小规模真实使用，而不是继续重复基础设施修补、合成负载或扩大 UAT 组合。Alpha 上线前仍保留身份授权、业务事实完整性和可恢复运行所需的最小核验；这些是阻止真实伤害的底线，不是追求测试完备性。

候选 `8f77ceec…` 只改变 Learner 安全重新进入所需的 Web/API 身份路径，migration、TaskVersion、依赖锁文件和 Compose 不变。DEC-022 因此允许在精确候选部署成功后，以单一组织私密名单开始真实使用，并将非阻塞体验问题转入上线反馈队列。该决定不把 WP-13 正式真人 UAT、WP-12B、外部观测、通知、恢复或 production release gate 改记为通过。

### DEC-023｜为什么正式域名可以先服务受控 Alpha

当前旧站没有活跃学员，而 vNext 已由真人完成一条包含修订的完整业务闭环。继续把域名切换绑定到所有延期门禁，会推迟真实问题学习；直接把 staging 域名改名，又会失去安全测试环境并混合真实数据。最小可逆方案是保留同一低成本物理资源，在其内建立独立 production Compose、数据库和应用 secret，由同一个 Caddy 按 Host 分流，staging 持续在线。

这一方案只提供逻辑隔离，不提供独立故障域。它必须先完成源库只读备份、空白 production 库隔离恢复、加密异机保存和恢复事实一致性证明；正式域名只能在 TLS、OAuth 回调、allowed host 和 canonical URL 同时正确后切换。发生安全或数据完整性问题时先一键维护，不用旧备份覆盖新事实；旧站 DNS 只恢复入口，不恢复旧站为事实源。完整 production GO 仍需后续 WP-13/14/15 证据，不因域名变更自动获得。

2026-08-03 执行结果：run `30760806984` 的备份、隔离恢复、事实比对和加密解密证明通过，但工作流因 TOS `InvalidPathAccess` 归档失败而保持 `failure`；run `30761088830` 随后只读复核同一密文并成功保存为 30 天私有 Actions artifact。正式回调保存后，`journey` A 记录切至北京 vNext ECS。首次 TLS 握手因边缘容器早于 DNS 切换启动而未触发新证书申请；只读诊断 PR #127 合入后，maintenance run `30779397520` 只重建 edge 并成功签发 `journey.muchenai.com` 证书，维护页返回 503。live run `30779441351` 随后恢复 production Web；公开根页与 readiness 为 200/精确候选，匿名 `/ops`、`/review` 均为 401，OAuth `redirect_uri` 为正式回调，staging 继续 200。该事实把 DEC-023 记为 `CONTROLLED_ALPHA_LIVE`，不改变完整 release gate 的 `NO_GO`。

### DEC-024｜为什么必须恢复正式产品真相

单个 TSK-001 成功证明了 vNext 的身份、当前行动、不可变提交、评审、修订和结果基座，但没有证明它就是完整探索营。继续在单任务模型上只做视觉包装，会把技术风险收缩错误地固化为产品范围，并丢失探索营原本承担的“先建立认知基础，再观察三类真实能力”的价值。

旧归档的后端业务门禁实际要求 Day 0、四个认知宝藏和三道实操；部分前端把能力准入容器计作第五个宝藏，属于展示口径漂移。因此正式口径锁定为四加三。恢复的是产品目的、内容身份和顺序，不是旧实现：vNext 仍是唯一事实源，TSK-001 历史保持有效，旧代码/路由/数据仍受 Greenfield 隔离合同禁止。详细重接合同见 34 号文档。

## 4. 风险台账

| ID | 风险 | 概率/影响 | 早期信号 | 预防/缓解 | Owner |
| --- | --- | --- | --- | --- | --- |
| RSK-001 | 范围重新扩到多空间/平台 | 高/高 | PRD 出现 Academy/Village/Registry 空框架 | DEC-004；非目标；G0/DoR 拒绝 | Product |
| RSK-002 | 偷偷复用旧代码/适配器 | 高/高 | import、复制文件、旧 env/URL 出现 | ISO scan；空 runner；code review | Tech |
| RSK-003 | 新库仍连接/复制旧 schema | 中/高 | migration 从 0017 继续、旧表名/enum | 独立 DB ACL；0001；schema review | Data/Tech |
| RSK-004 | 旧系统变成 fallback | 高/高 | 错误时建议回旧页面/恢复旧写入 | DEC-002；网关外部切换；rollback 演练 | Product/Ops |
| RSK-005 | 身份方案迟迟变化 | 高/高 | join/SSO/绑定页面反复重写 | DEC-006 先做真实 prototype/discovery | Product/Security |
| RSK-006 | 历史导入拖垮新模型 | 高/高 | 要求 1:1 搬表、在线双读 | DEC-009；中性包；quarantine | Data/Product |
| RSK-007 | Agent/分支并行失控 | 高/高 | 多 worktree 改共享合同、候选漂移 | WIP 上限；单 Owner；唯一 RC | Tech |
| RSK-008 | 验收 harness 再次膨胀 | 中/高 | 单个 smoke 上千行、失败归属不明 | 小 runner + 场景文件；分层 gate | QA/Tech |
| RSK-009 | 时间压力绕过 G0/UAT | 高/高 | “先上线再补文档/真实用户” | No-Go 清单；Owner 签字；日期服从门禁 | Product |
| RSK-010 | 真用户/主管不可用 | 中/高 | 自动化全绿但无人做 UAT | DEC-007 在 G0 锁人和时间 | Product/QA |
| RSK-011 | 主管权限/班级 scope 不清 | 中/高 | 前端筛选代替后端授权 | 权限矩阵；真实组织样本；负向测试 | Product/Security |
| RSK-012 | AI 引入隐私/结论风险 | 中/高 | 完整正文发送、AI 结果直接 PASS | DEC-012；advisory-only；数据最小化 | Security/Tech |
| RSK-013 | 独立基础设施无人维护 | 中/高 | 新 env/备份/告警长期 TBD | DEC-003/013/014 指名 Owner | Ops |
| RSK-014 | 同栈导致无意识复制旧模式 | 中/高 | route registry、adapter、P0/V2 命名重现 | ADR review；forbidden pattern scan | Tech |
| RSK-015 | 过度文档化、决定仍不落地 | 中/中 | 文档更多但 TBD 不关闭 | G0 只看阻塞项和签署；限时决策会 | Product/Tech |
| RSK-016 | 新系统上线后 bug 继续上升 | 中/高 | RC 后 Sev-2 增长、同类 bug 3 次 | 停止规则；根因/门禁复盘；冻结功能 | QA/Tech |
| RSK-017 | 未完成物理文件门禁即误启用附件 | 中/高 | staging 配置或新 TaskVersion 出现附件类型/额度 | DEC-017；`ATTACHMENTS_ENABLED=false`；启用前重开 WP-10 五项门禁与新版本评审 | Product/Security/Tech |
| RSK-018 | Alpha 延期被误解为生产观测已通过 | 中/高 | 文档或发布门禁把 TLS/真实通知/告警标为 `VERIFIED`，或无外部观测即申请 production | DEC-018；三项保持 `NOT_RUN`；WP-11 保持 `NO_GO`；production release gate 拒绝 | Product/Security/Ops/Release |
| RSK-019 | 灾备故障域延期演变为无期限无恢复能力 | 中/高 | 没有登记 Alpha 起始日；30 日后不评审；把受管备份存在等同于隔离恢复通过 | DEC-019；30 日成熟触发器；严重事故重新计时；基础备份/恢复工程不停；`off_host_backup_restore` 保持阻塞 | Product/Data/Ops/Release |
| RSK-020 | Alpha 条件放行被误写成性能门禁通过 | 中/高 | 文档出现 `WP12B_CLOSED`、候选漂移后继续 UAT，或以 1.2 秒申请 production | DEC-020；保留原 run FAIL；WP-13 计划精确绑定候选；production 继续执行 DEC-013 的 1 秒 SLO | Product/Tech/QA/Release |
| RSK-021 | pending 候选重绑定或混合组件版本被误当成已部署 | 中/高 | Web readiness 为新 SHA，但 API/Worker/migration 仍为旧基线或 Worker stale；新 UAT 证据引用失败 run | DEC-021；组件级 Web-only + runtime-repair 合同；deployment run 为空时 resume=false；Web/API/Worker/migration/HTTP 全部通过后才单独 PR 激活 | Product/Tech/QA/Release |
| RSK-022 | 受控 Alpha 正式域名被误解为完整 production GO | 中/高 | 对外扩大名单、关闭 staging、把延期门禁写成 PASS，或共享 ECS/RDS 故障被当作独立灾备 | DEC-023；入口标记受控 Alpha；逻辑隔离、异机加密备份、维护模式、私密名单和 30 日故障域复审 | Product/Data/Security/Ops/Release |
| RSK-023 | 最小技术切片被误当成正式产品 | 高/高 | 继续只为 TSK-001 做视觉包装；路线点与正式阶段无对应；无法解释四宝藏和三评测去了哪里 | DEC-024；34 号合同；TSK-001 重定位；WP-19～23 单一 WIP | Product/Content/Design/Tech |
| RSK-024 | 量化评分被误当成自动淘汰或录用 | 高/高 | 达到阈值即自动准入；低分自动关闭身份；人工看不到证据或无法覆盖建议 | DEC-025；preview 与最终决定分离；覆盖理由；决定不可变；不得触发消息/身份/人事动作 | Product/Content/QA/Security/Tech |
| RSK-025 | 视觉叙事继续被独立坐标和重复文案破坏 | 高/中 | 路线点漂浮、同一动作在标题/说明/按钮/页脚重复、用户需口头解释入口 | WP-25 完整原型和真人定向先行；WP-26 起共享 SVG 坐标、文字预算、三视口与逐包真人验收 | Product/Design/Frontend/QA |
| RSK-026 | 为导入材料授予过宽运营权限 | 中/高 | 内容负责人可创建邀请、查看他组织、修改身份或直接发布 | DEC-026；最小 Content Editor capability；私密名册；Operator 最终发布；权限负测 | Product/Security/Tech |
| RSK-027 | 点击或停留时间被伪装成学习效果 | 高/高 | 自动滚动即完成、计时到点即解锁、material completion 直接 PASS/准入 | WP-26/27；显式完成事实只证明确认材料；小任务和 Reviewer 负责理解证据 | Product/Content/QA/Tech |
| RSK-028 | 内容导入绕过附件与外部内容安全 | 中/高 | 上传 PDF/视频、服务端抓取任意 URL、复制未授权材料或记录外部身份 | WP-10 保持关闭；仅清洗文本和 HTTPS 链接；不抓取/嵌入；来源与版权复核 | Content/Security/Tech/Privacy |
| RSK-029 | 工作包再次按技术层完成而不是用户结果完成 | 高/高 | 数据/组件/后台分别 PASS，但没有真人完成当包价值；问题集中到最后 UAT | DEC-026；WP-25 内容/原型先行；WP-26 单宝藏纵向切片；每包真人门禁；代码不得领先真人证据一个包以上 | Product/Tech/Design/QA |
| RSK-030 | 无止境内测推迟真实上线 | 高/中 | 每轮加入新偏好和增强项、重复全量回归、没有最后 UAT 和上线判定 | WP-29 是最后完整上线前 UAT；只让 P0 blocker 阻断；修复后重验受影响路径；增强项进入真实使用 backlog | Product/QA/Release |

## 5. 原开放问题的关闭结论

| 原问题组 | 关闭结论 | 约束来源 |
| --- | --- | --- |
| 产品闭环、结果与成功标准 | 当前 Alpha 以 TSK-001 验证闭环；正式探索营为 Day 0 + 四宝藏 + 三能力评测 + 完整结果；通过后生成可追溯 Outcome/Handoff | DEC-004/010/011/016/024 |
| 身份与权限 | 邀请建立 vNext 身份；非本地 Reviewer/Operator 绑定独立飞书身份；Reviewer 按 organization + explicit assignment 授权；紧急纠错需 Operator 原因与审计 | DEC-006/014；08 号文档 |
| 数据与旧数据 | P0 对象全部新建，不导入旧业务事实或附件；保留/删除期限按 DEC-008 | DEC-008/009 |
| 技术、资源与运行 | 使用批准栈和 `journey-next-*` 独立资源；AI 不进 P0；SLO/RPO/RTO 与生产权限已锁定 | DEC-003/005/012/013/014 |
| UI、内容与运营 | 当前 Alpha 使用 TSK-001/Rubric V1；正式内容按四宝藏＋三评测重新审查、版本化发布和校准；两工作日 SLA 保留 | DEC-015/016/024；14/15/34 号文档 |
| 真人和物理证据 | 真实名册、资源 ACL、双人批准、恢复演练、UAT 与试点结果不是开放设计问题，作为 G4/G5 `NOT_RUN` 执行门禁保留 | DEC-003/007/010/013/014/016 |

## 6. G0 批准记录

2026-07-20 已完成构建方向批准：DEC-001–016 全部为 `APPROVED`。本次批准授权建立独立仓库、WP-00 与最小 walking skeleton；不授权绕过 G4/G5 的真人、生产、恢复或发布证据，也不扩大为同时建设全部 P0 模块。

2026-07-28 后续执行决策：Product Owner 明确批准 DEC-017，以当前 Alpha/RC 无附件范围关闭 WP-10；该批准不授权云资源、部署或未来附件启用，也不改变整体 `NO_GO`。

2026-07-28 后续执行决策：Product Owner 明确批准 DEC-018，在 Alpha 阶段延期 TLS 外部日志采集、真实通知和告警演练，保留有界主机审计并允许启动 WP-12。该批准不把延期项记为通过，不授权真实发送、业务接收人或 production 行为，production 继续 `NO_GO`。

2026-07-28 后续执行决策：Product Owner 明确批准 DEC-019，Alpha 期间延期灾备故障域选型，待真实 Alpha 连续稳定运行 30 个自然日后重开。该批准不取消基础备份/恢复工程，不关闭 `off_host_backup_restore`，不授权 production，也不把 WP-12 记为 `RC_TECHNICALLY_READY`。

2026-07-30 后续执行决策：Product Owner 明确批准 DEC-020，保留候选 `02863d0…` 的 WP-12B run `30525165474` 为原合同 FAIL，仅按 p95≤1.2 秒条件边界启动同一候选的 WP-13 真人 UAT。该批准不重跑 WP-12B、不再次部署、不启动 WP-14、不修改 DEC-013 production SLO，也不构成 production GO。

2026-07-31 执行结果：DEC-021 的唯一有界 repair run `30616573615` 已成功并消费授权；`deployment_run_id` 已绑定、`human_uat_resume_allowed=true`。这只恢复 WP-13 真人执行入口，不把任何人工场景、签署、WP-14 时间窗或 WP-15/production 门禁记为通过，production 继续 `NO_GO`。

2026-08-03 后续产品决策：Product Owner 明确批准 DEC-024，恢复正式探索营为 Day 0、四个认知宝藏、三个能力评测和完整结果。该批准关闭产品结构歧义并授权 WP-19 的设计输入，不授权直接复制旧代码/材料、部署、迁移现有 Learner、改写 Alpha 历史或跳过内容/Reviewer 校准。

## 7. 签署区

| 角色 | 姓名 | 已批准 DEC | 未批准 DEC | 结论 | 日期 |
| --- | --- | --- | --- | --- | --- |
| Product Owner | Liu Mowen | DEC-001..024 | 完整 WP-13/14 结果 | CONTROLLED ALPHA GO | 2026-08-03 |
| Tech Lead | Liu Mowen | DEC-001..024 | 独立生产故障域；WP-19 schema/API 评审 | CONTROLLED ALPHA GO | 2026-08-03 |
| Data Owner | Liu Mowen | DEC-001..016/019/023/024 | 独立故障域恢复；WP-19 migration 评审 | CONTROLLED ALPHA GO | 2026-08-03 |
| Design Owner | Liu Mowen | DEC-015/016/024 | 正式四加三真人 5 秒测试 | BUILD GO | 2026-08-03 |
| Security/Privacy | Liu Mowen | DEC-006/008/012/014/017/018/023 | 完整生产安全门禁 | CONTROLLED ALPHA GO | 2026-08-02 |
| QA/UAT | Liu Mowen | DEC-007/010/016/020..024 | 完整四加三真人 UAT | CONTROLLED ALPHA GO | 2026-08-03 |
| Release/Ops | Liu Mowen | DEC-003/013/014/018/019/023 | 完整发布/观察证据 | CONTROLLED ALPHA GO | 2026-08-02 |
