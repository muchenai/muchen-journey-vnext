# 39｜WP-26～WP-30 本地构建记录与待授权账本

状态：`MAINLINE_MERGED / OWNER_AUTHORIZATION_RECEIVED / STAGING_CANDIDATE_BINDING / HUMAN_GATES_NOT_RUN / PRODUCTION_NO_GO`

版本：V0.2

日期：2026-08-05

依据：DEC-026、REQ-BR-016..018、AT-WP26-001..005、AT-WP27-001..005、AT-WP28-001..005、AT-WP29-001..005、AT-WP30-001..006

## 1. 结论先行

WP-26～WP-30 已完成可在本地诚实验证的产品与发布控制实现，但没有把机器通过写成真人通过：

- WP-26 已具备独立 Content Editor、组织隔离草稿、Operator 精确发布、固定学习材料、不可变完成事实和“材料未完成不得开始/提交”的服务端门禁；
- WP-27 已具备八站精确顺序的 Journey V3 组合入口，路线节点与线路共享同一坐标源；空材料、错顺序、跨组织或未发布 TaskVersion 均被拒绝；
- WP-28 已把学习完成、三项能力证据、Reviewer 人工结论、系统非决定建议和 Operator 人工准入分开；等待开始评审与正在评审也不再是同一显示事实；
- WP-29 已形成只接受固定候选、固定 V3、真人名册、真人签署和零 P0 blocker 的 fail-closed RC 验证器；验证器不能运行或伪造 UAT；
- WP-30 已形成受控上线 preflight、PII-free 每日指标与停止判定，并实现组织级新邀请冻结/恢复；冻结只阻止新邀请，不删除已有 Enrollment、提交、评审或重新进入事实。

当前没有发布 Journey V3、没有部署 staging/production、没有创建真人邀请、没有写入云资源，也没有产生 `P0_RC_SIGNED` 或 `P0_LIVE_CONTROLLED`。正式 production gate 继续为 `NO_GO`。

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

## 4. 真人门禁账本

| 工作包 | 仍需真人完成 | 当前状态 |
| --- | --- | --- |
| WP-26 | Content Editor 导入一个真实宝藏材料；2 名 Learner 完成学习→小任务→修订/恢复；独立 Reviewer 复核 | `NOT_RUN / CONTENT_INPUT_REQUIRED` |
| WP-27 | 四宝藏真实材料全部批准；目标 Learner 验证路线理解、文字预算与无死路；Operator 只发布精确 V3 | `NOT_RUN / JOURNEY_V3_NOT_PUBLISHED` |
| WP-28 | 2 名独立 Reviewer 校准三题；至少 1 名 Learner 完成真实修订；Operator 作出人工准入 | `NOT_RUN` |
| WP-29 | 1 Content Editor、1 Operator、≥3 Learner、2 Reviewer、1 QA Recorder 完成 10:00–19:00 固定候选 UAT 与六方签署 | `HUMAN_UAT_NOT_RUN / UNSIGNED` |
| WP-30 | 正式域名 readback、名单正负测、回退/维护演练、首批 cohort 与真实观察窗 | `NOT_STARTED / AUTHORIZATION_REQUIRED` |

任何一项表格、聊天确认或自动化输出都不能替代上述真人观察和签署。

## 5. 六小时后待授权事项（严格按顺序）

2026-08-05 Owner 已明确同意本节全部待授权事项。该授权允许按以下顺序推进，但不把尚未发生的真人材料、独立复核、UAT、六方签署、正式域名 readback 或观察窗口写成通过；任何前置门禁失败即停止，production 在 `P0_RC_SIGNED` 前继续 `NO_GO`。

1. 审阅并合入本地 PR；合入本身不部署。`DONE`：PR #148 已通过 Fast Gate 并合入主线 `a2312b269b1806cd3d5ce7d26fbc693466399035`。
2. 在 staging 创建/绑定真实 Content Editor；不读取通讯录，不扩大其他身份。
3. 由 Content Editor 导入并提交批准材料，由独立 Reviewer 线下复核，Operator 精确发布八个 TaskVersion。
4. 生成唯一候选并申请一次 staging 部署；核对 Web/API/Worker digest、migration `0019`、readiness、匿名拒绝和邀请控制默认状态。`DEPLOYED_WITH_P0_BLOCKER`：run `30959911465` 已部署候选 `a2312b2…` 并完成 `0016→0019`、readiness、`/ops`/`/review` 匿名 401 和 SSH 关闭；独立 readback 发现新增 `/content` 匿名返回 500，已停止身份写入并进入最小修复，修复部署前本项不得记为完成。
5. Operator 单独发布 Journey V3；不迁移 V1/V2 Enrollment，不自动创建邀请。
6. 依次执行 WP-26、WP-27、WP-28 真人门禁；失败保留原证据，只修 P0 blocker。
7. 固定候选与 V3 后执行 WP-29 整日 UAT；只有私密证据通过验证器并完成六方签署，才可形成 `P0_RC_SIGNED`。
8. 另行授权 production deploy、DNS/TLS/OAuth readback、V3 发布、私密邀请和回退演练；每项授权单独消费，不打包推定。

## 6. 上线停止条件

以下任一事实出现，立即冻结新邀请：业务事实丢失、跨组织访问、持续登录失败、核心闭环中断或 P0 事件。冻结不撤销已接受邀请，不删除已有业务事实；恢复必须由 Operator 以新理由和新 expected revision 明确执行。

`P0_LIVE_CONTROLLED` 只在固定候选、固定 V3、正式域名、私密名单和回退能力完成真实 readback 后成立；`P0_VALIDATED` 只能在 cohort 结束后依据真实分子/分母判断。
