import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const inviteForm = await readFile(
  new URL("../src/app/join/invite-token-exchange-form.tsx", import.meta.url),
  "utf8",
);
const taskPage = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url),
  "utf8",
);
const opsPage = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
const contentPublicationPanel = await readFile(
  new URL("../src/app/ops/content-draft-publication-panel.tsx", import.meta.url),
  "utf8",
);

test("a fresh invite completes exchange and identity confirmation in one learner action", () => {
  assert.match(actions, /export async function acceptInvite/);
  assert.match(actions, /acceptInvite[\s\S]*?\/api\/v1\/join\/exchange/);
  assert.match(actions, /acceptInvite[\s\S]*?\/api\/v1\/identity\/confirm/);
  assert.match(inviteForm, /action=\{acceptInvite\}/);
  assert.match(inviteForm, /开启旅程/);
  assert.doesNotMatch(inviteForm, /打开通行证/);
});

test("learner reentry is explicit and restores the existing journey", () => {
  assert.match(actions, /createLearnerReentry[\s\S]*?&flow=reentry/);
  assert.match(actions, /createLearnerInvite[\s\S]*?joinPath: `\/join#token=\$\{encodeURIComponent\(result\.invite_token\)\}`/);
  assert.match(inviteForm, /恢复原有进度，不会创建新的学习记录/);
  assert.match(inviteForm, /继续旅程/);
});

test("https links embedded in frozen text materials remain clickable without unsafe html", () => {
  assert.match(taskPage, /function textWithSafeLinks/);
  assert.match(taskPage, /part\.startsWith\("https:\/\/"\)/);
  assert.match(taskPage, /target="_blank" rel="noreferrer" aria-label="打开学习材料"/);
  assert.match(taskPage, /new URL\(href\)\.hostname/);
  assert.doesNotMatch(taskPage, /dangerouslySetInnerHTML/);
});

test("operations shows an explicit production environment notice", () => {
  assert.match(opsPage, /production: "当前为 production/);
  assert.match(opsPage, /staging: "当前为 Alpha staging/);
  assert.doesNotMatch(opsPage, /const isStaging/);
});

test("content publication requires every embedded and external material link to be opened", () => {
  assert.match(contentPublicationPanel, /material\.kind === "HTTPS_LINK"/);
  assert.match(contentPublicationPanel, /material\.body\.matchAll\(HTTPS_URL\)/);
  assert.match(contentPublicationPanel, /name="verified_material_url"/);
  assert.match(actions, /data\.getAll\("verified_material_url"\)/);
  assert.match(opsPage, /version\.material_links\.map/);
  assert.doesNotMatch(contentPublicationPanel, /material_link_verified_/);
  assert.match(contentPublicationPanel, /type="checkbox"/);
  assert.match(contentPublicationPanel, /required/);
  assert.match(contentPublicationPanel, /target="_blank" rel="noreferrer"/);
  assert.match(contentPublicationPanel, /必须在当前浏览器实际打开并确认可访问/);
});
