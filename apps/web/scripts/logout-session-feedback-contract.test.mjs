// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const actionSource = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const controlSource = readFileSync(
  new URL("../src/app/app/logout-control.tsx", import.meta.url),
  "utf8",
);
const learnerHomeSource = readFileSync(
  new URL("../src/app/app/page.tsx", import.meta.url),
  "utf8",
);
const publicHomeSource = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");

test("logout clears browser credentials only after success or an authoritative already-logged-out response", () => {
  assert.match(actionSource, /error\.status === 401/);
  assert.match(actionSource, /error\.code === "UNAUTHENTICATED"/);
  assert.match(actionSource, /退出没有完成，当前会话仍然有效/);
  assert.match(actionSource, /cookieStore\.delete\(SESSION_COOKIE\)/);
  assert.match(actionSource, /cookieStore\.delete\(CSRF_COOKIE\)/);
  assert.match(actionSource, /redirect\("\/\?session=logged_out"\)/);

  const failureReturn = actionSource.indexOf("退出没有完成，当前会话仍然有效");
  const cookieDeletion = actionSource.indexOf("cookieStore.delete(SESSION_COOKIE)");
  assert.ok(failureReturn > -1 && cookieDeletion > failureReturn);
});
