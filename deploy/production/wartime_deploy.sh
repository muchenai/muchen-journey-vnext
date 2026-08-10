#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WP15_WARTIME_DEPLOY_ERROR: %s\n' "$*" >&2
  exit 1
}

root=/srv/journey-next-production
candidate=ff53052847a268d025bceb93c3eab37986d50219
migration=0019_wp30_invitation_control
database=journey_next_cutover_20260810
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${CANDIDATE_COMMIT:-}" == "$candidate" ]] || fail "unexpected candidate"
[[ "${PRODUCTION_HOST:-}" == "journey.muchenai.com" ]] || fail "unexpected production host"
[[ "${PRODUCTION_DATABASE:-}" == "$database" ]] || fail "unexpected production database"
[[ "${BACKUP_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "backup run identifier is invalid"
[[ "${WP15_BACKUP_KEY:-}" && ${#WP15_BACKUP_KEY} -ge 32 ]] || fail "backup key is missing"

[[ "${API_IMAGE:-}" == 'ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@sha256:2a053bad89bea8c06daba6e929af49a4804cc06a2321e49e93858f1f4fda6a6c' ]] || fail "API digest differs"
[[ "${WEB_IMAGE:-}" == 'ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:a3335542f74d09f4bc394119cee81ba7b866edc6ef041f3f4444949d271e2aee' ]] || fail "Web digest differs"
[[ "${WORKER_IMAGE:-}" == 'ghcr.io/muchenai2024-creator/muchen-journey-vnext-worker@sha256:2ef3cd1b05c545810929a3136ac8259042f6b6c586ccb8c59af90c579bfd9f38' ]] || fail "Worker digest differs"

for path in compose.yaml compose.migrate.yaml grant_runtime.py wartime_rollback.sh db_facts.py; do
  [[ -f "$PWD/$path" && ! -L "$PWD/$path" ]] || fail "$path must be a regular file"
done
for path in api.env migration.env worker.env web.env backup.env target-facts.env; do
  [[ -f "$PWD/secrets/$path" && ! -L "$PWD/secrets/$path" ]] || fail "secret file $path is missing"
  [[ "$(stat -c '%a' "$PWD/secrets/$path")" == "600" ]] || fail "secret file $path must be 0600"
done
ca_path="$PWD/secrets/volcengine-rds-ca.pem"
[[ -f "$ca_path" && ! -L "$ca_path" && "$(stat -c '%a' "$ca_path")" == "444" ]] || fail "RDS CA is invalid"
openssl x509 -in "$ca_path" -noout -checkend 2592000 >/dev/null || fail "RDS CA expires within 30 days"

grep -qx 'APP_ENV=production' secrets/api.env || fail "API environment differs"
grep -qx 'APP_ENV=production' secrets/worker.env || fail "Worker environment differs"
grep -qx 'ALLOWED_HOSTS=journey.muchenai.com,production-api,localhost,127.0.0.1' secrets/api.env || fail "allowed hosts differ"
grep -qx 'FEISHU_OAUTH_REDIRECT_URI=https://journey.muchenai.com/auth/feishu/callback' secrets/api.env || fail "OAuth callback differs"
grep -qx 'NOTIFICATION_RESULT_URL=https://journey.muchenai.com/app/result' secrets/worker.env || fail "canonical result URL differs"
grep -q "/$database?" secrets/api.env || fail "API is not bound to the wartime database"
runtime_envs=(secrets/api.env secrets/migration.env secrets/worker.env secrets/web.env)
! grep -q '/journey_next_staging?' "${runtime_envs[@]}" || fail "runtime bundle references staging database"
! grep -q '/journey_next_production?' "${runtime_envs[@]}" || fail "runtime bundle references preserved failed database"
! grep -q '/journey_next_restore_20260803?' "${runtime_envs[@]}" || fail "runtime bundle references rollback database"
for path in api.env worker.env web.env; do
  grep -qx "APP_RELEASE=$candidate" "secrets/$path" || fail "$path release differs"
done

backup_root="$root/backups/$BACKUP_RUN_ID"
manifest="$backup_root/backup-manifest.json"
archived_facts="$backup_root/target-facts.json"
[[ -f "$manifest" && ! -L "$manifest" && -f "$archived_facts" && ! -L "$archived_facts" ]] || \
  fail "reviewed backup proof is missing"
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" python3 - "$manifest" "$BACKUP_RUN_ID" "$candidate" "$migration" <<'PY'
import hashlib
import hmac
import json
import os
import sys

path, run_id, candidate, migration = sys.argv[1:]
value = json.load(open(path))
signature = value.pop("manifest_hmac_sha256", "")
canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
expected = hmac.new(os.environ["WP15_BACKUP_KEY"].encode(), canonical, hashlib.sha256).hexdigest()
assert hmac.compare_digest(signature, expected)
assert value["run_id"] == run_id
assert value["candidate_sha"] == candidate
assert value["migration"] == migration
assert value["isolated_restore_database"] == "journey_next_cutover_20260810"
assert value["backup"] == value["restore"] == "PASS"
assert value["encrypted_artifact_decrypt_verified"] is True
assert value["active_notification_recipients"] == 0
assert value["source_modified"] is False
PY

current_facts=$(mktemp "$PWD/.wp15-current-target-facts.XXXXXX")
cleanup_current_facts() { rm -f -- "$current_facts"; }
trap cleanup_current_facts EXIT
docker run --rm --network host --env-file secrets/target-facts.env \
  -e PGOPTIONS=-c\ default_transaction_read_only=on -e REQUIRE_READ_ONLY=true \
  -v "$ca_path:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$PWD/db_facts.py:/tmp/db_facts.py:ro" \
  "$API_IMAGE" python /tmp/db_facts.py >"$current_facts"
cmp -s "$archived_facts" "$current_facts" || fail "restored target changed after backup proof"
python3 - "$current_facts" "$migration" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1]))
assert value["migration"] == sys.argv[2]
assert value["active_notification_recipients"] == 0
PY

docker network inspect journey-next-staging_default >/dev/null || fail "shared edge network is missing"
docker compose -f compose.yaml -f compose.migrate.yaml config --quiet
docker compose pull
docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api \
  python -c "from pathlib import Path; Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()"

[[ -L "$root/current" ]] || fail "current rollback release is missing"
previous=$(readlink -f "$root/current")
[[ "$previous" =~ ^/srv/journey-next-production/releases/[0-9a-f]{40}-[1-9][0-9]*$ ]] || \
  fail "current rollback release path is invalid"
printf '%s\n' "$previous" >"$root/PREVIOUS_RELEASE"
chmod 0600 "$root/PREVIOUS_RELEASE"

rollback() {
  code=$?
  trap - ERR
  printf 'WP15_WARTIME_DEPLOY_ROLLBACK=START\n' >&2
  if "$PWD/wartime_rollback.sh"; then
    printf 'WP15_WARTIME_DEPLOY_ROLLBACK=PASS\n' >&2
  else
    printf 'WP15_WARTIME_DEPLOY_ROLLBACK=FAILED maintenance_required=true\n' >&2
  fi
  exit "$code"
}
trap rollback ERR

docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api alembic upgrade head
docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api \
  python /tmp/grant_runtime.py
docker compose up -d --remove-orphans --wait

api_health=$(docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).read().decode())")
web_release=$(docker compose exec -T web node -e 'process.stdout.write(process.env.APP_RELEASE || "")')
worker_release=$(docker compose exec -T worker printenv APP_RELEASE)
python3 - "$candidate" "$api_health" "$web_release" "$worker_release" <<'PY'
import json
import sys

candidate, raw, web_release, worker_release = sys.argv[1:]
assert json.loads(raw) == {"status": "ok", "release": candidate}
assert web_release == candidate
assert worker_release == candidate
PY

ln -sfn "$PWD" "$root/current"
printf '%s\n' "$candidate" >"$root/DEPLOYED_CANDIDATE"
printf '%s\n' "$candidate" >"$root/DEPLOYED_WEB_CANDIDATE"
chmod 0644 "$root/DEPLOYED_CANDIDATE" "$root/DEPLOYED_WEB_CANDIDATE"
trap - ERR
cleanup_current_facts
trap - EXIT
printf 'WP15_WARTIME_DEPLOY=PASS candidate=%s database=%s migration=%s notifications=0\n' \
  "$candidate" "$database" "$migration"
