import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const prototype = await readFile(new URL("./index.html", import.meta.url), "utf8");
const contract = JSON.parse(
  await readFile(new URL("../../outputs/map-workstreams/delivery-guild/contract.json", import.meta.url), "utf8"),
);

test("the map owns exactly one bounded active golden path", () => {
  assert.equal(contract.map, "delivery-guild");
  assert.equal(contract.phase, "ISOLATED_DRAFT_BUILD");
  assert.equal(contract.active_golden_paths.length, 1);
  assert.equal(contract.active_golden_paths[0].id, "delivery-guild-first-bounded-evidence-draft");
  assert.equal(contract.formal_product_integration, false);
  assert.equal(contract.production_mutation_authorized, false);
});

test("shared facts remain read-only and the prototype output remains local pending input", () => {
  assert.equal(contract.input_contract.shared_sources_are_read_only, true);
  assert.equal(contract.output_contract.shared_evidence_write, false);
  assert.equal(contract.output_contract.prototype_output, "browser-local-pending-draft");
  for (const source of ["person", "capability", "evidence-ledger", "progress", "identity"]) {
    assert.ok(contract.shared_surfaces_read_only.includes(source));
  }
  assert.match(prototype, /LOCAL_PENDING_HUMAN_REVIEW/);
  assert.match(prototype, /localStorage\.setItem/);
  assert.doesNotMatch(prototype, /\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|<form[^>]+action=/);
});

test("the experience visibly preserves synthetic, responsibility, and governance boundaries", () => {
  for (const phrase of [
    "合成沙盒数据",
    "不连接真实客户、项目、外部消息或共享 Evidence Ledger",
    "角色与协作准备度",
    "AI 能力档案",
    "非目标",
    "允许数据",
    "时间盒",
    "完成条件",
    "你 / 任务执行者",
    "模拟协作者",
    "导师",
    "AI 助手",
    "待人工复核",
    "没有真人验收",
  ]) {
    assert.match(prototype, new RegExp(phrase));
  }
});

test("each path step declares one primary action and required recovery support", () => {
  const actions = contract.active_golden_paths[0].single_primary_action_by_step;
  assert.equal(Object.keys(actions).length, 5);
  for (const action of Object.values(actions)) assert.match(prototype, new RegExp(action));
  assert.match(prototype, /prefers-reduced-motion: reduce/);
  assert.match(prototype, /width=device-width, initial-scale=1/);
  assert.match(prototype, /浏览器未允许本地保存/);
  assert.match(prototype, /form\.elements\[firstMissing\]\.focus/);
  assert.match(prototype, /form\.addEventListener\("input"/);
  assert.match(prototype, /清除本地草稿并重新开始/);
});

test("machine and human acceptance remain explicitly separate", () => {
  const path = contract.active_golden_paths[0];
  assert.equal(path.machine_acceptance.length, 6);
  assert.equal(path.human_acceptance.length, 5);
  assert.match(contract.promotion_rule, /READY_FOR_HUMAN only/);
  assert.match(contract.freeze_rule, /preserve the exact candidate/);
  assert.match(prototype, /不代表真人通过、总控集成或正式发布/);
});
