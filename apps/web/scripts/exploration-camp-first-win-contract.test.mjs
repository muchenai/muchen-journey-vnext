import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const taskPage = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url),
  "utf8",
);
const composer = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url),
  "utf8",
);

test("the first station keeps approved learning input before any personal output", () => {
  assert.ok(taskPage.indexOf('id="first-learning-input"') < taskPage.indexOf("<SubmissionComposer"));
  assert.match(taskPage, /isFirstStation=\{assignment\.journey_stage\?\.position === 0\}/);
  assert.match(taskPage, /material\.key === nextMaterialKey/);
  assert.match(taskPage, /完成上一份后开放/);
  assert.match(taskPage, /: materialsReady \? \(/);
});

test("the first-station composer returns one truthful judgement and experiment from little input", () => {
  assert.match(composer, /60 秒起点判断/);
  assert.match(composer, /你现在最真实的卡点是什么/);
  assert.match(composer, /起点判断/);
  assert.match(composer, /今天的实验/);
  assert.match(composer, /这里不评分，也不会作为绩效结论/);
  assert.match(composer, /aria-pressed=\{firstWinKey === key\}/);
  assert.match(composer, /type="button"/);
  assert.doesNotMatch(composer, /AI (?:判断|诊断)|智能判断|自动评估/);
});
