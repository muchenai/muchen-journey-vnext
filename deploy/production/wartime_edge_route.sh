#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WP15_WARTIME_EDGE_ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${WP15_EDGE_MODE:-}" == "maintenance" || "${WP15_EDGE_MODE:-}" == "live" ]] || \
  fail "edge mode is invalid"
[[ "${WP15_EDGE_SOURCE:-}" =~ ^/run/wp15-wartime-edge-[1-9][0-9]*/Caddyfile\.(maintenance|live)$ ]] || \
  fail "edge source path is invalid"
[[ -f "$WP15_EDGE_SOURCE" && ! -L "$WP15_EDGE_SOURCE" ]] || fail "edge source is missing"

release=/srv/journey-next-staging/current
[[ -L "$release" ]] || fail "staging current release is missing"
release=$(readlink -f "$release")
[[ "$release" =~ ^/srv/journey-next-staging/releases/[0-9a-f]{40}-[1-9][0-9]*$ ]] || \
  fail "staging current release is invalid"
cd "$release"
for path in compose.yaml Caddyfile edge.env .deployment.env; do
  [[ -f "$path" && ! -L "$path" ]] || fail "edge input is missing: $path"
done

umask 077
backup=$(mktemp "$PWD/.wp15-edge-backup.XXXXXX")
cp Caddyfile "$backup"
changed=0
rollback() {
  code=$?
  trap - ERR
  if [[ "$changed" -eq 1 ]]; then
    cp "$backup" Caddyfile
    set -a
    . ./edge.env
    . ./.deployment.env
    set +a
    docker compose run --rm --no-deps edge caddy validate --config /etc/caddy/Caddyfile || true
    docker compose up -d --no-deps --force-recreate --pull never edge || true
    printf 'WP15_WARTIME_EDGE_ROLLBACK=ATTEMPTED\n' >&2
  fi
  rm -f -- "$backup"
  exit "$code"
}
trap rollback ERR

install -m 0600 "$WP15_EDGE_SOURCE" Caddyfile
changed=1
set -a
. ./edge.env
. ./.deployment.env
set +a
docker compose run --rm --no-deps edge caddy validate --config /etc/caddy/Caddyfile
docker compose up -d --no-deps --force-recreate --pull never edge
sleep 2
if [[ "$WP15_EDGE_MODE" == "maintenance" ]]; then
  code=$(curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' \
    https://journey.muchenai.com/)
  [[ "$code" == "503" ]] || fail "maintenance route did not converge"
else
  code=$(curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' \
    https://journey.muchenai.com/)
  [[ "$code" == "200" ]] || fail "live route did not converge"
fi
rm -f -- "$backup"
trap - ERR
printf 'WP15_WARTIME_EDGE=PASS mode=%s status=%s\n' "$WP15_EDGE_MODE" "$code"
