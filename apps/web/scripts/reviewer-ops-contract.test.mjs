import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const queue = await readFile(new URL("../src/app/review/page.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/app/review/[reviewId]/page.tsx", import.meta.url), "utf8");
const workbench = await readFile(new URL("../src/app/review/[reviewId]/review-workbench.tsx", import.meta.url), "utf8");
const ops = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
const types = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("review queue exposes authoritative priority, SLA, risk, revisions and escalation", () => {
  for (const field of ["feedback_sla_business_days", "revision_count", "sensitivity", "audience", "conflict_status"]) {
    assert.match(types, new RegExp(field));
  }
  assert.match(queue, /最高优先级待审提交/);
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
  assert.match(queue, /查询已成功/);
  assert.match(queue, /不是数据未加载/);
  assert.match(queue, /最近检查/);
});
