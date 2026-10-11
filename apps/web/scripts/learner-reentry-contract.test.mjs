// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
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


test("operator creates a bounded reentry link for the existing enrollment", () => {
  assert.match(ops, /create_learner_reentry/);
  assert.match(panel, /生成 30 分钟重新进入链接/);
  assert.match(actions, /\/learner-reentry/);
  assert.match(actions, /expires_in_minutes: 30/);
  assert.match(actions, /`\/join#token=\$\{encodeURIComponent\(result\.invite_token\)\}`/);
  assert.doesNotMatch(actions, /\/join\?token=/);
});
