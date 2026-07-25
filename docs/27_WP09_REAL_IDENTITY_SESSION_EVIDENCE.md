# 27｜WP-09 真实身份与会话构建证据

状态：`LOCAL_IDENTITY_IMPLEMENTATION_VERIFIED / REAL_IDENTITY_NOT_RUN`
日期：2026-07-25
当前发布判断：`NO_GO`

## 1. 结论

WP-09 的最小代码闭环已经实现：Learner 继续使用一次性邀请；Reviewer 与 Operator 使用 vNext 独立飞书 OAuth、内部 `user_id` 和独立 cookie session。当前证据只证明实现和本地负向合同，不证明真实飞书应用、真实人员或 staging 权限矩阵已经通过。

WP-08 的 Alpha 运行面已经验证，物理 ACL 仍有一项供应商字段证据债。该债不再阻塞 WP-09 代码和小规模 Alpha 学习，但必须在 WP-12 RC 冻结或任何 production 行为前关闭。

## 2. 已实现范围

- OAuth code 只在服务端交换；外部 `open_id` 只以按应用域分离的 HMAC 摘要入库；
- OAuth state 与 path-scoped HttpOnly browser cookie 双绑定、短时有效且一次消费；
- `/review`、`/ops` 是唯一允许的返回入口，拒绝开放重定向和角色错配；
- Operator 通过一次性绑定链接把已有内部 Reviewer/Operator 绑定到飞书；首次 Operator 只能通过 staging-only、显式确认、可审计的受控命令建立，不开放公共 bootstrap API；
- 新登录轮换同用户同角色旧 session；外部身份撤销、用户停用或角色移除立即使 session 失效；
- mutating Operator 命令使用 revision 和 idempotency；跨 organization、对象和角色范围 fail closed；
- Next Route Handler 把含 code/state 的浏览器 GET 转为无查询串的 API POST；Caddy 对 `/auth/feishu*` 跳过 access log，审计记录不包含 token、原始飞书 subject 或业务正文；
- staging 配置强制独立 subject secret、飞书 App ID/Secret、HTTPS 精确 callback，缺失时 fail closed。

## 3. 机器证据

- `make api-test`：148 项通过；
- `npm run lint && npm run typecheck && npm run build`：通过，两个 OAuth Route Handler 均为动态路由；
- `make openapi-check`、`make traceability-check`、`make wp08-workflow-check`、`make isolation-check`：通过；
- 迁移 head：`0011_wp09_feishu_identity`；OpenAPI 已包含 identity link、revoke、OAuth start/callback 合同；
- 正负向覆盖：state replay、browser mismatch、provider failure、未绑定/已撤销身份、角色错配、跨 organization、停用用户、移除角色、会话轮换、撤销幂等、client IP 限流及审计脱敏。

## 4. 外部边界与下一动作

以下仍为 `NOT_RUN`，不能由 fixture 或代码审查替代：

1. 创建 vNext 独立飞书企业自建应用并锁定 Owner/测试租户；
2. 配置精确 callback：`https://staging-vnext.muchenai.com/auth/feishu/callback`；
3. 将独立 App ID、App Secret、subject secret 写入 GitHub `staging` Environment；
4. 用受控命令生成首个 Operator 15 分钟一次性绑定链接；
5. 真实 Operator 与 Reviewer 执行登录、对象/组织权限、旧 cookie、撤销和日志脱敏矩阵；
6. 形成 `IDENTITY_AND_ACCESS_VERIFIED` 或明确失败证据。

创建应用、写 secret、生成真实绑定链接和使用真实账号都会改变外部状态或处理真人身份，必须取得对应 Owner 的精确授权。完成前 WP-09 不关闭，WP-10 不激活，整体发布保持 `NO_GO`。
