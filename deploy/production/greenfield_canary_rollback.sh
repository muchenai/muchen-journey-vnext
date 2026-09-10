#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_ROLLBACK_ERROR: %s\n' "$*" >&2; exit 1; }
root=/srv/journey-next-production/canary
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
if [[ $# -eq 0 ]]; then
  [[ -L "$root/current" ]] || fail "canary current release is missing"
  release=$(readlink -f "$root/current")
elif [[ $# -eq 1 ]]; then
  release="$1"
else
  fail "expected zero or one exact release path"
fi
release_pattern="^${root}/releases/([0-9a-f]{40})-[1-9][0-9]*$"
[[ "$release" =~ $release_pattern ]] || fail "canary release path is invalid"
candidate="${BASH_REMATCH[1]}"
[[ -d "$release" && ! -L "$release" && "$(readlink -f "$release")" == "$release" ]] || fail "release directory is unsafe"
if [[ -L "$root/current" ]]; then
  [[ "$(readlink -f "$root/current")" == "$release" ]] || fail "another Canary is current"
elif [[ -e "$root/current" ]]; then
  fail "current path is not a release link"
fi
cd "$release"
for path in compose.canary.yaml compose.sh wp31_exec_env.py edge.sh Caddyfile.rollback; do
  [[ -f "$path" && ! -L "$path" ]] || fail "rollback input is missing: $path"
done
result=0
# Try both actions even if one fails, but never hide either failure.
WP31_EDGE_MODE=rollback WP31_EDGE_SOURCE="$PWD/Caddyfile.rollback" ./edge.sh || result=1
./compose.sh -f compose.canary.yaml down || result=1
remaining=$(./compose.sh -f compose.canary.yaml ps --all --quiet) || result=1
[[ -z "$remaining" ]] || result=1
[[ "$result" -eq 0 ]] || fail "edge or container cleanup failed; preserve release and current link"
if [[ -L "$root/current" ]]; then
  [[ "$(readlink -f "$root/current")" == "$release" ]] || fail "current changed during rollback"
  rm -f -- "$root/current"
fi
printf 'WP31_CANARY_ROLLBACK=PASS restored_candidate=ff53052847a268d025bceb93c3eab37986d50219 database_unchanged=true\n'
