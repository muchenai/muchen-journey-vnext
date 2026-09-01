# 新手村真人验收空白包

状态：`NOT_RUN`
冻结候选：`14cc8b31936597f846c9b48bdaa36f7658155e61`
目标：`newcomer-village-first-real-integration-action`

本目录只提供可直接执行的空白真人测试材料，不包含、推断或替代任何真人结果。冻结候选的 contract、prototype 与既有机器证据不得修改。

## 文件

- `protocol.md`：3 名目标新人的无讲解测试协议、起止边界、记录顺序和隐私停止规则。
- `human-validation-plan.json`：3 个匿名槽位、原始测量字段、契约原文、结构化阈值和 `NOT_RUN` 初态。
- `validate.mjs`：只读检查冻结文件、地图契约、协议与空白记录的一致性；不写文件、不计算真人结论。

## 运行空白包校验

从仓库根目录运行：

```bash
node outputs/map-workstreams/newcomer-village/human-validation/validate.mjs
```

预期输出：

```text
HUMAN_VALIDATION_PACKAGE=PASS
TARGET=newcomer-village-first-real-integration-action
FROZEN_CANDIDATE=14cc8b31936597f846c9b48bdaa36f7658155e61
HUMAN_VALIDATION=NOT_RUN
PARTICIPANT_SLOTS=3
HUMAN_RESULT_INFERRED=false
```

## 执行边界

真人测试前，把 `human-validation-plan.json` 复制到获批的私有证据位置再填写；不要在本仓库提交填有真人数据的副本。只允许使用匿名槽位和不含敏感正文的证据引用。测试者不得创建真实业务邀请、修改身份、连接共享事实源或执行发布动作。

完成 3 个槽位并取得合格的非敏感证据后，仍须由独立 Evaluator 按地图契约判定 `HUMAN_FAIL` 或 `HUMAN_PASS_CURRENT_GOLDEN_PATH`；本校验器不会自动作出该判定。
