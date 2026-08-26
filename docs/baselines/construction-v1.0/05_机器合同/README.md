# 机器合同使用说明

本目录把施工文档压缩成 Mini 可直接解析的合同。Markdown解释“为什么”，JSON固定“必须做什么、如何验收”。两者冲突时，先按 `SOURCE_MANIFEST.md` 的来源顺序裁决，再更新JSON；不得只改代码绕过合同。

## 文件

- `requirements.v1.json`：P0/P1需求、来源、Owner、验收和负向测试。
- `state-machines.v1.json`：正式状态与禁止转换。
- `release-gates.v1.json`：从开发到受控发布的机器/真人Gate。
- `traceability.v1.json`：来源、冲突、模块、现有技术载体与要求ID映射。
- `module-content-package.schema.v1.json`：四模块正式内容包的失败关闭格式。
- `implementation-evidence.schema.v1.json`：Mini逐Requirement提交实现/测试证据的格式。

## Mini执行循环

```text
读取 contracts → 选择最小未完成P0 → 标注实现目标
→ 先写正向/负向测试 → 实现 → 全量回归
→ 更新 evidence（不是自改requirement）
→ 若需要Owner内容/真人Gate则停止该分支，继续其他安全P0
→ 候选冻结后停止业务开发，进入UAT/发布Gate
```

## 状态

- `APPROVED_FOR_BUILD`：可实现。
- `OWNER_CONTENT_BINDING_REQUIRED`：只可实现通用载体，不可发明内容。
- `DEFERRED`：不得进入9/1路由、迁移或发布包。
- `NOT_RUN`：不能当作失败或成功；需要真实执行证据。

## 提交证据格式

每个 Requirement ID 至少登记：`implementation_refs, test_refs, negative_test_refs, commit_sha, status, executed_at, evidence_hashes, remaining_risks`。机器只能把完成项标为 `READY_FOR_HUMAN`；真人/发布状态由对应签署合同产生。

Owner内容包应先通过 `module-content-package.schema.v1.json`，再由对应Owner签署其hash；Mini只消费签署后的包。实现证据应逐条通过 `implementation-evidence.schema.v1.json`，但schema通过本身不等于测试或真人Gate通过。

