import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const source = path => readFile(new URL(path, import.meta.url), "utf8");
const [queue, detail, actions, redirect, ops, types, list] = await Promise.all([
 source("../src/app/review/review-admin.tsx"), source("../src/app/review/review-dialog.tsx"),
 source("../src/app/review/admin-actions.ts"), source("../src/app/review/[reviewId]/page.tsx"),
 source("../src/app/ops/page.tsx"), source("../src/lib/server/api.ts"), source("../src/app/review/review-queue.tsx"),
]);
test("review queue loads real records and keeps camp, AI, passed and returned views",()=>{
 assert.match(actions,/\/api\/v1\/review-admin\/reviews/);
 for(const label of ['探索营','新手村','待人工审核','AI 自测结果','已审核','审核未通过']) assert.ok((queue+list).includes(label));
 assert.match(queue,/document.visibilityState/);
 assert.match(queue,/12000/);
 assert.match(types,/feedback_sla_business_days/);
});
test("review detail binds saved AI advice and prior results to the fixed submission",()=>{
 assert.match(actions,/\/api\/v1\/review-admin\/reviews\/\$\{encodeURIComponent\(id\)\}/);
 assert.match(detail,/d\.submission_body/);
 assert.match(detail,/d\.document_ai_checks/);
 assert.match(detail,/check\.history/);
 assert.match(detail,/最终审核/);
 assert.match(redirect,/redirect\(`/);
});
test("ops workload and capacity continue to use the existing approved source",()=>{
 assert.match(ops,/\/api\/v1\/ops\/reviewer-workload/);
 assert.match(ops,/不可计算/);
 assert.doesNotMatch(ops,/capacity_limit\s*\?\?\s*0/);
});
test("failed reads cannot masquerade as a successful empty queue",()=>{
 assert.match(queue,/error&&<div className="admin-error" role="alert"/);
 assert.match(queue,/重新连接/);
 assert.match(actions,/ok: false, error:/);
 assert.match(list,/rows.length/);
});
test("review mutation preserves optimistic revision and server idempotency",()=>{
 assert.match(detail,/expected_revision:d.revision/);
 assert.match(actions,/"Idempotency-Key": key/);
 assert.match(detail,/if \(result.ok\) done\(\); else setError\(result.error\)/);
 assert.match(detail,/d.status === 'ASSIGNED' \|\| d.status === 'IN_REVIEW'/);
});
test("human feedback remains bounded and return requires an actionable explanation",()=>{
 assert.match(detail,/feedback.trim\(\).slice\(0,500\)/);
 assert.match(detail,/maxLength=\{2000\}/);
 assert.match(detail,/feedback.trim\(\).length < 10/);
 assert.match(detail,/!reasons.length/);
 assert.match(detail,/busy\s*\|\|\s*!editable/);
});
