# 27｜WP-09 真实身份与会话构建证据

状态：`STAGING_IDENTITY_DEPLOYED / FIRST_OPERATOR_LINK_BLOCKED / REAL_IDENTITY_NOT_RUN`
日期：2026-07-26
当前发布判断：`NO_GO`

## 1. 结论

WP-09 的最小代码闭环已经实现：Learner 继续使用一次性邀请；Reviewer 与 Operator 使用 vNext 独立飞书 OAuth、内部 `user_id` 和独立 cookie session。当前证据只证明实现和本地负向合同，不证明真实飞书应用、真实人员或 staging 权限矩阵已经通过。

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

- `make api-test`：150 项通过；
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
- 唯一 staging deploy run `30181022690` 已成功部署候选
  `26d56010125024ca2dbc6e85f7dfeb59857f93dd`；外部 TLS/readiness 返回同一 release，匿名
  `/ops` 返回 `401`，临时 SSH `/32` 已撤销；
- 未启用机器人、消息发送或全量通讯录能力，未发送飞书消息。

首次 Operator 链接 run `30181111242` 在进入 bootstrap CLI 前失败：远端 Compose 调用未先加载
`.deployment.env`，因镜像变量缺失而停止。该 run 未执行 `journey_api.wp09_bootstrap`、未创建绑定记录、
未上传密文，并已撤销 SSH。修复已增加“Compose 前加载部署环境”的机器门禁；不得把该失败当作已生成链接。

以下仍为 `NOT_RUN`，不能由 fixture 或代码审查替代：

1. 通过 PR 合入 Operator bootstrap 的 Compose 环境加载修复并完成主线门禁；
2. 用修复后的受控命令生成首个 Operator 15 分钟一次性绑定链接；
3. 真实 Operator 与 Reviewer 执行登录、对象/组织权限、旧 cookie、撤销和日志脱敏矩阵；
4. 形成 `IDENTITY_AND_ACCESS_VERIFIED` 或明确失败证据。

创建应用、写 secret、生成真实绑定链接和使用真实账号都会改变外部状态或处理真人身份，必须取得对应 Owner 的精确授权。完成前 WP-09 不关闭，WP-10 不激活，整体发布保持 `NO_GO`。
