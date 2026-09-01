# AI 学院第一条黄金路径

状态：`READY_FOR_HUMAN`（隔离候选，未集成、未发布）  
地图：`ai-academy`  
People AI 输出方向：`ai-capability-profile`

## 人现在可以做什么

学员可以从一组明确标为合成夹具的“个人能力目标 + 岗位 AI 能力需求”开始，完成第一份四格学习输入，在一个合成工作场景中分别写出产出、背景、边界和核验方式，并查看一份只陈述可观察事实的会话内练习记录。

记录会回显学员原文和 4/4 确定性完成检查，同时明确否认课程通过、能力掌握、岗位胜任、绩效、晋升或任何用人结论。

## 唯一活动黄金路径

- 合同：`outputs/map-workstreams/ai-academy/contract.json`
- 起点：`synthetic-personal-goal-and-role-requirement-visible`
- 终点：`explainable-practice-evidence-visible`
- 路由：`/ai-academy/`
- 步骤：看见目标 → 完成输入 → 做一次练习 → 查看证据

## 本地可运行入口

在仓库根目录运行：

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory prototypes
```

然后打开：

```text
http://127.0.0.1:4173/ai-academy/
```

该页面不需要身份、会话、API 或数据库。页面刷新会清空练习文字；唯一网络读取是同目录的 `synthetic-fixture.json`。

## 数据与内容边界

- 人物、岗位、课程和场景均为合成夹具，并在每一步可见标注。
- Person、Capability、Evidence、Progress 与 Identity 共享事实源未读取或写入。
- 没有正式课程、公司岗位标准、真人结论或人才判断。
- 没有生产变更、真实邀请、发布配置或共享 API 变更。

## 验收状态

- Product Doctor：`PASS`
- 原型合同测试：4/4 通过
- 浏览器：390 / 768 / 1280 完整路径通过，无横向溢出，正常路径零控制台错误
- 独立 Evaluator：`READY_FOR_HUMAN`
- 真人门槛：`NOT_INFERRED`

完整机器证据见 `outputs/map-workstreams/ai-academy/evaluator-report.json` 与 `outputs/map-workstreams/ai-academy/browser-evidence/manifest.json`。

## 冻结规则

当前候选只允许接受真人测试，不得因机器通过而宣称正式课程有效、能力提升、地图集成、晋级或发布。任何交互或内容改动都会产生新候选并要求重新执行机器验收。
