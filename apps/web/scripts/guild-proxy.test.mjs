import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const id = "11111111-1111-4111-8111-111111111111";
class ApiRequestError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
function harness(admin = false, failure = null) {
  const file = admin ? "../src/app/api/review-native/guild-requests/route.ts" : "../src/app/api/learner/guild/route.ts";
  const calls = [];
  const compiledModule = { exports: {} };
  const dependencies = {
    "next/server": { NextResponse: { json: (value, init) => Response.json(value, init) } },
    "@/lib/server/api": { ApiRequestError, apiRequest: async (...args) => { calls.push(args); if (failure) throw failure; return { level: 1, requests: [] }; } },
  };
  const source = ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, require: name => dependencies[name], Response, URL, Buffer });
  const request = (body = admin ? { id, decision: "approved" } : { command: "apply", guildId: "multilingual", level: 1, expectedRevision: 1 }, headers = {}, raw) => new Request("http://localhost:3000/api/guild", {
    method: "POST", headers: { host: "localhost:3000", origin: "http://localhost:3000", "content-type": "application/json", ...headers },
    body: raw === undefined ? JSON.stringify(body) : raw,
  });
  return { ...compiledModule.exports, calls, request };
}

for (const admin of [false, true]) {
  const name = admin ? "reviewer" : "learner";
  test(`${name} guild GET selects its fixed role and endpoint without caching`, async () => {
    const h = harness(admin), response = await h.GET();
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "private, no-store");
    assert.equal(h.calls[0][0], admin ? "/api/v1/review-admin/guild-requests" : "/api/v1/me/guild");
    assert.equal(h.calls[0][1], admin ? "REVIEWER" : "LEARNER");
  });
  test(`${name} guild rejects cross-site, missing and malformed origins before calling the API`, async () => {
    const h = harness(admin);
    for (const headers of [{ origin: "https://evil.invalid" }, { origin: "" }, { origin: "not a url" }, { origin: "file://localhost:3000" }, { "sec-fetch-site": "cross-site" }]) {
      const response = await h.POST(h.request(undefined, headers));
      assert.equal(response.status, 403);
    }
    assert.equal(h.calls.length, 0);
  });
  test(`${name} guild rejects content type, malformed JSON and excessive body`, async () => {
    const h = harness(admin);
    assert.equal((await h.POST(h.request(undefined, { "content-type": "text/plain" }))).status, 415);
    assert.equal((await h.POST(h.request(undefined, {}, "{"))).status, 400);
    assert.equal((await h.POST(h.request(undefined, {}, " ".repeat(admin ? 10001 : 30001)))).status, 413);
    assert.equal(h.calls.length, 0);
  });
  test(`${name} guild preserves authorization failures and does not expose unexpected exceptions`, async () => {
    const unauthorized = harness(admin, new ApiRequestError(401, "请先登录"));
    const denied = await unauthorized.GET();
    assert.equal(denied.status, 401);
    assert.equal((await denied.json()).error, "请先登录");
    const unexpected = harness(admin, new Error("sensitive internal exception"));
    const failure = await unexpected.POST(unexpected.request());
    assert.equal(failure.status, 502);
    assert.doesNotMatch(await failure.text(), /sensitive internal exception/);
    assert.equal(failure.headers.get("cache-control"), "private, no-store");
  });
}

test("learner applies only integer L1-L3 and cannot forward client identity or evidence", async () => {
  const h = harness();
  for (const body of [null, [], {}, { level: true }, { level: "1" }, { level: 1.1 }, { level: 0 }, { level: 4 }]) assert.equal((await h.POST(h.request(body && { command: "apply", guildId: "multilingual", expectedRevision: 1, ...body }))).status, 400);
  for (const expectedRevision of [undefined, 0, -1, "1", true, 1.5]) assert.equal((await h.POST(h.request({ command: "apply", guildId: "multilingual", level: 1, expectedRevision }))).status, 400);
  assert.equal(h.calls.length, 0);
  const response = await h.POST(h.request({ command: "apply", guildId: "multilingual", level: 2, expectedRevision: 7, studentId: "other", status: "approved", evidence: ["fake"] }));
  assert.equal(response.status, 200);
  assert.equal(h.calls[0][0], "/api/v1/me/guild/requests");
  assert.equal(h.calls[0][1], "LEARNER");
  assert.equal(h.calls[0][2].method, "POST");
  assert.deepEqual(JSON.parse(h.calls[0][2].body), { guildId: "multilingual", level: 2, expectedRevision: 7 });
});

test("learner joins only known guilds using a fixed endpoint and server-owned identity", async () => {
  const h = harness();
  for (const guildId of [null, "all", "../../users", {}, 1]) assert.equal((await h.POST(h.request({ command: "join", guildId }))).status, 400);
  assert.equal((await h.POST(h.request({ command: "approve", guildId: "functional" }))).status, 400);
  assert.equal(h.calls.length, 0);
  assert.equal((await h.POST(h.request({ command: "join", guildId: "functional", userId: "other", level: 3 }))).status, 200);
  assert.equal(h.calls[0][0], "/api/v1/me/guild/join");
  assert.deepEqual(JSON.parse(h.calls[0][2].body), { guildId: "functional" });
});

test("learner persists task artifacts, self-checks and optimistic revision without forwarding approval data", async () => {
  const h = harness();
  const draft = { command: "task", guildId: "multilingual", level: 1, artifact: "", checks: [], submit: false, expectedRevision: 0 };
  for (const invalid of [{artifact: 3}, {artifact: "字".repeat(6001)}, {checks: "yes"}, {checks: [3]}, {checks: ["a", "b", "c", "d"]}, {checks: ["a".repeat(201)]}, {submit: "true"}, {expectedRevision: -1}, {expectedRevision: 0.5}]) assert.equal((await h.POST(h.request({ ...draft, ...invalid }))).status, 400);
  assert.equal(h.calls.length, 0);
  assert.equal((await h.POST(h.request({ ...draft, status: "approved", taskId: "forged" }))).status, 200);
  assert.equal(h.calls[0][0], "/api/v1/me/guild/tasks");
  assert.deepEqual(JSON.parse(h.calls[0][2].body), { guildId: "multilingual", level: 1, artifact: "", checks: [], submit: false, expectedRevision: 0 });
  assert.equal((await h.POST(h.request({ ...draft, artifact: "字".repeat(6000), checks: ["自查"], submit: true }))).status, 200);
});

test("reviewer validates UUID, decision and mandatory bounded return reason", async () => {
  const h = harness(true);
  for (const body of [null, [], {}, { id: "../../users", decision: "approved" }, { id, decision: "pending" }, { id, decision: "returned" }, { id, decision: "returned", reason: "   " }, { id, decision: "approved", reason: 3 }, { id, decision: "approved", reason: "字".repeat(1001) }]) assert.equal((await h.POST(h.request(body))).status, 400);
  assert.equal(h.calls.length, 0);
  const response = await h.POST(h.request({ id, decision: "returned", reason: "  请补充凭证  ", level: 3, studentId: "other" }));
  assert.equal(response.status, 200);
  assert.equal(h.calls[0][0], `/api/v1/review-admin/guild-requests/${id}/review`);
  assert.equal(h.calls[0][1], "REVIEWER");
  assert.deepEqual(JSON.parse(h.calls[0][2].body), { decision: "returned", reason: "请补充凭证" });
});
