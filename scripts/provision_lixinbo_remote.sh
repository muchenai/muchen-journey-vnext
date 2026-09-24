#!/usr/bin/env bash
set -euo pipefail

root=/srv/journey-next-production
edge=journey-next-staging-edge-1
script="$1"
[[ -f "$script" && ! -L "$script" ]] || { echo 'ACCESS_PROVISION=FAIL reason=script'; exit 2; }

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
if upstreams not in (["production-web:3000"], ["greenfield-canary-web:3000"]):
    raise SystemExit(2)
print(upstreams[0].removesuffix(":3000"))
'
) || { echo 'ACCESS_PROVISION=FAIL reason=production-upstream'; exit 2; }

case "$production_upstream" in
  production-web)
    project=journey-next-production
    working_dir=$(readlink -f "$root/current" 2>/dev/null || true)
    container=journey-next-production-api-1
    case "$working_dir" in
      "$root"/releases/[0-9a-f]*-[1-9][0-9]*) ;;
      *) echo 'ACCESS_PROVISION=FAIL reason=active-production-release'; exit 2 ;;
    esac
    ;;
  greenfield-canary-web)
    project=journey-next-greenfield-canary
    working_dir=$(readlink -f "$root/canary/current" 2>/dev/null || true)
    case "$working_dir" in
      "$root"/canary/releases/[0-9a-f]*-[1-9][0-9]*) ;;
      *) echo 'ACCESS_PROVISION=FAIL reason=active-canary-release'; exit 2 ;;
    esac
    for path in compose.sh wp31_exec_env.py compose.canary.yaml .deployment.env; do
      [[ -f "$working_dir/$path" && ! -L "$working_dir/$path" ]] || {
        echo 'ACCESS_PROVISION=FAIL reason=active-canary-runtime'
        exit 2
      }
    done
    mapfile -t api_containers < <(
      cd "$working_dir"
      ./compose.sh -f compose.canary.yaml ps -q api
    )
    [[ "${#api_containers[@]}" -eq 1 && -n "${api_containers[0]}" ]] || {
      echo 'ACCESS_PROVISION=FAIL reason=active-canary-api-count'
      exit 2
    }
    container="${api_containers[0]}"
    ;;
  *) echo 'ACCESS_PROVISION=FAIL reason=production-upstream-map'; exit 2 ;;
esac

running=$(docker inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)
current_project=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container" 2>/dev/null || true)
current_service=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' "$container" 2>/dev/null || true)
[[ "$running" == true && "$current_project" == "$project" && "$current_service" == api ]] || {
  echo 'ACCESS_PROVISION=FAIL reason=active-api-container'
  exit 2
}

api_working_dir=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$container")
api_release_dir=$(readlink -f "$api_working_dir" 2>/dev/null || true)
[[ "$api_release_dir" == "$working_dir" ]] || { echo 'ACCESS_PROVISION=FAIL reason=active-release-mismatch'; exit 2; }

app_release=$(docker exec "$container" printenv APP_RELEASE)
[[ "$app_release" =~ ^[0-9a-f]{40}$ ]] || { echo 'ACCESS_PROVISION=FAIL reason=api-release'; exit 2; }
api_health_release=$(
  docker exec "$container" python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3))["release"])'
)
[[ "$api_health_release" == "$app_release" ]] || { echo 'ACCESS_PROVISION=FAIL reason=api-health'; exit 2; }

container_script=/tmp/provision_lixinbo_access.py
cleanup() { docker exec -u 0 "$container" rm -f -- "$container_script" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker cp "$script" "$container:$container_script" >/dev/null
docker exec "$container" python "$container_script" --confirm PROVISION_LIXINBO_OPERATOR_REVIEWER
echo "ACCESS_PROVISION=PASS release=$app_release"
