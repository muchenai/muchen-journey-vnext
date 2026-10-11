// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const task = await readFile(new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url), "utf8");
const composer = await readFile(new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url), "utf8");
const result = await readFile(new URL("../src/app/app/result/page.tsx", import.meta.url), "utf8");
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const apiTypes = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const domain = await readFile(new URL("../../api/journey_api/domain.py", import.meta.url), "utf8");



test("workspace keeps a local recovery copy, server receipts, and a two-step formal submit", () => {
  assert.match(composer, /localStorage/);
  assert.match(composer, /本浏览器有一份未同步副本/);
  assert.match(composer, /草稿已保存/);
  assert.match(actions, /savedAt/);
  assert.match(composer, /检查并提交/);
  assert.match(composer, /event\.preventDefault\(\)/);
  assert.match(composer, /确认正式提交/);
  assert.match(composer, /提交后进入人工审核/);
  assert.match(composer, /任务版本/);
  assert.match(composer, /Rubric 版本/);
});

test("AI self-check fails closed without invented provenance or formal mutation", () => {
  assert.match(composer, /AI 自查（当前不可用）/);
  assert.match(composer, /模型版本：未绑定/);
  assert.match(composer, /Prompt 版本：未绑定/);
  assert.match(composer, /跳过 AI 自查/);
  assert.match(composer, /function skipAiSelfCheck\(\)/);
  assert.match(composer, /setAiSelfCheckSkipped\(true\)/);
  assert.match(composer, /已跳过 AI 自查。没有生成 AI 评价，任务状态未改变/);
  assert.match(composer, /reviewSubmissionRef\.current\?\.scrollIntoView/);
  assert.match(composer, /aria-pressed=\{aiSelfCheckSkipped\}/);
  const skipHandler = composer.match(/function skipAiSelfCheck\(\) \{([\s\S]*?)\n  \}/)?.[1];
  assert.ok(skipHandler);
  assert.doesNotMatch(skipHandler, /submitAssignment|saveSubmissionDraft|submitAction|draftAction/);
});

test("result renders completion, human, AI, incentive and system facts as separate ledgers", () => {
  for (const kind of ["completion", "human", "ai", "incentive", "system"]) {
    assert.match(result, new RegExp(`<FactLabel kind="${kind}"`));
  }
  assert.match(result, /\/api\/v1\/me\/incentives/);
  assert.match(result, /formal_effect/);
  assert.match(result, /不改变正式状态/);
  assert.match(result, /submission_version_id/);
});
