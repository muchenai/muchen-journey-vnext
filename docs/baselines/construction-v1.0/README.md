# Muchen Journey 施工总包 V1.0.3

> 版本：`V1.0.3`  
> 初版日期：`2026-08-26`  
> 合同变更日期：`2026-08-27`  
> UAT模式：`PRODUCTION_CANARY_UAT`  
> 目标发布：`2026-09-01 CONTROLLED_COHORT_RELEASE`  
> 内容候选收口日期：`2026-08-27`  
> 当前文档状态：`APPROVED_PRODUCT_BASELINE / G1_CONTENT_BINDING_PASS / FINAL_CANDIDATE_FREEZE_REQUIRED / CANARY_DEPLOYMENT_NOT_AUTHORIZED / RELEASE_NOT_AUTHORIZED`

## 一句话施工口径

**沐晨新手村已验证的任务闭环 + 探索营 V1.0 的真实业务方案 + 已批准的治理升级，定义产品行为；Mac mini 的 `Muchen Journey2.0` 定义技术运行底座。**

这意味着：技术可以 Greenfield，产品行为不能 Greenfield；可以重构旧表和清空 Journey2.0 开发/测试数据，但不能丢掉已验证的任务、运营、审核和返工闭环。

## 本包怎么用

| 使用者 | 先读 | 直接产出 |
| --- | --- | --- |
| Mini Codex / 开发者 | `00_施工总册.md` → `01_共享底座/*` → 对应模块分册 → `05_机器合同/*` | 按 Requirement ID 实现、测试、留证；不得自行新增业务语义 |
| Pro / 独立复核 | `SOURCE_MANIFEST.md` → `04_UAT与发布/*` → 机器合同 | 检查来源、冲突、负向合同、候选 SHA、真人 Gate 和发布风险 |
| 产品/业务 Owner | `00_施工总册.md` → 对应模块分册的“Owner 内容绑定表” | 批准内容版本、首批任务、Rubric、Reviewer、SLA 和例外 |
| QA/UAT / Release Reviewer | `04_UAT与发布/*` | 在固定候选 SHA 上执行真人 UAT 和独立发布复核 |

## 目录

```text
00_施工总册.md
SOURCE_MANIFEST.md
01_共享底座/
  01_产品行为基线与来源优先级.md
  02_统一用户旅程与信息架构.md
  03_共享领域模型状态机与任务引擎.md
  04_身份权限证据AI与审计.md
02_模块分册/
  01_探索营_V1.0.md
  02_沐晨新手村.md
  03_AI学院.md
  04_交付线公会.md
03_技术运行/
  01_MacMini技术运行基线继承合同.md
  02_API数据迁移部署与回滚合同.md
04_UAT与发布/
  01_真人UAT合同.md
  02_2026-09-01受控发布合同.md
  03_PRODUCTION_CANARY_UAT合同变更_V1.0.1.md
05_机器合同/
  README.md
  requirements.v1.json
  state-machines.v1.json
  release-gates.v1.json
  production-canary-uat-authorization.schema.v1.json
  traceability.v1.json
  module-content-package.schema.v1.json
  implementation-evidence.schema.v1.json
SHA256SUMS
```

## 四条硬边界

1. 正式结果只能来自实操证据和真人 Gate；阅读、点击、自证、积分和 AI 初评均不能替代。
2. 受控真实项目任务可以进入 Journey 编排，但生产动作永远在获授权业务系统中执行；Journey 不直接写生产。
3. 2026-09-01 是最多 25 人的受控发布，不是全量产品发布；竞技场、Career Map 复杂计算、历史数据正式迁移和复杂积分均延期。
4. 文档完成不等于发布完成；发布必须绑定干净候选 SHA、同 SHA 真人 UAT、独立 QA、独立 Release Reviewer、备份恢复和回滚证据。
5. 真人 UAT 使用生产基础设施上的 8 人白名单 Canary；`CANARY_DEPLOYMENT_GO` 只允许 UAT，不等于 `RELEASE_GO`。

## 当前已确定与仍待绑定

- 已确定：产品继承公式、四个首发模块、共享任务闭环、AI/真人边界、真实任务边界、历史数据参考策略、Owner 名单、9 月 1 日受控发布范围。
- 已生效：郑田源、屠元琦、段超群分别批准四模块精确候选 hash；屠元琦同时接受 Reviewer 运营合同。批准证据 hash 为 `2a1b46fd042f8ab96643266d973ab9c8b21c8a6c26199404a1862f6beb6000fc`。
- 已绑定：探索营目标 Sheet 的文档 token、sheet ID、标题、Owner、只读状态和页面可见修改时间；版本绑定 hash 为 `4ce0734ea7b3b21c768e706a28b836a06d164a9d194a822788a6e49f56bf3c6b`。该证据不是完整导出 hash，任一绑定字段变化均触发重新批准。
- 已生成：四模块正式内容包，索引 hash 为 `76086990bf28fdf567b7f21f4600e3a9828de116c41c4b0b3166ef233f22bfdd`；`G1_CONTENT_BINDING=PASS`。
- 待技术形成：干净发布候选、不可移动 tag/候选 SHA、当前工作树资产收口、候选部署物与迁移版本绑定。
- 待真人完成：在 `PRODUCTION_CANARY_UAT` 中每模块至少 2 名真实目标用户 UAT、独立 QA、发布复核和小名单放行。

## 状态解释

- `APPROVED_PRODUCT_BASELINE`：产品方向和约束可用于施工。
- `OWNER_CONTENT_BINDING_REQUIRED`：框架已定，但具体材料/题目/Reviewer 不得由开发者发明。
- `READY_FOR_MACHINE_TEST`：实现已具备机器验收条件。
- `READY_FOR_HUMAN_UAT`：同一候选机器验收通过，可开始真人 UAT。
- `PRODUCTION_CANARY_READY`：同一候选的扫描、恢复、回滚、8人白名单和停线能力齐全，等待 `CANARY_DEPLOYMENT_GO`。
- `PRODUCTION_CANARY_UAT_ACTIVE`：同一候选仅对8名白名单学员开放真人UAT，不代表正式发布。
- `READY_FOR_RELEASE_DECISION`：真人与运行 Gate 齐全，等待明确发布决定。
- `RELEASE_GO`：只能由产品 Owner/业务 Decider 在独立复核后显式签署。
