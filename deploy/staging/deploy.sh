#!/usr/bin/env bash
set -euo pipefail

ROOT=/srv/journey-next-staging
SECRETS="$PWD/secrets"

fail() {
  printf 'WP08_DEPLOY_ERROR: %s\n' "$*" >&2
  exit 1
}

pull_with_bounded_retry() {
  local label=$1
  shift
  local attempt status category log_file
  log_file=$(mktemp /tmp/wp08-image-pull.XXXXXX)

  for attempt in 1 2 3; do
    : >"$log_file"
    if timeout --signal=TERM --kill-after=30s 8m "$@" >"$log_file" 2>&1; then
      rm -f "$log_file"
      printf 'WP08_IMAGE_PULL label=%s attempt=%s max_attempts=3 result=PASS\n' \
        "$label" "$attempt"
      return 0
    else
      status=$?
    fi
    category=NON_RETRYABLE
    if [[ "$status" -eq 124 || "$status" -eq 137 ]]; then
      category=COMMAND_TIMEOUT
    elif grep -Eiq \
      'TLS handshake timeout|i/o timeout|connection reset by peer|unexpected EOF|temporary failure|502 Bad Gateway|503 Service Unavailable|429 Too Many Requests' \
      "$log_file"; then
      category=TRANSIENT_NETWORK
    fi

    if [[ "$category" == "NON_RETRYABLE" || "$attempt" -eq 3 ]]; then
      rm -f "$log_file"
      printf 'WP08_IMAGE_PULL label=%s attempt=%s max_attempts=3 category=%s result=FAIL\n' \
        "$label" "$attempt" "$category" >&2
      return "$status"
    fi

    rm -f "$log_file"
    printf 'WP08_IMAGE_PULL label=%s attempt=%s max_attempts=3 category=%s result=RETRY next_in_seconds=%s\n' \
      "$label" "$attempt" "$category" "$((attempt * 5))"
    sleep "$((attempt * 5))"
    log_file=$(mktemp /tmp/wp08-image-pull.XXXXXX)
  done
}

[[ "${EUID}" -eq 0 ]] || fail "deploy.sh must run as root"
[[ "${CANDIDATE_COMMIT:-}" == "3e7624f28fcf8d99fb7bb4e8155708acf75cdd2c" ]] || fail "unexpected candidate"
[[ "${STAGING_HOST:-}" == "staging-vnext.muchenai.com" ]] || fail "unexpected staging host"
[[ "${PRODUCTION_HOST:-}" == "journey.muchenai.com" ]] || fail "unexpected production host"
[[ "${DEPLOY_MODE:-}" == "full" || "${DEPLOY_MODE:-}" == "web-only" || "${DEPLOY_MODE:-}" == "runtime-repair" ]] || fail "unexpected deploy mode"
[[ "${BASELINE_CANDIDATE:-}" == "9e8a8063ebd8fadb2ca3761e867c12b270dcbfb4" ]] || fail "unexpected Web-only baseline"

for name in API_IMAGE WEB_IMAGE WORKER_IMAGE; do
  value=${!name:-}
  [[ "$value" == ghcr.io/muchenai2024-creator/muchen-journey-vnext-*"@sha256:"* ]] || fail "$name is not an immutable vNext GHCR digest"
done
[[ "${WEB_IMAGE#*@}" == "sha256:2d38ae3ceff1503bf97e91c0be8bb2588fc6507a60ae47d8ed6ce4fe5e09e890" ]] || fail "Web digest differs from candidate manifest"
if [[ "$DEPLOY_MODE" == "full" ]]; then
  [[ "${API_IMAGE#*@}" == "sha256:47061e27901abe38945393cd6a03f466fbecaf190154d5c605b65a0a1335e628" ]] || fail "API digest differs from candidate manifest"
  [[ "${WORKER_IMAGE#*@}" == "sha256:bd73dc55d9ed57338e53c1989f61117a9e239520fee333fb805e96d2016a7277" ]] || fail "Worker digest differs from candidate manifest"
else
  [[ "${API_IMAGE#*@}" == "sha256:ceb2d7827d68f0d7132d862196657e0f656ed64239a487e470286ee4ffc4d86d" ]] || fail "API digest differs from the Web-only baseline"
  [[ "${WORKER_IMAGE#*@}" == "sha256:15ab046a369b62a0605ce90b760559bb1d45290f951bd7741ca8ec251e4652da" ]] || fail "Worker digest differs from the Web-only baseline"
fi

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
grep -qx 'NOTIFICATION_RECIPIENTS_ENABLED=true' "$SECRETS/api.env" || fail "staging notification recipients must be enabled"
grep -qx 'DB_POOL_SIZE=20' "$SECRETS/api.env" || fail "API database pool size is not the bounded WP-12B value"
grep -qx 'DB_MAX_OVERFLOW=5' "$SECRETS/api.env" || fail "API database overflow is not the bounded WP-12B value"
grep -qx 'APP_ENV=staging' "$SECRETS/worker.env" || fail "Worker must run as staging"
grep -qx 'DB_POOL_SIZE=2' "$SECRETS/worker.env" || fail "Worker database pool size is not bounded"
grep -qx 'DB_MAX_OVERFLOW=1' "$SECRETS/worker.env" || fail "Worker database overflow is not bounded"
grep -qx 'NOTIFICATION_ADAPTER=FEISHU' "$SECRETS/worker.env" || fail "WP-11 worker must use the dedicated Feishu adapter"
grep -qx 'NOTIFICATION_RESULT_URL=https://staging-vnext.muchenai.com/app/result' "$SECRETS/worker.env" || fail "WP-11 notification result URL is not canonical"
grep -qx 'OBSERVABILITY_SNAPSHOT_SECONDS=60' "$SECRETS/worker.env" || fail "WP-11 observability snapshot cadence is not canonical"
runtime_release="$CANDIDATE_COMMIT"
if [[ "$DEPLOY_MODE" != "full" ]]; then
  runtime_release="$BASELINE_CANDIDATE"
fi
grep -qx "APP_RELEASE=$runtime_release" "$SECRETS/api.env" || fail "API release differs from the selected runtime"
grep -qx "APP_RELEASE=$runtime_release" "$SECRETS/worker.env" || fail "Worker release differs from the selected runtime"
grep -qx "APP_RELEASE=$CANDIDATE_COMMIT" "$SECRETS/web.env" || fail "Web release differs from the candidate"
api_recipient_key=$(sed -n 's/^NOTIFICATION_RECIPIENT_KEY=//p' "$SECRETS/api.env")
worker_recipient_key=$(sed -n 's/^NOTIFICATION_RECIPIENT_KEY=//p' "$SECRETS/worker.env")
[[ -n "$api_recipient_key" && "$api_recipient_key" == "$worker_recipient_key" ]] || fail "API and Worker recipient keys must be identical and non-empty"
unset api_recipient_key worker_recipient_key
! grep -R -E 'journey\.muchenai\.com|muchen-journey-production|LOCAL_TEST' \
  "$SECRETS/api.env" "$SECRETS/migration.env" "$SECRETS/worker.env" "$SECRETS/web.env" \
  >/dev/null || fail "production or local-only configuration found in staging runtime"
grep -qx 'PRODUCTION_HOST=journey.muchenai.com' "$SECRETS/edge.env" || fail "production edge host differs"

docker compose -f compose.yaml -f compose.migrate.yaml config --quiet

verify_web_only_runtime() {
  local release_dir=$1
  local api_runtime worker_runtime
  local compose=(docker compose --project-directory "$release_dir" -f "$release_dir/compose.yaml")
  api_runtime=$("${compose[@]}" exec -T api python -c '
import json
import urllib.request
from sqlalchemy import text
from journey_api.config import get_settings
from journey_api.db import SessionLocal
s = SessionLocal()
revision = s.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
s.close()
settings = get_settings()
health = json.loads(urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3).read())
assert health == {"status": "ok", "release": settings.app_release}
print(json.dumps({"release": settings.app_release, "config_schema_version": settings.config_schema_version, "migration_revision": revision, "status": "READY"}))
')
  worker_runtime=$("${compose[@]}" exec -T worker python -c '
import json
import os
from datetime import UTC, datetime, timedelta
from sqlalchemy import text
from journey_api.db import SessionLocal
s = SessionLocal()
row = s.execute(text("SELECT release,last_seen_at FROM worker_heartbeats WHERE worker_name=\u0027notification-worker\u0027")).one()
s.close()
print(json.dumps({"release": os.environ["APP_RELEASE"], "heartbeat_release": row.release, "stale": row.last_seen_at < datetime.now(UTC) - timedelta(seconds=20)}))
')
  python3 - "$BASELINE_CANDIDATE" "$api_runtime" "$worker_runtime" <<'PY'
import json
import sys

baseline, api_raw, worker_raw = sys.argv[1:]
api = json.loads(api_raw)
worker = json.loads(worker_raw)
assert api == {
    "release": baseline,
    "config_schema_version": 3,
    "migration_revision": "0021_p0_identity_principal",
    "status": "READY",
}
assert worker["release"] == baseline
assert worker["heartbeat_release"] == baseline
assert worker["stale"] is False
PY
}

validate_component_marker_shape() {
  local path=$1
  python3 - "$path" <<'PY'
import json
import re
import sys

components = json.loads(open(sys.argv[1], encoding="utf-8").read())
full_sha = re.compile(r"^[0-9a-f]{40}$")
assert set(components) == {"web", "api", "worker"}
assert all(isinstance(value, str) and full_sha.fullmatch(value) for value in components.values())
PY
}

verify_runtime_repair_prestate() {
  local release_dir=$1
  local api_runtime worker_runtime web_release
  local compose=(docker compose --project-directory "$release_dir" -f "$release_dir/compose.yaml")
  api_runtime=$("${compose[@]}" exec -T api python -c '
import json
import urllib.request
from sqlalchemy import text
from journey_api.config import get_settings
from journey_api.db import SessionLocal
s = SessionLocal()
revision = s.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
s.close()
settings = get_settings()
health = json.loads(urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3).read())
assert health == {"status": "ok", "release": settings.app_release}
print(json.dumps({"release": settings.app_release, "config_schema_version": settings.config_schema_version, "migration_revision": revision, "status": "READY"}))
')
  worker_runtime=$("${compose[@]}" exec -T worker python -c '
import json
import os
from datetime import UTC, datetime, timedelta
from sqlalchemy import text
from journey_api.db import SessionLocal
s = SessionLocal()
row = s.execute(text("SELECT release,last_seen_at FROM worker_heartbeats WHERE worker_name=\u0027notification-worker\u0027")).one()
s.close()
print(json.dumps({"release": os.environ["APP_RELEASE"], "heartbeat_release": row.release, "stale": row.last_seen_at < datetime.now(UTC) - timedelta(seconds=20)}))
')
  web_release=$("${compose[@]}" exec -T web node -e 'process.stdout.write(process.env.APP_RELEASE || "")')
  python3 - "$CANDIDATE_COMMIT" "$BASELINE_CANDIDATE" "$web_release" "$api_runtime" "$worker_runtime" <<'PY'
import json
import sys

candidate, baseline, web_release, api_raw, worker_raw = sys.argv[1:]
old = "172c9f62ffdcd4fce31fb4900fdca46b3405ab89"
api = json.loads(api_raw)
worker = json.loads(worker_raw)
allowed = {candidate, old, baseline}
assert web_release == candidate
assert api["release"] in allowed
assert api["config_schema_version"] == 3
assert api["migration_revision"] in {
    "0013_wp11_notify_observability",
    "0014_wp12_data_lifecycle",
}
assert api["status"] == "READY"
assert worker["release"] in allowed
assert worker["heartbeat_release"] in allowed
assert isinstance(worker["stale"], bool)
PY
}

write_component_markers() {
  local previous=$1
  printf '%s\n' "$previous" >"$ROOT/PREVIOUS_RELEASE"
  printf '%s\n' "$CANDIDATE_COMMIT" >"$ROOT/DEPLOYED_CANDIDATE.tmp"
  printf '%s\n' "$CANDIDATE_COMMIT" >"$ROOT/DEPLOYED_WEB_CANDIDATE.tmp"
  python3 - "$CANDIDATE_COMMIT" "$BASELINE_CANDIDATE" >"$ROOT/DEPLOYED_COMPONENTS.json.tmp" <<'PY'
import json
import sys

web, baseline = sys.argv[1:]
print(json.dumps({"web": web, "api": baseline, "worker": baseline}, sort_keys=True))
PY
  chmod 0644 "$ROOT/DEPLOYED_CANDIDATE.tmp" "$ROOT/DEPLOYED_WEB_CANDIDATE.tmp" "$ROOT/DEPLOYED_COMPONENTS.json.tmp"
  ln -sfn "$PWD" "$ROOT/current"
  mv "$ROOT/DEPLOYED_CANDIDATE.tmp" "$ROOT/DEPLOYED_CANDIDATE"
  mv "$ROOT/DEPLOYED_WEB_CANDIDATE.tmp" "$ROOT/DEPLOYED_WEB_CANDIDATE"
  mv "$ROOT/DEPLOYED_COMPONENTS.json.tmp" "$ROOT/DEPLOYED_COMPONENTS.json"
}

if [[ "$DEPLOY_MODE" == "web-only" ]]; then
  [[ -L "$ROOT/current" ]] || fail "Web-only deploy requires an existing current release"
  previous=$(readlink -f "$ROOT/current")
  [[ -d "$previous" && -f "$previous/compose.yaml" ]] || fail "current release is invalid"
  [[ -f "$ROOT/DEPLOYED_CANDIDATE" ]] || fail "latest deployed candidate marker is missing"
  [[ -f "$ROOT/DEPLOYED_COMPONENTS.json" ]] || fail "deployed component marker is missing"
  validate_component_marker_shape "$ROOT/DEPLOYED_COMPONENTS.json" || \
    fail "deployed component marker shape is invalid"
  previous_candidate_marker=$(cat "$ROOT/DEPLOYED_CANDIDATE")
  verify_web_only_runtime "$previous" || fail "runtime baseline is not healthy and compatible"
  pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"

  rollback_web() {
    local code=${1:-$?}
    trap - ERR HUP INT TERM
    printf 'WP08_WEB_ONLY_ROLLBACK=START previous=%s\n' "$previous" >&2
    ln -sfn "$previous" "$ROOT/current" || true
    printf '%s\n' "$previous_candidate_marker" >"$ROOT/DEPLOYED_CANDIDATE" || true
    rm -f "$ROOT/DEPLOYED_CANDIDATE.tmp" "$ROOT/DEPLOYED_WEB_CANDIDATE.tmp" "$ROOT/DEPLOYED_COMPONENTS.json.tmp"
    (
      cd "$previous"
      set -a
      . ./.deployment.env
      set +a
      timeout --signal=TERM --kill-after=30s 4m docker compose up -d --no-deps --wait --wait-timeout 180 web
    ) || true
    exit "$code"
  }
  trap 'rollback_web $?' ERR
  trap 'rollback_web 129' HUP
  trap 'rollback_web 130' INT
  trap 'rollback_web 143' TERM

  timeout --signal=TERM --kill-after=30s 4m docker compose up -d --no-deps --wait --wait-timeout 180 web
  web_release=$(docker compose exec -T web node -e 'process.stdout.write(process.env.APP_RELEASE || "")')
  if [[ "$web_release" != "$CANDIDATE_COMMIT" ]]; then
    printf 'WP08_DEPLOY_ERROR: Web container release differs from the candidate\n' >&2
    rollback_web 1
  fi
  if ! verify_web_only_runtime "$PWD"; then
    printf 'WP08_DEPLOY_ERROR: runtime baseline changed during Web-only deployment\n' >&2
    rollback_web 1
  fi

  write_component_markers "$previous"
  trap - ERR HUP INT TERM
  printf 'WP08_WEB_ONLY_DEPLOY=PASS web=%s api_worker=%s\n' "$CANDIDATE_COMMIT" "$BASELINE_CANDIDATE"
  exit 0
fi

if [[ "$DEPLOY_MODE" == "runtime-repair" ]]; then
  [[ -L "$ROOT/current" ]] || fail "runtime repair requires an existing current release"
  previous=$(readlink -f "$ROOT/current")
  [[ -d "$previous" && -f "$previous/compose.yaml" ]] || fail "current release is invalid"
  [[ -f "$ROOT/DEPLOYED_CANDIDATE" ]] || fail "deployed candidate marker is missing"
  previous_candidate_marker=$(cat "$ROOT/DEPLOYED_CANDIDATE")
  [[ "$previous_candidate_marker" == "$BASELINE_CANDIDATE" || "$previous_candidate_marker" == "$CANDIDATE_COMMIT" ]] || fail "deployed marker is outside the reviewed repair set"
  api_container=$(docker compose --project-directory "$previous" -f "$previous/compose.yaml" ps -q api)
  worker_container=$(docker compose --project-directory "$previous" -f "$previous/compose.yaml" ps -q worker)
  [[ -n "$api_container" && -n "$worker_container" ]] || fail "API or Worker container is missing"
  backend_previous=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$api_container")
  worker_previous=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$worker_container")
  [[ "$backend_previous" == "$worker_previous" ]] || fail "API and Worker do not share one rollback release"
  [[ "$backend_previous" == "$ROOT"/releases/* && -f "$backend_previous/compose.yaml" && -f "$backend_previous/.deployment.env" ]] || fail "backend rollback release is outside the staging root"
  verify_runtime_repair_prestate "$previous" || fail "runtime repair prestate is not reviewed"
  pull_with_bounded_retry runtime-api docker pull "$API_IMAGE"
  pull_with_bounded_retry runtime-worker docker pull "$WORKER_IMAGE"

  rollback_runtime() {
    local code=${1:-$?}
    trap - ERR HUP INT TERM
    printf 'WP08_RUNTIME_REPAIR_ROLLBACK=START backend=%s\n' "$backend_previous" >&2
    ln -sfn "$previous" "$ROOT/current" || true
    printf '%s\n' "$previous_candidate_marker" >"$ROOT/DEPLOYED_CANDIDATE" || true
    rm -f "$ROOT/DEPLOYED_CANDIDATE.tmp" "$ROOT/DEPLOYED_WEB_CANDIDATE.tmp" "$ROOT/DEPLOYED_COMPONENTS.json.tmp"
    (
      cd "$backend_previous"
      set -a
      . ./.deployment.env
      set +a
      timeout --signal=TERM --kill-after=30s 4m docker compose up -d --no-deps --wait --wait-timeout 180 api
      timeout --signal=TERM --kill-after=30s 4m docker compose up -d --no-deps --wait --wait-timeout 180 worker
    ) || true
    exit "$code"
  }
  trap 'rollback_runtime $?' ERR
  trap 'rollback_runtime 129' HUP
  trap 'rollback_runtime 130' INT
  trap 'rollback_runtime 143' TERM

  timeout --signal=TERM --kill-after=30s 5m docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api alembic upgrade 0014_wp12_data_lifecycle
  timeout --signal=TERM --kill-after=30s 2m docker compose -f compose.yaml -f compose.migrate.yaml run --rm --no-deps api python /tmp/grant_runtime.py
  timeout --signal=TERM --kill-after=30s 4m docker compose up -d --no-deps --wait --wait-timeout 180 api
  timeout --signal=TERM --kill-after=30s 4m docker compose up -d --no-deps --wait --wait-timeout 180 worker
  verify_web_only_runtime "$PWD" || rollback_runtime 1
  web_release=$(docker compose exec -T web node -e 'process.stdout.write(process.env.APP_RELEASE || "")')
  [[ "$web_release" == "$CANDIDATE_COMMIT" ]] || rollback_runtime 1
  write_component_markers "$previous"
  trap - ERR HUP INT TERM
  printf 'WP08_RUNTIME_REPAIR=PASS web=%s api_worker=%s migration=0014_wp12_data_lifecycle\n' "$CANDIDATE_COMMIT" "$BASELINE_CANDIDATE"
  exit 0
fi

pull_with_bounded_retry full-api docker pull "$API_IMAGE"
pull_with_bounded_retry full-web docker pull "$WEB_IMAGE"
pull_with_bounded_retry full-worker docker pull "$WORKER_IMAGE"
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
