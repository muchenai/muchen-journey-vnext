import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const taskPage = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url),
  "utf8",
);
const submissionComposer = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url),
  "utf8",
);
const joinPage = await readFile(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const resultPage = await readFile(
  new URL("../src/app/app/result/page.tsx", import.meta.url),
  "utf8",
);
const homePage = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
const learnerLayout = await readFile(
  new URL("../src/app/app/layout.tsx", import.meta.url),
  "utf8",
);
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("the task page reveals one learning material at a time", () => {
  assert.match(taskPage, /const activeMaterialIndex =/);
  assert.match(taskPage, /const isActive = index === activeMaterialIndex/);
  assert.match(taskPage, /const isLocked = !isComplete && !isActive/);
  assert.match(taskPage, /className="learning-material-card" open=\{isActive\}/);
  assert.match(taskPage, /完成上一项后解锁/);
  assert.match(taskPage, /我找到 1 条线索，开始\$\{practiceNoun\}/);
  assert.match(taskPage, /<summary>查看材料说明<\/summary>/);
  assert.match(taskPage, /function MaterialOpenLink/);
  assert.match(taskPage, /用企业飞书打开/);
  assert.match(taskPage, /首次打开需登录/);
  assert.match(taskPage, /<summary>打不开？<\/summary>/);
  assert.match(taskPage, /const taskActionUrl = instructionLinks\.find\(isFeishuMaterial\)/);
  assert.match(taskPage, /taskActionUrl=\{taskActionUrl\}/);
  assert.match(submissionComposer, /打开本主题题面/);
  assert.match(submissionComposer, /首次打开需使用企业飞书登录/);
  assert.match(styles, /\.external-document-launch/);
  assert.match(taskPage, /请勿标记完成/);
  assert.match(styles, /\.learning-material-card\[open\] > summary::after/);
  assert.doesNotMatch(styles, /\.learning-material-card\[open\] summary::after/);
  assert.match(taskPage, /className="material-focus-prompt"/);
  assert.match(taskPage, /不用通读，先带着这一个问题/);
});

test("the response workspace stays hidden until required input is complete", () => {
  assert.match(
    taskPage,
    /<section className="task-brief"[\s\S]*\{materialsReady \? <section id="task-workspace" className="task-workspace"[\s\S]*<SubmissionComposer/,
  );
  assert.match(taskPage, /开始\{practiceNoun\}/);
  assert.match(taskPage, /isDayZero \? "选一个出发问题" : "打开当前线索"/);
  assert.doesNotMatch(taskPage, /沿着动作前进/);
  assert.doesNotMatch(taskPage, /当前固定任务版本不接收附件/);
});

test("the task contract leads with one deliverable and keeps secondary criteria on demand", () => {
  assert.match(taskPage, /<section className="task-brief"/);
  assert.match(taskPage, /const taskBriefHeading = isDayZero/);
  assert.match(taskPage, /\? "完成一张三句出发卡"/);
  assert.match(taskPage, /: assignment\.required_deliverables\[0\]/);
  assert.match(taskPage, /<h3 id="task-deliverables-title">这一站只交付<\/h3>/);
  assert.match(taskPage, /assignment\.required_deliverables\.map/);
  assert.ok(taskPage.indexOf("task-brief") < taskPage.indexOf("task-workspace"));
  assert.match(taskPage, /className="task-supporting-rules task-contract-columns"/);
  assert.match(taskPage, /怎么完成<\/h3>/);
  assert.match(taskPage, /className="task-success-criteria"/);
  assert.match(taskPage, /<summary>怎样算完成？<\/summary>/);
  assert.ok(taskPage.indexOf("task-brief") < taskPage.indexOf("task-workspace"));
  assert.doesNotMatch(taskPage, /<details className="task-supporting-rules"/);
  assert.doesNotMatch(taskPage, /需要时查看方法与完成标准/);
});

test("Day 0 begins with a concrete 10-second choice and a three-line departure card", () => {
  assert.match(taskPage, /className="day-zero-briefing"/);
  assert.match(taskPage, /一天结束时，你会带走什么？/);
  assert.match(taskPage, /这家公司为什么做 AI 数据？/);
  assert.match(taskPage, /真实项目里，我要负责什么？/);
  assert.match(taskPage, /我会怎样证明自己的判断力？/);
  assert.match(taskPage, /带一个问题/);
  assert.match(taskPage, /找一条线索/);
  assert.match(taskPage, /做一个动作/);
  assert.match(taskPage, /完成一张三句出发卡/);
  assert.match(taskPage, /需要帮助？查看完整要求/);
  assert.match(taskPage, /href=\{isDayZero \? "#day-zero-choice" : "#learning-materials-title"\}/);
  assert.match(taskPage, /href="#learning-materials-title"/);
});

test("long source materials are framed as one-answer exploration instead of required consumption", () => {
  assert.match(taskPage, /原材料约 \{material\.estimated_duration_minutes\} min · 这一轮只找 1 条线索/);
  assert.match(taskPage, /不用通读，先带着这一个问题/);
  assert.match(taskPage, /className="material-exploration-contract"/);
  assert.match(taskPage, /找到一条线索/);
  assert.match(taskPage, /立即返回/);
  assert.match(taskPage, /从信里找一句/);
});

test("treasure one begins with a quick judgment and a three-line response map", () => {
  assert.match(taskPage, /const isFirstTreasure =/);
  assert.match(taskPage, /客户真正买的是什么？/);
  assert.match(taskPage, /更多低价人力/);
  assert.match(taskPage, /可验收的确定性交付/);
  assert.match(taskPage, /先找证据，不用记住全文/);
  assert.match(taskPage, /把答案放进这三格/);
  assert.match(taskPage, /公司在解决什么问题？/);
  assert.match(taskPage, /未来一周你会做什么？/);
  assert.match(taskPage, /需要提示？查看完成方法/);
});

test("historical evidence stays available on demand", () => {
  assert.match(taskPage, /<summary>查看提交历史<\/summary>/);
});

test("default learner copy does not repeat input or completion instructions", () => {
  assert.doesNotMatch(taskPage, /先完成输入/);
  assert.doesNotMatch(taskPage, /完成当前材料后，小任务会自动出现/);
  assert.doesNotMatch(taskPage, /完成本阶段/);
});

test("join and result pages keep operational explanations below the primary experience", () => {
  assert.match(joinPage, /从上次离开的地方继续/);
  assert.doesNotMatch(joinPage, /Enrollment|Assignment/);
  assert.match(resultPage, /<summary>查看通知与过程记录<\/summary>/);
  assert.match(resultPage, /<summary>查看评审与准入详情<\/summary>/);
  assert.match(resultPage, /你走完了这段探索/);
  assert.match(resultPage, /也留下了只属于你的判断/);
  assert.match(resultPage, /你带走的，不只是答案/);
  assert.match(resultPage, /Journey 8 \/ 8/);
  assert.match(resultPage, /className="treasure-collection"/);
  assert.match(resultPage, /className="ability-collection"/);
  assert.match(resultPage, /learnerPageRequest<CurrentAction>\("\/api\/v1\/me\/current-action"\)/);
  assert.match(resultPage, /aria-label="回看启程"/);
  assert.match(resultPage, /aria-label=\{`回看宝藏/);
  assert.match(resultPage, /aria-label=\{`回看能力评测/);
  assert.match(resultPage, /href=\{`\/app\/tasks\/\$\{node\.assignment_id\}`\}/);
  assert.ok(resultPage.indexOf("下一步") < resultPage.indexOf("结论分层"));
  assert.doesNotMatch(resultPage, /04 · 通知状态|05 · 不可变时间线/);
  assert.doesNotMatch(resultPage, /系统只整理固定证据/);
});

test("the golden path starts as a journey instead of a generic session shortcut", () => {
  assert.match(homePage, /一天，八站。带走四份认知与三项真实能力证据/);
  assert.match(homePage, /Day 0 · 启程/);
  assert.match(joinPage, /className="join-scene"/);
  assert.match(joinPage, /第一站已经为你亮起/);
  assert.match(joinPage, /走进第一站/);
  assert.match(api, /export async function hasLearnerSession/);
  assert.match(api, /\/api\/v1\/me\/current-action/);
  assert.doesNotMatch(layout, /hasLearnerSession|learnerPageRequest/);
  assert.match(learnerLayout, /href="\/app">我的旅程/);
});
