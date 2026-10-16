# Phone login release

Baseline verified by read-only production run 38869109007: API fc591682,
Web 7361d0fe, schema 0032, both healthy. This release adds schema 0033–0035,
enables password login, and keeps OTP disabled. Existing Feishu configuration,
reviewer assignments, signing keys and business records are retained.

Run the workflow on main only after the Mainline Candidate Gate succeeds for the
same exact commit. Supply its successful run ID. The package verifies the build
binding, archive hashes, platform and image revision before transfer. The GitHub
production environment requires human approval.

Before maintenance, the runner stages the images, copies existing server-only
configuration, creates an encrypted consistent backup, restores it into a new
isolated container and rehearses the exact migrations. Old services remain live
through this preparation. A pre-existing attempt or backup stops replay.

Allow a five-minute maintenance window for stopping API/Web, migrating, granting
DML on only the three new tables and checking readiness. This is a planning
budget, not a measured availability guarantee. The old API is probed against the
new schema before switching. If the switch fails before new business writes,
the previous application is restored; schemas and production data are never
downgraded or restored automatically. New writes require a forward repair.

The migration fingerprint checks all existing business tables without ignoring
enrollment review mode. New authentication tables must remain empty through the
maintenance check. Readiness confirms deployment health, not a person's actual
Feishu authorization or completed learner acceptance test.

Completion-code claims retain the corporate User, Feishu identity, sessions and
all staff role/assignment IDs. A consumed code binds that account to the original
immutable learning history through learner-only authorization. The phone User
and its sessions/identities are disabled, not the corporate User. Existing target
learning activity blocks silent replacement; one target can claim one history.
Staff endpoints always use the corporate principal. Migrated work cannot become
self-reviewable by acquiring reviewer access on the receiving account.
