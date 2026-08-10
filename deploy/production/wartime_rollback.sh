#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WP15_WARTIME_ROLLBACK_ERROR: %s\n' "$*" >&2
  exit 1
}

root=/srv/journey-next-production
baseline=8f77ceec570e2ec5e9c52861fcdc27748d7bb44a
web_baseline=8e56e759152efcbf17f4373f2132e02a8762af81
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ -f "$root/PREVIOUS_RELEASE" && ! -L "$root/PREVIOUS_RELEASE" ]] || \
  fail "previous release marker is missing"
previous=$(cat "$root/PREVIOUS_RELEASE")
[[ "$previous" =~ ^/srv/journey-next-production/releases/[0-9a-f]{40}-[1-9][0-9]*$ ]] || \
  fail "previous release path is invalid"
[[ -d "$previous" && ! -L "$previous" ]] || fail "previous release directory is invalid"
cd "$previous"

for path in compose.yaml .deployment.env secrets/api.env secrets/worker.env secrets/web.env; do
  [[ -f "$path" && ! -L "$path" ]] || fail "rollback input is missing: $path"
done
grep -qx "CANDIDATE_COMMIT=$baseline" .deployment.env || fail "rollback candidate differs"
grep -qx 'PRODUCTION_DATABASE=journey_next_restore_20260803' .deployment.env || \
  fail "rollback database differs"
grep -qx 'API_IMAGE=ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@sha256:553055d921f75bc7f7df0e176d5176f0546ee7f75f37e9757a0be09edf3520ff' .deployment.env || fail "rollback API image differs"
grep -qx 'WEB_IMAGE=ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:c86b4a443ecdc9160c5cb59b742c5c7882ea46aaf401e0a487d3bdad11d86d6f' .deployment.env || fail "rollback Web image differs"
grep -qx 'WORKER_IMAGE=ghcr.io/muchenai2024-creator/muchen-journey-vnext-worker@sha256:16bf2c7515d68fab164704438b23f691917213c8946a8c3dff8a4116fb3df0c7' .deployment.env || fail "rollback Worker image differs"
grep -qx "APP_RELEASE=$baseline" secrets/api.env || fail "rollback API release differs"
grep -qx "APP_RELEASE=$baseline" secrets/worker.env || fail "rollback Worker release differs"
grep -qx "APP_RELEASE=$web_baseline" secrets/web.env || fail "rollback Web release differs"

set -a
. ./.deployment.env
set +a
docker compose config --quiet
docker compose up -d --remove-orphans --wait

api_release=$(docker compose exec -T api printenv APP_RELEASE)
worker_release=$(docker compose exec -T worker printenv APP_RELEASE)
web_release=$(docker compose exec -T web printenv APP_RELEASE)
[[ "$api_release" == "$baseline" ]] || fail "rollback API did not converge"
[[ "$worker_release" == "$baseline" ]] || fail "rollback Worker did not converge"
[[ "$web_release" == "$web_baseline" ]] || fail "rollback Web did not converge"
ready=$(curl -fsS --connect-timeout 2 --max-time 5 \
  https://journey.muchenai.com/health/ready)
python3 - "$ready" "$web_baseline" <<'PY'
import json
import sys

assert json.loads(sys.argv[1]) == {"status": "ready", "release": sys.argv[2]}
PY

ln -sfn "$previous" "$root/current"
printf '%s\n' "$baseline" >"$root/DEPLOYED_CANDIDATE"
printf '%s\n' "$web_baseline" >"$root/DEPLOYED_WEB_CANDIDATE"
chmod 0644 "$root/DEPLOYED_CANDIDATE" "$root/DEPLOYED_WEB_CANDIDATE"
printf 'WP15_WARTIME_ROLLBACK=PASS api_worker=%s web=%s database=journey_next_restore_20260803\n' \
  "$baseline" "$web_baseline"
