import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const taskPage = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url),
  "utf8",
);
const joinPage = await readFile(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const resultPage = await readFile(
  new URL("../src/app/app/result/page.tsx", import.meta.url),
  "utf8",
);
const homePage = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("the task page reveals one learning material at a time", () => {
  assert.match(taskPage, /const activeMaterialIndex =/);
  assert.match(taskPage, /const isActive = index === activeMaterialIndex/);
  assert.match(taskPage, /const isLocked = !isComplete && !isActive/);
  assert.match(taskPage, /className="learning-material-card" open=\{isActive\}/);
  assert.match(taskPage, /完成上一项后解锁/);
  assert.match(taskPage, /完成材料，开始\$\{practiceNoun\}/);
  assert.match(taskPage, /<summary>查看材料说明<\/summary>/);
  assert.match(taskPage, /<span>打开学习材料<\/span>/);
});

test("the response workspace stays hidden until required input is complete", () => {
  assert.match(
    taskPage,
    /<section className="task-brief"[\s\S]*\{materialsReady \? <section id="task-workspace" className="task-workspace"[\s\S]*<SubmissionComposer/,
  );
  assert.match(taskPage, /开始\{practiceNoun\}/);
  assert.doesNotMatch(taskPage, /沿着动作前进/);
  assert.doesNotMatch(taskPage, /当前固定任务版本不接收附件/);
});

test("the complete task contract is visible before input is complete or response begins", () => {
  assert.match(taskPage, /<section className="task-brief"/);
  assert.match(taskPage, /<p className="task-outcome">\{assignment\.learner_outcome\}<\/p>/);
  assert.match(taskPage, /<h3 id="task-deliverables-title">最后留下<\/h3>/);
  assert.match(taskPage, /assignment\.required_deliverables\.map/);
  assert.ok(taskPage.indexOf("task-brief") < taskPage.indexOf("task-workspace"));
  assert.match(taskPage, /className="task-supporting-rules task-contract-columns"/);
  assert.match(taskPage, /行动路径<\/h3>/);
  assert.match(taskPage, /过关条件<\/h3>/);
  assert.ok(taskPage.indexOf("task-brief") < taskPage.indexOf("task-workspace"));
  assert.doesNotMatch(taskPage, /<details className="task-supporting-rules"/);
  assert.doesNotMatch(taskPage, /需要时查看方法与完成标准/);
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
  assert.match(resultPage, /四枚宝藏 · 三项能力证据/);
  assert.match(resultPage, /className="treasure-collection"/);
  assert.match(resultPage, /className="ability-collection"/);
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
  assert.match(layout, /learnerSession \? \(/);
});
