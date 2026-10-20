import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const require = createRequire(import.meta.url);
class ApiRequestError extends Error {}
function actions(apiRequest) {
  const source = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(compiled, {
    module, exports: module.exports,
    require: name => name === "@/lib/server/api" ? { apiRequest, ApiRequestError }
      : name.startsWith("node:") ? require(name) : {},
    console, FormData, URL,
  });
  return module.exports;
}
const assignment = "00000000-0000-4000-8000-000000000001";
const click = "00000000-0000-4000-8000-000000000002";
const history = [{ id: "latest", status: "COMPLETED", result: "新评价" },
  { id: "previous", status: "COMPLETED", result: "旧评价" }];

test("self-check action passes click identity, saves draft first and returns full server history", async () => {
  const calls = [];
  const { runAiSelfCheck } = actions(async (path, role, init) => {
    calls.push({ path, role, init });
    if (init?.method === "PUT") return {};
    if (init?.method === "POST") return history[0];
    return history;
  });
  const result = await runAiSelfCheck(assignment, "https://test.feishu.cn/docx/example", 6, click);
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    document_url: "https://test.feishu.cn/docx/example", request_id: click,
  });
  assert.equal(calls[0].init.method, "PUT");
  assert.equal(calls[2].init, undefined);
  assert.equal(result.records, history);
  assert.equal(result.error, undefined);
});

test("AI failure still loads older saved results", async () => {
  const { runAiSelfCheck } = actions(async (path, role, init) => {
    if (init?.method === "POST") throw new ApiRequestError("自查失败");
    return history;
  });
  const result = await runAiSelfCheck(assignment, "https://test.feishu.cn/docx/example", undefined, click);
  assert.equal(result.error, "自查失败");
  assert.equal(result.records, history);
});

test("history failure is not presented as a complete one-record history", async () => {
  const { runAiSelfCheck } = actions(async (path, role, init) => {
    if (init?.method === "POST") return history[0];
    throw new ApiRequestError("历史读取失败");
  });
  const result = await runAiSelfCheck(assignment, "https://test.feishu.cn/docx/example", undefined, click);
  assert.equal(result.record, history[0]);
  assert.equal(result.records, undefined);
  assert.match(result.error, /完整历史读取失败/);
});
