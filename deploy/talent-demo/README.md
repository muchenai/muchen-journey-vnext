# Talent Demo deployment via the Journey host

User-authorized scope: deploy the independent synthetic Talent demo at talent.muchenai.com on the existing Journey server. This does not authorize a Journey release, database migration, real personnel import or changes to existing Journey role assignments.

The workflow is manually dispatched on protected main with its exact commit. It uses the existing staging environment SSH key and existing exact-runner security-group helper. It shares Journey's host deployment concurrency group. Ingress cleanup runs even when inventory fails. Private keys stay on the ephemeral runner and are never exported as artifacts.

## Stage 1: inspect

Dispatch `Talent Demo Deployment` with `phase=inspect` and `expected_commit=<full main SHA>`.
This reads architecture, resources, listeners, running container names/networks/mounts, Caddy version and selected routing directives, Talent install presence and Journey public readiness. It does not read application records, container environments, database contents or private credentials. The temporary runner /32 TCP 22 rule is the only remote mutation and is revoked and verified before completion.

The first connection follows the existing deployment's accept-new host-key policy on a dedicated ephemeral known_hosts file. It does not disable host verification. Subsequent connections in a run must use that same file.

Inventory must be reviewed before adding the separate install, migration, route and acceptance stages. A failed stage is reconciled before retrying. Do not invoke an existing Journey release workflow to deploy Talent. No Talent installation or DNS changes are performed by this initial inspection stage.

The Journey repository is public. Host and security-group identifiers are environment variables `TALENT_HOST` and `TALENT_SECURITY_GROUP`. Inventory stdout/stderr is AES-256-GCM sealed with a dedicated `TALENT_TRANSPORT_KEY` environment secret before upload; only the owner-held local key can decode downloaded evidence. That key is independent of SSH credentials. The workflow must never upload the plaintext inventory or credentials. The public artifact contains only nonce, authentication tag and ciphertext and expires after seven days.
