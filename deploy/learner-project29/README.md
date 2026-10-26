# Learner Project29 release

Publishes the locally accepted learner experience and its required profile, phone
encryption, notification read receipts, and bounded AI retry/fallback APIs. The
administrator UI remains at the current production version. No local test data,
document unlocks, fixture identities, credentials or account resets are deployed.

The workflow requires the exact main commit and its successful Mainline Candidate
Gate build, then the existing `production-canary-uat` environment approval. It
verifies the current production release is the successful `f8afcb5` administrator
release and binds previous image IDs to its stored manifest and activation receipt.
It preserves production credentials and config except the release IDs and the
approved AI model pair: `deepseek-v4.1-flash`, `deepseek-v4-pro-0813`.

Before switching, the workflow verifies archive/config hashes, creates an encrypted
database backup and proves a restore into an isolated database. It rehearses
0044 → 0047 there, checking existing business row fingerprints. Migration 0045
retains the admin decision basis; 0046 adds an empty encrypted phone display column;
0047 adds notification read receipts. Existing users and learning records are kept.

Active AI requests block the switch. During brief API/Web maintenance the real
migration is applied and verified before granting the runtime role access to the
new table. On a failure before business changes, the previous application images
and pointer are restored with the compatible additive schema retained. If business
writes are detected, automatic rollback stops for diagnosis. Do not blindly rerun
a failed deployment; staged release and backup paths are intentionally exclusive.

The initial run `40307327520` stopped before production migration: the external
identity fingerprint passed JSONB to `md5` because its cast lacked parentheses.
The corrected expression casts the complete JSONB subtraction to text. PostgreSQL
tests prove the new phone column is ignored while existing field changes are caught.

`learner-project29-resume.yml` is restricted to that exact pre-migration stop and
the already approved application candidate `6fbc42e`. It verifies the original
scripts, prepared manifest and immutable image configurations; it rejects an
activated release, changed schema or completed backup. Original failure evidence
is retained. A new backup, restore and 0044 → 0047 rehearsal must pass before the
existing activation and rollback guards run. No application images are re-uploaded.
