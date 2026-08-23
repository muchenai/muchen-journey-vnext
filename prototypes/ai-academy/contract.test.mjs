import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const prototype = await readFile(new URL("./index.html", import.meta.url), "utf8");
const script = await readFile(new URL("./app.js", import.meta.url), "utf8");
const styles = await readFile(new URL("./styles.css", import.meta.url), "utf8");
const fixture = JSON.parse(await readFile(new URL("./synthetic-fixture.json", import.meta.url), "utf8"));
const contract = JSON.parse(
  await readFile(new URL("../../outputs/map-workstreams/ai-academy/contract.json", import.meta.url), "utf8"),
);

test("the prototype is visibly isolated and synthetic at every step", () => {
  assert.match(prototype, /全部人物、岗位、课程与场景均为合成夹具/);
  assert.match(prototype, /合成人物与岗位夹具/);
  assert.match(prototype, /合成学习输入 · 非正式课程/);
  assert.match(prototype, /合成练习场景 · 不写入档案/);
  assert.match(prototype, /会话内练习记录 · 非正式评估/);
  assert.equal(fixture.fixture_type, "SYNTHETIC_LEARNING_FIXTURE");
  assert.equal(fixture.formal_course, false);
});

test("the active path preserves input before practice and explainable evidence", () => {
  const steps = ["data-step=\"1\"", "data-step=\"2\"", "data-step=\"3\"", "data-step=\"4\""];
  let cursor = -1;
  for (const marker of steps) {
    const next = prototype.indexOf(marker, cursor + 1);
    assert.ok(next > cursor, `${marker} must appear in order`);
    cursor = next;
  }
  assert.match(script, /if \(!learningExpanded\)/);
  assert.match(script, /value\.length >= field\.minimum/);
  assert.match(prototype, /原文回显 · 无模型评分/);
  assert.match(prototype, /不证明课程通过、能力掌握、岗位胜任、绩效表现、晋升资格或任何用人结论/);
});

test("the prototype does not create a second shared fact source", () => {
  assert.doesNotMatch(script, /localStorage|sessionStorage|indexedDB|XMLHttpRequest/);
  assert.match(script, /fetch\("\.\/synthetic-fixture\.json"/);
  assert.match(prototype, /不上传、不持久化、不写入共享 Evidence Ledger/);
  assert.equal(contract.shared_facts_policy.persistence, "NONE");
  assert.equal(contract.shared_facts_policy.evidence, "NO_SHARED_WRITE");
});

test("the isolated experience declares one path and responsive interaction support", () => {
  assert.equal(contract.active_golden_path.id, "ai-academy-first-explainable-practice-evidence");
  assert.equal(contract.status, "READY_FOR_HUMAN");
  assert.equal(contract.machine_evaluation.verdict, "READY_FOR_HUMAN");
  assert.equal(contract.machine_evaluation.candidate_frozen, true);
  assert.equal(contract.machine_evaluation.human_validation, "NOT_INFERRED");
  assert.equal(contract.formal_golden_path_promoted, false);
  assert.equal(contract.active_golden_path.steps.length, 4);
  assert.match(styles, /@media \(max-width: 900px\)/);
  assert.match(styles, /@media \(max-width: 600px\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(styles, /min-height: 52px/);
  assert.match(prototype, /width=device-width, initial-scale=1/);
});
