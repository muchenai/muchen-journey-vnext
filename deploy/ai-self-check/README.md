# AI self-check release

Baseline: successful production read-only preflight 39373329816, API/Web
106a599b1e7d80d51336d93aa28d980939f4e8f0, schema 0035. The release adds
0036/0037 and updates only Journey API/Web. No local account, task, history or
database reset is transferred.

The workflow runs on main with an exact successful Mainline Candidate Gate
build. The existing production-canary-uat environment requires human approval.
Production AI_API_KEY and AI_FEISHU_APP_SECRET are GitHub encrypted environment
secrets. They travel over SSH stdin, never inside the image or release artifact.
The server writes them to private files under the new release's root-only
secrets directory, mode 0600 and owned by API UID 10001. Only the API receives
read-only file mounts. Environment variables carry file paths, not values.
Root/Docker administrators can still access runtime secrets; filesystem
permissions and Compose mounts do not provide encryption at rest.

Before maintenance, verify all 13 reference documents and a synthetic model
connectivity request (no learner data or comments), create and decrypt-verify an
encrypted database backup, restore it in isolation, then rehearse 0035 -> 0037.
The migration fingerprints all existing business tables, including login tables.
Only the new ai_self_checks table receives runtime DML grants.

During the short maintenance window, migrate, verify unchanged business data,
probe the old API against the new schema, and switch API/Web. A failure permits
application rollback only while the fingerprint proves no new business writes.
Never downgrade or restore the production database automatically.

Local self-check data remain local. Production learner and Review histories
start accumulating from real production self-checks.

On 2026-10-20 the owner explicitly renewed only the dev-only
GHSA-vfj7-8cjw-p6xm exception through 2026-10-27. All other advisories, runtime
reachability and expiry remain blocking. The release also scans the actual
loaded Web image and stops before staging if any braces package is present.
