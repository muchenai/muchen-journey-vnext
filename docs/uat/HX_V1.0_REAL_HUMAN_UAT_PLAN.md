# Muchen Journey 人本体验层 V1.0 真人 UAT 计划

状态：`NOT_RUN`  
适用发布合同：`PRODUCTION_CANARY_UAT`  
当前用途：固定候选形成后的真人安排输入；不是 UAT 结果、Owner 签署、Canary 或 Release 授权。

## 进入条件

- V3-08 固定候选 SHA、构建标识、migration head 与证据 manifest 已生成且工作树干净。
- `HX-GATE-001` 机器证据由 Tech Lead、QA/UAT Owner、Security/Privacy Owner 独立复核；当前均为 `NOT_RUN`。
- 8 名具名白名单真人和不可变 allowlist hash 由获授权 Owner 提供；当前没有人员姓名、账号或 allowlist，状态为 `NOT_RUN`。
- 每模块恰有 2 名学员路径；另有至少 1 名独立 Reviewer 与 1 名运营参与者，角色不得自审。
- 环境明确标记 `PRODUCTION_CANARY_UAT`；本实现任务不部署、不扩大白名单、不写生产数据。

## 参与者槽位与覆盖

| 槽位 | 模块 | 角色 | 具名真人 | 白名单证据 | 执行状态 |
| --- | --- | --- | --- | --- | --- |
| HX-UAT-L01 | 探索营 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L02 | 探索营 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L03 | 新手村 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L04 | 新手村 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L05 | AI 学院 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L06 | AI 学院 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L07 | 公会 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-L08 | 公会 | 学员 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-R01 | 跨模块 | 独立 Reviewer | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-O01 | 跨模块 | 运营 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |
| HX-UAT-W01 | 跨模块 | 独立见证人 | `NOT_ASSIGNED` | `NOT_RUN` | `NOT_RUN` |

## 固定脚本

每名学员必须在同一固定候选上完成并保留原始记录：进入模块、理解任务、完成实操、提交证据、等待审核、收到具名真人返工、重提、由具名真人通过、查看结果与申诉回链，以及一次越权/非白名单负向路径。阅读、点击、自证、AI 建议或积分不得替代任一步正式状态。

Reviewer 必须完成队列定位、固定 SubmissionVersion 与 Rubric 核对、返工理由、重提历史、通过签署、冲突/容量/替补/通知失败/升级检查。运营必须完成锁定、空态、失败态、Reviewer 容量与证据回链检查，不得绕过服务端权限。

键盘与读屏分别执行探索营、新手村、AI 学院、公会、Reviewer、运营共 6 条路径，合计 12 次；当前全部 `NOT_RUN`。

## 指标记录

`HX-METRIC-001/002/003/007/009/010` 必须使用合同固定分母、排除项和阈值。逐人计时、原话、路由日志、Submission/Evaluation/Outcome 链、焦点/读屏记录与结构化访谈均应绑定候选 SHA。没有执行的单元必须写 `NOT_RUN`；不得用 AI、合成人员、机器截图或口头说明补齐。

## 停止与重测

出现跨组织读取、无真人 Gate 的正式结果、旧版本覆盖、假成功、AI/激励越权、死 CTA、键盘/读屏阻断、候选漂移或 allowlist 扩大时立即停止受影响 mutation。修复后形成新候选，或按合同证明仍为同一固定候选后从前置 Gate 重新执行。任何通过结论都必须由合同指定的具名真人签署。
