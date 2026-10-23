# Administrator directory and review release

This release carries the locally accepted administrator workspace changes onto
the existing production API and Web images. It preserves the Ops resilience
fixes in `3729336320fcf1ce6bfd3bd8da94dc5af19ecf86`.

Ordinary administrators review their authored tasks; exploration submissions
are shared, including self submissions. Super administrators can review all
tasks. Review leases last 120 seconds and renew while the review is active.
Only the two explicitly approved owners can grant additional super admins.

The shared Feishu directory is persisted in PostgreSQL, replaced atomically,
and refreshed at 03:00 Asia/Shanghai daily or manually. Searches and bulk
previews read this snapshot. Synchronization itself never grants access.
Bulk grants use each root department's scope, domain and certification level;
existing administrators, super administrators and revoked accounts are skipped.

## Release sequence

1. Pass PR and Mainline Candidate Gate checks for the exact release commit.
2. Dispatch `admin-directory-release.yml` with that commit and its successful
   mainline package run. The production environment requires human approval.
3. Validate immutable images and the currently deployed release. Verify the
   two approved owners against live Feishu identities and existing user IDs.
4. Encrypt a database backup, restore it to an isolated database, and rehearse
   migrations 0039 through 0044 while comparing existing business records.
5. Briefly stop API/Web, migrate production, compare business records again,
   grant only the necessary new-table runtime privileges, and activate images.
6. Bootstrap only the two approved owners, retaining existing user IDs and
   assignments. No local database, test account, or bulk grant is imported.
7. Prepare the shared directory and verify administrator profiles, employee
   number search and a read-only bulk preview before reporting completion.

## Failure handling

Before new business writes, failed activation restores the previous API/Web
images. Additive tables remain; cache writes do not prevent application rollback.
New access records or review claims, or any changed existing business record,
block automatic rollback and require a forward fix. Post-activation owner or
directory verification failures stop with an explicit incomplete release;
do not blindly rerun the workflow. The prior release and encrypted backup remain.

Migration 0044 changes the final-outcome authorization trigger while preserving
existing outcomes and evidence checks. It does not rewrite submission history.

## Known pre-migration recovery

Run 39926387464 uploaded and verified the complete f8afcb5 release, staged the
configuration, then stopped during the read-only owner check. It never reached
backup, database migration or service replacement. `admin-directory-resume.yml`
reuses only that prepared candidate and package run 39925261076; it refuses any
state with an existing backup or activation receipt, changed current release,
changed original scripts, changed prepared configuration, or a migrated schema.
The recovery rechecks imported image configs and emits bounded owner diagnostics
without exception messages, secrets or personnel data. Only a transient read-only
directory failure may be retried once; identity mismatches always stop. If checks
pass, the original backup/restore rehearsal and activation sequence still apply.
The workflow retains the same mandatory human production environment approval.
