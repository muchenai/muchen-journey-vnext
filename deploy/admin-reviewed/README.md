# Reviewed administrator update

Publishes the locally accepted review tabs, optional approval feedback, five-character
return validation, and name plus Feishu employee number or verified phone display.
The learner UI, directory rules, task ownership and review claim boundaries stay
at the successful learner release `6fbc42e`.

This update requires schema 0047 before and after deployment; it applies no schema
migration, grants, account reset or data import. The release verifies the baseline
receipt, immutable images and prepared configuration, takes a fresh encrypted
backup and proves restoration before briefly switching API/Web. Fingerprints
include existing notification read receipts and encrypted phone data. If business
writes occur, automatic rollback stops rather than discarding them.

Deployment uses the established production-canary-uat approval gate and pinned
Mainline Candidate Gate package. Runtime credentials and the approved model pair
are preserved. A failed preparation must be diagnosed before any retry.
