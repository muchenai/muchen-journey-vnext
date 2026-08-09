import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
const panel = await readFile(
  new URL("../src/app/ops/invite-management-panel.tsx", import.meta.url),
  "utf8",
);
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");

test("ops exposes a discoverable, human-readable learner invitation entry", () => {
  assert.match(page, /href="#learner-invites">邀请新人<\/a>/);
  assert.match(page, /id="learner-invites"/);
  assert.match(panel, /选择已绑定 Reviewer/);
  assert.match(panel, /选择已发布任务版本/);
  assert.match(panel, /生成 24 小时邀请链接/);
  assert.match(panel, /复制完整邀请链接/);
  assert.doesNotMatch(panel, /Reviewer UUID/);
});

test("formal journey labels do not repeat a version already present in the title", () => {
  assert.match(panel, /function formatJourneyOptionLabel/);
  assert.match(panel, /titleAlreadyIncludesVersion/);
  assert.match(panel, /formatJourneyOptionLabel\(journey\)/);
  assert.doesNotMatch(panel, /\{journey\.title\} · V\{journey\.version\}/);
});

test("ops reuses scoped invitation contracts and keeps credentials out of query strings", () => {
  assert.match(actions, /"\/api\/v1\/ops\/invites"/);
  assert.match(actions, /reviewer_id: reviewerId/);
  assert.match(actions, /task_version_id: taskVersionId/);
  assert.match(actions, /journey_version_id: journeyVersionId/);
  assert.match(actions, /target_user_id: null/);
  assert.match(actions, /`\/join#token=\$\{encodeURIComponent\(result\.invite_token\)\}`/);
  assert.match(panel, /new URL\(state\.joinPath, window\.location\.origin\)\.href/);
  assert.doesNotMatch(actions, /\/join\?token=/);
});

test("formal journey publication requires an explicit offline review attestation", () => {
  assert.match(panel, /已完成线下复核的 Reviewer/);
  assert.match(panel, /name="review_acknowledged" type="checkbox" required/);
  assert.match(panel, /useActionState\(\s*publishFormalJourney/);
  assert.match(panel, /state\.requestId \? <code>request ID:/);
  assert.match(actions, /data\.get\("review_acknowledged"\) === "on"/);
  assert.match(actions, /review_acknowledged: reviewAcknowledged/);
  assert.match(actions, /export type PublishFormalJourneyActionState = SubmissionActionState/);
  assert.match(actions, /export async function publishFormalJourney\([\s\S]*?return submissionError\(error\)/);
});

test("active invites can be revoked without persisted token display", () => {
  assert.match(actions, /export async function revokeLearnerInvite/);
  assert.match(actions, /expected_revision: requiredRevision\(data\)/);
  assert.match(panel, /invite\.status === "ACTIVE"/);
  assert.doesNotMatch(panel, /invite_token/);
});

test("operator can freeze future invites without deleting accepted facts", () => {
  assert.match(page, /\/api\/v1\/ops\/invitation-control/);
  assert.match(panel, /新邀请总开关/);
  assert.match(panel, /停止创建新邀请/);
  assert.match(panel, /不撤销已接受邀请，也不删除任何业务事实/);
  assert.match(actions, /export async function updateInvitationControl/);
  assert.match(actions, /invitation-control\/\$\{target === "FROZEN" \? "freeze" : "resume"\}/);
  assert.match(actions, /expected_revision: requiredRevision\(data\)/);
});
