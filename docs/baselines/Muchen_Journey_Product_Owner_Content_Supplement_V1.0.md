# Muchen Journey 产品 Owner 内容补充与模块签署包 V1.0

> 状态：`PRODUCT_OWNER_SUPPLEMENT_COMPLETE / MODULE_OWNER_HASH_SIGNATURE_PENDING / NO_RELEASE`
>
> 目标版本：2026-09-01 `PRODUCTION_CANARY_UAT`
>
> 产品 Owner 决策源：`SRC-OWNER-03`

## 1. 本包解决什么

本包把探索营、新手村、AI 学院和交付线公会的最低 P0 内容补齐为可验证的候选，不把机器生成候选伪装成模块 Owner 已批准内容。

内容完整与批准生效分成两个 Gate：

1. 本包固定任务、Rubric、Reviewer、容量、SLA、积分和边界，并以 SHA-256 防止静默变化；
2. 郑田源、屠元琦、段超群分别确认自己负责模块的精确候选 hash 后，才可生成正式 `module-content-package.v1`；
3. 之后仍须通过候选冻结、安全扫描、固定候选恢复、8 人真人 Canary UAT 和独立 Release Review；本包本身不构成发布授权。

## 2. 已确认事实与产品 Owner 补充

### 已确认事实

- 郑田源已确认探索营目标 Sheet 包含三项实操和 Rubric；正式候选仍须绑定该 Sheet 的可复核版本或导出 hash。
- 新手村主 Reviewer 为万雨欣，周容量为 25 名唯一学员。
- AI 学院首单元已有历史方案及新手村多维表中的第 1 月任务包和两项必修资源。
- 交付线公会尚无首个正式任务包。

### 产品 Owner 授权下的最低补充

- 主 Reviewer：万雨欣；备用 Reviewer：屠元琦。同一人不能同时构成主备冗余。
- 容量：每滚动 7 日最多 25 名唯一学员，8 人 Canary 包含在内。
- SLA：12 小时未接单触发备用；24 小时首次反馈；48 小时完成审核；返工后 24 小时反馈。
- 申诉：由未参与原结论的真人处理；屠元琦不能同时成为同一任务唯一 Reviewer 和唯一 UAT 签署人。
- 独立 UAT 见证：冯宇汀。
- 允许范围：公开、合成或获批脱敏材料；本批任务均为模拟任务，不执行生产作业，不写入生产系统。
- AI 只做自查、初评和摘要；正式通过、返工、申诉与高影响结论由真人签署。
- 积分只作激励与参考，不直接产生录用、淘汰、项目准入或人才结论。

## 3. 四模块候选

| 模块 | 模块 Owner | P0 内容 | P0 任务 | 候选 SHA-256 | 待办 |
|---|---|---:|---:|---|---|
| 探索营 | 郑田源 | 4 个宝藏 | 3 项实操 | `1d9feb1672c847279c0b85cdc5a13ea9a9890d45cad4b223dd59ef2f05bbeb1c` | 确认精确 hash，并补目标 Sheet 版本/导出 hash |
| 新手村 | 屠元琦 | 2 张任务说明 | 2 项任务 | `6dfedfa9e95e78b8ab06115b08f0b5e7379b988b87f59de5c166c37f45937f1b` | 确认任务及 Reviewer 运营合同 |
| AI 学院 | 段超群 | 2 个资源＋1 个指南 | 1 项首单元任务 | `e58880f712ee6c1aa3e4e31e5a51e62e15ac1e8bd9a75ec3600ca8b03095a894` | 确认精确 hash |
| 交付线公会 | 段超群 | 使命边界＋交接指南 | 1 项首个任务 | `4ffe612ddec9b177596d7cc4b03d29f1231a00c42c63ad4f0f4759c72d793cba` | 确认新补任务的精确 hash |

完整机器清单 SHA-256：

`b517977338de3da689bc5e61b5bb81c57d0932f5759b3423b79e15ab8f98b3a6`

## 4. 任务验收摘要

### 探索营

- `EXP-P1 规则拆解`：把业务要求拆成输入、输出、约束、质量标准和风险；关键红线识别不得失败。
- `EXP-P2 模型回答判断`：识别事实、推断、风险与待核验项，不能把 AI 输出当真人结论。
- `EXP-P3 边界与问题提报`：明确停止线、临时安全处理和升级路径；停止线与安全处理为必过项。
- 三项均须提交可访问证据，经真人 Reviewer 作出 `通过` 或 `返工`；每项通过后 10 分。
- Day 1 结果包只用于决定下一训练阶段，不作录用、淘汰或项目准入终判。

### 新手村

- `NV-T1-COMPANY-INDUSTRY-CARD`：形成公司、行业、客户价值和待核验问题卡；通过后 10 分。
- `NV-T2-AI-DELIVERY-GLOSSARY`：用可操作语言解释 AI 数据交付关键词并标明限制；通过后 10 分。
- 历史 `T+30 个人成长复盘` 暂不进入 9 月 1 日 P0 Canary，不代表废弃。

### AI 学院

- 首单元资源：`AI for Everyone`、`Generative AI for Everyone` 核心选段和第 1 月任务指南。
- `AIA-M1-AI-LITERACY-CARD`：使用真实但脱敏、或合成的沐晨项目场景，解释表层交付、模型能力、数据质量及 AI 数据工程与标注的区别。
- 必须披露 AI 使用、来源和限制；通过后 20 分。仅在另经真人批准为组织资产时追加 10 分。

### 交付线公会

- `DLG-P1-TRACEABLE-HANDOFF`：提交范围与成功标准、输入输出证据索引、质量检查、风险与停止线、下一责任人和回滚方式、AI 使用披露。
- 证据可访问、质量可复现和停止线为必过项；真人导师确认接收人可继续后才通过；通过后 30 分。
- 首批仅用模拟或获批脱敏材料，不等于真实项目生产授权。

## 5. 三位模块 Owner 的有效回复格式

模块 Owner 必须本人回复，且回复需包含姓名、模块、精确 hash 和决定。允许的决定只有 `APPROVED` 或 `CHANGES_REQUIRED`。

示例：

```text
PERSON_NAME=郑田源
MODULE_KEY=exploration-camp
CANDIDATE_SHA256=1d9feb1672c847279c0b85cdc5a13ea9a9890d45cad4b223dd59ef2f05bbeb1c
DECISION=APPROVED
SIGNED_AT=<ISO-8601时间>
```

段超群需分别确认 AI 学院和交付线公会两个 hash；不能只说“总体同意”。如要求修改，必须指出任务 key、字段和值，修改后重新计算 hash 并重新签署。

## 6. 当前 Gate

- `CONTENT_CANDIDATES_MACHINE_VALIDATION=PASS`
- `MODULE_OWNER_HASH_SIGNATURES=PENDING_3_PEOPLE_4_MODULES`
- `OWNER_CONTENT_BINDING_REQUIRED=OPEN`
- `FINAL_CANDIDATE_FREEZE=NOT_STARTED`
- `REAL_HUMAN_UAT=NOT_STARTED`
- `RELEASE=NO`

## 7. 证据边界

- 本包未替任何模块 Owner 签署。
- 本包未执行生产写入、部署、迁移、外部消息或真人 UAT。
- 未读取到的飞书正文不以推测补写；探索营目标 Sheet 的“三项实操＋Rubric”采用郑田源的确认作为当前来源声明，精确版本证据仍待绑定。
- 机器清单 `config/module-content-candidates.v1.json` 是详细字段的唯一候选事实源；本文只作人类签署说明。
