import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../../", import.meta.url);
const contract = JSON.parse(await readFile(new URL("outputs/map-workstreams/boss-dungeon/contract.json", root), "utf8"));
const html = await readFile(new URL("prototypes/boss-dungeon/index.html", root), "utf8");
const js = await readFile(new URL("prototypes/boss-dungeon/app.js", root), "utf8");
const css = await readFile(new URL("prototypes/boss-dungeon/styles.css", root), "utf8");

test("binds to one exact boss-dungeon golden path", () => {
  assert.equal(contract.map, "boss-dungeon");
  assert.equal(contract.phase, "ISOLATED_DRAFT_BUILD");
  assert.equal(contract.golden_path.active, true);
  assert.equal(contract.golden_path.starts_at, "synthetic-capability-briefing");
  assert.equal(contract.golden_path.ends_at, "local-decision-receipt-visible");
  assert.deepEqual(contract.golden_path.routes, ["prototypes/boss-dungeon/index.html"]);
});

test("keeps every entity and outcome visibly synthetic", () => {
  assert.match(html, /合成模拟/g);
  assert.match(html, /不连接真实公司、客户、人员或评估数据/);
  assert.match(html, /不评价真人/);
  assert.match(html, /不得用于真实录用、晋升、淘汰、薪酬或绩效评级/);
  assert.doesNotMatch(html, /准备度[：:]?\s*\d|绩效[：:]?\s*[A-E]|录用建议/);
  assert.equal(contract.scenario.data_classification, "SYNTHETIC_ONLY");
  assert.equal(contract.scenario.employment_or_performance_use, false);
});

test("requires evidence and constraints before a verifiable decision", () => {
  const orderedStates = ["briefing", "safety", "team", "decision", "receipt"];
  let cursor = -1;
  for (const state of orderedStates) {
    const next = html.indexOf(`data-stage="${state}"`, cursor + 1);
    assert.ok(next > cursor, `${state} must follow the golden path order`);
    cursor = next;
  }
  assert.match(js, /rationale\.length < 20/);
  assert.match(js, /!decision \|\| !evidence \|\| !constraint/);
  assert.match(html, /合成事实/);
  assert.match(html, /AI 建议/);
  assert.match(html, /人类选择/);
  assert.match(html, /系统状态/);
});

test("does not create a second shared fact source", () => {
  assert.doesNotMatch(js, /\bfetch\s*\(|XMLHttpRequest|indexedDB|localStorage/);
  assert.match(js, /sessionStorage/);
  assert.match(html, /不调用共享 API，不写入 Person、Evidence 或 Progress/);
  assert.equal(contract.shared_fact_policy.writes_to_shared_platform, false);
  assert.ok(Object.entries(contract.shared_fact_policy).filter(([key]) => ["person", "capability", "evidence", "progress", "identity"].includes(key)).every(([, value]) => value === "READ_ONLY"));
});

test("supports responsive, keyboard, reduced-motion, error and re-entry behavior", () => {
  assert.match(html, /width=device-width, initial-scale=1/);
  assert.match(css, /@media \(max-width: 900px\)/);
  assert.match(css, /@media \(max-width: 620px\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /focus-visible/);
  assert.match(css, /min-height: 52px/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /id="receipt-title" tabindex="-1"/);
  assert.match(html, /class="field-error"/);
  assert.match(js, /loadState\(\)/);
  assert.match(js, /aria-busy/);
});
