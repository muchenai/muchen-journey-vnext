import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const nativeRequire = createRequire(import.meta.url);
function load(relative, mocks) {
  const filename = new URL(relative, import.meta.url);
  const source = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    fileName: filename.pathname,
  }).outputText;
  const compiled = { exports: {} };
  vm.runInThisContext("(function(require,module,exports,console){" + source + "\n})")(
    (name) => name in mocks ? mocks[name] : nativeRequire(name), compiled, compiled.exports,
    { error: mocks.log ?? (() => {}) },
  );
  return compiled.exports;
}

class ApiRequestError extends Error {
  constructor(status, code) { super("private upstream detail"); this.status = status; this.code = code; this.requestId = "test-request"; }
}
const redirect = new Error("NEXT_REDIRECT");
function loader(request, log = () => {}) {
  return load("../src/app/ops/ops-data.ts", {
    "server-only": {},
    "next/navigation": { unstable_rethrow(error) { if (error === redirect) throw error; } },
    "@/lib/server/api": { ApiRequestError, identityPageRequest: request }, log,
  }).opsModuleRequest;
}

test("an unavailable module does not reject other reads or leak upstream details", async () => {
  const messages = [];
  const request = loader(async (path) => {
    if (path.endsWith("enrollments")) throw new ApiRequestError(409, "VERSION_CONFLICT");
    return { items: ["identity"] };
  }, (message) => messages.push(message));
  const [enrollments, identities] = await Promise.all([
    request("/api/v1/ops/enrollments", "OPERATOR"), request("/api/v1/ops/identity-access", "OPERATOR"),
  ]);
  assert.equal(enrollments, null);
  assert.deepEqual(identities, { items: ["identity"] });
  assert.equal(JSON.parse(messages[0]).status, 409);
  assert.doesNotMatch(messages.join(""), /private upstream detail/);
});

test("login redirects propagate; transport failure is isolated", async () => {
  await assert.rejects(loader(async () => { throw redirect; })("/ops", "OPERATOR"), (e) => e === redirect);
  assert.equal(await loader(async () => { throw new TypeError("private network detail"); })("/ops", "OPERATOR"), null);
});

const paths = ["task-definitions", "enrollments", "audit?limit=20", "runtime-status", "identity-access",
  "invites", "invitation-control", "notification-endpoints", "notification-deliveries?status=DEAD",
  "formal-journeys", "content-drafts", "reviewer-workload", "invite-targets"];
async function render(failures = [], extra = {}) {
  const fixtures = Object.fromEntries(paths.map((key) => [key, { items: [] }]));
  fixtures["identity-access"].revoked_transfer_candidates = [];
  fixtures["runtime-status"] = { environment: "test", config_schema_version: 3, worker: {}, api: {}, database: {}, metrics: {} };
  Object.assign(fixtures, extra);
  const mocks = {
    "next/link": ({ children, href }) => React.createElement("a", { href }, children),
    "@/app/ops/ops-data": { opsModuleRequest: async (path) => {
      const key = path.replace("/api/v1/ops/", "");
      return failures.includes(key) ? null : fixtures[key];
    } },
    "@/app/actions": new Proxy({}, { get: () => () => { throw new Error("Unexpected mutation"); } }),
    "@/lib/date-time": { formatProductDateTime: (value) => value },
  };
  for (const [file, name] of Object.entries({ "identity-access-panel": "IdentityAccessPanel", "invite-management-panel": "InviteManagementPanel",
    "learner-reentry-panel": "LearnerReentryPanel", "content-draft-publication-panel": "ContentDraftPublicationPanel", "journey-v3-assembly-panel": "JourneyV3AssemblyPanel" })) {
    mocks["@/app/ops/" + file] = { [name]: () => React.createElement("div", { "data-panel": name }) };
  }
  const { default: OpsPage } = load("../src/app/ops/page.tsx", mocks);
  return renderToStaticMarkup(await OpsPage({ searchParams: Promise.resolve({}) }));
}

test("every individual module may fail without crashing the ops page", async () => {
  for (const key of paths) {
    const html = await render([key]);
    assert.match(html, /本模块读取失败/);
    if (key !== "identity-access") assert.match(html, /data-panel="IdentityAccessPanel"/);
    else {
      assert.doesNotMatch(html, /data-panel="IdentityAccessPanel"/);
      assert.doesNotMatch(html, /data-panel="ContentDraftPublicationPanel"/);
    }
  }
  const html = await render(paths);
  assert.equal((html.match(/role="alert"/g) || []).length, 10);
  assert.doesNotMatch(html, /当前没有 DEAD 通知/);
});

test("multiple pending reviews are visible without offering ambiguous mutations", async () => {
  const html = await render([], { enrollments: { items: [{ id: "e1", learner_display_name: "测试学员",
    assignment_statuses: ["SUBMITTED"], status: "ACTIVE", allowed_commands: [], open_review_count: 2,
    open_review_status: null, open_review_revision: null }] } });
  assert.match(html, /当前有 2 条待审记录/);
  assert.doesNotMatch(html, /name="expected_review_revision"/);
  assert.match(html, /data-panel="IdentityAccessPanel"/);
});
