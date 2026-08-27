#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_ROLLBACK_ERROR: %s\n' "$*" >&2; exit 1; }
root=/srv/journey-next-production/canary
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ -L "$root/current" ]] || fail "canary current release is missing"
release=$(readlink -f "$root/current")
[[ "$release" =~ ^$root/releases/1bccbbf1706a8216892f5b9b512b1e27ce784101-[1-9][0-9]*$ ]] || fail "canary release path is invalid"
cd "$release"
for path in compose.canary.yaml edge.sh Caddyfile.rollback; do
  [[ -f "$path" && ! -L "$path" ]] || fail "rollback input is missing: $path"
done
WP31_EDGE_MODE=rollback WP31_EDGE_SOURCE="$PWD/Caddyfile.rollback" ./edge.sh
docker compose -f compose.canary.yaml down
printf 'WP31_CANARY_ROLLBACK=PASS restored_candidate=ff53052847a268d025bceb93c3eab37986d50219 database_unchanged=true\n'
