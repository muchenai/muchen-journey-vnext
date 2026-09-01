#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_DEPLOY_ERROR: %s\n' "$*" >&2; return 1; }
candidate=c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f
database=journey_next_canary_20260901_c72fea5
migration=0028_canary_main_merge
root=/srv/journey-next-production/canary
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${CANDIDATE_COMMIT:-}" == "$candidate" ]] || fail "candidate differs"
[[ "${CANARY_DATABASE:-}" == "$database" ]] || fail "database differs"
[[ "${PRODUCTION_HOST:-}" == journey.muchenai.com ]] || fail "host differs"
[[ "${BACKUP_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "backup run ID is invalid"
[[ "${PREFLIGHT_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "preflight run ID is invalid"
[[ "${WP31_OPS_MANIFEST_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || fail "ops manifest hash is invalid"
[[ "${WP31_DEPLOY_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "deploy run ID is invalid"
[[ -n "${WP15_BACKUP_KEY:-}" && ${#WP15_BACKUP_KEY} -ge 32 ]] || fail "backup key is missing"
[[ "${API_IMAGE:-}" == ghcr.io/muchenai/muchen-journey-vnext-api@sha256:d7131d5e8af5cf0a7cef6e4aa4cd6a8a2e6eec0816424f7010efad86224da74c ]] || fail "API digest differs"
[[ "${WEB_IMAGE:-}" == ghcr.io/muchenai/muchen-journey-vnext-web@sha256:fcfd637bef0e6722d45494c7e4b0099270e41046c356eaa981d702935a0a6fc3 ]] || fail "Web digest differs"

for path in compose.canary.yaml compose.migrate.yaml grant_runtime.py edge.sh Caddyfile.canary Caddyfile.rollback allowlist-proof.json db_facts.py; do
  [[ -f "$PWD/$path" && ! -L "$PWD/$path" ]] || fail "required input is missing: $path"
done
for path in api.env migration.env web.env backup.env target-facts.env; do
  [[ -f "$PWD/secrets/$path" && ! -L "$PWD/secrets/$path" && "$(stat -c '%a' "$PWD/secrets/$path")" == 600 ]] || fail "secret input is invalid: $path"
done
[[ "$(docker compose -f compose.canary.yaml config --services | tr '\n' ',')" == api,web, ]] || fail "worker or extra service entered canary compose"
grep -qx 'APP_ENV=production' secrets/api.env || fail "API environment differs"
grep -qx 'RELEASE_MARKER=PRODUCTION_CANARY_UAT' secrets/api.env || fail "release marker differs"
grep -qx 'RELEASE_MARKER=PRODUCTION_CANARY_UAT' secrets/web.env || fail "Web release marker differs"
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
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" python3 - "$manifest" "$BACKUP_RUN_ID" "$PREFLIGHT_RUN_ID" "$WP31_OPS_MANIFEST_SHA256" "$root/backups/$BACKUP_RUN_ID" <<'PY'
import hashlib, hmac, json, os, sys
from datetime import datetime, timezone
value = json.load(open(sys.argv[1])); signature = value.pop("manifest_hmac_sha256", "")
expected = hmac.new(os.environ["WP15_BACKUP_KEY"].encode(), json.dumps(value, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
assert hmac.compare_digest(signature, expected)
assert value["run_id"] == sys.argv[2]
assert value["preflight_run_id"] == sys.argv[3]
assert value["ops_manifest_sha256"] == sys.argv[4]
assert value["candidate_sha"] == "c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f"
assert value["isolated_canary_database"] == "journey_next_canary_20260901_c72fea5"
assert value["backup"] == value["restore"] == "PASS"
assert value["source_modified"] is False
root=sys.argv[5]
digest=lambda name: hashlib.sha256(open(os.path.join(root,name),"rb").read()).hexdigest()
assert digest("canary-source.dump.enc") == value["encrypted_backup_sha256"]
assert digest("source-facts.json") == value["source_facts_sha256"]
assert digest("restored-facts.json") == value["restored_facts_sha256"]
assert json.load(open(os.path.join(root,"source-facts.json"))) == json.load(open(os.path.join(root,"restored-facts.json")))
assert datetime.now(timezone.utc) < datetime.fromisoformat(value["expires_at_utc"].replace("Z","+00:00"))
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
  docker compose -f compose.canary.yaml down || true
  if [[ -L "$root/current" && "$(readlink -f "$root/current")" == "$PWD" ]]; then rm -f -- "$root/current"; fi
  install -d -m 0700 "$root/failures"
  printf '{"candidate_sha":"%s","database_preserved":true,"release_path_preserved":true,"rollback_attempted":true}\n' "$candidate" \
    >"$root/failures/$WP31_DEPLOY_RUN_ID.json" || true
  chmod 0600 "$root/failures/$WP31_DEPLOY_RUN_ID.json" 2>/dev/null || true
  printf 'WP31_CANARY_DEPLOY_AUTOMATIC_ROLLBACK=ATTEMPTED\n' >&2
  exit "$code"
}
trap rollback ERR
before="$root/backups/$BACKUP_RUN_ID/restored-facts.json"
current_before="$root/backups/$BACKUP_RUN_ID/deploy-pre-migration-facts.json"
docker run --rm --network host --env-file secrets/target-facts.env \
  -e PGOPTIONS=-c\ default_transaction_read_only=on -e REQUIRE_READ_ONLY=true \
  -v "$PWD/secrets/volcengine-rds-ca.pem:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$PWD/db_facts.py:/tmp/db_facts.py:ro" "$API_IMAGE" python /tmp/db_facts.py >"$current_before"
cmp -s "$before" "$current_before" || fail "restored database drifted before migration"
docker compose -f compose.canary.yaml -f compose.migrate.yaml run --rm --no-deps api alembic upgrade head
current=$(docker compose -f compose.canary.yaml -f compose.migrate.yaml run --rm --no-deps api alembic current | tail -1)
[[ "$current" == *"$migration"* ]] || fail "migration did not converge"
docker compose -f compose.canary.yaml -f compose.migrate.yaml run --rm --no-deps api python /tmp/grant_runtime.py
after="$root/backups/$BACKUP_RUN_ID/deploy-post-migration-facts.json"
docker run --rm --network host --env-file secrets/target-facts.env \
  -e PGOPTIONS=-c\ default_transaction_read_only=on -e REQUIRE_READ_ONLY=true \
  -v "$PWD/secrets/volcengine-rds-ca.pem:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$PWD/db_facts.py:/tmp/db_facts.py:ro" "$API_IMAGE" python /tmp/db_facts.py >"$after"
python3 - "$before" "$after" <<'PY'
import json,sys
before,after=(json.load(open(path)) for path in sys.argv[1:])
assert before["migration"] == "0019_wp30_invitation_control"
assert after["migration"] == "0028_canary_main_merge"
for table,count in before["counts"].items():
    assert after["counts"].get(table) == count, table
assert after["active_notification_recipients"] == before["active_notification_recipients"]
PY
docker compose -f compose.canary.yaml up -d --wait
started=1
api_health=$(docker compose -f compose.canary.yaml exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).read().decode())")
web_release=$(docker compose -f compose.canary.yaml exec -T web printenv APP_RELEASE)
python3 - "$api_health" "$web_release" <<'PY'
import json, sys
assert json.loads(sys.argv[1]) == {"status": "ok", "release": "c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f"}
assert sys.argv[2] == "c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f"
PY
install -d -m 0700 "$root"
ln -sfn "$PWD" "$root/current"
WP31_EDGE_MODE=canary WP31_EDGE_SOURCE="$PWD/Caddyfile.canary" ./edge.sh
ready=$(curl -fsS --connect-timeout 3 --max-time 10 https://journey.muchenai.com/health/ready)
python3 - "$ready" <<'PY'
import json,sys
assert json.loads(sys.argv[1]) == {"status":"ready","release":"c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f"}
PY
trap - ERR
printf 'WP31_CANARY_DEPLOY=PASS candidate=%s database=%s migration=%s worker_started=false release_go=false\n' "$candidate" "$database" "$migration"
