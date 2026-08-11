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

test("the task page reveals one learning material at a time", () => {
  assert.match(taskPage, /const activeMaterialIndex =/);
  assert.match(taskPage, /const isActive = index === activeMaterialIndex/);
  assert.match(taskPage, /const isLocked = !isComplete && !isActive/);
  assert.match(taskPage, /className="learning-material-card" open=\{isActive\}/);
  assert.match(taskPage, /完成上一项后解锁/);
  assert.match(taskPage, /完成并继续/);
  assert.match(taskPage, /<summary>查看材料说明<\/summary>/);
  assert.match(taskPage, /<span>打开学习材料<\/span>/);
});

test("the response workspace stays hidden until required input is complete", () => {
  assert.match(
    taskPage,
    /\{materialsReady \? <section className="task-workspace"[\s\S]*<SubmissionComposer/,
  );
  assert.match(taskPage, /完成当前材料后，小任务会自动出现/);
  assert.match(taskPage, /开始小任务/);
  assert.doesNotMatch(taskPage, /沿着动作前进/);
  assert.doesNotMatch(taskPage, /当前固定任务版本不接收附件/);
});

test("rules and historical evidence are available on demand instead of competing with the next action", () => {
  assert.match(taskPage, /<summary>查看任务要求<\/summary>/);
  assert.match(taskPage, /<summary>查看提交历史<\/summary>/);
  assert.ok(taskPage.indexOf("查看任务要求") < taskPage.indexOf("task-workspace"));
});

test("join and result pages keep operational explanations below the primary experience", () => {
  assert.match(joinPage, /从上次离开的地方继续/);
  assert.doesNotMatch(joinPage, /Enrollment|Assignment/);
  assert.match(resultPage, /<summary>查看通知与过程记录<\/summary>/);
  assert.match(resultPage, /<summary>查看评审与准入详情<\/summary>/);
  assert.ok(resultPage.indexOf("下一步") < resultPage.indexOf("结论分层"));
  assert.doesNotMatch(resultPage, /04 · 通知状态|05 · 不可变时间线/);
  assert.doesNotMatch(resultPage, /系统只整理固定证据/);
});
