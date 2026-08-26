# Muchen Journey 全模块开发解锁决议 V0.1

> 状态：`DIRECT_FULL_MODULE_DEVELOPMENT_AUTHORIZED / DEVELOPMENT_STARTED / RELEASE_BLOCKED`  
> 决议日期：2026-08-23  
> 决议人：刘默文  
> 决议身份：业务 Decider、产品 Owner、Tech Lead

> 开发主机补充决议：2026-08-23 起，后续持续开发由 Mac mini 本地 Codex 执行，MacBook Pro 只负责阶段复盘和校正；见 `Muchen_Journey_MacMini原生开发交接单_V0.1.md`。

## 1. 决议

刘默文明确指令“直接开始全模块开发”。该指令覆盖此前 `0/6 Build Contract` 状态下的开发冻结，但不改变以下事实：

- 刘默文本人承担的六项角色已接受；
- 郑田源、屠元琦、段超群的八项角色仍待本人接受；
- 六份 Build Contract 仍未完成全体签署；
- 本次解锁授权开发，不授权正式发布、生产数据迁移、生产任务执行或自动人才结论。

开发分支固定为：`codex/full-module-development`。

## 2. 本次直接进入开发的六个模块

| BC | 模块 | 业务 Owner | 第一开发结果 |
|---|---|---|---|
| BC-001 | 探索营 | 郑田源 | V1.0 四宝藏、三项能力实操与个人成长基线入口 |
| BC-002 | 新手村 | 屠元琦 | 受控真实任务的提交、审核、返工/通过闭环 |
| BC-003 | AI 学院 | 段超群 | 异步学习＋实操证据＋人工能力 Gate |
| BC-004 | 公会 | 段超群 | 真实业务授权任务、导师反馈与交付证据 |
| BC-005 | 认证竞技场 | 段超群 | 固定挑战、真人 Panel 签署与独立申诉 |
| BC-006 | Career Map | 段超群 | 事实、人工判断、AI 建议和 Growth Plan 分层呈现 |

## 3. 解锁后仍不可突破的最低边界

1. Journey 可以承载受控真实项目训练，但不得在系统内直接执行生产作业。
2. 正式能力结果必须来自实操、证据和真人签署；自证、积分、学习完成或 AI 初评均不能产生正式状态。
3. AI 只做自查、初评和摘要；高影响结论由真人负责并允许申诉。
4. 屠元琦不能同时成为自己运营任务的唯一 Reviewer 和唯一 UAT 签署人。
5. 刘默文不能以产品、技术、数据、安全、发布多重身份完成自审自放；发布候选必须有独立复核证据。
6. 历史数据必须先审计、分类和演练，不能因开发解锁而直接迁移生产数据。

违反任一边界时，允许继续隔离开发，但禁止将候选标记为 `READY_FOR_RELEASE`。

## 4. 开发与发布状态分离

| 状态 | 当前值 | 含义 |
|---|---|---|
| 开发授权 | `AUTHORIZED` | 六模块可以并行开发 |
| Owner 任命 | `14/14 APPOINTED` | 组织任命已完成 |
| 本人接受 | `6/14 ACCEPTED` | 三名团队 Owner 仍需本人确认 |
| Build Contract 完整签署 | `0/6` | 未签署项继续作为发布前责任 Gate |
| 正式发布授权 | `NOT_AUTHORIZED` | 不得部署或对外声称全模块可用 |

## 5. 第一批代码事实

- 分支：`codex/full-module-development`
- 已建立：全旅程总览、六模块统一产品合同、六模块详情路由、人与证据导向的信息架构。
- 产品事实源：`config/muchen_journey_product.json#/approved_product_modules`
- 当前认证竞技场产品键：`certification-arena`；旧运行键 `boss-dungeon` 仅作为兼容别名保留，不再作为对人产品名称。
- 验证：Web 合同测试、TypeScript、ESLint、Next.js production build 必须全部通过后，才可形成开发候选。

## 6. 下一开发 Gate

开发继续按共享底座依赖顺序推进：

1. 共享 Person、Evidence、Human Gate、Appeal 和 Growth Plan 领域合同；
2. 探索营与新手村继承闭环；
3. AI 学院、公会、认证竞技场；
4. Career Map 聚合与解释；
5. 历史数据审计和只读迁移演练；
6. 独立 QA/UAT、发布候选和显式发布决议。

本文件只解除开发冻结，不替代任何人的接受记录、人工评审证据或发布签署。
