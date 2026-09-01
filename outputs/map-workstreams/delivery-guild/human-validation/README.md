# delivery-guild 空白真人测试包

状态：`NOT_RUN`

本目录只为冻结候选 `9b222163ca5137acd2f1d726a8686c6675eb5089` 准备真人验收，不包含任何真人结果，也不改变候选、共享事实或发布状态。

## 包内容

- `test-plan.json`：三名目标学员、精确路径、五项契约标准与判定规则。
- `facilitator-protocol.md`：可直接照读的无引导脚本、计时点和记录规则。
- `results.blank.json`：三名匿名学员的空白结果槽位；所有结果保持 `NOT_RUN`。
- `privacy-evidence.json`：隐私最小化规则、允许的非敏感证据引用和冻结机器基线。
- `validate.mjs`：只读校验器；验证契约一致性、空白初态、隐私边界与冻结哈希。

## 执行前校验

在仓库根目录运行：

```bash
node outputs/map-workstreams/delivery-guild/human-validation/validate.mjs
```

预期输出：

```text
HUMAN_VALIDATION_PACKAGE=PASS
STATUS=NOT_RUN
PARTICIPANT_SLOTS=3
FROZEN_CANDIDATE_HASHES=PASS
```

## 真人执行规则

1. 先运行只读校验器；若失败，不开始测试，也不修冻结候选。
2. 仅招募满足 `test-plan.json` 目标画像、从未使用该候选的 3 名学员。
3. 每人使用全新浏览器本地状态，从精确起点自然走到精确终点。
4. 主持人逐字执行 `facilitator-protocol.md`，不得解释界面、术语、路径或下一步。
5. 不在本仓库的空白模板里直接记录真人数据。由获授权的人在批准的私密位置复制模板，只填写匿名、最小必要结果。
6. 不录入姓名、邮箱、电话、工号、部门、汇报关系、真实客户/项目/人员信息，不默认录音或录像。
7. 三场结束后才能计算总判定；机器证据不能替代任何真人观测。

## 状态边界

- 当前：`NOT_RUN`
- 允许的下一状态只能由有效真人证据得出：`HUMAN_FAIL` 或交由独立 Evaluator 判断是否满足 `HUMAN_PASS_CURRENT_GOLDEN_PATH`
- 本地图无权据此发布、集成、修改共享 Evidence Ledger 或声明完整 Journey 通过
