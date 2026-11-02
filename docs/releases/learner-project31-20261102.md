# Learner project31 release

Baseline: `b581826481e076fb91eeaec3d5369803e1de4ecd` (administrator departments release).

Publish the accepted local learner experience: project30 task cards and details, project31 publishing-department filters (including the union of all seven delivery lines), real task claiming/drafts/submissions, real medal catalog and redemption history, account switching, personal profile, the optimized standalone world map in all four modules, and scene backgrounds in the three selected module navigation cards.

Promote the real novice workflow out of its local preview switch. Learner identity and the existing server authorization remain required. AI Academy and Delivery Guild pages retain the accepted appearance and unavailable states for unconnected data; no demonstration courses, accounts, balances or completion records are imported.

The API adds the learner medal catalog and publishes the task's immutable publishing department and review method. Existing administrator assets, operations resilience fixes, dependency remediation, session isolation, AI configuration and directory refresh schedule remain unchanged. The schema stays `0051_community_modules`; no database migration, seed, cleanup or account reset is included.

## Release controls

`Learner Project31 Release` consumes only the exact successful Mainline Candidate Gate build, and requires the existing `production-canary-uat` environment approval. It verifies the baseline receipt and image identities, restores an encrypted database backup into an isolated database, verifies business fingerprints, and replaces API/Web with the existing rollback protection. Worker behavior and configuration are preserved.

Before dispatch, run focused learner/API/release regression checks, the frontend suite and production build, then complete PR and mainline CI. After activation, verify the candidate health, learner assets, world-map CSP and images, and unauthenticated learner/staff isolation without creating business records.

Local release validation completed: 31 focused API, permissions, session-isolation and release-control tests; 236 frontend tests; ESLint, TypeScript and the production Next.js build. The production-mode web container also served the world-map HTML and bundled WebP successfully with the intended nonce policy and same-origin framing. All database tests used a disposable database, and no user or production data was changed.
