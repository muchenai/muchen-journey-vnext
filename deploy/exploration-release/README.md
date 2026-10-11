# Exploration release preparation, 2026-10-11

Application candidate: `05e7e0d2ca488bcdbf0fbf8ab964d98ea3efc292`, built and pushed by successful Mainline Candidate Gate run `38117619977`.

The approved read-only inventory (run `38117979961`) found the existing release `9a35f45053e903aa8e4d113aadbf7168d9ae9d0d`, migration `0029_treasure_coaching_reviews`, healthy API/Web, an existing Feishu callback, four bound reviewers and formal exploration journey V3. No production business data has been changed.

`exploration-release-prepare.yml` requires the existing `production-canary-uat` approval and exact main commit. It downloads the exact candidate binding, validates the image digests/SBOMs, copies existing server configuration into a new private release directory and stages immutable images. Existing signing keys, database, account IDs and OAuth credentials remain on the server. No local `.env`, fixtures, sessions or database are transferred.

`prepare.py` reuses the older release's snapshot and image-staging implementation without changing its frozen manifest gates. Its overridden restore method proves the synchronized database snapshot in an isolated scratch PostgreSQL container, encrypts the backup and verifies decryption. It never executes Alembic, grants, seeds, application switching or content publication. An existing backup stops replay and is never automatically removed. Scratch containers are removed only if created by this invocation.

The artifact contains bounded reviewer/content metadata and backup verification receipts, never database dumps, credentials, identity subjects or learner submissions. The temporary runner SSH ingress is removed by the final cleanup step.

## Still required before live activation

- Match the owner's selected default reviewer against active, Feishu-bound production records. Existing enrollment assignments remain unchanged.
- Compare the eight published stages and material URLs with the requested content. Preserve immutable historical task versions and completion records; do not copy test fixture versions into production.
- Prepare and test the exact migration/configuration/switch operation, using migrations 0030 and 0031. Any subsequent production operation requires its own environment approval.
- Define a bounded interruption and recovery path before accepting new learner writes. Keep the encrypted backup and old release. Never automatically restore production data or downgrade after new facts exist.
- Verify learner login, submission visibility in Review and returned feedback; container readiness alone is not end-to-end acceptance.
