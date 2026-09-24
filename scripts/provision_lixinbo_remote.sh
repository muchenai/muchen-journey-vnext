#!/usr/bin/env bash
set -euo pipefail

root=/srv/journey-next-production
script="$1"
[[ -f "$script" && ! -L "$script" ]] || { echo 'ACCESS_PROVISION=FAIL reason=script'; exit 2; }

live_release=$(curl -fsS --connect-timeout 3 --max-time 10 https://journey.muchenai.com/health/ready | python3 -c 'import json,sys; print(json.load(sys.stdin)["release"])')
[[ "$live_release" =~ ^[0-9a-f]{40}$ ]] || { echo 'ACCESS_PROVISION=FAIL reason=live-release'; exit 2; }

matches=0
container=""
for candidate in "$root/current" "$root/canary/current"; do
  [[ -L "$candidate" ]] || continue
  release=$(readlink -f "$candidate")
  case "$release" in
    "$root"/releases/[0-9a-f]*-[1-9][0-9]*|"$root"/canary/releases/[0-9a-f]*-[1-9][0-9]*) ;;
    *) continue ;;
  esac
  if [[ "$candidate" == "$root/canary/current" ]]; then
    current_container=$(cd "$release" && ./compose.sh -f compose.canary.yaml ps -q api)
  else
    current_container=$(cd "$release" && docker compose ps -q api)
  fi
  [[ -n "$current_container" ]] || continue
  app_release=$(docker exec "$current_container" printenv APP_RELEASE)
  if [[ "$app_release" == "$live_release" ]]; then
    matches=$((matches + 1))
    container="$current_container"
  fi
done

[[ "$matches" -eq 1 && -n "$container" ]] || { echo 'ACCESS_PROVISION=FAIL reason=runtime-selection'; exit 2; }
container_script=/tmp/provision_lixinbo_access.py
cleanup() { docker exec -u 0 "$container" rm -f -- "$container_script" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker cp "$script" "$container:$container_script" >/dev/null
docker exec "$container" python "$container_script" --confirm PROVISION_LIXINBO_OPERATOR_REVIEWER
echo "ACCESS_PROVISION=PASS release=$live_release"
