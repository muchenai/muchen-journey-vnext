# 探索营内测候选版本

此次替换学员端界面：默认飞书登录、Project 9 页面、仅探索营开放、提交即解锁、审核后完成。旧版四模块公开首页、邀请码主入口、单材料折叠和阶段完成跳转的源码正则测试已不再对应产品要求。

以 `project9-render.test.mjs` 对真实 React 组件的渲染测试替换这些页面结构断言；保留身份安全、审核、文档链接、反馈和 AI 历史记录测试。后端使用独立数据库验证实际提交、审核、返工和登录权限。没有通过跳过测试或关闭 CI 解决差异。

生产发布前仍需实际环境盘点、备份、正式组织与审核人配置、迁移及线上往返验收。不得复制本地 fixture 用户或密钥。

## 被新版行为替代的旧页面断言

- `exploration-camp-first-win-contract.test.mjs`: the first station keeps approved learning input before any personal output
- `exploration-camp-private-invite-orientation-contract.test.mjs`: the orientation is non-interactive and preserves one primary form action
- `full-module-journey-contract.test.mjs`: the current learner action precedes the controlled-module directory
- `full-module-journey-contract.test.mjs`: a learner without a journey projection still receives one executable current action
- `full-module-journey-contract.test.mjs`: module entry reuses existing Enrollment facts and does not create a second task source
- `full-module-journey-contract.test.mjs`: public orientation is limited to the four controlled release modules
- `human-experience-shell-contract.test.mjs`: the shared shell exposes the five contract fact labels as text
- `human-experience-shell-contract.test.mjs`: authority lookup failures fail closed instead of guessing an active state
- `human-experience-shell-contract.test.mjs`: waiting work exposes the submitted version as the single current action
- `human-experience-shell-contract.test.mjs`: the current task card projects immutable task, assignment, SLA and review facts
- `learner-experience-contract.test.mjs`: the task page reveals one learning material at a time
- `learner-experience-contract.test.mjs`: the response workspace stays hidden until required input is complete
- `learner-experience-contract.test.mjs`: the task contract leads with one deliverable and keeps secondary criteria on demand
- `learner-experience-contract.test.mjs`: Day 0 begins with a concrete 10-second choice and a three-line departure card
- `learner-experience-contract.test.mjs`: the Day 0 current action explains its value before the learner opens it
- `learner-experience-contract.test.mjs`: long source materials are framed as one-answer exploration instead of required consumption
- `learner-experience-contract.test.mjs`: treasure one begins with a quick judgment and a three-line response map
- `learner-experience-contract.test.mjs`: historical evidence stays available on demand
- `learner-experience-contract.test.mjs`: join and result pages keep operational explanations below the primary experience
- `learner-experience-contract.test.mjs`: the golden path starts from the governed shared home and private orientation
- `learner-loop-contract.test.mjs`: task detail and waiting states expose authoritative review and safety facts
- `learner-loop-contract.test.mjs`: revision keeps old evidence and displays structured human rubric feedback
- `learner-reentry-contract.test.mjs`: expired learner pages fail closed into an explicit operator-assisted recovery state
- `learner-reentry-contract.test.mjs`: reentry confirmation does not collect a new display name or claim new business facts
- `logout-session-feedback-contract.test.mjs`: learner exit control explains impact, exposes progress and errors, and blocks duplicate submits
- `logout-session-feedback-contract.test.mjs`: logged-out home receipt requires a confirmed non-valid session and offers reentry
- `ops-timezone.test.mjs`: server-rendered journey workspaces share the explicit product timezone
- `p0-closure-contract.test.mjs`: https links embedded in frozen text materials remain clickable without unsafe html
- `p0-learner-flow-repair-contract.test.mjs`: the station shows a three-step path instead of an undefined quiz
- `p0-learner-flow-repair-contract.test.mjs`: pending review is never presented as a completed station
- `p0-learner-flow-repair-contract.test.mjs`: revision gives the learner an immediate route back to their own work
- `p0-learner-flow-repair-contract.test.mjs`: a passed revision replaces the old revision callout with the final outcome
- `p0-learner-flow-repair-contract.test.mjs`: learner and reviewer status pages refresh while visible and announce changes
- `p0-learner-flow-repair-contract.test.mjs`: answer references are accepted by the editor but hidden until submission
- `p0-learner-flow-repair-contract.test.mjs`: Feishu-document work has a visible submission entry and novice guidance
- `p0-learner-flow-repair-contract.test.mjs`: material transitions preserve context while submissions show completion first
- `p0-learner-flow-repair-contract.test.mjs`: long links wrap and the three-step path becomes vertical on mobile
- `p0-learner-flow-repair-contract.test.mjs`: the learner sees a single current focus and visible response map
- `p0-learner-flow-repair-contract.test.mjs`: completed evidence stations can be retested without mixing in reviewer revision
- `p0-learner-flow-repair-contract.test.mjs`: the current-mission card occupies normal space immediately before the three-step path
- `p0-learner-flow-repair-contract.test.mjs`: formal model-judgement materials ask concrete questions that match the task
- `p0-learner-flow-repair-contract.test.mjs`: completed stations become achievement views instead of stale action prompts
- `p0-learner-flow-repair-contract.test.mjs`: long materials lead with a bounded exploration time without hiding source length
- `p0-learner-one-page-contract.test.mjs`: the essential task remains visible while secondary criteria stay on demand
- `p0-learner-one-page-contract.test.mjs`: learner copy removes repeated locking and stage labels
- `p0-learner-one-page-contract.test.mjs`: stage completion is seen before the learner chooses the next station
- `p0-learner-one-page-contract.test.mjs`: Day 0 opens with one achievable action instead of an eighty-minute burden
- `p0-learner-one-page-contract.test.mjs`: learner failure surfaces provide bounded recovery without raw API JSON
- `p0-learner-one-page-contract.test.mjs`: private invitation headline remains deliberate across desktop and mobile
- `product-entry-contract.test.mjs`: shared home is bound to the product contract and controlled release overlay
- `product-entry-contract.test.mjs`: public entry uses the approved visual-first journey proposition
- `product-entry-contract.test.mjs`: staff tools stay out of the public learner entry
- `product-entry-contract.test.mjs`: all canonical maps and growth missions remain ordered in the shared product contract
- `product-entry-contract.test.mjs`: the four contract states each resolve to their one exact primary action
- `product-entry-contract.test.mjs`: visitor and expired states validate complete invitation links on the homepage
- `product-entry-contract.test.mjs`: returning states use verified server facts and avoid authentication prefetch
- `production-canary-banner-contract.test.mjs`: production canary banner is bound to the runtime marker
- `submission-feedback-contract.test.mjs`: successful submission stays on the task and exposes an accessible receipt
- `wp24-formal-camp-v2-contract.test.mjs`: learner receives the V2 learning input before the response composer
- `wp27-journey-map-contract.test.mjs`: the route is orientation-only and leaves one primary current-stage entry
