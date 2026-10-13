import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/lib/journey-entry-preload.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const compiled = { exports: {} };
vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(require, compiled, compiled.exports);
const { JOURNEY_ENTRY_RESOURCES, preloadJourneyEntryResources } = compiled.exports;

test("entry preload manifest covers the complete Project 9 bundle plus font and Feishu SDK", () => {
  assert.equal(JOURNEY_ENTRY_RESOURCES.length, 62);
  assert.equal(new Set(JOURNEY_ENTRY_RESOURCES).size, JOURNEY_ENTRY_RESOURCES.length);
  assert.ok(JOURNEY_ENTRY_RESOURCES.every(path => path.startsWith("/") && !path.includes("..")));
  assert.ok(JOURNEY_ENTRY_RESOURCES.includes("/fonts/project9/SourceHanSansSC-VF.woff2"));
  assert.ok(JOURNEY_ENTRY_RESOURCES.includes("/vendor/feishu/h5-js-sdk-1.5.26.csp.js"));
});

test("preloader reports real completed resources and limits concurrency", async () => {
  let active = 0;
  let maximum = 0;
  const progress = [];
  const fetchResource = async () => {
    active += 1;
    maximum = Math.max(maximum, active);
    await new Promise(resolve => setImmediate(resolve));
    active -= 1;
    return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) };
  };
  await preloadJourneyEntryResources((loaded, total) => progress.push([loaded, total]), new AbortController().signal, fetchResource);
  assert.equal(maximum, 4);
  assert.deepEqual(progress[0], [0, 62]);
  assert.deepEqual(progress.at(-1), [62, 62]);
});

test("preloader refuses to show completion when any resource fails", async () => {
  let calls = 0;
  const fetchResource = async () => ({
    ok: ++calls !== 7,
    arrayBuffer: async () => new ArrayBuffer(1),
  });
  await assert.rejects(
    preloadJourneyEntryResources(() => {}, new AbortController().signal, fetchResource),
    /ENTRY_RESOURCES_UNAVAILABLE/,
  );
});
