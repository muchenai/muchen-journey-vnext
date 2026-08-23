import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const prototype = await readFile(new URL("./index.html", import.meta.url), "utf8");
const script = await readFile(new URL("./app.js", import.meta.url), "utf8");
const styles = await readFile(new URL("./styles.css", import.meta.url), "utf8");
const contentStructure = JSON.parse(await readFile(new URL("./content-structure.json", import.meta.url), "utf8"));
const contract = JSON.parse(await readFile(new URL("../../outputs/map-workstreams/newcomer-village/contract.json", import.meta.url), "utf8"));

test("the runnable draft binds to exactly one newcomer-village contract and route", () => {
  assert.equal(contract.map, "newcomer-village");
  assert.equal(contract.phase, "ISOLATED_DRAFT_BUILD");
  assert.deepEqual(contract.routes, ["/prototypes/newcomer-village/index.html"]);
  assert.equal(contract.starts_at, "isolated-arrival-with-authorized-context-snapshot");
  assert.equal(contract.ends_at, "local-evidence-draft-receipt-after-self-attested-real-action");
  assert.equal(contentStructure.contract_ref, "../../outputs/map-workstreams/newcomer-village/contract.json");
  assert.equal(contentStructure.route, contract.routes[0]);
  assert.deepEqual(contentStructure.states, contract.states.map((state) => state.id));
});

test("the prototype keeps shared facts read-only and labels synthetic inputs", () => {
  assert.match(prototype, /合成 fixture/);
  assert.match(prototype, /探索营真人状态：未验证/);
  assert.match(prototype, /不代表任何真人或公司事实/);
  assert.match(prototype, /READ ONLY · 本原型不修改这些字段/);
  assert.match(prototype, /本地临时草稿 · 未提交/);
  assert.match(prototype, /无共享事实写入/);
  assert.equal(contentStructure.shared_fact_sources, "READ_ONLY");
  assert.equal(contentStructure.prototype_data, "SYNTHETIC_FIXTURE_ONLY");
  assert.equal(contract.output_contract.shared_write_permitted, false);
});

test("the experience requires context, a real action plan, and evidence before receipt", () => {
  const orderedScreens = ["arrival", "context-review", "action-plan", "action-check", "evidence-capture", "receipt"];
  let cursor = -1;
  for (const screen of orderedScreens) {
    const next = prototype.indexOf(`data-screen="${screen}"`, cursor + 1);
    assert.ok(next > cursor, `${screen} must follow the contract order`);
    cursor = next;
  }
  assert.match(prototype, /我已真实完成，留下证据/);
  assert.match(prototype, /不在原型里/);
  assert.match(script, /draft\.observation\.length >= 12/);
  assert.match(script, /draft\.repeatBehavior\.length >= 12/);
  assert.match(script, /draft\.privacyAttestation/);
  assert.equal(contract.first_real_action_options.length, 3);
});

test("the local recovery draft is isolated and restartable", () => {
  assert.match(script, /sessionStorage\.getItem\(STORAGE_KEY\)/);
  assert.match(script, /sessionStorage\.setItem\(STORAGE_KEY/);
  assert.match(script, /sessionStorage\.removeItem\(STORAGE_KEY\)/);
  assert.doesNotMatch(script, /\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|localStorage/);
  assert.equal(contentStructure.recovery.truth_status, "DISPOSABLE_DRAFT_NOT_SHARED_FACT");
});

test("the path preserves five-map order, keyboard semantics, and responsive/reduced-motion support", () => {
  const orderedMaps = ["探索营", "新手村", "AI 学院", "交付线工会", "BOSS 副本"];
  let cursor = -1;
  for (const map of orderedMaps) {
    const next = prototype.indexOf(`<strong>${map}</strong>`, cursor + 1);
    assert.ok(next > cursor, `${map} must appear in canonical order`);
    cursor = next;
  }
  assert.match(prototype, /<button class="primary-action"/);
  assert.match(prototype, /<form id="action-form" novalidate>/);
  assert.match(prototype, /<form id="evidence-form" class="evidence-form" novalidate>/);
  assert.match(styles, /@media \(max-width: 980px\)/);
  assert.match(styles, /@media \(max-width: 700px\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("human acceptance stays explicit and untouched", () => {
  assert.equal(contract.human_gate.status, "NOT_RUN");
  assert.equal(contract.human_gate.machine_evidence_may_substitute, false);
  assert.equal(contract.human_acceptance.length, 5);
  assert.ok(contract.prohibited_claims.includes("Exploration Camp human validation passed"));
  assert.match(prototype, /机器证据不能替代真人/);
});
