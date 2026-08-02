#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WP15_SCHEMA_AUDIT_ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "schema_audit.sh must run as root"
[[ "${TARGET_DATABASE:-}" == "journey_next_production" ]] || fail "unexpected target database"
[[ "${DBTOOL_IMAGE:-}" == *"@sha256:"* ]] || fail "database tool is not digest pinned"

umask 077
bundle_dir=$(pwd -P)
CA_PATH=${CA_PATH:-"$bundle_dir/secrets/volcengine-rds-ca.pem"}
[[ -f "$CA_PATH" && ! -L "$CA_PATH" ]] || fail "RDS CA is missing"

row=$(
  docker run --rm --network host \
    -e PGPASSWORD="$MIGRATION_DB_PASSWORD" \
    -e PGSSLMODE=verify-full \
    -e PGSSLROOTCERT=/run/secrets/volcengine-rds-ca.pem \
    -e PGOPTIONS='-c default_transaction_read_only=on' \
    -v "$CA_PATH:/run/secrets/volcengine-rds-ca.pem:ro" \
    "$DBTOOL_IMAGE" psql \
      -h "$RDS_HOST" -p "$RDS_PORT" \
      -U journey_next_migrator -d "$TARGET_DATABASE" \
      -qAt -F '|' -v ON_ERROR_STOP=1 -c \
      "SELECT
         pg_get_userbyid(n.nspowner),
         COALESCE(n.nspacl::text, 'DEFAULT'),
         (SELECT count(*) FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'),
         has_schema_privilege('journey_next_migrator', 'public', 'USAGE'),
         has_schema_privilege('journey_next_migrator', 'public', 'CREATE')
       FROM pg_namespace n
       WHERE n.nspname='public'"
)

IFS='|' read -r owner acl table_count migrator_usage migrator_create <<<"$row"
[[ "$owner" =~ ^[a-z_][a-z0-9_]*$ ]] || fail "schema owner result is invalid"
[[ "$acl" != *$'\n'* && "$acl" != *'|'* && ${#acl} -le 1024 ]] || fail "schema ACL result is invalid"
[[ "$table_count" =~ ^[0-9]+$ ]] || fail "table count result is invalid"
for value in "$migrator_usage" "$migrator_create"; do
  [[ "$value" == "t" || "$value" == "f" ]] || fail "schema privilege result is invalid"
done

printf 'WP15_PRODUCTION_PUBLIC_SCHEMA owner=%s acl=%s table_count=%s migrator_usage=%s migrator_create=%s\n' \
  "$owner" "$acl" "$table_count" "$migrator_usage" "$migrator_create"

[[ "$table_count" == "0" ]] || fail "TARGET_DATABASE_NOT_EMPTY table_count=$table_count"
printf 'WP15_PRODUCTION_PUBLIC_SCHEMA_AUDIT=PASS mutation=false target_empty=true\n'
