#!/usr/bin/env bash
set -euo pipefail

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
    ;;
  greenfield-canary-web)
    project=journey-next-greenfield-canary
    ;;
  *) echo 'ACCESS_PROVISION=FAIL reason=production-upstream-map'; exit 2 ;;
esac

mapfile -t web_containers < <(
  docker ps \
    --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=web \
    --format '{{.ID}}'
)
[[ "${#web_containers[@]}" -eq 1 ]] || { echo 'ACCESS_PROVISION=FAIL reason=active-web-count'; exit 2; }
web_container="${web_containers[0]}"
web_aliases=$(docker inspect --format '{{range $network, $config := .NetworkSettings.Networks}}{{range $config.Aliases}}{{println .}}{{end}}{{end}}' "$web_container")
grep -Fxq "$production_upstream" <<<"$web_aliases" || { echo 'ACCESS_PROVISION=FAIL reason=active-web-alias'; exit 2; }

mapfile -t api_containers < <(
  docker ps \
    --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=api \
    --format '{{.ID}}'
)
[[ "${#api_containers[@]}" -eq 1 ]] || { echo 'ACCESS_PROVISION=FAIL reason=active-api-count'; exit 2; }
container="${api_containers[0]}"

running=$(docker inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)
current_project=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container" 2>/dev/null || true)
current_service=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' "$container" 2>/dev/null || true)
[[ "$running" == true && "$current_project" == "$project" && "$current_service" == api ]] || {
  echo 'ACCESS_PROVISION=FAIL reason=active-api-container'
  exit 2
}

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
