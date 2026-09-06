# WP-31 受控 Canary 运行时绑定修复与上线计划

## 目标

修复当前 `main@74f5e64...` 上 Canary 运行时仍引用历史候选和旧 GHCR namespace 的根因，使运行时脚本、候选 binding、镜像 digest、Ops closure 和 Workflow 在同一条可审计链路上，然后只生成一次新的候选 artifact，并在所有现场核验通过后执行一次受控 `PRODUCTION_CANARY_UAT` fast Canary。

## 不在本计划范围内

- 不执行正式发布、promotion、`RELEASE_GO` 或生产作业。
- 不复用旧候选、旧 package Run、旧 review tag、旧授权或旧运行证据。
- 不读取、输出或写入任何 secret 的明文；不删除数据库。
- 不在 SHA、artifact、tag、Environment authorization 或运行状态不一致时自行选择或重试。

## 执行任务

### 1. 基线与回归测试

- 在隔离 worktree 复核当前 HEAD、binding、Workflow 和运行脚本的现状。
- 先添加针对运行时候选传播、API/Web digest、dbtool namespace、edge/rollback release 校验的静态回归测试。
- 证明新测试在修复前失败，并保存失败原因；不把失败隐藏为环境通过。

### 2. 修复运行时绑定

- 让备份、部署、edge 和 rollback 脚本从生成 bundle 的候选变量或 release path 读取候选，不再硬编码历史 SHA。
- 让生成脚本把候选写入备份环境，并把 dbtool 目标固定到 `ghcr.io/muchenai/muchen-journey-vnext-dbtool` 的已知 digest。
- 保持 API/Web/Worker 仅使用 candidate binding 提供的 digest；不改变 API/Web only、worker 关闭、`release_go=false` 和独立数据库语义。
- 同步修正 dbtool mirror Workflow 的目标 namespace；源镜像是否仍可读取必须由 Actions 运行时验证，不能由本地 login 推断。

### 3. 本地验证与 closure 更新

- 运行新增回归测试、WP-31 focused tests、Candidate binding/数据库 guard/identity tests。
- 运行 Ops closure discovery/validation，确认所有 Workflow 引用文件均在 manifest 中且无旧 namespace/旧候选残留。
- 重新计算 Ops manifest 文件 hash；确保 manifest 自身和 candidate binding 一致。
- 对所有修改后的脚本执行 shell/Python 语法检查，并在可用条件下运行完整 CI 等价测试。

### 4. 集成到权威远端

- 复核 canonical remote、当前远端 main 和 GitHub CLI 身份；只向 `muchenai/muchen-journey-vnext` 推送。
- 请求独立只读代码审查；审查通过后提交并创建/更新唯一 PR，等待必要检查。
- 合并后重新读取远端 main SHA；若远端 SHA、PR head、Workflow SHA 不一致，立即停止。

### 5. 生成并核验唯一新候选

- 只从合并后的权威 main 触发一次 package Workflow（若已有同 SHA 成功 Run，则复用并现场核验，不重复触发）。
- 从 candidate binding/handoff artifact 读取 candidate SHA、package Run、API/Web/Worker digest、SBOM hash 和 release manifest hash。
- 核对 binding、package artifact、Workflow 输入/输出、远端 main 和新 reviewed Ops tag 全部一致；旧链路不得作为输入。

### 6. 准备受控身份与授权材料

- 在受限本地目录生成三个新的 UUIDv4（Operator、组长 Learner、刘总 Learner）；不把 UUID 写入聊天或普通日志，只写入受控 bootstrap payload/Environment secret。
- 只使用两个 Learner UUID 形成 allowlist；Operator/Reviewer 身份不自动计入 Learner allowlist。
- 生成与新 candidate、新 reviewed Ops tag、新 Ops manifest hash 绑定的 execution authorization payload，并只写入 `WP31_EXECUTION_AUTHORIZATION_B64`；生成 RSA-4096 临时接收公钥供 Workflow 使用，私钥只留在受限本地位置，绝不上传或输出。
- 对 Environment secret 名称、当前 policy、分支/tag 绑定和 GitHub Actions 权限做现场核验；不擅自放宽 policy。

### 7. 单次 fast Canary 执行

- 只在上述链路全部一致、缺失 secret 已由受控值补齐、数据库 guard 可证明安全时 dispatch 一次 `greenfield-canary-fast`。
- 先观察 package/binding/authorization/preflight，再观察 backup/restore/deploy/inspect/rollback/cleanup 状态。
- 数据库只允许在 guard 证明目标存在且为空、未被使用，或安全创建且不存在并且无冲突 workflow 时继续；非空、使用中、状态不明或任一证据不一致时停止。
- 成功仅定义为：Actions Run 成功、Canary health/allowlist/banner/release_go/worker 约束证据齐全、artifact 与 binding 一致。届时再通知组长测试；在此之前不宣称“已上线”。

## 停止条件

出现重复 dispatch、同一失败连续重试、candidate/Run/digest/hash/tag 相互改变、旧 namespace 残留、权限不足、Environment secret 无法安全写入、数据库状态无法只读确认、或 Workflow 长时间无进展时，立即停止并报告证据，不继续猜测或重试。

## 验收证据

- 本地测试与 closure 输出及退出码。
- PR、合并后的远端 main SHA、package Run 和候选 binding artifact。
- reviewed Ops tag、Ops manifest hash、authorization hash（只报告 hash，不报告 payload/secret）。
- Canary Run ID、各 job 状态、artifact 名称/hash、最终受控入口健康检查和 Learner allowlist proof。
