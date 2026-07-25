#!/usr/bin/env bash
set -euo pipefail

ROOT=/srv/journey-next-staging
SECRETS="$PWD/secrets"

fail() {
  printf 'WP08_DEPLOY_ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "deploy.sh must run as root"
[[ "${CANDIDATE_COMMIT:-}" == "14c9ba073c293da1d4c6b615ea1f07c6c50688fa" ]] || fail "unexpected candidate"
[[ "${STAGING_HOST:-}" == "staging-vnext.muchenai.com" ]] || fail "unexpected staging host"

for name in API_IMAGE WEB_IMAGE WORKER_IMAGE; do
  value=${!name:-}
  [[ "$value" == ghcr.io/muchenai2024-creator/muchen-journey-vnext-*"@sha256:"* ]] || fail "$name is not an immutable vNext GHCR digest"
done
[[ "${API_IMAGE#*@}" == "sha256:4f205e46a7d8574a503b40f4fca165d10fff11dc2286c7cde44751e87d32c949" ]] || fail "API digest differs from candidate manifest"
[[ "${WEB_IMAGE#*@}" == "sha256:ce05e4d49f779cb1daa0b81047a416357a6e72bff7fb113742520c12832b8ff6" ]] || fail "Web digest differs from candidate manifest"
[[ "${WORKER_IMAGE#*@}" == "sha256:25451ac5a5ca7ad14ca913f49fdfad30f06624ae65036c351190a973440448cc" ]] || fail "Worker digest differs from candidate manifest"

command -v docker >/dev/null || fail "docker is missing"
docker compose version >/dev/null || fail "docker compose plugin is missing"
for path in compose.yaml compose.migrate.yaml Caddyfile grant_runtime.py; do
  [[ -f "$PWD/$path" && ! -L "$PWD/$path" ]] || fail "$path must be a regular file"
done
for path in api.env migration.env worker.env web.env edge.env; do
  [[ -f "$SECRETS/$path" && ! -L "$SECRETS/$path" ]] || fail "secret file $path is missing"
  [[ "$(stat -c '%a' "$SECRETS/$path")" == "600" ]] || fail "secret file $path must be mode 0600"
done
ca_path="$SECRETS/volcengine-rds-ca.pem"
[[ -f "$ca_path" && ! -L "$ca_path" ]] || fail "RDS CA file is missing"
[[ "$(stat -c '%a' "$ca_path")" == "444" ]] || fail "RDS CA file must be mode 0444"
openssl x509 -in "$ca_path" -noout -checkend 2592000 >/dev/null || fail "RDS CA is invalid or expires within 30 days"

grep -qx 'APP_ENV=staging' "$SECRETS/api.env" || fail "API must run as staging"
grep -qx 'ALLOW_FIXTURE_IDENTITY=false' "$SECRETS/api.env" || fail "fixture identity must be disabled"
grep -qx 'APP_ENV=staging' "$SECRETS/worker.env" || fail "Worker must run as staging"
grep -qx 'NOTIFICATION_ADAPTER=DISABLED' "$SECRETS/worker.env" || fail "WP-08 worker must not use LOCAL_TEST or a real external adapter"
! grep -R -E 'journey\.muchenai\.com|muchen-journey-production|LOCAL_TEST' "$SECRETS"/*.env >/dev/null || fail "legacy or local-only configuration found"

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
    printf 'WP08_ROLLBACK=START previous=%s\n' "$previous" >&2
    (cd "$previous" && docker compose up -d --remove-orphans --wait) || true
  else
    printf 'WP08_ROLLBACK=STOP_FAILED_FIRST_RELEASE\n' >&2
    docker compose down --remove-orphans || true
  fi
  exit "$code"
}
trap rollback ERR

docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api alembic upgrade head
docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api python /tmp/grant_runtime.py
docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api python -m journey_api.seed
docker compose up -d --remove-orphans --wait

api_health=$(docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).read().decode())")
web_release=$(docker compose exec -T web node -e 'process.stdout.write(process.env.APP_RELEASE || "")')
python3 - "$CANDIDATE_COMMIT" "$api_health" "$web_release" <<'PY'
import json
import sys

candidate, raw, web_release = sys.argv[1:]
payload = json.loads(raw)
assert payload["release"] == candidate
assert web_release == candidate
PY

ln -sfn "$PWD" "$ROOT/current"
printf '%s\n' "$CANDIDATE_COMMIT" >"$ROOT/DEPLOYED_CANDIDATE"
chmod 0644 "$ROOT/DEPLOYED_CANDIDATE"

if [[ -n "$previous" && "$previous" != "$PWD" ]]; then
  printf '%s\n' "$previous" >"$ROOT/PREVIOUS_RELEASE"
fi
trap - ERR
printf 'WP08_DEPLOY=PASS candidate=%s\n' "$CANDIDATE_COMMIT"
