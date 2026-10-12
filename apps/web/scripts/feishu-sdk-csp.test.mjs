import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../public/vendor/feishu/h5-js-sdk-1.5.26.js", import.meta.url), "utf8");
const compatible = readFileSync(new URL("../public/vendor/feishu/h5-js-sdk-1.5.26.csp.js", import.meta.url), "utf8");

function initialize(code, userAgent = "Mozilla/5.0 Chrome/140.0 Lark/7.50.0 WebApp") {
  const context = {
    navigator: { userAgent, platform: "Win32" },
    document: { addEventListener() {}, head: {}, createElement() { return { style: {} }; }, querySelectorAll() { return []; } },
    console, setTimeout: () => 1, clearTimeout() {},
    MutationObserver: class { observe() {} }, CustomEvent: class {},
    addEventListener() {}, dispatchEvent() {},
  };
  context.window = context;
  vm.runInNewContext(code, context, { contextCodeGeneration: { strings: false, wasm: false } });
  return context;
}

test("reproduces original SDK initialization failure under strict CSP", () => {
  assert.throws(() => initialize(source), /Code generation from strings disallowed/);
});

test("compatible SDK changes only the two constant global getters", () => {
  assert.equal(compatible, source.replaceAll('new Function("return this;")()', "globalThis"));
});

test("actual compatible SDK exposes Feishu login APIs without eval", () => {
  const context = initialize(compatible);
  assert.equal(typeof context.h5sdk?.ready, "function");
  assert.equal(typeof context.tt?.requestAccess, "function");
});

test("actual SDK does not expose login APIs in an ordinary desktop Feishu webview", () => {
  const context = initialize(compatible, "Mozilla/5.0 Chrome/140.0 Lark/7.50.0");
  assert.equal(context.h5sdk, undefined);
  assert.equal(context.tt?.requestAccess, undefined);
});
