# Treasure Coaching Production Delivery Plan

> Confirmed by the user on 2026-09-23. This is the authoritative remaining-work plan. Execute one phase at a time. Do not expand scope merely because an external task is waiting.

**Goal:** Safely deliver the already-completed four-treasure non-blocking coaching feature, preserve identity and immutable history, backfill only the intended latest treasure submissions, and hand the verified production release to human UAT.

**Current status:** Feature development and the immutable application package are complete. Production remains on `b8a5dd580eaec72945cbe4f0e37c1152ee4645a1`. Candidate `9a35f45053e903aa8e4d113aadbf7168d9ae9d0d` is blocked in release preparation because the production host could not download the pinned dbrestore image within the existing 1800-second per-image timeout. No schema migration, switch, or backfill has run.

**2026-09-23 Phase 1 amendment:** The first immutable-cache run (`35857068059`) exported all three exact images but its uncompressed `docker save` archive did not finish the GitHub Runner-to-Beijing SCP transfer before the 65-minute job boundary. The import never started, no phase receipt was produced, and the temporary SSH rule was closed successfully. With user approval, Phase 1 now compresses the archive before transfer, records raw/compressed byte counts and SHA-256, bounds the individual SCP operation to 50 minutes, verifies the complete gzip and SHA-256 before import, and otherwise preserves the same fail-closed boundaries. This is a transport correction only; it does not relax digest, revision, base-release, lock, database, container, or history protections.

**2026-09-23 Phase 1 network amendment:** Attempt 2 of Run `35866415282` reduced the archive to `254355894` bytes, but the single SCP connection dropped after about ten minutes with `server not responding`. Import never started and SSH ingress closed successfully. With user approval, the same compressed archive is now split into fixed 16 MiB chunks. Each chunk has an exact size and SHA-256, is transferred to a temporary name with at most three bounded attempts, and is atomically accepted only after remote verification. The complete archive is reconstructed and checked against its original SHA-256 and gzip stream before the existing image digest/revision/base-release checks run. The overall job and transfer deadline remain bounded; this does not add a generic transfer service or relax any production boundary.

**2026-09-23 Phase 1 resume amendment:** Run `35877827757` proved that even the first 16 MiB chunk could outlive three five-minute SCP attempts (`124`, `124`, `137`). Because SCP restarted the same partial file on every attempt, retries discarded prior progress; image import never started, the temporary SSH rule closed successfully, and public health remained on `b8a5dd580eaec72945cbe4f0e37c1152ee4645a1`. With user approval, the bounded chunk loop now uses OpenSSH SFTP `reput` to resume the run-scoped partial file. Before every attempt it rejects symlinks, non-numeric or oversized partials; a complete partial is accepted only after exact SHA-256 verification and atomic rename. The existing three-attempt, 300-second-per-attempt, 3000-second-overall deadlines and all image, release, database, container, and history protections remain unchanged.

Run `35885196380` then exposed a bounded implementation error before any image bytes were uploaded: SFTP `reput` requires the remote partial to exist. The corrected loop uses `put` only when the verified offset is zero and `reput` only when a non-empty partial exists. The run again stopped before import, closed temporary SSH ingress, and left public production healthy on the base release.

Run `35886588963` proved that the corrected resume path preserves progress (`0` to `4439040` to `9661440` bytes), but also proved that serial transfer cannot meet the release budget: one connection moved only about 4.4–5.2 MB per five-minute attempt, so the complete 254 MB archive would require roughly 4–5 hours before import. The run stopped on the first chunk, closed temporary SSH ingress, and left public production healthy on the base release. Further serial retries or longer jobs are prohibited. Phase 1 is paused at a transport decision: the minimal proposed path is bounded parallel transfer of the existing independently hashed chunks, retaining resume, exact verification, the 3000-second overall deadline, and all production non-mutation guarantees.

The user approved the bounded parallel path on 2026-09-24. The existing 16 independently hashed chunks are transferred in batches of at most eight concurrent SSH/SFTP connections. Each chunk retains zero-offset `put`, non-zero-offset `reput`, at most four five-minute attempts, exact size/SHA-256 verification, and atomic acceptance. A shared 3000-second deadline remains authoritative; any failed chunk prevents archive assembly and image import. This introduces no storage service and does not change the candidate package or any production application/database state.

Run `35893852269` validated the transport capacity but exposed an implementation defect: the first eight chunks all passed in about ten minutes, while background SSH checks consumed the process-substitution input that was feeding the foreground manifest loop, so chunks 8–15 were never scheduled. The importer correctly stopped with `CHUNKS_DIRECTORY_CONTENTS` before archive assembly or Docker load; SSH ingress closed and production remained healthy on the base release. The bounded fix materializes and count-checks all manifest rows before starting workers and redirects every background SSH check from `/dev/null`, while leaving parallelism, retry limits, deadline, hashes, and non-mutation boundaries unchanged.

Run `35896309692` scheduled and verified all 16 chunks in about ten minutes, resolving the transfer blocker. Import then stopped with the generic `IMAGE_CACHE_COMMAND_FAILED` category after archive assembly. Because the existing wrapper suppresses the failing command identity and stderr, retrying the load would be blind. A read-only `cache-diagnose` phase therefore validates the retained archive SHA/gzip stream and reports only whether the original digest references and deterministic cache tags are present with the expected platform/revision. It performs no Docker load, container operation, database access, release-pointer change, or cleanup.

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
