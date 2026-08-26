# BC-003｜AI学院 Build Contract V0.1

> 状态：`BUILD_STARTED_BY_DECIDER_OVERRIDE / TEAM_ACCEPTANCE_AND_FIRST_UNIT_PENDING / NO_RELEASE`  
> 开发授权：见 `../Muchen_Journey_全模块开发解锁决议_V0.1.md`；未签署项继续作为发布前Gate。
> MAP-ID：MAP-007—010、021—023、027  
> 权威方向：学习可异步；正式能力结果必须来自实操、证据和人工Gate。

## 1. 贡献契约

使用者是学习者、内容Owner、业务Reviewer和下一任务/公会Owner。完成一个学习单元后，学习者不仅看过内容，还产出一份可复核练习；Reviewer能依据版本化Rubric给出返工或通过；下一环节能读取证据而不是相信课程完成率。

AI学院不以课程数量、观看时长、签到、题库分数或AI评价作为正式能力成果。

## 2. 最小产品结构

第一发布至少包含一个经批准的学习单元，完整闭环为：

`目标与适用条件 → 异步学习输入 → 示例/反例 → 结构化实操 → 提交 → 人工点评 → 返工/通过 → 能力证据 → 下一练习`

每个单元必须明确：目标能力、适用角色、前置条件、内容来源、版本、预计时间、练习任务、交付格式、Rubric、Reviewer、有效期和下一行动。

## 3. 正式状态与证据

材料阅读只写 `LearningMaterialCompletion`。练习沿用Assignment、SubmissionVersion、Review和Evaluation。只有Reviewer `PASS` 后才能写入正式能力证据；AI建议和自测分数作为附属字段，不得覆盖人工结论。

学习证据至少包含：学习单元版本、练习任务版本、原始产物、修订历史、Reviewer、Rubric、反馈、结论、AI使用说明和有效期。

## 4. AI边界

允许：个性化解释、示例生成、练习自查、缺项提示、初评和Reviewer摘要。

禁止：自动授予能力等级、认证、岗位适配、项目准入；隐藏模型/Prompt版本；用AI生成内容冒充学员产出；把AI初评写成 `FINALIZED`。

## 5. 复用与候选处置

复用2.0的Content Draft、Task/Journey版本、材料完成、提交修订、Reviewer工作台、证据、审计和权限。

当前 `ai-academy-first-explainable-practice-evidence` 合成原型保留为UX候选：目标—输入—练习—证据四步可参考；其合成内容、无共享写入和机器 `READY_FOR_HUMAN` 不构成正式AI学院产品事实。

## 6. 验收 Gate

| Gate | 通过标准 | Owner |
| --- | --- | --- |
| P-01 单元合同 | 首批单元的目标、来源、练习、Rubric、Reviewer和有效期全部批准 | AI学院 Owner＋Content Owner |
| M-01 状态隔离 | 阅读、自测、AI初评、提交、人工结论五类状态可区分 | Tech Lead＋QA |
| H-01 学习迁移 | 3/3目标学习者无需讲解完成练习，并能说明把方法用于什么任务 | AI学院 Owner |
| H-02 Reviewer可用 | 2名Reviewer完成同一校准样例，反馈可执行且差异在阈值内 | Reviewer Owner |
| G-01 可解释 | 学员能看到内容/任务版本、证据、真人结论和AI建议的区别 | 产品 Owner＋治理 Owner |

## 7. 第一发布指标

主指标：通过人工审核的练习产出率。配套指标：首次提交到首次人工反馈时长、返工后通过率、Reviewer一致性、30天内证据被下一任务实际使用率。观看完成率只作过程诊断。

## 8. 签署前缺口

- 首批学习单元与权威内容来源；
- Content Owner、执行Reviewer及独立复核人；
- 目标能力模型、Rubric和有效期；
- AI使用、抄袭/代做、申诉和隐私规则。

角色任命：产品 Owner 刘默文 `ACCEPTED_ROLE`；AI学院 Owner 段超群 `APPOINTED_PENDING_ACCEPTANCE`；Tech/Data/Security 刘默文 `ACCEPTED_ROLE`；QA/UAT 与 Reviewer/Panel Owner 屠元琦 `APPOINTED_PENDING_ACCEPTANCE`。首个单元的Content Owner和执行Reviewer仍需另行指定；合同结论仍为 `PENDING`。
