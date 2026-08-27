#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'WP31_CANARY_BACKUP_RESTORE_ERROR: %s\n' "$*" >&2; exit 1; }

candidate=1bccbbf1706a8216892f5b9b512b1e27ce784101
source_database=journey_next_cutover_20260810
target_database=journey_next_canary_20260827_1bccbbf
[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${SOURCE_DATABASE:-}" == "$source_database" ]] || fail "unexpected source database"
[[ "${TARGET_DATABASE:-}" == "$target_database" ]] || fail "unexpected target database"
[[ "${WP31_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "workflow run ID is invalid"
[[ "${WP31_PREFLIGHT_RUN_ID:-}" =~ ^[1-9][0-9]{5,19}$ ]] || fail "preflight run ID is invalid"
[[ "${WP31_OPS_MANIFEST_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || fail "ops manifest hash is invalid"
[[ -n "${WP15_BACKUP_KEY:-}" && ${#WP15_BACKUP_KEY} -ge 32 ]] || fail "backup key is missing"
[[ "${DBTOOL_IMAGE:-}" == ghcr.io/muchenai2024-creator/muchen-journey-vnext-dbtool@sha256:3a82828474772d2b9c94fb51ae343e464c2f13dd1f2d7d90c807a46b104f53e9 ]] || fail "database tool differs"

bundle=$(pwd -P)
ca="$bundle/secrets/volcengine-rds-ca.pem"
facts_script="$bundle/db_facts.py"
target_env="$bundle/secrets/target-facts.env"
source_env="$bundle/secrets/source-facts.env"
for path in "$ca" "$facts_script" "$target_env" "$source_env"; do
  [[ -f "$path" && ! -L "$path" ]] || fail "required input is missing"
done
root="/srv/journey-next-production/canary/backups/$WP31_RUN_ID"
[[ ! -e "$root" ]] || fail "backup run already exists"
install -d -m 0700 "$root"
plain="$root/canary-source.dump"
encrypted="$root/canary-source.dump.enc"
verify="$root/canary-source.verify.dump"
facts="$root/restored-facts.json"
source_facts="$root/source-facts.json"
manifest="$root/backup-manifest.json"
cleanup() { rm -f -- "$plain" "$verify"; }
trap cleanup EXIT

pg() {
  docker run --rm --network host \
    -e PGPASSWORD="$MIGRATION_DB_PASSWORD" \
    -e PGSSLMODE=verify-full \
    -e PGSSLROOTCERT=/run/secrets/volcengine-rds-ca.pem \
    -v "$ca:/run/secrets/volcengine-rds-ca.pem:ro" \
    -v "$root:/backup" "$DBTOOL_IMAGE" "$@"
}

tables=$(pg psql -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$target_database" -Atqc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
[[ "$tables" == 0 ]] || fail "isolated canary database is not empty"
pg pg_dump -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$source_database" --format=custom --compress=9 --no-owner --no-acl \
  --serializable-deferrable --file=/backup/canary-source.dump
pg pg_restore -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator \
  -d "$target_database" --exit-on-error --no-owner --no-acl /backup/canary-source.dump

docker run --rm --network host --env-file "$source_env" \
  -e PGOPTIONS=-c\ default_transaction_read_only=on -e REQUIRE_READ_ONLY=true \
  -v "$ca:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$facts_script:/tmp/db_facts.py:ro" "$API_IMAGE" \
  python /tmp/db_facts.py >"$source_facts"
docker run --rm --network host --env-file "$target_env" \
  -e PGOPTIONS=-c\ default_transaction_read_only=on -e REQUIRE_READ_ONLY=true \
  -v "$ca:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$facts_script:/tmp/db_facts.py:ro" "$API_IMAGE" \
  python /tmp/db_facts.py >"$facts"
python3 - "$source_facts" "$facts" <<'PY'
import json, sys
source, restored = (json.load(open(path)) for path in sys.argv[1:])
assert source == restored
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
  "$WP31_PREFLIGHT_RUN_ID" "$WP31_OPS_MANIFEST_SHA256" <<'PY'
import hashlib, hmac, json, os, sys
from datetime import datetime, timedelta, timezone
path, run_id, plain_sha, encrypted_sha, source_facts_sha, facts_sha, preflight_run_id, ops_manifest_sha = sys.argv[1:]
now = datetime.now(timezone.utc).replace(microsecond=0)
body = {
    "schema_version": 2,
    "run_id": run_id,
    "preflight_run_id": preflight_run_id,
    "candidate_sha": "1bccbbf1706a8216892f5b9b512b1e27ce784101",
    "ops_manifest_sha256": ops_manifest_sha,
    "source_database": "journey_next_cutover_20260810",
    "isolated_canary_database": "journey_next_canary_20260827_1bccbbf",
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
