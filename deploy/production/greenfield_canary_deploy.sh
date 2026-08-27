#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_DEPLOY_ERROR: %s\n' "$*" >&2; exit 1; }
candidate=1bccbbf1706a8216892f5b9b512b1e27ce784101
database=journey_next_canary_20260827_1bccbbf
migration=0027_next_stage_review
root=/srv/journey-next-production/canary
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${CANDIDATE_COMMIT:-}" == "$candidate" ]] || fail "candidate differs"
[[ "${CANARY_DATABASE:-}" == "$database" ]] || fail "database differs"
[[ "${PRODUCTION_HOST:-}" == journey.muchenai.com ]] || fail "host differs"
[[ "${BACKUP_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "backup run ID is invalid"
[[ -n "${WP15_BACKUP_KEY:-}" && ${#WP15_BACKUP_KEY} -ge 32 ]] || fail "backup key is missing"
[[ "${API_IMAGE:-}" == ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@sha256:772ea55221ab07fdec746c9098542c2e627a658239b2769cc214c969e1ed1a85 ]] || fail "API digest differs"
[[ "${WEB_IMAGE:-}" == ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:743d441ef04c1d23e7cc77c34c4216028ec2b8f2499260a98283428803b6cdbb ]] || fail "Web digest differs"

for path in compose.canary.yaml compose.migrate.yaml grant_runtime.py edge.sh Caddyfile.canary Caddyfile.rollback allowlist-proof.json; do
  [[ -f "$PWD/$path" && ! -L "$PWD/$path" ]] || fail "required input is missing: $path"
done
for path in api.env migration.env web.env backup.env target-facts.env; do
  [[ -f "$PWD/secrets/$path" && ! -L "$PWD/secrets/$path" && "$(stat -c '%a' "$PWD/secrets/$path")" == 600 ]] || fail "secret input is invalid: $path"
done
[[ "$(docker compose -f compose.canary.yaml config --services | tr '\n' ',')" == api,web, ]] || fail "worker or extra service entered canary compose"
grep -qx 'APP_ENV=production' secrets/api.env || fail "API environment differs"
grep -qx 'RELEASE_MARKER=PRODUCTION_CANARY_UAT' secrets/api.env || fail "release marker differs"
grep -qx 'ALLOW_FIXTURE_IDENTITY=false' secrets/api.env || fail "fixture identity differs"
grep -qx 'NOTIFICATION_RECIPIENTS_ENABLED=false' secrets/api.env || fail "notifications must be disabled"
! grep -q '^WORKER_' secrets/api.env || fail "worker configuration is forbidden"
python3 - secrets/api.env allowlist-proof.json <<'PY'
import hashlib, json, sys, uuid
lines = dict(line.rstrip("\n").split("=", 1) for line in open(sys.argv[1]))
raw = lines.get("CANARY_LEARNER_USER_IDS", "")
values = [str(uuid.UUID(item)) for item in raw.split(",") if item]
assert len(values) == len(set(values)) <= 8
proof = json.load(open(sys.argv[2]))
assert proof["allowlist_count"] == len(values)
assert proof["allowlist_sha256"] == hashlib.sha256(",".join(sorted(values)).encode()).hexdigest()
assert proof["raw_identifiers_in_proof"] is False
print(f"WP31_CANARY_ALLOWLIST=PASS count={len(values)} sha256={proof['allowlist_sha256']}")
PY

manifest="$root/backups/$BACKUP_RUN_ID/backup-manifest.json"
[[ -f "$manifest" && ! -L "$manifest" ]] || fail "backup/restore proof is missing"
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" python3 - "$manifest" "$BACKUP_RUN_ID" <<'PY'
import hashlib, hmac, json, os, sys
value = json.load(open(sys.argv[1])); signature = value.pop("manifest_hmac_sha256", "")
expected = hmac.new(os.environ["WP15_BACKUP_KEY"].encode(), json.dumps(value, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
assert hmac.compare_digest(signature, expected)
assert value["run_id"] == sys.argv[2]
assert value["candidate_sha"] == "1bccbbf1706a8216892f5b9b512b1e27ce784101"
assert value["isolated_canary_database"] == "journey_next_canary_20260827_1bccbbf"
assert value["backup"] == value["restore"] == "PASS"
assert value["source_modified"] is False
PY

docker network inspect journey-next-staging_default >/dev/null || fail "edge network is missing"
docker compose -f compose.canary.yaml -f compose.migrate.yaml config --quiet
docker compose -f compose.canary.yaml pull
started=0
rollback() {
  code=$?
  trap - ERR
  printf 'WP31_CANARY_DEPLOY_AUTOMATIC_ROLLBACK=START\n' >&2
  WP31_EDGE_MODE=rollback WP31_EDGE_SOURCE="$PWD/Caddyfile.rollback" ./edge.sh || true
  if [[ "$started" == 1 ]]; then docker compose -f compose.canary.yaml down || true; fi
  printf 'WP31_CANARY_DEPLOY_AUTOMATIC_ROLLBACK=ATTEMPTED\n' >&2
  exit "$code"
}
trap rollback ERR
docker compose -f compose.canary.yaml -f compose.migrate.yaml run --rm --no-deps api alembic upgrade head
current=$(docker compose -f compose.canary.yaml -f compose.migrate.yaml run --rm --no-deps api alembic current | tail -1)
[[ "$current" == *"$migration"* ]] || fail "migration did not converge"
docker compose -f compose.canary.yaml -f compose.migrate.yaml run --rm --no-deps api python /tmp/grant_runtime.py
docker compose -f compose.canary.yaml up -d --wait
started=1
api_health=$(docker compose -f compose.canary.yaml exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).read().decode())")
web_release=$(docker compose -f compose.canary.yaml exec -T web printenv APP_RELEASE)
python3 - "$api_health" "$web_release" <<'PY'
import json, sys
assert json.loads(sys.argv[1]) == {"status": "ok", "release": "1bccbbf1706a8216892f5b9b512b1e27ce784101"}
assert sys.argv[2] == "1bccbbf1706a8216892f5b9b512b1e27ce784101"
PY
install -d -m 0700 "$root"
ln -sfn "$PWD" "$root/current"
WP31_EDGE_MODE=canary WP31_EDGE_SOURCE="$PWD/Caddyfile.canary" ./edge.sh
trap - ERR
printf 'WP31_CANARY_DEPLOY=PASS candidate=%s database=%s migration=%s worker_started=false release_go=false\n' "$candidate" "$database" "$migration"
