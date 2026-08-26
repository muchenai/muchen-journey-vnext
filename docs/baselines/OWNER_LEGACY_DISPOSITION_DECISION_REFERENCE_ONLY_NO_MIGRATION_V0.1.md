# Owner Legacy 处置决策｜REFERENCE ONLY / NO MIGRATION V0.1

> 决策日期：2026-08-26
> 决策人：刘默文
> 决策角色：Product Owner / Data Owner / Security-Privacy Owner
> 状态：`OWNER_CONFIRMED / EFFECTIVE / NO_RELEASE`

## 1. 决策

`OWNER_LEGACY_DISPOSITION_DECISION=REFERENCE_ONLY_NO_MIGRATION`

旧 `muchen-quest`、飞书多维表和既有只读审计证据仅作历史参考。Journey2.0 不再以补齐 23 表、正式回源抽取、逐记录分类或 Legacy 导入作为发布前置条件。

必须同时保留两组互不覆盖的事实：

- 历史审计结论：`LEGACY_COMPLETENESS_GATE=FAIL`；`COMPLETE_LEGACY_SNAPSHOT=NOT_ESTABLISHED`。
- 前瞻发布处置：`LEGACY_COMPLETENESS_GATE=SUPERSEDED_FOR_RELEASE`；`LEGACY_DATA_USAGE=REFERENCE_ONLY`；`LEGACY_FORMAL_MIGRATION=NOT_REQUIRED`；`MIGRATE_RECORD_COUNT=0`。

`SUPERSEDED_FOR_RELEASE` 不是 `PASS`，也不证明 23 表完整、准确、同一时点或可迁移。

## 2. 立即终止的路线

- 23 表完整性补证；
- 飞书正式回源抽取；
- 逐记录 Legacy 分类；
- Legacy migration manifest；
- Legacy 数据导入 Journey2.0。

既有迁移 shadow、schema、mapping、preflight 和 synthetic rehearsal 只保留为历史工程证据，状态统一为 `SUPERSEDED / NON_EXECUTABLE_FOR_LEGACY_IMPORT`。它们不再构成待完成工作，也不授权任何写入。

## 3. 历史资料的允许用途

允许：理解旧产品术语、运营习惯、已知问题、历史交互和待业务 Owner 重新确认的候选需求。

禁止：

- 作为 Journey2.0 人员、任务、积分、认证、人才或准入状态的事实源；
- 作为数据库字段、表结构、状态机或权限模型的直接约束；
- 以旧字段存在为由复制字段；
- 从旧积分、AI、自证、排行榜或阶段分流推导正式人才状态；
- 覆盖、删除或修正既有不可变审计 Run。

## 4. Journey2.0 新模型的唯一产品依据

按以下层级使用：

1. `Muchen_Journey_产品-代码继承映射表_V0.1.md` 中已经批准的继承方向；
2. `Muchen_Journey_冲突裁决清单_V0.1.md` 及本决策等 Owner 已批准裁决；
3. `build-contracts/00_Build_Contract_总索引_V0.1.md` 登记的逐模块 Build Contract；
4. Owner 后续明确决策。

候选合同、原型、机器测试和旧 23 表均不能自行提升为产品权威源。G1—G34 继续只是机器合同候选，除非另有 Pro 与 Runtime Gate。

## 5. 保护与保留

- 不删除、不修改飞书源数据；
- 不删除、不修改旧项目文件；
- 不修改既有不可变审计 Run；
- 不连接或写入 Journey2.0 数据库；
- 不创建或执行 migration；
- 不提交、合并、部署或发布。

## 6. 临时飞书应用

完成本决策记录和 `LEGACY_REFERENCE_ARCHIVE_V0.1` 后，提交“`Muchen Journey Phase0 只读审计`”临时应用撤销清单。撤销必须由 Security/Privacy Owner 对该清单另行明确确认；在确认前保持 `REVOCATION_NOT_AUTHORIZED`，不得操作应用。

## 7. 下一 Gate

`PRO_JOURNEY2_DOMAIN_MODEL_REBASE_REVIEW`
