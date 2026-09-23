# Treasure Coaching Production Delivery Plan

> Confirmed by the user on 2026-09-23. This is the authoritative remaining-work plan. Execute one phase at a time. Do not expand scope merely because an external task is waiting.

**Goal:** Safely deliver the already-completed four-treasure non-blocking coaching feature, preserve identity and immutable history, backfill only the intended latest treasure submissions, and hand the verified production release to human UAT.

**Current status:** Feature development and the immutable application package are complete. Production remains on `b8a5dd580eaec72945cbe4f0e37c1152ee4645a1`. Candidate `9a35f45053e903aa8e4d113aadbf7168d9ae9d0d` is blocked in release preparation because the production host could not download the pinned dbrestore image within the existing 1800-second per-image timeout. No schema migration, switch, or backfill has run.

**Evidence:** Feature PRs #409/#410 merged; package Run `35843223116` passed; Prepare Run `35843920266` stopped with `COMMAND_TIMEOUT`; detailed retrospective is `D:/muchen_journey/9.6日项目阻塞复盘.md`, section 13.

## Non-negotiable boundaries

- Preserve organization and role isolation, explicit Reviewer assignment/delegation, and Operator-only controls.
- Preserve every existing SubmissionVersion, Review, Evaluation, Outcome, Enrollment, identity, and audit fact.
- Day 0 remains Learner Evidence; only four treasures use non-blocking coaching; the three assessments remain the only formal Human Gates.
- Coaching must not create Evaluation or block progression, graduation, or admission.
- Migration, backup/restore comparison, idempotent backfill, protected-count checks, and rollback/forward-fix boundaries remain mandatory.
- Before coaching facts exist, a failed switch may return to the verified old application. After any coaching facts exist, old application rollback and database restore-overwrite are forbidden; use forward-fix only.
- CI, API tests, and synthetic-browser tests are not human UAT.
- No real Learner account is used for automation, load testing, migration verification, or synthetic smoke tests.

## Work already complete — do not repeat

- [x] Non-blocking `LEARNING_COACHING` domain model and immutable CoachingFeedback.
- [x] Formal evaluation/coaching separation and protected history constraints.
- [x] Learner feedback, revision flow, targeted post-completion re-entry, and old-version read-only history.
- [x] Reviewer coaching queue/detail and organization/reviewer authorization boundaries.
- [x] Strict HTTPS Feishu/Lark link validation.
- [x] Advisory-only AI record contract; no model generation write path.
- [x] Migration `0029_treasure_coaching_reviews` and idempotent historical backfill.
- [x] API/Web/OpenAPI and existing targeted/full gates used by PRs #409–#415.
- [x] Candidate package `35843223116`, SHA256SUMS, manifest hash, pinned image digests, exact release tag/policy, and inspect phase.
- [x] Read-only diagnosis of Prepare Run `35843920266`.

## Deferred enhancements

- A permanent China-region image mirror or general artifact distribution platform.
- A general release progress dashboard and recurring background monitor.
- Actual AI-model execution and AI advice generation.
- Broad release-framework refactoring and low-probability automatic recovery machinery.
- GitHub Actions deprecation-warning cleanup unrelated to this release.

## Phase 1 — Unblock immutable image preparation

**Status:** CURRENT; implementation may begin only from this confirmed plan.

**Objective:** Preload only the three pinned candidate images without changing containers, configuration, database, or the current release; then make the original immutable Prepare phase succeed.

**Necessary changes:**

- Replace the untested cache draft with a minimal one-shot preload path.
- Use the already verified package manifest and exact manifest SHA-256 as the source of image references.
- Pull only candidate API, Web, and dbrestore images on the controlled runner; do not package the already-running old images.
- Produce a Docker archive, hash it, transfer it through the existing temporary SSH boundary, load it on the host, and verify exact RepoDigest/platform plus application revision for API/Web.
- Share the existing release concurrency boundary and remote lock. Refuse to run if another release phase is active.
- Add focused tests for manifest binding, archive hash, exact image checks, refusal on an occupied lock, and absence of container/database/release mutations.
- After the preload passes, rerun the original immutable Prepare phase and verify its receipt plus old production health.

**Explicitly out of scope:**

- No product, migration, schema, or business-data changes.
- No process scanning or termination; no concurrent execution beside Prepare.
- No generic OCI parser or reusable mirror platform.
- No candidate image rebuild and no repetition of completed feature gates beyond the repository-required gate for the operational change.
- No Learner/Reviewer pause and no human UAT.

**Acceptance:**

- All three new images pass exact digest/platform checks; API/Web revision equals `9a35f45053e903aa8e4d113aadbf7168d9ae9d0d`.
- Current containers, database, business facts, and release pointer are unchanged by preload.
- Original Prepare returns a successful immutable receipt and the prepared release has correct file permissions.
- Old production remains healthy.

**Stop conditions:**

- Archive hash, digest, platform, revision, candidate, or manifest differs.
- A release lock or another release run is active.
- Transfer stops without bounded progress or produces the same unresolved network failure.
- Prepare fails for a new category or completing the phase would require a product/database change.
- Never retry the same failure without new evidence or a relevant change.

**Dependency:** Existing package Run `35843223116`, manifest hash `4aecaebcbad12bb06b836ad63a115474bb1600e7e2b738f1748398eb2ed66ed0`, and existing production release controls.

**User action:** None during implementation or preload. Do not pause Learners or Reviewers.

## Phase 2 — Backup, migrate, and reversible switch

**Objective:** Prove a recoverable migration, upgrade schema `0028 → 0029`, and switch to the candidate while the old application remains a valid pre-backfill rollback target.

**Necessary execution:** Recheck old production health/current pointer/no parallel release; obtain a fresh user-approved pause window; create and decrypt-verify the encrypted backup; restore it in isolation and compare facts; migrate; prove protected business counts unchanged and new fact tables empty; grant exact runtime permissions; run old-API compatibility probe; switch API/Web; verify internal and public health.

**Explicitly out of scope:** No historical backfill, no human UAT, no bypass of restore/count/compatibility checks.

**Acceptance:** Backup/restore proof passes; revision is `0029`; protected counts are unchanged; new fact tables are empty; old API is schema-compatible; candidate API/Web and public health are correct.

**Stop conditions:** Any backup, restore, count, migration, grant, compatibility, health, identity, or release-pointer mismatch; any unexpected coaching fact before switch. On switch failure, confirm the old version healthy or stop with `ROLLBACK_NOT_CONFIRMED`.

**Dependency:** Phase 1 accepted.

**User action:** Confirm a new write-pause window immediately before this phase; keep Learners and Reviewers paused until explicitly released.

## Phase 3 — Forward-only historical backfill and release closure

**Objective:** Add only the expected coaching Review records for eligible existing treasure submissions and prove all protected facts remain unchanged.

**Necessary execution:** Generate and retain the private plan; report only non-sensitive scope/counts; apply idempotently; verify Review delta equals the plan, remaining is zero, and Evaluation/SubmissionVersion/Enrollment/Outcome deltas are zero; run synthetic authorization and UI smoke checks; retain receipts; release the write pause.

**Explicitly out of scope:** No Day 0 backfill, no formal Evaluation, no cancelled-Enrollment pending work, no old-version rollback after coaching facts exist.

**Acceptance:** Exact expected Review delta, zero remaining candidates, all protected deltas correct, production healthy, Reviewer/Learner synthetic smoke checks pass.

**Stop conditions:** Plan scope includes an ineligible task/enrollment; actual delta differs; any protected fact changes; permissions or health fail. Once coaching facts exist, forward-fix only.

**Dependency:** Phase 2 accepted and pause still active.

**User action:** None beyond maintaining the agreed pause; resume only after explicit release notice.

## Phase 4 — Human UAT

**Objective:** Have the actual Learner and Reviewer validate the production workflow after technical release verification.

**UAT scope:** Treasure submission continues the Journey; Reviewer sees the fixed version under Treasure Coaching; PASS and REVISION_REQUIRED are visible to the Learner without blocking progress; targeted re-entry uses the same Enrollment; a new immutable version preserves old versions and feedback; non-Feishu links are rejected and valid Feishu links pass.

**Explicitly out of scope:** No scripts, migration checks, high-frequency tests, or automated use of Liu Chunjie's account.

**Acceptance:** Refresh-persistent results, correct role boundaries, preserved history, no formal Evaluation pollution, and user-recorded UAT outcome.

**Stop conditions:** Production is not on the candidate, permissions cross organization/reviewer boundaries, history changes, or real behavior differs from synthetic smoke evidence.

**Dependency:** Phase 3 accepted and the user has received an explicit “可以测试” notice.

**User action:** Arrange Liu Chunjie and the assigned Reviewer only after that notice.

## Reporting and anti-loop discipline

- Report only on phase completion, a new blocker, a required plan change, or a user decision.
- Distinguish `feature complete`, `release preparation`, `external wait`, `production change`, and `human UAT` in every status report.
- Give every external wait an object, success condition, failure condition, and time bound; do not expand scope to appear busy.
- Do not repeat package creation, completed gates, tags, policies, diagnostics, or authorizations without evidence that they are stale or invalid.
- Execute one phase at a time. Do not begin the next phase until the current acceptance criteria are satisfied.
