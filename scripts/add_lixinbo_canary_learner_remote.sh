#!/usr/bin/env bash
set -euo pipefail

allowlist_file="$1"
run_tag="$2"
target_user_id=934d4bab-2494-4ed3-ac15-9378913b9c01
edge=journey-next-staging-edge-1
root=/srv/journey-next-production/canary

[[ -f "$allowlist_file" && ! -L "$allowlist_file" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=allowlist-file'; exit 2; }
[[ "$run_tag" =~ ^[0-9]+-[0-9]+$ ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=run-tag'; exit 2; }

production_upstream=$(
  docker exec "$edge" cat /etc/caddy/Caddyfile | python3 -c '
import sys

active = False
depth = 0
upstreams = []
for line in sys.stdin:
    stripped = line.strip()
    if depth == 0 and stripped == "{$PRODUCTION_HOST} {":
        active = True
    if active and stripped.startswith("reverse_proxy "):
        parts = stripped.split()
        if len(parts) == 2:
            upstreams.append(parts[1])
    depth += line.count("{") - line.count("}")
    if depth == 0:
        active = False
if upstreams not in (["greenfield-canary-web:3000"],):
    raise SystemExit(2)
print(upstreams[0].removesuffix(":3000"))
'
) || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=production-upstream'; exit 2; }
[[ "$production_upstream" == greenfield-canary-web ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=upstream-name'; exit 2; }
project=journey-next-greenfield-canary

mapfile -t containers < <(
  docker ps --filter "label=com.docker.compose.project=$project" --format '{{.ID}}'
)
[[ "${#containers[@]}" -eq 2 ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=container-count'; exit 2; }

api_container=
web_container=
for candidate in "${containers[@]}"; do
  service=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' "$candidate")
  case "$service" in
    api) api_container=$candidate ;;
    web) web_container=$candidate ;;
    *) echo 'CANARY_LEARNER_UPDATE=FAIL reason=unexpected-service'; exit 2 ;;
  esac
done
[[ -n "$api_container" && -n "$web_container" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=service-count'; exit 2; }

api_dir=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$api_container")
web_dir=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$web_container")
[[ "$api_dir" == "$web_dir" && "$api_dir" == "$root"/releases/* ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=active-release'; exit 2; }
active_dir=$(readlink -f -- "$api_dir")
[[ "$active_dir" == "$api_dir" && "$(readlink -f -- "$root/current")" == "$active_dir" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=current-pointer'; exit 2; }

for path in compose.canary.yaml compose.sh .deployment.env secrets/api.env secrets/web.env; do
  [[ -f "$active_dir/$path" && ! -L "$active_dir/$path" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=release-file'; exit 2; }
done

app_release=$(docker exec "$api_container" printenv APP_RELEASE)
[[ "$app_release" =~ ^[0-9a-f]{40}$ ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=api-release'; exit 2; }
api_health_release=$(
  docker exec "$api_container" python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3))["release"])'
)
[[ "$api_health_release" == "$app_release" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=api-health-before'; exit 2; }

new_dir="$root/releases/$app_release-learner-$run_tag"
[[ ! -e "$new_dir" && ! -L "$new_dir" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=release-exists'; exit 2; }
install -d -m 0700 "$new_dir"
cp -a -- "$active_dir/." "$new_dir/"

python3 - "$allowlist_file" "$new_dir/secrets/api.env" "$target_user_id" <<'PY'
import os
from pathlib import Path
import sys
from uuid import UUID

allowlist_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
target = str(UUID(sys.argv[3]))
raw = allowlist_path.read_text(encoding="utf-8").strip()
values = [str(UUID(item.strip())) for item in raw.split(",") if item.strip()]
if len(values) != len(set(values)) or not 1 <= len(values) <= 8 or target not in values:
    raise SystemExit(2)

original = env_path.read_text(encoding="utf-8")
lines = original.splitlines(keepends=True)
matches = [index for index, line in enumerate(lines) if line.startswith("CANARY_LEARNER_USER_IDS=")]
if len(matches) != 1:
    raise SystemExit(2)
ending = "\n" if lines[matches[0]].endswith("\n") else ""
lines[matches[0]] = "CANARY_LEARNER_USER_IDS=" + ",".join(values) + ending
updated = "".join(lines)
temp = env_path.with_name(".api.env.allowlist.tmp")
fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
    handle.write(updated)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temp, env_path)
PY

compose_up() {
  local release=$1
  (
    cd "$release"
    ./compose.sh -f compose.canary.yaml up -d --no-deps --no-build --pull never \
      --force-recreate --wait --wait-timeout 240 api web
  )
}

rollback() {
  set +e
  compose_up "$active_dir" >/dev/null 2>&1
  temporary="$root/.current-learner-rollback-$run_tag"
  rm -f -- "$temporary"
  ln -s "$active_dir" "$temporary"
  mv -Tf -- "$temporary" "$root/current"
}

switched=0
committed=0
on_exit() {
  status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$switched" -eq 1 && "$committed" -eq 0 ]]; then
    rollback
  fi
  exit "$status"
}
trap on_exit EXIT

if ! compose_up "$new_dir"; then
  echo 'CANARY_LEARNER_UPDATE=FAIL reason=compose-switch'
  exit 2
fi
switched=1

mapfile -t new_api < <(
  docker ps \
    --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=api \
    --format '{{.ID}}'
)
[[ "${#new_api[@]}" -eq 1 ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=api-count-after'; exit 2; }
new_api_container=${new_api[0]}
new_api_dir=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$new_api_container")
new_release=$(docker exec "$new_api_container" printenv APP_RELEASE)
new_allowlist=$(docker exec "$new_api_container" printenv CANARY_LEARNER_USER_IDS)
[[ "$new_api_dir" == "$new_dir" && "$new_release" == "$app_release" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=runtime-after'; exit 2; }

if ! python3 - "$allowlist_file" "$new_allowlist" "$target_user_id" <<'PY'
from pathlib import Path
import sys
from uuid import UUID

expected = [str(UUID(item.strip())) for item in Path(sys.argv[1]).read_text().strip().split(",") if item.strip()]
actual = [str(UUID(item.strip())) for item in sys.argv[2].split(",") if item.strip()]
target = str(UUID(sys.argv[3]))
if actual != expected or target not in actual:
    raise SystemExit(2)
PY
then
  echo 'CANARY_LEARNER_UPDATE=FAIL reason=allowlist-after'
  exit 2
fi

public_release=$(curl -fsS --connect-timeout 3 --max-time 10 https://journey.muchenai.com/health/ready | python3 -c 'import json,sys; print(json.load(sys.stdin)["release"])')
[[ "$public_release" == "$app_release" ]] || { echo 'CANARY_LEARNER_UPDATE=FAIL reason=public-health'; exit 2; }

temporary="$root/.current-learner-$run_tag"
ln -s "$new_dir" "$temporary"
mv -Tf -- "$temporary" "$root/current"
committed=1
trap - EXIT

allowlist_count=$(python3 - "$allowlist_file" <<'PY'
from pathlib import Path
import sys
print(len([item for item in Path(sys.argv[1]).read_text().strip().split(",") if item.strip()]))
PY
)
echo "CANARY_LEARNER_UPDATE=PASS release=$app_release learner_count=$allowlist_count target_present=true"
