import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const queue = await readFile(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/app/review/[reviewId]/page.tsx", import.meta.url), "utf8");
const workbench = await readFile(new URL("../src/app/review/[reviewId]/review-workbench.tsx", import.meta.url), "utf8");
const characterProgress = await readFile(new URL("../src/app/character-progress.tsx", import.meta.url), "utf8");
const ops = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
const types = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("review queue exposes authoritative priority, SLA, risk, revisions and escalation", () => {
  for (const field of ["feedback_sla_business_days", "revision_count", "sensitivity", "audience", "conflict_status"]) {
    assert.match(types, new RegExp(field));
  }
  assert.match(queue, /正式评测/);
  assert.match(queue, /宝藏辅导/);
  assert.match(queue, /容量：未获批准，无法计算/);
  assert.match(queue, /主备与升级/);
  assert.match(queue, /材料不完整/);
});

test("review detail separates fixed evidence, advisory AI and human conclusion impact", () => {
  assert.match(detail, /固定 SubmissionVersion/);
  assert.match(detail, /AI 建议/);
  assert.match(workbench, /提交真人结论/);
  assert.match(detail, /通用高影响申诉政策尚未获批准/);
  assert.match(detail, /提交结果未知/);
});

test("ops overview consumes approved workload facts and fails closed on missing capacity", () => {
  assert.match(ops, /\/api\/v1\/ops\/reviewer-workload/);
  assert.match(ops, /处理最高优先级异常/);
  assert.match(ops, /PENDING_OWNER_CONTENT/);
  assert.match(ops, /不可计算/);
  assert.match(ops, /DEAD/);
  assert.doesNotMatch(ops, /capacity_limit\s*\?\?\s*0/);
});

test("successful empty queue is distinct from unavailable data", () => {
  assert.match(queue, /当前没有待处理记录/);
  assert.match(queue, /Day 0 仍由 Learner 自证完成/);
  assert.match(queue, /三项评测/);
  assert.match(queue, /不影响旅程推进、结营或准入/);
});

test("finalized reviews remain visible after the active queue is refreshed", () => {
  assert.match(queue, /\/api\/v1\/reviews\/history/);
  assert.match(queue, /已完成评阅/);
  assert.match(queue, /已通过/);
  assert.match(queue, /已达到学习目标/);
  assert.match(detail, /审核结果提交成功/);
  assert.match(detail, /刷新后仍会保留/);
});

test("reviewer feedback shows live bounded character progress", () => {
  assert.match(workbench, /<CharacterProgress/);
  assert.match(workbench, /minimum=\{5\}/);
  assert.match(workbench, /maximum=\{500\}/);
  assert.match(workbench, /minimum=\{10\}/);
  assert.match(workbench, /maximum=\{2000\}/);
  assert.match(characterProgress, /已输入 \{count\} 个有效字符/);
  assert.match(characterProgress, /还差/);
  assert.match(characterProgress, /已超出/);
});
