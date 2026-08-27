# Muchen Journey Construction V1 Owner Decision Pack V1.1

> 状态：`ACTIVE_DECISION_PACK / G1_CONTENT_BINDING_PASS / FINAL_CANDIDATE_FREEZE_REQUIRED`
>
> 生效范围：Construction V1 四模块 P0 内容候选
>
> 替代：`Muchen_Journey_Construction_V1_Owner_Decision_Pack_V1.0.md` 中所有旧 Owner 输入占位符
>
> 不替代：模块 Owner 本人批准、真人 UAT、独立复核、Canary 部署授权或 `RELEASE_GO`

## 1. 活动事实源

- 详细内容候选：`config/module-content-candidates.v1.json`
- 候选清单内置 SHA-256：`b517977338de3da689bc5e61b5bb81c57d0932f5759b3423b79e15ab8f98b3a6`
- 签署台账：`config/module-content-signoff-manifest.v1.json`
- 人类说明：`docs/baselines/Muchen_Journey_Product_Owner_Content_Supplement_V1.0.md`
- 产品 Owner 授权：`SRC-OWNER-03 / AUTHORIZE_MINIMUM_P0_CONTENT_COMPLETION`

字段解释、任务正文、Rubric、Reviewer、SLA、数据边界和积分以详细内容候选为唯一候选事实源。本文件不复制全部字段，避免形成第二套内容版本。

## 2. 已完成的决定

| 范围 | 决定 |
|---|---|
| 探索营结构 | V1.0 四宝藏；个人成长基线为结果包 |
| 探索营实操 | `EXP-P1`、`EXP-P2`、`EXP-P3`，分别提交、真人审核、允许返工 |
| 新手村 P0 | `NV-T1-COMPANY-INDUSTRY-CARD` 与 `NV-T2-AI-DELIVERY-GLOSSARY`；历史 T+30 不进入本次 Canary |
| AI 学院 P0 | 两项必修资源、首单元指南、`AIA-M1-AI-LITERACY-CARD` |
| 交付线公会 P0 | 交付使命与边界、可追溯交接指南、`DLG-P1-TRACEABLE-HANDOFF` |
| 任务环境 | 本批全部为 `SIMULATION`；不执行生产作业，不写外部生产系统 |
| 数据 | 只用公开、合成或获批脱敏材料；证据默认保留 180 天 |
| AI | 只做自查、初评和摘要；不产生正式结论 |
| 积分 | 真人通过后追加；只作激励与参考，不产生人才结论 |
| Reviewer | 主 Reviewer 万雨欣；备用 Reviewer 屠元琦 |
| 容量 | 每滚动 7 日最多 25 名唯一学员，8 人 Canary 包含在内 |
| SLA | 12 小时未接单触发备用；24 小时首次反馈；48 小时完成；返工后 24 小时反馈 |
| 升级 | 屠元琦负责运营升级，刘默文为最终升级人；申诉由未参与原结论的人处理 |
| UAT 见证 | 冯宇汀；候选 UAT 与 Release Review 仍未执行 |

## 3. 固定候选 hash

| 模块 | Owner | Candidate SHA-256 | 当前签署状态 |
|---|---|---|---|
| `exploration-camp` | 郑田源 | `1d9feb1672c847279c0b85cdc5a13ea9a9890d45cad4b223dd59ef2f05bbeb1c` | `APPROVED / SOURCE_VERSION_BOUND` |
| `newcomer-village` | 屠元琦 | `6dfedfa9e95e78b8ab06115b08f0b5e7379b988b87f59de5c166c37f45937f1b` | `APPROVED / REVIEWER_OPERATIONS_ACCEPTED` |
| `ai-academy` | 段超群 | `e58880f712ee6c1aa3e4e31e5a51e62e15ac1e8bd9a75ec3600ca8b03095a894` | `APPROVED` |
| `delivery-guild` | 段超群 | `4ffe612ddec9b177596d7cc4b03d29f1231a00c42c63ad4f0f4759c72d793cba` | `APPROVED` |

## 4. Owner 内容 Gate 结果

- 产品 Owner 已正式证明郑田源、屠元琦、段超群作出上述精确 hash 批准；证据为 `config/module-content-approval-evidence.v1.json`。
- 探索营目标 Sheet 已绑定可复核版本元数据：文档 token、sheet id、标题、可见 Owner、最近修改时间、当前 Sheet 标题和只读状态；绑定 hash 为 `4ce0734ea7b3b21c768e706a28b836a06d164a9d194a822788a6e49f56bf3c6b`。
- 该绑定不是 XLSX/CSV 全文 hash。任何最近修改时间、sheet id、标题或候选 hash 变化，均触发重新批准。
- 四个正式内容包索引为 `config/module-content-packages/module-content-package-index.v1.json`，内置 hash 为 `76086990bf28fdf567b7f21f4600e3a9828de116c41c4b0b3166ef233f22bfdd`。

结论：`G1_CONTENT_BINDING=PASS`。这一结论不替代最终候选冻结、同候选机器 Gate、恢复验证、真人 UAT、独立复核或发布决定。

## 5. 状态转换

```text
PRODUCT_OWNER_FIELDS_COMPLETE
  + 3人4模块批准证明
  + 探索营Sheet版本元数据绑定
  + 4个正式内容包机器校验
= G1_CONTENT_BINDING_PASS
```

当前可以：

- 把正式 `module-content-package.v1` 接入内容载入、路由、显示和机器验证；
- 开始最终候选收口与冻结准备；

当前仍不得：

- 不得执行生产 Canary 部署或真人 UAT；
- `RELEASE=NO`。

## 6. 生产影响

- `production_mutation_executed=false`
- `production_deployment_executed=false`
- `external_message_sent=false`
- `human_gate_filled_by_machine=false`
