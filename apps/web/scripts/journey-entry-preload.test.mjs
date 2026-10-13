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

test("entry preload manifest covers Project 9, later journey screens, font and Feishu SDK", () => {
  assert.equal(JOURNEY_ENTRY_RESOURCES.length, 78);
  assert.equal(new Set(JOURNEY_ENTRY_RESOURCES).size, JOURNEY_ENTRY_RESOURCES.length);
  assert.ok(JOURNEY_ENTRY_RESOURCES.every(path => path.startsWith("/") && !path.includes("..")));
  assert.ok(JOURNEY_ENTRY_RESOURCES.includes("/fonts/project9/SourceHanSansSC-VF.woff2"));
  assert.ok(JOURNEY_ENTRY_RESOURCES.includes("/vendor/feishu/h5-js-sdk-1.5.26.csp.js"));
  assert.ok(JOURNEY_ENTRY_RESOURCES.includes("/images/journey-v2-background.png"));
  assert.ok(JOURNEY_ENTRY_RESOURCES.includes("/journey/day0-threshold-v1.jpg"));
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
  await preloadJourneyEntryResources(({ loaded, total }) => progress.push([loaded, total]), new AbortController().signal, fetchResource, null, []);
  assert.equal(maximum, 4);
  assert.deepEqual(progress[0], [0, 78]);
  assert.deepEqual(progress.at(-1), [78, 78]);
});

test("preloader refuses to show completion when any resource fails", async () => {
  let calls = 0;
  const fetchResource = async () => ({
    ok: ++calls !== 7,
    arrayBuffer: async () => new ArrayBuffer(1),
  });
  await assert.rejects(
    preloadJourneyEntryResources(() => {}, new AbortController().signal, fetchResource, null, []),
    /ENTRY_RESOURCES_UNAVAILABLE/,
  );
});

test("preloader writes every successful response into the versioned browser cache", async () => {
  const cached = [];
  const cacheStorage = {
    keys: async () => ["muchen-journey-entry-v1"],
    delete: async () => true,
    open: async name => ({ put: async path => cached.push([name, path]) }),
  };
  const fetchResource = async () => ({
    ok: true,
    clone: () => ({}),
    arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
  });
  let finalProgress;
  await preloadJourneyEntryResources(progress => { finalProgress = progress; }, new AbortController().signal, fetchResource, cacheStorage, ["/_next/static/app.js"]);
  assert.equal(cached.length, JOURNEY_ENTRY_RESOURCES.length + 1);
  assert.deepEqual(cached.at(-1), ["muchen-journey-entry-v3", "/_next/static/app.js"]);
  assert.equal(finalProgress.loadedBytes, (JOURNEY_ENTRY_RESOURCES.length + 1) * 3);
});
