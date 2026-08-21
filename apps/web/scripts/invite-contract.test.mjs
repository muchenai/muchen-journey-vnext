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
  assert.match(actions, /createLearnerInvite[\s\S]*?joinPath: `\/join#token=\$\{encodeURIComponent\(result\.invite_token\)\}`/);
  assert.match(actions, /createLearnerReentry[\s\S]*?joinPath: `\/join#token=\$\{encodeURIComponent\(result\.invite_token\)\}&flow=reentry`/);
  assert.match(panel, /new URL\(state\.joinPath, window\.location\.origin\)\.href/);
  assert.doesNotMatch(actions, /\/join\?token=/);
});

test("expired Operator invitation action recovers through explicit Feishu login", () => {
  assert.match(actions, /createLearnerInvite[\s\S]*?error instanceof ApiRequestError && error\.status === 401/);
  assert.match(actions, /loginRequired: true/);
  assert.match(panel, /state\.loginRequired/);
  assert.match(panel, /href="\/auth\/feishu\?return_to=%2Fops"/);
  assert.match(panel, />\s*重新使用飞书进入\s*</);
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

test("unused and exchanged invites can be distinguished and revoked without persisted token display", () => {
  assert.match(actions, /export async function revokeLearnerInvite/);
  assert.match(actions, /expected_revision: requiredRevision\(data\)/);
  assert.match(panel, /EXCHANGED_PENDING_CONFIRMATION: "已兑换，待确认身份"/);
  assert.match(panel, /\["ACTIVE", "EXCHANGED_PENDING_CONFIRMATION"\]\.includes\(effectiveStatus\)/);
  assert.doesNotMatch(panel, /invite_token/);
});

test("ops derives expired display state from time without mutating invitation facts", () => {
  assert.match(panel, /function visibleInviteStatus\(invite: OpsInvite, observedAtMs: number\)/);
  assert.match(panel, /invite\.status === "ACTIVE" && new Date\(invite\.expires_at\)\.getTime\(\) <= observedAtMs/);
  assert.match(panel, /const effectiveStatus = visibleInviteStatus\(invite, observedAtMs\)/);
  assert.match(panel, /STATUS_LABELS\[effectiveStatus\]/);
  assert.match(panel, /setInterval\(\(\) => setObservedAtMs\(Date\.now\(\)\), 30_000\)/);
  assert.doesNotMatch(panel, /invite\.status\s*=(?!=)/);
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
