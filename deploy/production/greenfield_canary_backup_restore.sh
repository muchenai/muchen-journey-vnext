#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_BACKUP_RESTORE_ERROR: %s\n' "$*" >&2; exit 1; }

candidate="${CANDIDATE_COMMIT:-}"
source_database=journey_next_cutover_20260810
target_database=journey_next_canary_20260901_c72fea5
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "$candidate" =~ ^[0-9a-f]{40}$ ]] || fail "candidate is invalid"
[[ "${SOURCE_DATABASE:-}" == "$source_database" ]] || fail "unexpected source database"
[[ "${TARGET_DATABASE:-}" == "$target_database" ]] || fail "unexpected target database"
[[ "${WP31_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "workflow run ID is invalid"
[[ "${WP31_PREFLIGHT_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "preflight run ID is invalid"
[[ "${WP31_OPS_MANIFEST_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || fail "ops manifest hash is invalid"
[[ -n "${WP15_BACKUP_KEY:-}" && ${#WP15_BACKUP_KEY} -ge 32 ]] || fail "backup key is missing"
[[ "${DBTOOL_IMAGE:-}" == ghcr.io/muchenai/muchen-journey-vnext-dbtool@sha256:3a82828474772d2b9c94fb51ae343e464c2f13dd1f2d7d90c807a46b104f53e9 ]] || fail "database tool differs"

bundle=$(pwd -P)
ca="$bundle/secrets/volcengine-rds-ca.pem"
facts_script="$bundle/db_facts.py"
snapshot_script="$bundle/wp31_database_snapshot.py"
target_env="$bundle/secrets/target-facts.env"
source_env="$bundle/secrets/source-facts.env"
binding_proof="$bundle/candidate-binding-proof.json"
binding_module="$bundle/wp31_candidate_binding.py"
for path in "$ca" "$facts_script" "$snapshot_script" "$target_env" "$source_env" "$binding_proof" "$binding_module"; do
  [[ -f "$path" && ! -L "$path" ]] || fail "required input is missing"
done
python3 "$binding_module" runtime-verify \
  --binding "$binding_proof" --candidate "$candidate" \
  --api-image "${API_IMAGE:-}" --web-image "${WEB_IMAGE:-}" || fail "runtime binding differs"
root="/srv/journey-next-production/canary/backups/$WP31_RUN_ID"
[[ ! -e "$root" ]] || fail "backup run already exists"
install -d -m 0700 "$root"
plain="$root/canary-source.dump"
encrypted="$root/canary-source.dump.enc"
verify="$root/canary-source.verify.dump"
facts="$root/restored-facts.json"
source_facts="$root/source-facts.json"
manifest="$root/backup-manifest.json"
snapshot_exchange="$root/snapshot-exchange"
snapshot_id_file="$snapshot_exchange/snapshot-id"
snapshot_release_file="$snapshot_exchange/snapshot-release"
snapshot_container="wp31-canary-snapshot-$WP31_RUN_ID"
snapshot_started=false
install -d -m 0700 "$snapshot_exchange"

release_snapshot() {
  local holder_status
  [[ "$snapshot_started" == true ]] || return 0
  if [[ -L "$snapshot_release_file" || ( -e "$snapshot_release_file" && ! -f "$snapshot_release_file" ) ]]; then
    return 1
  fi
  if [[ ! -e "$snapshot_release_file" ]]; then
    install -m 0600 /dev/null "$snapshot_release_file" || return 1
  fi
  if ! holder_status=$(timeout 30 docker wait "$snapshot_container"); then
    docker rm -f "$snapshot_container" >/dev/null 2>&1 || true
    snapshot_started=false
    return 1
  fi
  if ! docker rm "$snapshot_container" >/dev/null 2>&1; then
    docker rm -f "$snapshot_container" >/dev/null 2>&1 || return 1
  fi
  snapshot_started=false
  [[ "$holder_status" == 0 ]]
}

cleanup() {
  set +e
  release_snapshot
  docker rm -f "$snapshot_container" >/dev/null 2>&1
  rm -f -- "$snapshot_id_file" "$snapshot_release_file" "$plain" "$verify"
  rmdir "$snapshot_exchange" >/dev/null 2>&1
}
trap cleanup EXIT

pg() {
  docker run --rm --network host \
    -e PGPASSWORD="$MIGRATION_DB_PASSWORD" \
    -e PGSSLMODE=verify-full \
    -e PGSSLROOTCERT=/run/secrets/volcengine-rds-ca.pem \
    -v "$ca:/run/secrets/volcengine-rds-ca.pem:ro" \
    -v "$root:/backup" "$DBTOOL_IMAGE" "$@"
}

facts() {
  local env_file="$1"
  local output="$2"
  local snapshot_id="${3:-}"
  local snapshot_env=()
  if [[ -n "$snapshot_id" ]]; then
    snapshot_env=(-e WP31_DATABASE_SNAPSHOT="$snapshot_id")
  fi
  docker run --rm --network host --env-file "$env_file" \
    -e PGOPTIONS=-c\ default_transaction_read_only=on -e REQUIRE_READ_ONLY=true \
    "${snapshot_env[@]}" \
    -v "$ca:/run/secrets/volcengine-rds-ca.pem:ro" \
    -v "$facts_script:/tmp/db_facts.py:ro" \
    -v "$snapshot_script:/tmp/wp31_database_snapshot.py:ro" "$API_IMAGE" \
    python /tmp/db_facts.py >"$output"
}

docker pull "$DBTOOL_IMAGE" >/dev/null
docker pull "$API_IMAGE" >/dev/null
tables=$(pg psql -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$target_database" -Atqc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
[[ "$tables" == 0 ]] || fail "isolated canary database is not empty"

docker run -d --name "$snapshot_container" --user 0:0 --network host \
  --env-file "$source_env" \
  -e PGOPTIONS=-c\ default_transaction_read_only=on \
  -v "$ca:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$snapshot_script:/tmp/wp31_database_snapshot.py:ro" \
  -v "$snapshot_exchange:/exchange" "$API_IMAGE" \
  python /tmp/wp31_database_snapshot.py \
    --exchange-dir /exchange --timeout-seconds 900 >/dev/null
snapshot_started=true
snapshot_ready_deadline=$((SECONDS + 900))
while [[ ! -f "$snapshot_id_file" || -L "$snapshot_id_file" ]]; do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$snapshot_container" 2>/dev/null)" != true ]]; then
    docker logs "$snapshot_container" >&2 || true
    fail "snapshot holder exited before becoming ready"
  fi
  (( SECONDS < snapshot_ready_deadline )) || fail "snapshot holder readiness timed out"
  sleep 1
done
[[ "$(stat -c '%a' "$snapshot_id_file")" == 600 ]] || fail "snapshot identifier file mode is invalid"
IFS= read -r snapshot_id <"$snapshot_id_file"
[[ "$snapshot_id" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9A-Fa-f]+$ ]] || fail "snapshot identifier is invalid"

pg pg_dump -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$source_database" --format=custom --compress=9 --no-owner --no-acl \
  --snapshot="$snapshot_id" --file=/backup/canary-source.dump
facts "$source_env" "$source_facts" "$snapshot_id"
release_snapshot || fail "snapshot holder release failed"
pg pg_restore -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$target_database" --exit-on-error --no-owner --no-acl \
  /backup/canary-source.dump

facts "$target_env" "$facts"
if ! cmp -s "$source_facts" "$facts"; then
  source_facts_sha=$(sha256sum "$source_facts" | awk '{print $1}')
  restored_facts_sha=$(sha256sum "$facts" | awk '{print $1}')
  printf 'WP31_CANARY_FACTS_MISMATCH source_sha256=%s restored_sha256=%s\n' \
    "$source_facts_sha" "$restored_facts_sha" >&2
  fail "RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT"
fi
python3 - "$facts" <<'PY'
import json, sys
restored = json.load(open(sys.argv[1]))
assert restored["migration"] == "0019_wp30_invitation_control"
assert restored["counts"]
assert len(restored["schema_sha256"]) == 64
PY

plain_sha=$(sha256sum "$plain" | awk '{print $1}')
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
  -salt -in "$plain" -out "$encrypted" -pass env:WP15_BACKUP_KEY
rm -f -- "$plain"
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -in "$encrypted" -out "$verify" -pass env:WP15_BACKUP_KEY
[[ "$(sha256sum "$verify" | awk '{print $1}')" == "$plain_sha" ]] || fail "encrypted backup verification failed"
rm -f -- "$verify"
encrypted_sha=$(sha256sum "$encrypted" | awk '{print $1}')
facts_sha=$(sha256sum "$facts" | awk '{print $1}')
source_facts_sha=$(sha256sum "$source_facts" | awk '{print $1}')
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" python3 - "$manifest" "$WP31_RUN_ID" \
  "$plain_sha" "$encrypted_sha" "$source_facts_sha" "$facts_sha" \
  "$WP31_PREFLIGHT_RUN_ID" "$WP31_OPS_MANIFEST_SHA256" "$candidate" <<'PY'
import hashlib, hmac, json, os, sys
from datetime import datetime, timedelta, timezone
path, run_id, plain_sha, encrypted_sha, source_facts_sha, facts_sha, preflight_run_id, ops_manifest_sha, candidate = sys.argv[1:]
now = datetime.now(timezone.utc).replace(microsecond=0)
body = {
    "schema_version": 2,
    "run_id": run_id,
    "preflight_run_id": preflight_run_id,
    "candidate_sha": candidate,
    "ops_manifest_sha256": ops_manifest_sha,
    "source_database": "journey_next_cutover_20260810",
    "isolated_canary_database": "journey_next_canary_20260901_c72fea5",
    "source_migration": "0019_wp30_invitation_control",
    "decrypted_backup_sha256": plain_sha,
    "encrypted_backup_sha256": encrypted_sha,
    "source_facts_sha256": source_facts_sha,
    "restored_facts_sha256": facts_sha,
    "source_restore_facts_equal": True,
    "backup": "PASS",
    "restore": "PASS",
    "source_modified": False,
    "created_at_utc": now.isoformat().replace("+00:00", "Z"),
    "expires_at_utc": (now + timedelta(minutes=60)).isoformat().replace("+00:00", "Z"),
}
canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
body["manifest_hmac_sha256"] = hmac.new(
    os.environ["WP15_BACKUP_KEY"].encode(), canonical, hashlib.sha256
).hexdigest()
open(path, "x").write(json.dumps(body, indent=2, sort_keys=True) + "\n")
PY
chmod 0600 "$encrypted" "$source_facts" "$facts" "$manifest"
printf 'WP31_CANARY_BACKUP_RESTORE=PASS run_id=%s source_modified=false target=%s\n' \
  "$WP31_RUN_ID" "$target_database"
