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
const learnerLayout = await readFile(
  new URL("../src/app/app/layout.tsx", import.meta.url),
  "utf8",
);
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("the task page reveals one learning material at a time", () => {
  assert.match(taskPage, /const activeMaterialIndex =/);
  assert.match(taskPage, /const isActive = index === activeMaterialIndex/);
  assert.match(taskPage, /const isLocked = !isComplete && !isActive/);
  assert.match(taskPage, /className="learning-material-card" open=\{isActive\}/);
  assert.match(taskPage, /完成上一项后解锁/);
  assert.match(taskPage, /我找到答案了，开始\$\{practiceNoun\}/);
  assert.match(taskPage, /<summary>查看材料说明<\/summary>/);
  assert.match(taskPage, /<span>打开学习材料<\/span>/);
  assert.match(taskPage, /className="material-focus-prompt"/);
  assert.match(taskPage, /打开前，先记住这一个问题/);
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

test("the task contract leads with one deliverable and keeps secondary criteria on demand", () => {
  assert.match(taskPage, /<section className="task-brief"/);
  assert.match(taskPage, /<h2 id="task-brief-title">\{assignment\.required_deliverables\[0\]/);
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

test("Day 0 gives a 60-second mission briefing before the learner is asked to respond", () => {
  assert.match(taskPage, /className="day-zero-briefing"/);
  assert.match(taskPage, /今天不是先答题，而是先看清地图/);
  assert.match(taskPage, /看 \{requiredMaterials\.length\} 份出发材料/);
  assert.match(taskPage, /写下一个想验证的问题/);
  assert.match(taskPage, /四个宝藏 · 三项真实能力评测/);
  assert.match(taskPage, /href="#learning-materials-title"/);
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
