# Exact-package preparation transport (no application switch)

This operations change leaves the packaged application at commit
`3fa84fdfe0d0e38fbab0b649e6a78f49713be10d`, package run `34589305423` attempt 1.
It does not rebuild images, rebind the old Greenfield authorization, restore a database,
initialize identities, change Feishu settings, start workers or switch application containers.

## Authorization boundary

The current `production-canary-uat` Environment allows only specifically authorized old
Greenfield tags. This workflow cannot run with that Environment until an owner explicitly
authorizes a NEW exact operations tag `canary-app-prepare-<full-reviewed-commit-sha>`.
Do not move an existing allowed tag, add a wildcard, remove Environment restrictions,
reuse old execution evidence, or call the old restore/deploy job to obtain credentials.
Adding that single tag's Environment policy and any required protection is a separate
owner-approved action, not performed by this PR. PR checks/merge alone do not authorize it.

## Bounded effects after authorization

- Read the existing Terraform state for ECS coordinates; no plan/apply and no database
  password or Feishu secret is provided to this job.
- Temporarily permit only the executing runner's public IPv4 `/32` on SSH port 22.
  Existing identical rules cause a stop; the runner closes its own rule in `always()`.
- Reuse the existing deployment SSH key solely inside the protected GitHub job. Its
  host-key behavior follows the existing deployment's fresh known-hosts/accept-new
  setup (TOFU); this is not a claim of an independently pinned host fingerprint.
- Copy the original package files without rewriting JSON. Verify provenance, exact
  candidate, successful run/attempt, and independently pinned file SHA256 values.
- Authenticate GHCR using this job's short-lived, packages-read token through stdin.
  Use a new private Docker config, never overwrite the server's existing Docker login.
- Run only the packaged runner's `prepare()` under the existing lock. A command gate
  rejects container exec/restart/recreate/down operations. Old/new images can be pulled;
  release configuration may be copied; current containers and current symlink are retained.
- Log only fixed step labels/error categories; never print raw Docker inspect/config
  output, uncontrolled stderr, credential files, or token values.
- Delete the temporary Docker login config in `finally`; close temporary SSH access
  in the workflow's `always` cleanup. Abrupt runner/host loss may prevent cleanup:
  inspect and remove the exact run's temporary rule/config before continuing, and do
  not claim cleanup succeeded unless evidenced. The GITHUB_TOKEN independently expires.

Preparation remains non-replayable if a release directory already exists. Inspect partial
state instead of deleting directories or blindly retrying. Final-image isolated rehearsal
and an explicit interruption notice are still required before any later switch; this
workflow contains no switch or rollback option.
