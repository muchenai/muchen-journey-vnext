# Administrator departments and access release

Baseline: `18ce021848fce239c27d22c77bff3ed0801d7b30` (reward types release).

This release carries the locally accepted administrator changes:

- Tasks select one of 19 publishing departments. Saving, publication approval, immutable published content, library filtering and previews retain this metadata independently of reward types and legacy task domains.
- Member certification and the member list display the configured department. Department edits are a separate operation from level changes and super-administrator demotion.
- Administrators with explicit super-administrator grant authority can demote or revoke nonprotected super-administrators. Self-management and protected grant owners remain blocked. Demotion and revocation invalidate affected staff sessions and preserve learner sessions and history.

Learner pages, assets, learner APIs, AI configuration, background directory cadence and database migrations remain at the baseline. Historical tasks without a publishing department remain readable; their next publication requires selecting one.

## Release controls

The `Administrator Departments and Access Release` workflow requires the exact successful Mainline Candidate Gate build and the existing `production-canary-uat` approval. Activation verifies the prior release receipt and immutable images, validates an encrypted backup by restoring an isolated copy, compares business-table fingerprints, and switches API/Web with rollback to the baseline if activation fails before new business writes.

The schema remains `0051_community_modules`. No seed, account cleanup, permission backfill or department backfill runs on production.

Local checks: 220 frontend tests and 60 focused backend/release tests passed. Complete PR and mainline checks must pass before dispatch. After deployment, verify public readiness, changed administrator assets and isolation between staff and learner sessions.

## Build dependency remediation

The new npm advisory GHSA-g3hv-75wg-m249 blocked the existing CI dependency gate. All minimatch copies are pinned to patched 11.0.3 (development only). A lint-only preload exposes the legacy callable CommonJS API to ESLint 9/plugins using the patched implementation; named exports remain available. Regression checks exercise both import styles and prove ESLint still reports rule violations. No advisory waiver or runtime dependency change is introduced.
