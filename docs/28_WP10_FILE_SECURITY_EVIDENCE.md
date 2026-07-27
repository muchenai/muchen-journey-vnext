# 28｜WP-10 真实附件与文件安全构建证据

状态：`ENGINEERING_VERIFIED / SECURELY_DISABLED_FOR_ALPHA / FUTURE_ENABLEMENT_GATED`
日期：2026-07-28
当前发布判断：`NO_GO`

## 1. 结论

WP-10 的最小工程闭环已实现，但未达到、也不宣称 `FILE_SECURITY_VERIFIED`。浏览器不再把文件正文转发给 Next Server Action；启用后的非本地环境只允许对象级短时 TOS PUT，API 在完成时重新读取对象元数据与内容，复核长度、声明类型、SHA-256 和魔数，随后通过 ClamAV `INSTREAM` 扫描。只有 `CLEAN` 对象进入 `READY`；恶意、扫描错误、存储错误和未完成对象均停留隔离态，不能绑定 SubmissionVersion。

当前 Alpha/RC Assignment 固定使用 `TSK-001 V1`：`allowed_attachment_types=[]`、`max_attachment_size_bytes=0`。staging 部署合同明确写入 `ATTACHMENTS_ENABLED=false`：Learner 响应不返回附件类型/额度，所有附件写入与下载端点 fail closed，结构化文本闭环继续可用。依据 2026-07-28 批准的 DEC-017，WP-10 当前范围以 `SECURELY_DISABLED_FOR_ALPHA` 关闭；这是一项明确的产品范围和安全边界，不是文件安全通过。

现有 Alpha 主机也不应直接承载 ClamAV。当前实例属于 4 GiB 级规格，而扫描容器将挤占 API/Web/Worker/Edge 的可靠余量；当前没有真实用户证据证明附件是完成任务的阻塞项。因此本次不创建文件 IAM/TOS CORS/扫描资源、不部署，也不把基础设施工作继续置于产品验证之前。

## 2. 已实现范围

- 官方火山 TOS Python SDK 固定为 `tos==2.9.0`，Python 3.14 镜像构建与漏洞审计通过；
- TOS 只使用 ECS metadata role provider，不接受长期 AK/SK 应用配置；
- 上传凭证默认 5 分钟，下载凭证默认 1 分钟；PUT 签名绑定对象 key、内容类型、下载 disposition、SHA-256 metadata 与禁止覆盖头；
- 对象 key 由 organization/owner/attachment 的服务端 UUID 构成，不接受用户路径；
- API complete 重新执行 size/type/SHA-256/魔数检查，并记录 opaque ETag/version；
- ClamAV 使用有界 socket/超时与 64 KiB 分块的 `INSTREAM`；`OK/FOUND` 之外均为 retryable dependency error；
- migration `0012_wp10_file_security` 将历史 `LOCAL_CLEAN/LOCAL_REJECTED` 映射为统一 `CLEAN/INFECTED`，新增上传过期、对象版本和扫描完成事实；
- Reviewer 下载仍先按 organization、明确 reviewer、固定 Review/SubmissionVersion 做二次授权，再返回短时对象 URL；本地下载强制 attachment、no-store 与 nosniff；
- 配置合同从 V1 升级 V2；非本地启用附件时缺 TOS/ClamAV 任一配置即启动失败；未启用时页面和 API 同时关闭附件入口。

## 3. 机器证据

- `make api-test`：160 项通过；新增正常、超大、伪 MIME、EICAR、跨 owner/assignment、Reviewer 固定版本、扫描不可用隔离、功能禁用矩阵；
- `tests/test_wp10_file_security.py`：TOS 签名头/TTL/对象元数据/有界读取、ClamAV clean/infected/unavailable 合同通过；
- `npm run lint && npm run typecheck`：通过；浏览器 Web Crypto 计算摘要并直传绝对对象 URL，本地测试才经受控 Server Action 适配；
- `make dependency-audit`：Web 审计按既有到期 waiver 通过；Python `No known vulnerabilities found`；
- OpenAPI 已重生，包含 `upload_headers`、`upload_expires_at` 与 config schema V2；
- 空库 migration `0001 → 0012`、已有绑定附件的持久库升降级、fixture seed 和完整 API 回归通过。

## 4. 未来启用附件的五项强制门禁

以下均不得由代码/mock 代替。它们不再阻塞当前无附件 Alpha/RC，但任何环境把 `ATTACHMENTS_ENABLED` 改为 `true`、发布带附件额度的新 TaskVersion 或向真实用户分配该版本之前，必须重新打开 WP-10 并全部关闭：

1. 创建并附加仅允许目标 staging bucket/prefix 所需 Put/Get/Head/Delete 的 ECS 实例角色；
2. 对现有独立 staging TOS 设置唯一 staging Web Origin、PUT 所需头和最小响应头的精确 CORS，确认 private ACL、加密、versioning、1 年保留、孤儿清理与删除审计；
3. 选择有足够内存且不突破月预算的扫描运行时，固定镜像摘要和病毒库更新/健康/告警合同；
4. 在物理 staging 完成正常、过期、伪 MIME、EICAR、跨对象、扫描不可用和短时下载矩阵；
5. 执行对象恢复样本并记录不含资源 ID、URL query、人员或业务数据的私有证据摘要。

在这五项关闭前，不能激活 staging/production 附件，不能把 V2 分配给真实 Alpha/RC 用户，也不能把本地 `TEST` 扫描器解释为真实恶意文件扫描。任何在途 V1 Assignment 继续固定原版本，不因未来启用而改写。

## 5. 当前范围批准与后续触发条件

2026-07-28，Product Owner 确认当前 Alpha/RC 使用无附件的 `TSK-001 V1`，授权将 WP-10 记为 `SECURELY_DISABLED_FOR_ALPHA`，保持 `ATTACHMENTS_ENABLED=false`，且本次不创建云资源、不部署。该批准只关闭当前范围，不授权未来附件启用，也不改变整体 `NO_GO`。

只有当真实 Alpha 用户证明附件是完成任务的阻塞项时，才重新评估 V2；届时应基于实测类型、大小和使用量选择独立扫描运行时，取得精确资源/IAM 授权，完成第 4 节五项物理门禁后再发布和分配新的 TaskVersion。
