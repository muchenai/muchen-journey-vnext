# WP-31 Canary grant target fix — 2026-09-10

## Evidence and direct cause

Run 34455353284 restored the isolated database successfully, then failed at the
runtime grant entrypoint before persistent API/Web startup. Its log reports
`RuntimeError: wartime grant runner connected to unexpected database` at
`grant_runtime.py:23`. The Canary bundle copied `wartime_grant_runtime.py`, whose
fixed target is the existing production cutover database. The actual connection
was configured for the isolated Canary database. Retargeting credentials or
removing the guard would be the wrong fix.

Deletion/recreation timeline (Asia/Shanghai): user deletion confirmed 16:20;
Run 34455353284 started 16:28:32; database creation 16:30:48–16:30:56; restore
completed 16:52:19; deploy failed 17:00:50. Public readiness at 17:03:15 returned
the old production release. The database was preserved, not deleted by rollback.

## Change

- Add a dedicated Canary grant entrypoint with one fixed database and the existing
  DML/sequence privilege set. Validate `current_database()` before any grant;
  execute within a transaction and dispose the engine on success or error.
- Change only the Canary bundle mapping. Keep the wartime production entrypoint
  and its frozen cutover target unchanged.
- Correct the known Canary service probe: inspect the actual Compose project label
  or either known container-name prefix, not the obsolete name prefix alone.
  Docker errors/timeouts/malformed results return UNKNOWN (exit 2), never absent
  (exit 1). The probe only checks running Docker services; it does not claim to
  inspect SQL connections or all possible external service references.

## Reproduction and regression coverage

The new test loads the entrypoint selected by the actual Workflow `cp` command.
Before the fix it reproduced the same wartime database RuntimeError with a fake
Canary connection. After the fix it accepts only the exact Canary database,
rejects production/staging/other targets before any GRANT, preserves the exact
privilege set, and exercises transaction exit/disposal on failure.

Additional tests cover Compose-label detection, legacy name compatibility,
malformed Docker results and command failures, and the post-grant ordering:
grant → migration/count checks → API/Web startup → current link → edge switch;
then identity initialization → encrypted delivery → final inspection. Existing
identity, binding, phase-evidence and rollback-boundary tests remain applicable.

These unit tests use synthetic connection objects, not production credentials or
cloud database connections. They do not establish successful real deployment.
The 21-minute restore duration is observed but its cause remains unproven; this
patch does not claim to fix that duration or add retries.

## Release boundary

This changes runtime/Workflow behavior: it requires a new application candidate,
package evidence, mechanical rebind, reviewed Ops tag and matching authorization.
It is not an Ops-only behavior fix. Do not rerun the failed Run, reuse its restored
database as an empty target, or treat a successful local test as Canary UAT ready.
Database cleanup is a separate controlled operation after replacement readiness.
