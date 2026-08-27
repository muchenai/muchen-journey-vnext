import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const task = await readFile(new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url), "utf8");
const composer = await readFile(new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url), "utf8");
const result = await readFile(new URL("../src/app/app/result/page.tsx", import.meta.url), "utf8");
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const apiTypes = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const domain = await readFile(new URL("../../api/journey_api/domain.py", import.meta.url), "utf8");

test("task detail and waiting states expose authoritative review and safety facts", () => {
  for (const field of ["reviewer_display_name", "assigned_at", "sensitivity", "audience", "reviewer_role"]) {
    assert.match(apiTypes, new RegExp(field));
  }
  assert.match(task, /任务版本/);
  assert.match(task, /任务非目标与安全边界/);
  assert.match(task, /积分规则：未配置/);
  assert.match(task, /SUBMITTED|IN_REVIEW/);
  assert.match(task, /查看已提交版本/);
  assert.match(task, /正式任务尚未批准撤回/);
  assert.doesNotMatch(domain, /两个工作日内反馈/);
});

test("revision keeps old evidence and displays structured human rubric feedback", () => {
  assert.match(apiTypes, /rubric_feedback/);
  assert.match(task, /NEEDS_REVISION/);
  assert.match(task, /开始修订/);
  assert.match(task, /revisionReady/);
  assert.match(task, /返工依据不完整，暂不能正式修订/);
  assert.match(task, /旧提交与旧结论保持只读/);
  assert.match(task, /未配置返工截止时间/);
});

test("workspace keeps a local recovery copy, server receipts, and a two-step formal submit", () => {
  assert.match(composer, /localStorage/);
  assert.match(composer, /本浏览器有一份未同步副本/);
  assert.match(composer, /自动保存到服务器/);
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
  assert.doesNotMatch(composer, /ai.*(submitAssignment|saveSubmissionDraft)/i);
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
