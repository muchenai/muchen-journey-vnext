# Canary application-only upgrade and rollback

Scope: current Canary application candidate `29c0473c488dd9f2d35ca40aec32e505169d4a72`
from switch run 35687074463, database `journey_next_canary_20260901_c72fea5`.
The successful application-only package run `35703762542` upgrades this exact deployed
candidate to `0e49004294763adfabae0130b13d4878b964c8c3`.
Never run Greenfield restore/deploy/bootstrap or its edge rollback for this operation.
Only API/Web containers are recreated. Existing database, account IDs, roles, Feishu
bindings, signing secrets, sessions, allowlist, disabled workers/notifications and edge
route are retained. No database or volume deletion, restore, migration, grant or seed.

## Preparation and compatibility gate

1. Review Learner draft/submission rate limits, recoverable cooldowns and the updated
   rollback baseline. Application PR #404 passed its gates and merged.
2. Package an exact new commit with `Canary Application-only Package`; it has no ECS/RDS
   credentials and does not deploy. Require successful machine gates and verify the
   downloaded artifact provenance (repository, workflow, run, candidate, attempt).
3. Compare the artifact checksums against the trusted workflow artifact, not an arbitrary
   file delivered beside the script. Record exact new API/Web digests and candidate.
4. The compatibility checker permits only the reviewed Learner write-limit API/Web
   surfaces and OpenAPI contract to change from the deployed application candidate.
   Models, migrations, signing/session/auth core, dependencies, images' Dockerfiles and
   worker code cannot change. This is not approval for a later arbitrary candidate.
5. Run the runner's `prepare` phase in the ECS root console with manifest path and exact
   SHA256. It snapshots the existing release files, copies only API/Web configuration,
   CA and Compose entrypoints to a new release, changes only image references/release
   markers and verifies the complete rendered Compose configuration. All new and old
   images are pulled and checked before any interruption. Original release stays intact.
6. Rehearse using the exact final images in an isolated environment before switching;
   synthetic drill results alone do not certify the final production images.

## Interruption notice and switch

Before `switch`, tell the operator the expected interruption and recovery budget, confirm
no user is submitting work and ask them to refresh after recovery. Reserve a five-minute
window as a planning budget, not a measured production guarantee. The new container
health wait is 90 seconds (command bound 120 seconds); failed switching can add another
90-second old-container wait plus health probes. Image downloading is outside this window.
Do not claim zero downtime or use the synthetic local ~6-second result as an ECS estimate.

`switch` additionally requires `--acknowledge-interruption`. It rechecks existing files,
current release, old health and cached old/new images, creates an exclusive attempt receipt,
then recreates API/Web with no build/pull/dependencies. It verifies runtime env, release,
image digests, Docker and public readiness before replacing `current` atomically.
Concurrent runner invocations are excluded by a non-blocking Linux file lock.

## Rollback

On switch exception the runner attempts the old API/Web exactly once. It accepts missing
API/Web containers left by failed recreation, but rejects unknown containers/images or
an unrelated current release. It does not touch the database, including business facts
created after the upgrade. Old health must pass before moving `current` back.

- `SWITCH_FAILED_OLD_VERSION_HEALTHY`: failed upgrade; old application restored.
- `SWITCH_FAILED_ROLLBACK_NOT_CONFIRMED`: do not report recovery or repeat blindly.
  Inspect current containers and journal; retain all release directories and images.
- A killed console or ambiguous result requires explicit inspection and, where safe,
  the `rollback` phase with the same manifest/hash and interruption acknowledgement.
- `prepare`/`switch` are not blindly replayable; existing preparation/attempt stops replay.
- Never call `docker compose down`, restore a backup, initialize identities or change
  credentials as part of rollback. Retain both releases for review and later recovery.

## Evidence and UAT after switch

Record candidate/image refs, verified artifact hashes, preparation, switch or rollback
result, actual interruption, and current public readiness. Do not record raw envs,
credentials, cookies, identity link tokens or invitation tokens in public artifacts.

Do not create another invitation or Enrollment for the team lead as part of this repair.
Use only an explicitly identified dedicated synthetic account for production business
smoke; if none is available, report that evidence as pending rather than borrow a real
Learner identity. High-frequency tests remain isolated/local only. The operator can later
ask the Learner to continue regression in her existing new Enrollment. Never manufacture
a human task response, approve on a Reviewer's behalf, reuse an operator link, or mark UAT
complete from container health or synthetic browser tests alone.
