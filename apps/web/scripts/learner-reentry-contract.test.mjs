import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const join = await readFile(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const ops = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
const panel = await readFile(
  new URL("../src/app/ops/learner-reentry-panel.tsx", import.meta.url),
  "utf8",
);

test("expired learner pages fail closed into an explicit operator-assisted recovery state", () => {
  assert.match(api, /export async function learnerPageRequest/);
  assert.match(api, /auth_error=LEARNER_SESSION_EXPIRED/);
  assert.match(home, /会话已失效，但你的成长进度和证据仍然保留/);
  assert.match(home, /一次性重新进入链接/);
});

test("operator creates a bounded reentry link for the existing enrollment", () => {
  assert.match(ops, /create_learner_reentry/);
  assert.match(panel, /生成 30 分钟重新进入链接/);
  assert.match(actions, /\/learner-reentry/);
  assert.match(actions, /expires_in_minutes: 30/);
  assert.match(actions, /`\/join#token=\$\{encodeURIComponent\(result\.invite_token\)\}`/);
  assert.doesNotMatch(actions, /\/join\?token=/);
});

test("reentry confirmation does not collect a new display name or claim new business facts", () => {
  assert.match(join, /summary\?\.flow === "REENTRY"/);
  assert.match(join, /原有进度会被安全恢复/);
  assert.match(join, /不会创建重复记录/);
  assert.match(join, /继续当前一站/);
});
