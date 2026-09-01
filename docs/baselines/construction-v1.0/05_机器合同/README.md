# 机器合同使用说明

本目录把施工文档压缩成 Mini 可直接解析的合同。Markdown解释“为什么”，JSON固定“必须做什么、如何验收”。两者冲突时，先按 `SOURCE_MANIFEST.md` 的来源顺序裁决，再更新JSON；不得只改代码绕过合同。

## 文件

- `requirements.v1.json`：P0/P1需求、来源、Owner、验收和负向测试。
- `state-machines.v1.json`：正式状态与禁止转换。
- `release-gates.v1.json`：从开发、生产Canary UAT到受控发布的机器/真人Gate。
- `production-canary-uat-authorization.schema.v1.json`：准确候选的8人生产Canary部署授权证据；schema本身不构成授权。
- `traceability.v1.json`：来源、冲突、模块、现有技术载体与要求ID映射。
- `module-content-package.schema.v1.json`：四模块正式内容包的失败关闭格式。
- 仓库 `config/module-content-candidates.v1.json`：保留四模块经批准候选及原始 hash，不直接作为正式内容包。
- 仓库 `config/module-content-approval-evidence.v1.json` 与 `config/exploration-sheet-version-binding.v1.json`：固定具名 Owner 批准证据和探索营目标 Sheet 版本元数据绑定。
- 仓库 `config/module-content-packages/module-content-package-index.v1.json`：四模块正式内容包索引；其状态为 `G1_CONTENT_BINDING_PASS`，不构成候选冻结、Canary 部署或发布授权。
- `implementation-evidence.schema.v1.json`：Mini逐Requirement提交实现/测试证据的格式。

## Mini执行循环

```text
读取 contracts → 选择最小未完成P0 → 标注实现目标
→ 先写正向/负向测试 → 实现 → 全量回归
→ 更新 evidence（不是自改requirement）
→ 若需要Owner内容/真人Gate则停止该分支，继续其他安全P0
→ 候选冻结后停止业务开发，完成扫描/恢复/回滚
→ `CANARY_DEPLOYMENT_GO`后仅对8人白名单执行生产Canary UAT
→ 独立复核和`RELEASE_GO`后才扩大至最多25人
```

## 状态

- `APPROVED_FOR_BUILD`：可实现。
- `OWNER_CONTENT_BINDING_REQUIRED`：只可实现通用载体，不可发明内容。
- `DEFERRED`：不得进入9/1路由、迁移或发布包。
- `NOT_RUN`：不能当作失败或成功；需要真实执行证据。

## 提交证据格式

每个 Requirement ID 至少登记：`implementation_refs, test_refs, negative_test_refs, commit_sha, status, executed_at, evidence_hashes, remaining_risks`。机器只能把完成项标为 `READY_FOR_HUMAN`；真人/发布状态由对应签署合同产生。

Owner内容候选先通过 `scripts/validate_module_content_candidates.py` 并固定模块 hash；具名 Owner 的批准由产品 Owner 证明绑定后，通过 `scripts/promote_module_content_packages.py` 转换为符合 `module-content-package.schema.v1.json` 的正式内容包。当前 G1 已通过，但 Mini 不得把 G1 扩张为候选冻结、生产 Canary 或发布授权。实现证据应逐条通过 `implementation-evidence.schema.v1.json`，但 schema 通过本身不等于测试或真人 Gate 通过。
