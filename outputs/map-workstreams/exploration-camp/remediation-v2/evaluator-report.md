# Exploration Camp Remediation V2 — Independent Evaluator Report

Evaluation date: 2026-08-23
Verdict: `BLOCKED_NO_RUNNABLE_TARGET`

## Evaluated target

- Map: `exploration-camp`
- Active golden path: `exploration-camp-first-meaningful-action`
- Exact start: `private-invitation-entry`
- Exact end: `first-required-learning-material-opened`
- Contract routes: `/`, `/join`, `/app`
- Remediation kind: `IMPLEMENTATION_READY_CONTRACT_ONLY`
- Frozen baseline: `a9381f0944fb4c8c852c115e3bc708363ac67a37`

This evaluation is read-only. It evaluates whether remediation v2 has a runnable target; it does not re-evaluate, mutate, or supersede the frozen candidate.

## Evidence examined

1. Product Doctor and Product Status both pass for the authoritative Exploration Camp golden path.
2. `validate-contract.py` passes and confirms that the package adds zero golden paths, keeps `READY_FOR_HUMAN=false`, and permits exactly five controller runtime writes.
3. The frozen candidate manifest still reports `AWAITING_HUMAN`, `HUMAN_GATE=NOT_RUN`, `RELEASE_AUTHORIZED=false`, and `PRODUCTION_MUTATION_EXECUTED=false`.
4. The three new runtime artifacts named by the contract do not exist:
   - `apps/web/src/app/join/private-invite-orientation.tsx`
   - `apps/web/src/app/join/private-invite-orientation.module.css`
   - `apps/web/scripts/exploration-camp-private-invite-orientation-contract.test.mjs`
5. The two existing `/join` files have not been changed by this workstream for remediation v2.

## Finding

The original P1 remains the machine blocker for the frozen runtime: a natural private invitation beginning at `/join#token=…` can reach the first required material without first receiving the required five-map, Exploration Camp starting-point, and immediate-next-step orientation.

The remediation v2 contract is internally implementable and preserves the fragment token, one-time exchange, identity/permission, CSRF, token non-disclosure, Enrollment, Assignment, and re-entry semantics. However, it is documentation only. There is no v2 runtime behavior to exercise, so browser evidence would test the frozen baseline rather than this remediation.

No new P0 or contract-level P1 contradiction was found. The unresolved runtime P1 is sufficient to block candidate promotion.

## Browser and human evidence

- Playwright/browser run: `NOT_RUN_NO_V2_RUNTIME_TARGET`
- Responsive and keyboard checks: `NOT_RUN_NO_V2_RUNTIME_TARGET`
- Token leakage and one-time exchange regression checks: `NOT_RUN_NO_V2_RUNTIME_TARGET`
- Human acceptance: `NOT_RUN`
- Machine evidence substituted for human evidence: `false`

The existing human gate remains untouched. This contract-only package is not `READY_FOR_HUMAN` and must not be entered into a candidate list.

## Precise unblock action

The controller must implement exactly the five paths in `runtime-write-set.json`, run every machine criterion in `acceptance.md`, and then request a new independent read-only evaluation of the implemented runtime. Only a passing runtime evaluation may prepare a new human-test candidate; only actual human results may satisfy the human gate.
