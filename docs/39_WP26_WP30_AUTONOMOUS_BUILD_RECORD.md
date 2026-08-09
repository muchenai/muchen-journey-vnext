# 39｜WP-26～WP-30 本地构建记录与待授权账本

状态：`STAGING_CANDIDATE_DEPLOYED / CONTENT_SOURCE_FROZEN / REVIEWER_REVIEW_OWNER_REPORTED / JOURNEY_V3_NOT_PUBLISHED / PRODUCTION_NO_GO`

版本：V0.4

日期：2026-08-09

依据：DEC-026、REQ-BR-016..018、AT-WP26-001..005、AT-WP27-001..005、AT-WP28-001..005、AT-WP29-001..005、AT-WP30-001..006

## 1. 结论先行

WP-26～WP-30 已完成可在本地诚实验证的产品与发布控制实现，但没有把机器通过写成真人通过：

- WP-26 已具备独立 Content Editor、组织隔离草稿、Operator 精确发布、固定学习材料、不可变完成事实和“材料未完成不得开始/提交”的服务端门禁；
- WP-27 已具备八站精确顺序的 Journey V3 组合入口，路线节点与线路共享同一坐标源；空材料、错顺序、跨组织或未发布 TaskVersion 均被拒绝；
- WP-28 已把学习完成、三项能力证据、Reviewer 人工结论、系统非决定建议和 Operator 人工准入分开；等待开始评审与正在评审也不再是同一显示事实；
- WP-29 已形成只接受固定候选、固定 V3、真人名册、真人签署和零 P0 blocker 的 fail-closed RC 验证器；验证器不能运行或伪造 UAT；
- WP-30 已形成受控上线 preflight、PII-free 每日指标与停止判定，并实现组织级新邀请冻结/恢复；冻结只阻止新邀请，不删除已有 Enrollment、提交、评审或重新进入事实。

当前没有发布 Journey V3、没有部署 production、没有创建 Journey V3 真人邀请、没有写入新云资源，也没有产生 `P0_RC_SIGNED` 或 `P0_LIVE_CONTROLLED`。staging 已在唯一 run `31261406217` 部署候选 `3b7d7573cd70b72868e427b523ff630b732f0603`；部署步骤成功，工作流末尾的外部验证发生竞态并使 run 标红，但随后同一公开合同立即通过且连续三次通过：根页 `200`、readiness 精确返回候选、匿名 `/ops` 与 `/review` 拒绝、匿名 `/content` 安全转入登录页。该事实不替代真人材料、复核或签署，正式 production gate 继续为 `NO_GO`。

## 2. 数据与 API 变化

| 工作包 | 新事实/合同 | 关键边界 |
| --- | --- | --- |
| WP-26 | `TaskVersion.learning_materials`、`LearningMaterialCompletion`、`ContentDraft`、`CONTENT_EDITOR` | Content Editor 只能编辑自己的同组织草稿；提交后正文由数据库拒绝改写；只有 Operator 能把精确草稿发布为新 TaskVersion |
| WP-27 | `POST /api/v1/ops/formal-journeys/assemble-v3` | 固定八个 stable key、精确顺序、同组织、已发布、每站至少一项 required material；不迁移既有 Enrollment |
| WP-28 | `GET /api/v1/me/result` 五层结果投影 | 系统建议始终 `advisory_only=true`；人工评分未输入时不制造推荐；Operator 决定不可变 |
| WP-29 | `scripts/wp29_p0_rc.py` 与固定合同 | PII/secret 字段拒绝；候选或 Journey 在 UAT 中变化即拒绝；自动模拟不能代替真人；P0 blocker 必须为 0 |
| WP-30 | `InvitationControl`、freeze/resume API、上线/指标验证器 | 初次 revision 0 可原子建立控制；写入仍需 Operator、理由、幂等键与 expected revision；恢复新邀请是独立命令 |

Migration head：`0019_wp30_invitation_control`。

## 3. 机器证据

本次已取得：

- 空测试 schema `0001 → 0019` 升级通过；
- `0019 → 0018 → 0019` 升降级通过；
- WP-26 Content Editor、材料门禁与不可变性定向测试通过；
- WP-27 V3 八站组合、空材料与错序拒绝定向测试通过；
- WP-28 完整 Journey 结果/准入定向测试通过；
- WP-29/WP-30 合同与负向验证 11 项通过；
- WP-30 邀请冻结、事实保留和显式恢复端到端测试通过；
- 空库全量 API/Worker 回归 `306 passed`；
- Web TypeScript、ESLint、17 项静态交互合同与 Next.js 生产构建通过；
- 真实浏览器桌面与 390px 移动视口复验通过：Content Editor 与 Operator 页面可读可操作；WP-27 路线改为 SVG 单坐标系，点、线和标签在严格 CSP 下不再因内联样式被剥离而漂移；
- runtime OpenAPI 与 `contracts/openapi.json` 一致。
- Greenfield isolation、traceability、gitleaks 和 Web dependency audit 通过；gitleaks 扫描约 4.98 MB、无泄漏，Web 漏洞包为 0。

Python `pip-audit` 因临时 PyPI TLS EOF 未能安装审计器，诚实记录为 `NOT_RUN_NETWORK_FAILURE`；不得把网络失败写成无漏洞，形成 PR 后仍需复验。以上机器证据不能替代真人内容、体验或签署。

2026-08-09 Journey V3 发布准备文档变更再次执行本地 Fast Gate：traceability、isolation、staging workflow、WP-29/WP-30 fail-closed 合同、gitleaks 和 Web dependency audit 均通过；完整 API 为 `306 passed / 2 skipped`，OpenAPI 与仓库合同一致，数据生命周期检查无写入，Web 为 `22/22`。Python `pip-audit` 已安装但访问外部漏洞索引持续无响应，超过有界等待后终止，记为 `NOT_RUN_NETWORK_TIMEOUT`；其余通过项不得被用来推断该项通过。

## 4. 真人门禁账本

| 工作包 | 仍需真人完成 | 当前状态 |
| --- | --- | --- |
| WP-26 | Content Editor 在产品内导入并提交一个真实宝藏；2 名 Learner 完成学习→小任务→修订/恢复；独立 Reviewer 复核 | `SOURCE_FROZEN / PRODUCT_IMPORT_NOT_READ_BACK / HUMAN_LOOP_NOT_RUN` |
| WP-27 | Operator 发布八个精确 TaskVersion 和 Journey V3；目标 Learner 验证路线理解、文字预算与无死路 | `SOURCE_FROZEN / JOURNEY_V3_NOT_PUBLISHED / HUMAN_ROUTE_NOT_RUN` |
| WP-28 | 2 名独立 Reviewer 校准三题；至少 1 名 Learner 完成真实修订；Operator 作出人工准入 | `REVIEWER_REVIEW_OWNER_REPORTED / RESULT_COPY_DRAFTED / HUMAN_LOOP_NOT_RUN` |
| WP-29 | 1 Content Editor、1 Operator、≥3 Learner、2 Reviewer、1 QA Recorder 完成 10:00–19:00 固定候选 UAT 与六方签署 | `HUMAN_UAT_NOT_RUN / UNSIGNED` |
| WP-30 | 正式域名 readback、名单正负测、回退/维护演练、首批 cohort 与真实观察窗 | `NOT_STARTED / AUTHORIZATION_REQUIRED` |

任何一项表格、聊天确认或自动化输出都不能替代上述真人观察和签署。

## 5. 六小时后待授权事项（严格按顺序）

2026-08-05 Owner 已明确同意本节全部待授权事项。该授权允许按以下顺序推进，但不把尚未发生的真人材料、独立复核、UAT、六方签署、正式域名 readback 或观察窗口写成通过；任何前置门禁失败即停止，production 在 `P0_RC_SIGNED` 前继续 `NO_GO`。

1. 审阅并合入本地 PR；合入本身不部署。`DONE`：PR #148 已通过 Fast Gate 并合入主线 `a2312b269b1806cd3d5ce7d26fbc693466399035`。
2. 在 staging 创建/绑定真实 Content Editor；不读取通讯录，不扩大其他身份。`IDENTITY_LINKED / ANONYMOUS_ENTRY_RECOVERY_CANDIDATE_READY`：受控历史身份迁移、新链接和本人 OAuth 已完成，机器读回确认身份为 `LINKED`；PR #154 已修复 `/content` callback cookie 转发，PR #156 又为匿名 `/content` 增加同源登录入口，当前等待候选绑定与新的部署授权。
3. `SOURCE_FROZEN / REVIEWER_REVIEW_OWNER_REPORTED`：唯一正式内容源已固定为 38 号文档第 2 节的飞书表格，Owner 已声明 Reviewer 完成复核，三类结果文案 V0.1 已写入施工文档。产品内导入、Operator 确认和不可变版本读回尚未执行。
4. `STAGING_DEPLOYED / PUBLIC_CONTRACT_VERIFIED`：Mainline Candidate Gate `31259643008` 已生成候选 `3b7d757…`；唯一 staging run `31261406217` 完成部署并关闭 SSH。末尾外部验证竞态保留为原始失败；随后 exact public contract 立即及连续三次通过。没有重试、Terraform、DNS、云资源、WP-12B、消息、邀请或 Journey V3 发布。
5. 下一单一 WIP 是：Content Editor/Operator 仅从唯一正式内容源形成八个新 TaskVersion，逐项只读核对 stable key、版本、required materials 和摘要；不得把表格 `DAY-1` 误建为第九站，不得修改 V1/V2 或在途事实。
6. 八个 TaskVersion 读回无误后，另行取得一次精确授权，由 Operator 组合并发布 Journey V3；不迁移 V1/V2 Enrollment，不自动创建邀请。发布后只读读取 JourneyVersion 版本、八站顺序、TaskVersion ID 摘要、Reviewer 和复核记录。
7. 依次执行 WP-26、WP-27、WP-28 真人门禁；失败保留原证据，只修 P0 blocker。
8. 固定候选与 V3 后执行 WP-29 整日 UAT；只有私密证据通过验证器并完成六方签署，才可形成 `P0_RC_SIGNED`。
9. 另行授权 production deploy、DNS/TLS/OAuth readback、私密邀请和回退演练；每项授权单独消费，不打包推定。

## 6. 上线停止条件

以下任一事实出现，立即冻结新邀请：业务事实丢失、跨组织访问、持续登录失败、核心闭环中断或 P0 事件。冻结不撤销已接受邀请，不删除已有业务事实；恢复必须由 Operator 以新理由和新 expected revision 明确执行。

`P0_LIVE_CONTROLLED` 只在固定候选、固定 V3、正式域名、私密名单和回退能力完成真实 readback 后成立；`P0_VALIDATED` 只能在 cohort 结束后依据真实分子/分母判断。

## 7. Content Editor 历史飞书身份迁移修复

2026-08-05，真实 Content Editor 首次使用绑定链接时，OAuth 命中此前按 WP-09 合同撤销的 Reviewer 外部身份并返回 `IDENTITY_REVOKED`。只读核验证明：目标 Content Editor 仍为 `UNLINKED`；历史身份原角色为 Reviewer、有效会话为 0；当前 Reviewer 已使用另一条后来验证的有效身份。账号持有人随后由 Owner 明确确认为目标 Content Editor 本人。

本次修复不允许直接清除 `revoked_at` 或绕过本人验证：

1. Operator 只能选择同组织、已撤销、来源仍有独立有效身份、来源角色为 Reviewer、且无任何未撤销会话的历史飞书身份；
2. 目标必须是同组织、ACTIVE、尚无任何飞书映射的 Content Editor，且不能存在未过期绑定链接；
3. 迁移命令只转移历史身份归属并增加 revision，身份继续保持 `REVOKED`；命令要求 expected revision、幂等键、至少 10 字理由和显式账号归属确认，并写入脱敏审计；
4. 迁移后必须由 Operator 新建撤销时间之后的一次性绑定链接，并由账号持有人本人重新完成飞书 OAuth；只有这一步才清除撤销状态、轮换会话并写入独立重新激活审计；
5. 撤销前生成的旧链接、跨组织目标、错误角色、目标已有映射、来源无独立有效身份或任何未撤销会话全部 fail closed。

本地复验：API `308 passed`；Web 合同 `19 passed` 且 Next.js production build 通过；OpenAPI readback、隔离检查、traceability 与 gitleaks 均通过。

PR #152/#153 已完成受控身份迁移实现、候选绑定和唯一 staging 部署；Operator 随后完成迁移和新链接，本人 OAuth 的机器读回确认身份为 `LINKED`。PR #154 修复 `/content` OAuth callback；PR #156 增加匿名 `/content` 的同源登录恢复与真实浏览器合同；PR #157 仅固定 `nanoid 3.3.17` 以关闭新出现的安全公告。新主线 `3b7d7573cd70b72868e427b523ff630b732f0603` 的 Mainline Candidate Gate `31259643008` 已完成完整 CI、SBOM、候选 manifest、三镜像 GHCR push 与远端 digest 复验，migration 保持 `0019_wp30_invitation_control`。唯一 staging deploy run `31261406217` 已部署该候选并关闭 SSH；末尾外部断言竞态导致 run 标红，但运行态 exact public contract 随即及连续三次通过。当前不需要再次部署；下一项是内容版本与 Journey V3 发布准备。

## 8. Journey V3 发布准备冻结

- 唯一正式内容源、八站/十六材料映射和三类结果文案见 38 号文档第 2 节；旧 Base、Wiki、PDF 或本地 seed 只可用于差异说明，不得成为第二内容源。
- Journey V3 只能绑定以下顺序：`DAY-0`、`TRE-001-COMPANY-VALUES`、`TRE-002-AI-DATA-BASICS`、`TRE-003-PROJECT-AWARENESS`、`TRE-004-DELIVERY-FIT`、`ASM-001-RULE-BREAKDOWN`、`ASM-002-MODEL-JUDGEMENT`、`ASM-003-DATA-CONSTRUCTION`。
- 每个站点必须选择一个同组织、已发布、至少含一项 required material 的不可变 TaskVersion；八个 ID 必须唯一，顺序错误或缺材料必须 fail closed。
- Reviewer 复核目前只有 Owner 陈述；发布动作必须再次显式选择真实独立 Reviewer、填写不少于 20 字的复核记录并勾选确认。该机器事实成功后才可写为 `REVIEW_BOUND`。
- 施工文档完成不授权发布。下一次外部写入必须精确限定为“发布八个 TaskVersion”或“组合发布 Journey V3”其中一项；不创建邀请、不发送消息、不改变 production。
