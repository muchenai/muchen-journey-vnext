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

test("learner exit control explains impact, exposes progress and errors, and blocks duplicate submits", () => {
  assert.match(learnerHomeSource, /<LogoutControl \/>/);
  assert.match(controlSource, /useActionState\(logoutSession, INITIAL_STATE\)/);
  assert.match(controlSource, /if \(submittingRef\.current\)/);
  assert.match(controlSource, /event\.preventDefault\(\)/);
  assert.match(controlSource, /disabled=\{pending\}/);
  assert.match(controlSource, /正在安全退出……/);
  assert.match(controlSource, /只退出当前浏览器会话/);
  assert.match(controlSource, /不会删除旅程进度、提交版本或评审记录/);
  assert.match(controlSource, /role="status"/);
  assert.match(controlSource, /role="alert"/);
  assert.match(controlSource, /请求 ID/);
});

test("logged-out home receipt requires a confirmed non-valid session and offers reentry", () => {
  assert.match(publicHomeSource, /query\.session === "logged_out"/);
  assert.match(publicHomeSource, /session\.status !== "VALID"/);
  assert.match(publicHomeSource, /session\.status !== "UNAVAILABLE"/);
  assert.match(publicHomeSource, /已安全退出 vNext 会话/);
  assert.match(publicHomeSource, /服务端已确认：当前浏览器会话已撤销/);
  assert.match(publicHomeSource, /旅程进度、历史提交和评审记录均已保留/);
  assert.match(publicHomeSource, /使用运营提供的当前有效重新进入链接/);
  assert.match(publicHomeSource, /if \(loggedOut\) return <InvitationAction expired \/>/);
  assert.match(publicHomeSource, /loggedOut=\{isLoggedOut\}/);
});
