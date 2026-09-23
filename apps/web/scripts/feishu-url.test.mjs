import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(new URL("../src/lib/feishu-url.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports, URL });
const validate = exports.validateFeishuDocumentUrl;

test("only credential-free HTTPS Feishu and LarkSuite hosts are accepted", () => {
  for (const value of [
    "https://feishu.cn/docx/abc",
    "https://team.feishu.cn/wiki/abc",
    "https://larksuite.com/docx/abc",
    "https://team.larksuite.com/wiki/abc",
  ]) assert.equal(validate(value), null, value);

  for (const value of [
    "http://team.feishu.cn/docx/abc",
    "https://github.com/example/repo",
    "https://feishu.cn.example.com/docx/abc",
    "https://notfeishu.cn/docx/abc",
    "https://user:secret@team.feishu.cn/docx/abc",
  ]) assert.notEqual(validate(value), null, value);
});
