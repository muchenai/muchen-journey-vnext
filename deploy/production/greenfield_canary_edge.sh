#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_EDGE_ERROR: %s\n' "$*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${WP31_EDGE_MODE:-}" == canary || "${WP31_EDGE_MODE:-}" == rollback ]] || fail "edge mode is invalid"
[[ "${WP31_EDGE_SOURCE:-}" =~ ^/srv/journey-next-production/canary/releases/1bccbbf1706a8216892f5b9b512b1e27ce784101-[1-9][0-9]*/Caddyfile\.(canary|rollback)$ ]] || fail "edge source is invalid"
[[ -f "$WP31_EDGE_SOURCE" && ! -L "$WP31_EDGE_SOURCE" ]] || fail "edge source is missing"

staging=/srv/journey-next-staging/current
[[ -L "$staging" ]] || fail "staging edge release is missing"
staging=$(readlink -f "$staging")
[[ "$staging" =~ ^/srv/journey-next-staging/releases/[0-9a-f]{40}-[1-9][0-9]*$ ]] || fail "staging edge release is invalid"
cd "$staging"
for path in compose.yaml Caddyfile secrets/edge.env .deployment.env; do
  [[ -f "$path" && ! -L "$path" ]] || fail "edge input is missing: $path"
done
backup=$(mktemp "$PWD/.wp31-edge-backup.XXXXXX")
cp Caddyfile "$backup"
changed=0
restore() {
  code=$?
  trap - ERR
  if [[ "$changed" == 1 ]]; then
    cp "$backup" Caddyfile
    set -a; . ./secrets/edge.env; . ./.deployment.env; set +a
    docker compose run --rm --no-deps edge caddy validate --config /etc/caddy/Caddyfile || true
    docker compose up -d --no-deps --force-recreate --pull never edge || true
    printf 'WP31_CANARY_EDGE_AUTOMATIC_RESTORE=ATTEMPTED\n' >&2
  fi
  rm -f -- "$backup"
  exit "$code"
}
trap restore ERR
install -m 0600 "$WP31_EDGE_SOURCE" Caddyfile
changed=1
set -a; . ./secrets/edge.env; . ./.deployment.env; set +a
docker compose run --rm --no-deps edge caddy validate --config /etc/caddy/Caddyfile
docker compose up -d --no-deps --force-recreate --pull never edge
sleep 2
code=$(curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' https://journey.muchenai.com/)
[[ "$code" == 200 ]] || fail "public surface did not converge"
rm -f -- "$backup"
trap - ERR
printf 'WP31_CANARY_EDGE=PASS mode=%s status=%s\n' "$WP31_EDGE_MODE" "$code"
