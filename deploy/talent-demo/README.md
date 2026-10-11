# Talent demo deployment

Deploy the independent synthetic demo through protected main and the existing production-canary-uat reviewer gate. This is not a Journey release. Existing Journey containers, data, permissions and release remain unchanged; adding Talent routing requires a brief restart of the shared Caddy 2.10.2 edge because its admin API is disabled.

Manual phases (each requires exact workflow commit):
- `inspect`: read bounded host inventory.
- `install`: transfer → prepare → migrate → start, as separate Actions steps. Does not change DNS or proxy.
- `resume-install`: after reviewing an installation failure, continue prepare → migrate → start without retransferring the application or rotating accounts. If Node is absent, the runner downloads the same official pinned archive, verifies SHA-256 and transfers it to the private stage; the host verifies it again. SSH errors do not trigger a missing-runtime fallback.
- `transfer`, `prepare`, `migrate`, `start`: resume a reconciled stage independently. Migration checks applied SQL history and backs up an existing Talent database first. Never blindly replay an entire failed workflow.
- `publish`: route → private health → external acceptance. DNS must first point exclusively to the inspected host.
- `route`, `verify`: independent proxy or acceptance steps.

The manifest pins the exact Talent source revision and archive SHA-256. The PUBLIC Journey repo contains only the AES-256-GCM encrypted application payload, deployment tools, manifest and service unit. TALENT_TRANSPORT_KEY seals payload/evidence; TALENT_USERS_JSON holds five scrypt records; TALENT_SMOKE_ACCOUNTS holds two trial credentials for acceptance. These are new Talent-only environment secrets. Existing SSH/cloud keys are used only on the ephemeral runner, never exported. Host/SG references are direct environment secrets. Sensitive command output is encrypted before artifact upload (7-day retention). Temporary exact-runner /32 SSH ingress is closed and verified in an always step.

Runtime: checksum-pinned official Node 24, unprivileged systemd service, private Docker bridge gateway bind on 3187, independent SQLite state and accounts. No public/wildcard runtime bind. The Caddy candidate is validated before applying; existing config hash and Journey release are drift guards. Proxy writes preserve the bind-mounted inode. Failed Journey readiness triggers original-config restoration and a second readiness check. TLS failure alone leaves Journey healthy and is investigated before retrying verification. Database downgrade is never automatic.

The temporary known_hosts uses the established accept-new policy; later connections reuse it. Stage scripts assert the expected host, release and paths. A partial preparation is stopped for explicit reconciliation. Remove only Talent paths/service/route if rolling back the initial install, retaining database/history for diagnosis. Future Journey proxy replacement must preserve this additional virtual host; it is not added to Journey's application release pipeline.

Validation: `python3 deploy/talent-demo/test_remote.py`, actionlint, shell/Node syntax; Talent repository runs its own domain/SQLite/auth tests and both builds. External acceptance verifies TLS, exact revision, anonymous rejection, authenticated UI/assets/workspace, origin rejection and Journey readiness. This does not establish production readiness or human trial outcomes.
