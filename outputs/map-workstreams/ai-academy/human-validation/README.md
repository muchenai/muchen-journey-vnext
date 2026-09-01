# AI 学院三人真人验收记录包

本目录只为冻结候选 `ai-academy-first-explainable-practice-evidence-20260823-r1` 提供执行支持。当前真人状态为 `NOT_RUN`；空白模板不是参与者证据，校验通过也不代表真人通过。

## 文件

- `three-person-records.blank.json`：3 个去身份化参与者槽位，覆盖原始耗时、主持人介入、目标连接复述、方法回忆、独立练习、内容价值、证据边界、清晰度和继续意愿。
- `result.NOT_RUN.json`：六项契约门槛的空白汇总，全部保持 `NOT_RUN`。
- `validate_human_validation.py`：只读校验器；读取记录、结果和冻结合同，只向 stdout 输出报告，不写文件。

## 执行前

1. 从冻结候选提交 `2e9561968d35676d09b3eacfe06b994276846e27` 运行原型，不修改候选。
2. 为每名学员复制一份独立、无旧状态的浏览器会话。
3. 确认参与者符合目标画像，且此前未参与本原型设计。
4. 主持人不得解释目标、岗位需求、四格方法、练习要求、证据含义或下一步。
5. 不记录姓名、邮箱、工号、真实客户、真实业务材料或练习原文；文本字段只记去身份化复述与观察摘要。

## 填录规则

- 测试尚未执行时，保留两个 JSON 模板原样；所有观察值为 `null` 或空数组。
- 真正执行后，先复制模板到新的证据目录，再把包级和三个会话的 `status` 改为 `COMPLETED`。
- `timing_raw_seconds` 从页面首次可见起连续计时，记录每个里程碑的原始秒数，不四舍五入为“通过/失败”。
- 主持人的任何说明、引导或救援都逐条加入 `facilitator.interventions`，并令 `intervention_count` 与数组长度一致。
- 量表使用 1–5 整数；不允许由观察者代填参与者评分。
- `content_value` 是补充诊断，不改变合同中 `clarity-and-continuation` 的三项中位数门槛。
- `result` 文件的六项状态必须来自原始三人记录，不得预先填写或用机器证据替代。

## 校验命令

在仓库根目录验证当前空白包：

```bash
python3 outputs/map-workstreams/ai-academy/human-validation/validate_human_validation.py \
  --records outputs/map-workstreams/ai-academy/human-validation/three-person-records.blank.json \
  --result outputs/map-workstreams/ai-academy/human-validation/result.NOT_RUN.json \
  --contract outputs/map-workstreams/ai-academy/contract.json
```

预期输出包含：

```text
HUMAN_VALIDATION_PACKAGE=PASS
HUMAN_VALIDATION_STATUS=NOT_RUN
```

若填写后的证据完整且有效，校验器会重新计算六项门槛，并要求结果文件逐项匹配。全部通过只产生 `HUMAN_PASS_CURRENT_GOLDEN_PATH`；任一项失败产生 `HUMAN_FAIL`。这两者都不授权集成或发布。
