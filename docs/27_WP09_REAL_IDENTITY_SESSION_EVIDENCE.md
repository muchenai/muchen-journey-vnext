# 27｜WP-09 真实身份与会话构建证据

状态：`IDENTITY_AND_ACCESS_VERIFIED / HUMAN_SESSION_UX_PASS`
日期：2026-07-28
当前发布判断：`NO_GO`

## 1. 结论

WP-09 的最小代码闭环已经实现：Learner 继续使用一次性邀请；Reviewer 与 Operator 使用 vNext 独立飞书 OAuth、内部 `user_id` 和独立 cookie session。首位真实 Operator 已完成飞书认证、一次性绑定和 cookie session 建立。首次 callback 曾错误跳转到容器内部 `https://0.0.0.0:3000/ops`；修复候选 `2ea51c0aba272769af8bd8f298242b35326d79ea` 已部署到冻结 staging，通过公网 readiness、身份入口和匿名拒绝机器复验，Environment Owner 随后从指定飞书登录入口完成真实登录并报告已进入 `/ops`。

随后由当前 Operator 为 PII-free 的“试点主管”创建 30 分钟一次性 Reviewer 绑定，真实 Reviewer 完成授权对象访问、未授权 `/ops` 拒绝、重新登录轮换旧会话、身份撤销立即失效和日志脱敏矩阵。撤销后的旧会话虽然不能继续读取 `/review`，但 Web 曾把 API `401` 落入通用错误页。明确会话失效/重新登录修复进入候选 `2ab2658…`，并由唯一冻结 staging deploy run `30242231558` 成功上线；公网 readiness、release、匿名 `/ops`/`/review` 拒绝与飞书入口机器复验通过。2026-07-28，指定真实 Reviewer 在新绑定会话中确认可进入 `/review`；Operator 随后只撤销该 Reviewer 身份，Reviewer 在原会话刷新后看到明确 `SESSION_EXPIRED` 和重新登录指引，关闭最后一项真人证据。WP-09 结论升级为 `IDENTITY_AND_ACCESS_VERIFIED`，整体发布仍 `NO_GO`。

WP-08 的 Alpha 运行面已经验证，物理 ACL 仍有一项供应商字段证据债。该债不再阻塞 WP-09 代码和小规模 Alpha 学习，但必须在 WP-12 RC 冻结或任何 production 行为前关闭。

## 2. 已实现范围

- OAuth code 只在服务端交换；外部 `open_id` 只以按应用域分离的 HMAC 摘要入库；
- OAuth state 与 path-scoped HttpOnly browser cookie 双绑定、短时有效且一次消费；
- `/review`、`/ops` 是唯一允许的返回入口，拒绝开放重定向和角色错配；
- Operator 通过一次性绑定链接把已有内部 Reviewer/Operator 绑定到飞书；首次 Operator 只能通过 staging-only、显式确认、可审计的受控命令建立，不开放公共 bootstrap API；
- Operator `/ops` 提供最小身份访问清单：仅列出同组织的有效 Reviewer/Operator，服务端返回可执行命令；支持一次性链接生成/撤销和外部身份撤销，不返回原始 subject 或 token，且拒绝当前 Operator 自我撤销；
- 新登录轮换同用户同角色旧 session；外部身份撤销、用户停用或角色移除立即使 session 失效；
- mutating Operator 命令使用 revision 和 idempotency；跨 organization、对象和角色范围 fail closed；
- Next Route Handler 把含 code/state 的浏览器 GET 转为无查询串的 API POST；Caddy 对 `/auth/feishu*` 跳过 access log，审计记录不包含 token、原始飞书 subject 或业务正文；
- staging 配置强制独立 subject secret、飞书 App ID/Secret、HTTPS 精确 callback，缺失时 fail closed。

## 3. 机器证据

- `make api-test`：151 项通过；
- `npm run lint && npm run typecheck && npm run build`：通过，两个 OAuth Route Handler 均为动态路由；
- `make openapi-check`、`make traceability-check`、`make wp08-workflow-check`、`make isolation-check`：通过；
- 迁移 head：`0011_wp09_feishu_identity`；OpenAPI 已包含 identity access/list、link/revoke、OAuth start/callback 合同；
- 正负向覆盖：state replay、browser mismatch、provider failure、未绑定/已撤销身份、角色错配、跨 organization、停用用户、移除角色、会话轮换、撤销幂等、client IP 限流、Operator-only 清单、原始 subject/token 不出现在响应中及审计脱敏。

## 4. 外部边界与下一动作

以下外部事实已经完成，并且只以非敏感元数据记录：

- 当前飞书租户已创建独立企业自建应用 `Muchen Journey vNext Staging`；没有修改其他飞书应用；
- Owner 已确认飞书安全设置保存精确 callback；GitHub `staging` Environment 已存在
  `WP09_FEISHU_APP_ID`、`WP09_FEISHU_APP_SECRET` 与新生成的独立
  `WP09_IDENTITY_SUBJECT_SECRET`；只复验 secret 名称和更新时间，未读取、输出或落盘 secret 值；
- App ID/App Secret 已通过飞书官方租户鉴权端点验证；返回 token 未输出或落盘；
- 首次身份 staging deploy run `30181022690` 已成功部署候选
  `26d56010125024ca2dbc6e85f7dfeb59857f93dd`；外部 TLS/readiness 返回同一 release，匿名
  `/ops` 返回 `401`，临时 SSH `/32` 已撤销；
- 未启用机器人、消息发送或全量通讯录能力，未发送飞书消息。

首次 Operator 链接 run `30181111242` 在进入 bootstrap CLI 前失败：远端 Compose 调用未先加载
`.deployment.env`，因镜像变量缺失而停止。修复后的 run `30181508821` 成功加载环境，但第一个
`docker compose exec -T` 继承并消费了 SSH heredoc 的剩余 stdin，后续 bootstrap 命令未执行，空输出在
JSON 校验处失败。两次 run 均未执行 `journey_api.wp09_bootstrap`、未创建绑定记录、未上传密文，并已撤销
SSH。修复后的 run `30181942549` 通过：两个 Compose 调用均隔离 stdin，CLI 只创建一个 15 分钟链接，
密文上传后临时 SSH 关闭，本地解密复制后私钥、明文和密文均删除。Owner 随后报告可进入 staging
`/ops`；不记录真人标识、cookie、飞书 subject 或一次性 token。

## 5. 首次真人 Operator 结果与缺陷边界

- `PASS`：真实飞书授权完成；一次性 Operator link 被消费；staging session cookie 生效；同一浏览器直接访问 canonical `/ops` 获准；
- `FAIL`：callback 后的自动站内跳转使用 Next standalone 内部 request origin，浏览器收到 `https://0.0.0.0:3000/ops`；
- 根因：Web Route Handler 使用 `new URL(safe_entry, request.url)` 生成同源返回地址，而 standalone runtime 的 `request.url` 不构成可信公网 Origin；
- 修复合同：所有站内 OAuth 成功/失败跳转只允许 `/` 起始且拒绝 `//`、CR/LF 的 root-relative `Location`；只有飞书官方授权地址允许绝对 HTTPS URL；真实 standalone 响应测试必须同时验证 `/ops` 相对跳转和 session cookie 透传；
- 当前真人会话已证明绑定成功，无需也不得重复生成首次 Operator 绑定链接。该 OAuth 修复部署后的自动进入 `/ops` 及后续对象/组织权限、旧 cookie、撤销和日志脱敏矩阵均已按第 6 节完成。
- 修复已通过 PR #52 合入主线候选 `2ea51c0aba272769af8bd8f298242b35326d79ea`；Mainline Candidate Gate `30183059038` attempt 2 已完成完整 CI、SBOM、GHCR push 与三摘要验证。attempt 1 仅因 GitHub runner 拉取固定 Syft 镜像时 Docker Hub 网络超时而停止，代码与真实回跳响应测试均已通过；没有触碰 staging。
- 用户精确授权该候选基于绑定主线 `2992841f375d101afdd90ff44117245bc72e55d6`，在火山引擎华北2（北京）冻结基础设施执行一次 `phase=deploy`，失败不重试。唯一 run [`30187687813`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30187687813) 在 18 分 56 秒内成功；候选/摘要合同、冻结 state、临时 SSH `/32`、私有 bundle、精确镜像部署、外部 TLS 与 release surface 全部通过，`always()` SSH 清理通过，未执行 audit、DNS reconcile、Terraform apply 或第二次部署。
- 独立公网复验返回 `health/ready.status=ready` 且 release 精确等于 `2ea51c0…`；根页为 `200`，匿名 `/ops` 为 `401`，身份入口以 `303` 跳转到飞书官方授权端点，回调仍固定为 staging canonical URL。该机器证据证明修复已部署且入口合同正确，但不能替代真人完成飞书授权后的浏览器落点。
- 2026-07-26T05:48:48Z，Environment Owner 在本任务中报告“已进入”，并提供登录完成后的 staging Operator 页面截图。截图人工核对显示 canonical staging 域名、`OPERATOR · STAGING`、候选 `2ea51c0…` 与 migration `0011_wp09_feishu_identity`；私有截图只以 SHA-256 `c1b91fbcf3ea786537866647005ad4e5dc7b2bf3d43059ad384022ed25afa390` 引用，不复制进 Public Git，不记录账号、cookie、飞书 subject 或 token。该证据把“修复后自动进入 `/ops`”记为真人 `PASS`，不外推其他真人权限场景。

## 6. Reviewer/Operator 真人权限矩阵

本轮只记录最小、PII-free 结论；不记录真实姓名、飞书 subject、cookie、一次性 token、完整业务正文或撤销理由正文：

| 场景 | 证据类型 | 结果 |
|---|---|---|
| 当前 Operator 进入 `/ops` | Environment Owner 真人浏览器报告；第 5 节既有私有截图摘要 | `PASS` |
| “试点主管”进入授权 `/review` | Reviewer 真人浏览器报告 | `PASS` |
| Reviewer 访问未授权 `/ops` | Reviewer 真人报告 HTTP 403/无权限 | `PASS` |
| Reviewer 再次登录后旧会话失效 | Reviewer 真人在两个独立浏览器上下文报告：新会话可用，旧会话返回 `AUTH_REQUIRED` | `PASS` |
| Operator 撤销 Reviewer 外部身份后旧会话失效 | Operator 受控命令审计为 `SUCCESS`；Reviewer 随后打开原 `/review` 不能继续访问。私有截图仅保留 SHA-256 `48773b36d883504e9462dd70e3098ff125ed238b0c0fd4dd2c7e5b878f3facb4` 引用，不复制进 Public Git | `PASS`（fail closed） |
| 身份撤销不改写业务事实，且审计脱敏 | Operator 页面复验：Reviewer 为 `REVOKED`、Operator 仍为 `LINKED`、Enrollment/业务事实未变化；审计 `external_identity.revoked / SUCCESS` 的安全字段为空，仅列出被裁剪字段名 | `PASS` |

机器测试已覆盖跨 organization、对象范围、state replay、CSRF、开放重定向、停用/移除角色和原始身份/token 不出响应。真人证据只补足浏览器、真实身份和撤销时序，不替代这些机器负测，也不外推到 WP-13 的完整真人 UAT。

## 7. 当前缺陷、修复与关闭条件

- 观察到的缺陷：撤销后的 Reviewer 会话由 API 正确返回 `401`，但 Server Component 抛错后进入通用“操作没有完成”页面；该页还声称显示 request ID，实际没有可显示的 API request ID。
- 候选修复：Reviewer/Operator 页面读取遇到 `401` 时只跳转到 allowlist 内的 `/review` 或 `/ops` 重新登录入口；匿名 `/review` 与 `/ops` 均在 Web 边界返回不可缓存的 `401`；通用错误页不再承诺不存在的 request ID，只在 Next 提供安全 digest 时显示页面参考编号。
- 机器复验：Next 16.2.11 lint、typecheck、production build 通过；standalone runtime 实测 `anonymous_ops=401`、`anonymous_review=401`、`expired_reviewer=explicit-relogin`、逐请求 CSP nonce 和 OAuth root-relative redirect 全部通过。
- PR #56 已合入主线 `2ab2658fc0341d11bc1434524d86128e23da9170`；Mainline Candidate Gate `30237677350` 已完成完整 CI、三镜像、SBOM、GHCR push 与远端摘要验证。候选绑定合同只允许该 SHA、该 run 和三个不可变摘要，不构成部署授权。
- 候选 `2ab2658fc0341d11bc1434524d86128e23da9170` 已基于主线 `354a68ad783fd67a623e2efbb2f4f164130ac3a9` 在唯一 run [`30242231558`](https://github.com/muchenai2024-creator/muchen-journey-vnext/actions/runs/30242231558) 成功部署，冻结基础设施、精确摘要、外部 TLS/release surface 与 SSH 清理均通过；未执行 Terraform apply、DNS 或第二次部署。
- 2026-07-28，指定真实 Reviewer 使用仅显示一次的 30 分钟替换链接完成飞书绑定并报告可进入授权 `/review`；Operator 页面随后只对该 PII-free Reviewer 执行一次身份撤销，页面复验为 Reviewer=`REVOKED`、Operator=`LINKED`，审计 `external_identity.revoked / SUCCESS` 仅显示空安全字段并裁剪 provider/reason 标记；
- Reviewer 在同一原浏览器会话刷新 `/review`，落到 `auth_error=SESSION_EXPIRED&return_to=%2Freview`，页面明确显示“当前会话已失效。业务事实未受影响；如仍有权限，请重新使用飞书登录。”，没有返回匿名 JSON `AUTH_REQUIRED`，也没有进入通用错误页；
- 真人截图仅以 SHA-256 `b4f0cb1687a7b86324c58731d4db28d7437823e64322844872d0ec353b77a193` 引用，不复制进 Public Git，不记录姓名、飞书 subject、cookie、链接 token 或业务正文。该证据关闭 `WAITING_FOR_HUMAN_UAT`，WP-09 记为 `IDENTITY_AND_ACCESS_VERIFIED / HUMAN_SESSION_UX_PASS`；不外推 WP-13 全量真人 UAT 或发布 GO。

创建应用、写 secret、生成真实绑定链接和使用真实账号都会改变外部状态或处理真人身份，必须取得对应 Owner 的精确授权。当前不得为已经撤销的 Reviewer 再创建链接来制造重复证据。整体发布保持 `NO_GO`。

## 8. 2026-08-12｜Content Editor 兼任 Reviewer 与待评审移交

Owner 已确认由已绑定的 Content Editor 郑田源兼任 Reviewer。实现坚持角色、身份与业务事实分离：

- 不创建第二个飞书身份、不恢复历史已撤销身份，也不覆盖 Content Editor 角色；Operator 只可为同组织、有效且已绑定飞书的 Content Editor 增加一条独立、幂等、可审计的 Reviewer `RoleAssignment`；
- 已提交且仍为 `ASSIGNED` 的 Review 不改写原 `reviewer_id`。Operator 通过独立命令建立不可更新、不可删除的 `ReviewDelegation`，同时只更新 Enrollment 的未来 Reviewer；Review 已进入 `IN_REVIEW` 或 `FINALIZED` 后拒绝移交；
- 委派 Reviewer 可看到、开始并完成该 Review。Evaluation 继续用原 `reviewer_id` 保留指派责任，同时用非空 `executor_id` 和 `created_by` 记录实际执行人；
- 新迁移 head 为 `0020_wp09_reviewer_delegation`。干净数据库全量 API 回归 `335 passed, 5 skipped`，Reviewer 双角色/委派专项 `24 passed`，Web lint、typecheck 与 `33` 项回归通过；OpenAPI、隔离、secret scan 与 Web 依赖审计通过；完整 `ci-fast` 仅在既有 Python 依赖审计因上游索引无法解析已锁定的 `cryptography==50.0.0` 而停止，该失败与本次变更无关，未放宽门禁；
- 本节只记录候选实现和机器证据。staging 尚未部署迁移，尚未授予真实角色，也尚未移交当前待评审事实；这些动作必须在 PR 合入、新候选和冻结基础设施部署完成后，由当前 Operator 在 `/ops` 分别确认执行。

## 9. 2026-08-12｜Reviewer 安全重新进入合同

真实试点再次暴露入口缺陷：未持有 Reviewer 会话时直接打开 `/review` 会看到原始
`AUTH_REQUIRED` JSON；已持有 Content Editor 等其他角色会话时，飞书 OAuth 虽正确拒绝
Reviewer 入口，却只回到泛化错误页。权限拒绝本身正确，但用户无法知道安全下一步。

本次修复不放宽 API、组织或对象权限：匿名 `/review` 只以不可缓存的 `303` 转到同源
`/review/login`；专用页面只提供“使用飞书进入”并固定 `return_to=/review`。失效 Reviewer
session 与有效的错误角色 session 也分别落到该页的 `SESSION_EXPIRED` / `FORBIDDEN`
提示；`/ops` 对匿名访问继续返回不可缓存的 `401`。API callback 仍必须找到同组织、有效用户
和独立 Reviewer RoleAssignment，才能签发 Reviewer session。

机器证据包括 Web `34/34`、ESLint、TypeScript/production build、standalone runtime，以及固定
Chromium `1232` 的真实浏览器烟测；浏览器实测 `/review → /review/login`、页面标题和飞书入口
均精确通过，三视口无横向溢出且 console 无 error。本证据不代表郑田源已经获得 Reviewer
角色，也不代表 staging 已部署或真人评审闭环完成。
