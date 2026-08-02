#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WP15_BACKUP_RESTORE_ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "backup_restore.sh must run as root"
[[ "${SOURCE_DATABASE:-}" == "journey_next_staging" ]] || fail "unexpected source database"
case "${TARGET_DATABASE:-}" in
  journey_next_production|journey_next_restore_20260803) ;;
  *) fail "unexpected target database" ;;
esac
[[ "$SOURCE_DATABASE" != "$TARGET_DATABASE" ]] || fail "source and target must differ"
[[ "${DBTOOL_IMAGE:-}" == *"@sha256:"* ]] || fail "database tool is not digest pinned"
[[ -n "${WP15_BACKUP_KEY:-}" && ${#WP15_BACKUP_KEY} -ge 32 ]] || fail "backup key is missing or short"

umask 077
bundle_dir=$(pwd -P)
CA_PATH=${CA_PATH:-"$bundle_dir/secrets/volcengine-rds-ca.pem"}
SOURCE_FACTS_ENV=${SOURCE_FACTS_ENV:-"$bundle_dir/secrets/source-facts.env"}
TARGET_FACTS_ENV=${TARGET_FACTS_ENV:-"$bundle_dir/secrets/target-facts.env"}
FACTS_SCRIPT=${FACTS_SCRIPT:-"$bundle_dir/db_facts.py"}
for path in "$CA_PATH" "$SOURCE_FACTS_ENV" "$TARGET_FACTS_ENV" "$FACTS_SCRIPT"; do
  [[ -f "$path" && ! -L "$path" ]] || fail "required backup input is missing"
done
run_id=$(date -u +%Y%m%dT%H%M%SZ)
root=/srv/journey-next-production/backups/$run_id
install -d -m 0700 "$root"
plain="$root/journey-next.dump"
encrypted="$root/journey-next.dump.enc"
source_facts="$root/source-facts.json"
source_facts_before="$root/source-facts-before.json"
target_facts="$root/target-facts.json"
manifest="$root/backup-manifest.json"
verify_dump="$root/journey-next.verify.dump"
cleanup_plaintext() {
  rm -f -- "$plain" "$verify_dump"
}
trap cleanup_plaintext EXIT

pg() {
  docker run --rm --network host \
    -e PGPASSWORD="$MIGRATION_DB_PASSWORD" \
    -e PGSSLMODE=verify-full \
    -e PGSSLROOTCERT=/run/secrets/volcengine-rds-ca.pem \
    -v "$CA_PATH:/run/secrets/volcengine-rds-ca.pem:ro" \
    -v "$root:/backup" \
    "$DBTOOL_IMAGE" "$@"
}

target_tables=$(pg psql -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator -d "$TARGET_DATABASE" -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
[[ "$target_tables" == "0" ]] || fail "TARGET_DATABASE_NOT_EMPTY"

docker run --rm --network host \
  --env-file "$SOURCE_FACTS_ENV" \
  -v "$CA_PATH:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$FACTS_SCRIPT:/tmp/db_facts.py:ro" \
  "$API_IMAGE" python /tmp/db_facts.py >"$source_facts_before"

pg pg_dump -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator -d "$SOURCE_DATABASE" \
  --format=custom --compress=9 --no-owner --no-acl --file=/backup/journey-next.dump

docker run --rm --network host \
  --env-file "$SOURCE_FACTS_ENV" \
  -v "$CA_PATH:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$FACTS_SCRIPT:/tmp/db_facts.py:ro" \
  "$API_IMAGE" python /tmp/db_facts.py >"$source_facts"

cmp -s "$source_facts_before" "$source_facts" || fail "source business facts changed during backup"

pg pg_restore -h "$RDS_HOST" -p "$RDS_PORT" -U journey_next_migrator -d "$TARGET_DATABASE" \
  --exit-on-error --no-owner --no-acl /backup/journey-next.dump

docker run --rm --network host \
  --env-file "$TARGET_FACTS_ENV" \
  -v "$CA_PATH:/run/secrets/volcengine-rds-ca.pem:ro" \
  -v "$FACTS_SCRIPT:/tmp/db_facts.py:ro" \
  "$API_IMAGE" python /tmp/db_facts.py >"$target_facts"

cmp -s "$source_facts" "$target_facts" || fail "restored database facts differ from source snapshot"
python3 - "$source_facts" <<'PY'
import json, sys
value=json.load(open(sys.argv[1]))
assert value["migration"] == "0014_wp12_data_lifecycle"
assert len(value["schema_sha256"]) == 64
assert value["counts"]
assert value["content_fingerprints"]
assert value["active_notification_recipients"] == 0
PY

plain_sha=$(sha256sum "$plain" | awk '{print $1}')
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt \
  -in "$plain" -out "$encrypted" -pass env:WP15_BACKUP_KEY
rm -f "$plain"
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -in "$encrypted" -out "$verify_dump" -pass env:WP15_BACKUP_KEY
[[ "$(sha256sum "$verify_dump" | awk '{print $1}')" == "$plain_sha" ]] || fail "encrypted backup decrypt verification failed"
rm -f "$verify_dump"
encrypted_sha=$(sha256sum "$encrypted" | awk '{print $1}')
facts_sha=$(sha256sum "$source_facts" | awk '{print $1}')
WP15_BACKUP_KEY="$WP15_BACKUP_KEY" python3 - "$manifest" "$run_id" "$plain_sha" "$encrypted_sha" "$facts_sha" "$TARGET_DATABASE" <<'PY'
import hashlib, hmac, json, os, sys
path, run_id, plain_sha, encrypted_sha, facts_sha, target_database = sys.argv[1:]
body = {
  "schema_version": 1,
  "run_id": run_id,
  "candidate_sha": "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
  "source_database": "journey_next_staging",
  "isolated_restore_database": target_database,
  "migration": "0014_wp12_data_lifecycle",
  "decrypted_backup_sha256": plain_sha,
  "encrypted_backup_sha256": encrypted_sha,
  "pii_free_facts_sha256": facts_sha,
  "backup": "PASS",
  "restore": "PASS",
  "encrypted_artifact_decrypt_verified": True,
  "active_notification_recipients": 0,
  "source_modified": False,
}
canonical=json.dumps(body,sort_keys=True,separators=(",",":")).encode()
body["manifest_hmac_sha256"] = hmac.new(os.environ["WP15_BACKUP_KEY"].encode(), canonical, hashlib.sha256).hexdigest()
open(path,"w").write(json.dumps(body,sort_keys=True,indent=2)+"\n")
PY
chmod 0600 "$encrypted" "$manifest" "$source_facts" "$target_facts"
printf 'WP15_BACKUP_RESTORE=PASS artifact=%s\n' "$root"
