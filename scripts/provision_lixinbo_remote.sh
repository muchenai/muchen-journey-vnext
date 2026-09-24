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

matches=0
project=""
working_dir=""
mapfile -t web_containers < <(
  docker ps \
    --filter label=com.docker.compose.service=web \
    --format '{{.ID}}'
)
for current_container in "${web_containers[@]}"; do
  aliases=$(docker inspect --format '{{range $network, $config := .NetworkSettings.Networks}}{{range $config.Aliases}}{{println .}}{{end}}{{end}}' "$current_container")
  grep -Fxq "$production_upstream" <<<"$aliases" || continue
  current_project=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$current_container")
  current_working_dir=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$current_container")
  case "$current_project" in
    journey-next-production|journey-next-greenfield-canary) ;;
    *) continue ;;
  esac
  release=$(readlink -f "$current_working_dir" 2>/dev/null || true)
  case "$release" in
    "$root"/releases/[0-9a-f]*-[1-9][0-9]*|"$root"/canary/releases/[0-9a-f]*-[1-9][0-9]*) ;;
    *) continue ;;
  esac
  matches=$((matches + 1))
  project="$current_project"
  working_dir="$release"
done
[[ "$matches" -eq 1 && -n "$project" && -n "$working_dir" ]] || { echo 'ACCESS_PROVISION=FAIL reason=active-web-selection'; exit 2; }

mapfile -t api_containers < <(
  docker ps \
    --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=api \
    --format '{{.ID}}'
)
[[ "${#api_containers[@]}" -eq 1 ]] || { echo 'ACCESS_PROVISION=FAIL reason=active-api-count'; exit 2; }
container="${api_containers[0]}"
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
