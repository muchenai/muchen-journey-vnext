import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const learner = "11111111-1111-4111-8111-111111111111";
const reviewer = "22222222-2222-4222-8222-222222222222";
const journey = "33333333-3333-4333-8333-333333333333";
class ApiRequestError extends Error {
  constructor(status) { super("Synthetic failure"); this.status = status; }
}
function setup(policy) {
  const posts = [];
  const reads = [];
  const api = {
    ApiRequestError,
    apiRequest: async (path, role, options) => {
      assert.equal(role, "OPERATOR");
      if (path === "/api/v1/ops/invite-targets") {
        reads.push(path);
        if (policy instanceof Error) throw policy;
        return policy;
      }
      assert.equal(path, "/api/v1/ops/invites");
      assert.equal(options.method, "POST");
      posts.push(JSON.parse(options.body));
      return { invite_token: "synthetic-token", expires_at: "2026-01-01T00:00:00Z" };
    },
  };
  const exports = {};
  vm.runInNewContext(compiled, { exports, require: (name) => {
    if (name === "@/lib/server/api") return api;
    if (name === "node:crypto") return { randomUUID };
    if (name === "next/cache") return { revalidatePath: () => {} };
    if (name === "next/headers" || name === "next/navigation") return {};
    throw new Error(`Unexpected import ${name}`);
  } });
  const data = new FormData();
  data.set("reviewer_id", reviewer);
  data.set("journey_version_id", journey);
  data.set("purpose", "Synthetic controlled invitation");
  return { posts, reads, data, action: () => exports.createLearnerInvite({}, data) };
}
const allowed = { target_required: true, items: [{ user_id: learner, display_name: "Synthetic learner" }] };

test("selected learner and reviewer reach the authenticated invitation API", async () => {
  const t = setup(allowed); t.data.set("target_user_id", learner);
  const r = await t.action();
  assert.equal(t.posts.length, 1);
  assert.equal(t.posts[0].target_user_id, learner);
  assert.equal(t.posts[0].reviewer_id, reviewer);
  assert.equal(t.posts[0].journey_version_id, journey);
  assert.equal(r.joinPath, "/join#token=synthetic-token");
});
for (const target of [null, "", reviewer, "not-a-uuid"]) {
  test(`missing or forged target rejected: ${target}`, async () => {
    const t = setup(allowed); if (target !== null) t.data.set("target_user_id", target);
    assert.ok((await t.action()).error);
    assert.equal(t.posts.length, 0);
  });
}
test("stale selection and empty allowlist cannot create an untargeted invite", async () => {
  const t = setup({ target_required: true, items: [] }); t.data.set("target_user_id", learner);
  assert.ok((await t.action()).error); assert.equal(t.posts.length, 0);
});
test("non-Canary keeps legacy untargeted behavior", async () => {
  const t = setup({ target_required: false, items: [] });
  assert.ok((await t.action()).joinPath); assert.equal(t.posts[0].target_user_id, null);
});
test("expired session cannot read targets or post an invite", async () => {
  const t = setup(new ApiRequestError(401)); t.data.set("target_user_id", learner);
  assert.equal((await t.action()).loginRequired, true); assert.equal(t.posts.length, 0);
});
test("unavailable policy fails closed", async () => {
  const t = setup(new ApiRequestError(503)); t.data.set("target_user_id", learner);
  assert.ok((await t.action()).error); assert.equal(t.posts.length, 0);
});
