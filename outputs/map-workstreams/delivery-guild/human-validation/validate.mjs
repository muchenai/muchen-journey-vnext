import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const packageRoot = new URL("./", import.meta.url);
const repoRoot = new URL("../../../../", import.meta.url);

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf8"));
}

async function readRepoJson(path) {
  return readJson(new URL(path, repoRoot));
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function collectKeys(value, keys = []) {
  if (Array.isArray(value)) {
    for (const item of value) collectKeys(item, keys);
    return keys;
  }
  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      keys.push(key);
      collectKeys(item, keys);
    }
  }
  return keys;
}

const [contract, manifest, plan, results, privacy, protocol] = await Promise.all([
  readRepoJson("outputs/map-workstreams/delivery-guild/contract.json"),
  readRepoJson("outputs/map-workstreams/delivery-guild/candidate-manifest.json"),
  readJson(new URL("test-plan.json", packageRoot)),
  readJson(new URL("results.blank.json", packageRoot)),
  readJson(new URL("privacy-evidence.json", packageRoot)),
  readFile(new URL("facilitator-protocol.md", packageRoot), "utf8"),
]);

assert.equal(contract.map, "delivery-guild");
assert.equal(contract.contract_status, "FROZEN_CANDIDATE");
assert.equal(contract.candidate_status, "READY_FOR_HUMAN");
assert.equal(contract.active_golden_paths.length, 1);
assert.equal(contract.human_evaluation.status, "NOT_RUN");
assert.equal(contract.human_evaluation.criteria_inferred_from_machine_evidence, false);

const goldenPath = contract.active_golden_paths[0];
assert.equal(plan.status, "NOT_RUN");
assert.equal(plan.golden_path_id, goldenPath.id);
assert.equal(plan.starts_at, goldenPath.starts_at);
assert.equal(plan.ends_at, goldenPath.ends_at);
assert.equal(plan.runtime_entry, goldenPath.runtime_entry);
assert.equal(plan.sample.required_count, 3);
assert.deepEqual(plan.sample.participant_ids, ["participant-01", "participant-02", "participant-03"]);
assert.equal(plan.session.facilitation, "UNPROMPTED_NO_EXPLANATION");
assert.equal(plan.session.maximum_first_draft_seconds, 180);
assert.equal(plan.session.rescue_interventions_allowed, 0);

const expectedHumanCriteria = goldenPath.human_acceptance.map(({ id, threshold }) => ({ id, threshold }));
const plannedHumanCriteria = plan.human_acceptance.map(({ id, threshold }) => ({ id, threshold }));
assert.deepEqual(plannedHumanCriteria, expectedHumanCriteria);
assert.deepEqual(expectedHumanCriteria, [
  { id: "task-boundary-comprehension", threshold: "3/3 target learners" },
  { id: "responsibility-comprehension", threshold: "3/3 target learners" },
  { id: "first-draft-within-3-minutes", threshold: "3/3 target learners within 3 minutes" },
  { id: "clarity-and-willingness", threshold: "median >= 4/5 for both questions" },
  { id: "zero-facilitator-rescue", threshold: "0 interventions" },
]);

assert.equal(results.status, "NOT_RUN");
assert.equal(results.contains_real_person_data, false);
assert.equal(results.participant_slots.length, 3);
assert.deepEqual(results.participant_slots.map(({ participant_id }) => participant_id), plan.sample.participant_ids);
for (const slot of results.participant_slots) {
  assert.equal(slot.eligibility_status, "NOT_RUN");
  assert.equal(slot.consent_status, "NOT_RUN");
  assert.equal(slot.session_status, "NOT_RUN");
  assert.equal(slot.viewport_css_width, null);
  for (const [key, value] of Object.entries(slot.task_boundary_comprehension)) {
    assert.equal(value, "NOT_RUN", `${slot.participant_id}.${key} must remain NOT_RUN`);
  }
  assert.equal(slot.task_boundary_comprehension.result, "NOT_RUN");
  for (const [key, value] of Object.entries(slot.responsibility_comprehension)) {
    assert.equal(value, "NOT_RUN", `${slot.participant_id}.${key} must remain NOT_RUN`);
  }
  assert.equal(slot.responsibility_comprehension.result, "NOT_RUN");
  assert.equal(slot.first_draft_within_3_minutes.elapsed_seconds, null);
  for (const [key, value] of Object.entries(slot.first_draft_within_3_minutes)) {
    if (key !== "elapsed_seconds") {
      assert.equal(value, "NOT_RUN", `${slot.participant_id}.${key} must remain NOT_RUN`);
    }
  }
  assert.equal(slot.first_draft_within_3_minutes.result, "NOT_RUN");
  assert.equal(slot.clarity_and_willingness.task_boundary_clarity_1_to_5, null);
  assert.equal(slot.clarity_and_willingness.willingness_to_continue_1_to_5, null);
  assert.equal(slot.clarity_and_willingness.result, "NOT_RUN");
  assert.equal(slot.zero_facilitator_rescue.rescue_intervention_count, null);
  assert.equal(slot.zero_facilitator_rescue.result, "NOT_RUN");
  assert.deepEqual(slot.privacy_safe_evidence_refs, []);
}
assert.equal(results.aggregate.valid_target_learner_count, 0);
assert.equal(results.aggregate.human_gate, "NOT_RUN");

assert.equal(privacy.status, "NOT_RUN");
assert.equal(privacy.data_minimization.anonymous_participant_ids_only, true);
assert.equal(privacy.data_minimization.audio_recording_default, false);
assert.equal(privacy.data_minimization.video_recording_default, false);
assert.equal(privacy.data_minimization.raw_transcript_storage, false);
assert.equal(privacy.data_minimization.real_business_content_allowed, false);
assert.deepEqual(privacy.human_evidence_refs, []);
assert.equal(privacy.machine_evidence_may_substitute_for_human, false);
assert.equal(privacy.frozen_machine_baseline_refs.length, 6);
for (const ref of privacy.frozen_machine_baseline_refs) {
  assert.equal(ref.human_result, false);
  await readFile(new URL(ref.path, repoRoot));
}

const prohibitedKeyNames = new Set(privacy.data_minimization.prohibited_fields);
const resultKeys = collectKeys(results);
assert.deepEqual(resultKeys.filter((key) => prohibitedKeyNames.has(key)), []);

for (const entry of manifest.candidate_files) {
  const content = await readFile(new URL(entry.path, repoRoot));
  assert.equal(sha256(content), entry.sha256, `frozen hash mismatch: ${entry.path}`);
}
for (const entry of manifest.representative_evidence) {
  const content = await readFile(new URL(entry.path, repoRoot));
  assert.equal(sha256(content), entry.sha256, `frozen evidence hash mismatch: ${entry.path}`);
}

assert.match(protocol, /3 名目标学员/);
assert.match(protocol, /不会解释页面、术语、操作或下一步/);
assert.match(protocol, /180|三分钟|3 分钟/);
assert.match(protocol, /待人工复核/);
assert.match(protocol, /rescue_intervention/);
assert.match(protocol, /不得在仓库中保存学员的原话、身份或真实业务内容/);

console.log("HUMAN_VALIDATION_PACKAGE=PASS");
console.log("STATUS=NOT_RUN");
console.log(`PARTICIPANT_SLOTS=${results.participant_slots.length}`);
console.log("FROZEN_CANDIDATE_HASHES=PASS");
console.log(`VALIDATOR=${fileURLToPath(import.meta.url)}`);
