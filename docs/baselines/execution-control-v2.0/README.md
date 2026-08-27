# Muchen Journey 候选收口执行控制包 V2.0

> 状态：`ACTIVE_EXECUTION_CONTROL / G1_APPROVED / G2_RUNTIME_COMPATIBILITY_FAIL / NO_DEPLOY / NO_RELEASE`  
> 事实快照：`2026-08-27`  
> 起始代码基线：`codex/construction-v1-candidate-prep-20260826@7c57a2f7fa16eacdf2a3a6e2a8bfd594d00460f1`  
> 使用者：Mac mini Codex（执行）、Pro Codex（独立复核）、刘默文（最终判断）

## 这套 V2.0 替代什么

V1.0/V1.0.3 施工总包继续作为**产品语义和边界基线**，但其中的进度、Owner 阻塞、dirty overlay、下一任务和旧命令不再作为执行依据。

V2.0 是从当前代码状态到固定候选的**增量执行控制包**。Mini 只需读取本包、V1.0.3 中被本包明确引用的产品合同，以及仓库当前代码，不再从头复述或重新实现 26 项 Requirement。

## 当前最重要的四个事实

1. `G1_CONTENT_BINDING=PASS`，Owner 内容不再是当前阻塞。
2. 四个正式内容包无法被当前 Runtime 接受：`0/4 PASS`，根因是生成器和 Runtime 的 canonical hash 规则不一致。
3. 产品插件要求 `muchen_journey_product.schema_version=2` 且验证通过；旧运维插件仍硬编码 schema 1。Mini 不得为迁就旧插件把产品合同降级。
4. 默认 Compose 项目名 `journey-next` 与 Mini 上另一工作区的运行容器冲突；所有 V2 验证必须使用独立项目名、端口和证据根目录。

## 文件

- `00_当前事实快照.md`：已验证事实、推论与未知项。
- `01_剩余施工清单.v2.json`：Mini 唯一机器 backlog。
- `02_命令与环境运行手册.md`：不与现有容器冲突的命令顺序。
- `03_证据与Gate合同.v2.json`：允许写入的状态与 Pro 验收格式。
- `04_Pro独立复核清单.md`：候选形成后 Pro 的检查入口。
- `MINI_AUTONOMOUS_GOAL_PROMPT_V2.0.md`：可直接交给 Mini Codex 的持续目标。
- `config/muchen_journey_execution_control.v2.json`：仓库机器入口，声明本包为当前执行控制源。
- `scripts/v2_preflight.py`：只读检查当前仓库是否满足 V2 起跑条件。
- `SHA256SUMS`：本包文件完整性。

## 一句话执行顺序

`V2起跑校验 → 内容包Runtime兼容 → 隔离G2全量机器Gate → 干净提交 → 在固定SHA上重跑 → 候选外部清单与镜像摘要 → 隔离恢复/回滚 → Pro复核`

在 `PRODUCTION_CANARY_UAT` 获得单独授权之前，本包不得部署任何环境。
