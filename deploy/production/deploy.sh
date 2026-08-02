#!/usr/bin/env bash
set -euo pipefail

ROOT=/srv/journey-next-production
SECRETS="$PWD/secrets"

fail() {
  printf 'WP15_PRODUCTION_DEPLOY_ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "deploy.sh must run as root"
[[ "${CANDIDATE_COMMIT:-}" == "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a" ]] || fail "unexpected candidate"
[[ "${PRODUCTION_HOST:-}" == "journey.muchenai.com" ]] || fail "unexpected production host"
[[ "${PRODUCTION_DATABASE:-}" == "journey_next_restore_20260803" ]] || fail "unexpected production database"

for name in API_IMAGE WEB_IMAGE WORKER_IMAGE; do
  value=${!name:-}
  [[ "$value" == ghcr.io/muchenai2024-creator/muchen-journey-vnext-*"@sha256:"* ]] || fail "$name is not immutable"
done
[[ "${API_IMAGE#*@}" == "sha256:553055d921f75bc7f7df0e176d5176f0546ee7f75f37e9757a0be09edf3520ff" ]] || fail "API digest differs"
[[ "${WEB_IMAGE#*@}" == "sha256:401e5158fdcf7be11a3b2539fdbeb7c222ff9813267aa7c3cbcd7a2f9e24f1f5" ]] || fail "Web digest differs"
[[ "${WORKER_IMAGE#*@}" == "sha256:16bf2c7515d68fab164704438b23f691917213c8946a8c3dff8a4116fb3df0c7" ]] || fail "Worker digest differs"

for path in compose.yaml compose.migrate.yaml grant_runtime.py; do
  [[ -f "$PWD/$path" && ! -L "$PWD/$path" ]] || fail "$path must be a regular file"
done
for path in api.env migration.env worker.env web.env; do
  [[ -f "$SECRETS/$path" && ! -L "$SECRETS/$path" ]] || fail "secret file $path is missing"
  [[ "$(stat -c '%a' "$SECRETS/$path")" == "600" ]] || fail "secret file $path must be 0600"
done
ca_path="$SECRETS/volcengine-rds-ca.pem"
[[ -f "$ca_path" && ! -L "$ca_path" && "$(stat -c '%a' "$ca_path")" == "444" ]] || fail "RDS CA is invalid"
openssl x509 -in "$ca_path" -noout -checkend 2592000 >/dev/null || fail "RDS CA expires within 30 days"

grep -qx 'APP_ENV=production' "$SECRETS/api.env" || fail "APP_ENV=production is required"
grep -qx 'APP_ENV=production' "$SECRETS/worker.env" || fail "worker APP_ENV=production is required"
grep -qx 'ALLOWED_HOSTS=journey.muchenai.com,production-api,localhost,127.0.0.1' "$SECRETS/api.env" || fail "allowed hosts differ"
grep -qx 'FEISHU_OAUTH_REDIRECT_URI=https://journey.muchenai.com/auth/feishu/callback' "$SECRETS/api.env" || fail "OAuth callback differs"
grep -qx 'NOTIFICATION_RESULT_URL=https://journey.muchenai.com/app/result' "$SECRETS/worker.env" || fail "canonical result URL differs"
grep -q '/journey_next_restore_20260803?' "$SECRETS/api.env" || fail "API is not bound to the verified restore database"
! grep -q '/journey_next_production?' "$SECRETS"/*.env || fail "production bundle references the preserved failed restore database"
! grep -q '/journey_next_staging?' "$SECRETS"/*.env || fail "production bundle references staging database"
grep -qx 'APP_RELEASE=8f77ceec570e2ec5e9c52861fcdc27748d7bb44a' "$SECRETS/api.env" || fail "API release differs"
grep -qx 'APP_RELEASE=8f77ceec570e2ec5e9c52861fcdc27748d7bb44a' "$SECRETS/worker.env" || fail "Worker release differs"
grep -qx 'APP_RELEASE=8f77ceec570e2ec5e9c52861fcdc27748d7bb44a' "$SECRETS/web.env" || fail "Web release differs"

docker network inspect journey-next-staging_default >/dev/null || fail "shared edge network is missing"
docker compose -f compose.yaml -f compose.migrate.yaml config --quiet
docker compose pull
docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api \
  python -c "from pathlib import Path; Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()"

previous=""
if [[ -L "$ROOT/current" ]]; then
  previous=$(readlink -f "$ROOT/current")
fi

rollback() {
  code=$?
  if [[ -n "$previous" && "$previous" != "$PWD" && -f "$previous/compose.yaml" ]]; then
    printf 'WP15_PRODUCTION_ROLLBACK=START\n' >&2
    (cd "$previous" && set -a && . ./.deployment.env && set +a && docker compose up -d --remove-orphans --wait) || true
    ln -sfn "$previous" "$ROOT/current" || true
  else
    printf 'WP15_PRODUCTION_ROLLBACK=MAINTENANCE_REQUIRED\n' >&2
    docker compose down --remove-orphans || true
  fi
  exit "$code"
}
trap rollback ERR

docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api alembic upgrade head
docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api python /tmp/grant_runtime.py
docker compose up -d --remove-orphans --wait

api_health=$(docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).read().decode())")
web_release=$(docker compose exec -T web node -e 'process.stdout.write(process.env.APP_RELEASE || "")')
python3 - "$CANDIDATE_COMMIT" "$api_health" "$web_release" <<'PY'
import json
import sys
candidate, raw, web_release = sys.argv[1:]
assert json.loads(raw) == {"status": "ok", "release": candidate}
assert web_release == candidate
PY

ln -sfn "$PWD" "$ROOT/current"
printf '%s\n' "$CANDIDATE_COMMIT" >"$ROOT/DEPLOYED_CANDIDATE"
chmod 0644 "$ROOT/DEPLOYED_CANDIDATE"
if [[ -n "$previous" && "$previous" != "$PWD" ]]; then
  printf '%s\n' "$previous" >"$ROOT/PREVIOUS_RELEASE"
fi
trap - ERR
printf 'WP15_PRODUCTION_DEPLOY=PASS candidate=%s database=journey_next_restore_20260803\n' "$CANDIDATE_COMMIT"
