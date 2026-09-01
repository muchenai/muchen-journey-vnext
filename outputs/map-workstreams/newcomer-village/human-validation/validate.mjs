import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const packageDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(packageDir, "../../../..");
const planPath = path.join(packageDir, "human-validation-plan.json");
const contractPath = path.join(packageDir, "..", "contract.json");
const protocolPath = path.join(packageDir, "protocol.md");
const expectedCommit = "14cc8b31936597f846c9b48bdaa36f7658155e61";
const frozenPaths = [
  "docs/maps/newcomer-village/FIRST_GOLDEN_PATH.md",
  "prototypes/newcomer-village",
  "outputs/map-workstreams/newcomer-village/contract.json",
  "outputs/map-workstreams/newcomer-village/browser-evidence",
  "outputs/map-workstreams/newcomer-village/machine-acceptance.md",
  "outputs/map-workstreams/newcomer-village/controller-proposal.md",
];

function runGit(args) {
  return spawnSync("git", args, { cwd: repoRoot, encoding: "utf8" });
}

function assertGitSuccess(result, label) {
  assert.equal(result.status, 0, `${label}: ${result.stderr || result.stdout}`);
}

function get(object, dottedPath) {
  return dottedPath.split(".").reduce((value, key) => value?.[key], object);
}

const plan = JSON.parse(await readFile(planPath, "utf8"));
const contract = JSON.parse(await readFile(contractPath, "utf8"));
const protocol = await readFile(protocolPath, "utf8");

const commitExists = runGit(["cat-file", "-e", `${expectedCommit}^{commit}`]);
assertGitSuccess(commitExists, "frozen candidate commit must exist");
const frozenDiff = runGit(["diff", "--quiet", expectedCommit, "--", ...frozenPaths]);
assertGitSuccess(frozenDiff, "frozen candidate files must match 14cc8b3");

assert.equal(contract.id, plan.target_contract_id);
assert.equal(contract.map, plan.map);
assert.equal(contract.candidate_status, "READY_FOR_HUMAN");
assert.equal(contract.candidate_frozen, true);
assert.equal(contract.human_gate.status, "NOT_RUN");
assert.equal(plan.frozen_candidate_commit, expectedCommit);
assert.equal(plan.candidate_status, contract.candidate_status);
assert.equal(plan.candidate_frozen, true);
assert.equal(plan.route, contract.routes[0]);
assert.equal(contract.routes.length, 1);
assert.equal(plan.starts_at, contract.starts_at);
assert.equal(plan.ends_at, contract.ends_at);
assert.deepEqual(plan.human_acceptance, contract.human_acceptance);

assert.equal(plan.validation.status, "NOT_RUN");
assert.equal(plan.validation.started_at, null);
assert.equal(plan.validation.completed_at, null);
assert.equal(plan.validation.human_verdict, "NOT_RUN");
assert.equal(plan.validation.human_result_inferred, false);
assert.equal(plan.participant_profile.required_sample_size, 3);
assert.equal(plan.participant_profile.recruitment_status, "NOT_RUN");
assert.equal(plan.facilitator.mode, "NO_EXPLANATION");
assert.equal(plan.facilitator.facilitator_rescue_threshold, 0);
assert.equal(plan.facilitator.may_explain_entry_route_terminology_or_next_action, false);
assert.equal(plan.evidence_policy.filled_record_may_be_committed, false);
assert.equal(plan.evidence_policy.repo_may_store_only_privacy_safe_references, true);

const thresholds = plan.normalized_thresholds;
assert.deepEqual(thresholds.orientation_and_source_boundary, {
  required_pass_count: 3,
  sample_size: 3,
  requires_exploration_input_identified: true,
  requires_role_org_input_identified: true,
  requires_no_shared_write_identified: true,
});
assert.equal(thresholds.independent_action_selection.required_pass_count, 3);
assert.equal(thresholds.independent_action_selection.sample_size, 3);
assert.equal(thresholds.independent_action_selection.maximum_raw_elapsed_seconds, 180);
assert.equal(thresholds.independent_action_selection.maximum_total_facilitator_interventions, 0);
assert.equal(thresholds.real_integration_action.required_pass_count, 3);
assert.equal(thresholds.real_integration_action.must_complete_within_one_working_day, true);
assert.equal(thresholds.real_integration_action.prototype_click_is_proof, false);
assert.equal(thresholds.reviewable_evidence.required_pass_count, 3);
assert.equal(thresholds.reviewable_evidence.human_reviewer_required, true);
assert.equal(thresholds.reviewable_evidence.private_names_or_confidential_details_required, false);
assert.equal(thresholds.clarity_and_willingness.minimum_clarity_median, 4);
assert.equal(thresholds.clarity_and_willingness.minimum_willingness_median, 4);

assert.equal(plan.participant_slots.length, 3);
assert.deepEqual(plan.participant_slots.map((slot) => slot.slot_id), ["NV-H01", "NV-H02", "NV-H03"]);
const nullFields = [
  "profile_fit_confirmed",
  "non_sensitive_profile_ref",
  "consent_ref",
  "start_time_iso",
  "action_card_time_iso",
  "receipt_time_iso",
  "raw_elapsed_seconds",
  "facilitator_intervention_count",
  "understanding_restatement_verbatim",
  "understanding_coding.exploration_input_identified",
  "understanding_coding.role_org_input_identified",
  "understanding_coding.no_shared_write_identified",
  "selected_action_id",
  "planned_counterpart_role",
  "planned_time",
  "real_action.confirmed",
  "real_action.confirmed_within_one_working_day",
  "real_action.privacy_safe_confirmation_ref",
  "evidence_review.reviewer_role",
  "evidence_review.accepted",
  "evidence_review.minimum_fields_present",
  "evidence_review.specific_enough",
  "evidence_review.privacy_safe",
  "evidence_review.supports_allowed_output",
  "evidence_review.non_sensitive_review_ref",
  "clarity_rating_1_to_5",
  "willingness_to_continue_rating_1_to_5",
];
for (const slot of plan.participant_slots) {
  assert.equal(slot.status, "NOT_RUN");
  for (const field of nullFields) assert.equal(get(slot, field), null, `${slot.slot_id}.${field} must remain null before testing`);
  assert.deepEqual(slot.privacy_safe_evidence_refs, []);
}

for (const prohibitedKey of plan.participant_profile.prohibited_identifiers) {
  assert.ok(!JSON.stringify(plan.participant_slots).includes(`"${prohibitedKey}"`), `${prohibitedKey} must not be a participant field`);
}
assert.match(protocol, /过程中我不会解释页面、路线、术语或下一步/);
assert.match(protocol, /raw_elapsed_seconds/);
assert.match(protocol, /facilitator_intervention_count/);
assert.match(protocol, /understanding_restatement_verbatim/);
assert.match(protocol, /一个工作日内/);
assert.match(protocol, /中位数至少 4\/5/);
assert.match(protocol, /获批的私有证据位置/);

console.log("HUMAN_VALIDATION_PACKAGE=PASS");
console.log(`TARGET=${plan.target_contract_id}`);
console.log(`FROZEN_CANDIDATE=${expectedCommit}`);
console.log("HUMAN_VALIDATION=NOT_RUN");
console.log(`PARTICIPANT_SLOTS=${plan.participant_slots.length}`);
console.log("HUMAN_RESULT_INFERRED=false");
