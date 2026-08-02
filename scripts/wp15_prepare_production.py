#!/usr/bin/env python3
"""Create owner-only production and backup env files without printing values."""

from __future__ import annotations

import argparse
import base64
import os
import re
from pathlib import Path
from urllib.parse import quote


CANDIDATE = "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a"
PRODUCTION_HOST = "journey.muchenai.com"
PRODUCTION_DATABASE = "journey_next_production"
STAGING_DATABASE = "journey_next_staging"
IMAGES = {
    "API_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@sha256:553055d921f75bc7f7df0e176d5176f0546ee7f75f37e9757a0be09edf3520ff",
    "WEB_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:401e5158fdcf7be11a3b2539fdbeb7c222ff9813267aa7c3cbcd7a2f9e24f1f5",
    "WORKER_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-worker@sha256:16bf2c7515d68fab164704438b23f691917213c8946a8c3dff8a4116fb3df0c7",
}
DBTOOL_IMAGE = "ghcr.io/muchenai2024-creator/muchen-journey-vnext-dbtool@sha256:3a82828474772d2b9c94fb51ae343e464c2f13dd1f2d7d90c807a46b104f53e9"


class PrepareError(RuntimeError):
    pass


def require(name: str, minimum: int = 1) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum or "\n" in value or "\r" in value:
        raise PrepareError(f"required environment variable is invalid: {name}")
    return value


def dsn(user: str, password: str, host: str, port: int, database: str) -> str:
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )


def write_env(path: Path, values: dict[str, str], mode: int = 0o600) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or "\n" in value or "\r" in value:
            raise PrepareError(f"unsafe env value: {key}")
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(mode)


def prepare(output: Path, host: str, port: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or host in {"localhost", "127.0.0.1"}:
        raise PrepareError("RDS host is invalid")
    if not 1 <= port <= 65535:
        raise PrepareError("RDS port is invalid")
    migration_password = require("WP08_MIGRATION_DB_PASSWORD", 20)
    runtime_password = require("WP08_RUNTIME_DB_PASSWORD", 20)
    session_secret = require("WP15_SESSION_SECRET", 32)
    invite_secret = require("WP15_INVITE_SECRET", 32)
    import_key = require("WP15_IMPORT_SIGNING_KEY", 32)
    backup_key = require("WP15_BACKUP_KEY", 32)
    identity_secret = require("WP09_IDENTITY_SUBJECT_SECRET", 32)
    feishu_app_id = require("WP09_FEISHU_APP_ID", 3)
    feishu_app_secret = require("WP09_FEISHU_APP_SECRET", 16)
    recipient_key = require("WP11_NOTIFICATION_RECIPIENT_KEY", 32)
    notify_app_id = require("WP11_FEISHU_APP_ID", 3)
    notify_app_secret = require("WP11_FEISHU_APP_SECRET", 16)
    acme_email = require("WP08_ACME_EMAIL", 5)
    ca_b64 = require("WP08_RDS_CA_PEM_B64", 20)
    if len({session_secret, invite_secret, import_key, backup_key}) != 4:
        raise PrepareError("production application and backup secrets must be independent")

    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    secrets = output / "secrets"
    secrets.mkdir(mode=0o700)
    runtime_url = dsn("journey_next_runtime", runtime_password, host, port, PRODUCTION_DATABASE)
    migration_url = dsn("journey_next_migrator", migration_password, host, port, PRODUCTION_DATABASE)
    source_url = dsn("journey_next_migrator", migration_password, host, port, STAGING_DATABASE)
    shared = {
        "APP_ENV": "production",
        "APP_RELEASE": CANDIDATE,
        "CONFIG_SCHEMA_VERSION": "3",
        "ALLOWED_HOSTS": f"{PRODUCTION_HOST},production-api,localhost,127.0.0.1",
        "ALLOW_FIXTURE_IDENTITY": "false",
        "SESSION_SECRET": session_secret,
        "INVITE_SECRET": invite_secret,
        "IMPORT_SIGNING_KEY": import_key,
        "IDENTITY_SUBJECT_SECRET": identity_secret,
        "FEISHU_OAUTH_ENABLED": "true",
        "FEISHU_APP_ID": feishu_app_id,
        "FEISHU_APP_SECRET": feishu_app_secret,
        "FEISHU_OAUTH_REDIRECT_URI": f"https://{PRODUCTION_HOST}/auth/feishu/callback",
        "ATTACHMENTS_ENABLED": "false",
        "NOTIFICATION_CHANNEL": "FEISHU",
        "NOTIFICATION_RECIPIENTS_ENABLED": "true",
        "NOTIFICATION_RECIPIENT_KEY": recipient_key,
        "DB_POOL_SIZE": "20",
        "DB_MAX_OVERFLOW": "5",
        "DB_POOL_TIMEOUT_SECONDS": "5",
    }
    write_env(secrets / "api.env", {**shared, "DATABASE_URL": runtime_url})
    write_env(secrets / "migration.env", {**shared, "DATABASE_URL": migration_url})
    write_env(secrets / "source-facts.env", {**shared, "DATABASE_URL": source_url})
    write_env(secrets / "target-facts.env", {**shared, "DATABASE_URL": migration_url})
    write_env(secrets / "worker.env", {
        "APP_ENV": "production", "APP_RELEASE": CANDIDATE, "DATABASE_URL": runtime_url,
        "NOTIFICATION_ADAPTER": "FEISHU", "NOTIFICATION_RECIPIENT_KEY": recipient_key,
        "FEISHU_NOTIFICATION_APP_ID": notify_app_id, "FEISHU_NOTIFICATION_APP_SECRET": notify_app_secret,
        "NOTIFICATION_RESULT_URL": f"https://{PRODUCTION_HOST}/app/result",
        "NOTIFICATION_PROVIDER_TIMEOUT_SECONDS": "10", "OBSERVABILITY_SNAPSHOT_SECONDS": "60",
        "DB_POOL_SIZE": "2", "DB_MAX_OVERFLOW": "1", "DB_POOL_TIMEOUT_SECONDS": "5",
        "NOTIFICATION_MAX_ATTEMPTS": "3", "NOTIFICATION_RETRY_BASE_SECONDS": "5",
        "OUTBOX_LEASE_SECONDS": "30", "WORKER_POLL_SECONDS": "2",
    })
    write_env(secrets / "web.env", {
        "APP_ENV": "production", "APP_RELEASE": CANDIDATE, "CONFIG_SCHEMA_VERSION": "3",
        "API_INTERNAL_URL": "http://production-api:8000", "ALLOW_FIXTURE_IDENTITY": "false",
    })
    write_env(secrets / "backup.env", {
        "SOURCE_DATABASE": STAGING_DATABASE, "TARGET_DATABASE": PRODUCTION_DATABASE,
        "RDS_HOST": host, "RDS_PORT": str(port), "MIGRATION_DB_PASSWORD": migration_password,
        "WP15_BACKUP_KEY": backup_key, "DBTOOL_IMAGE": DBTOOL_IMAGE, "API_IMAGE": IMAGES["API_IMAGE"],
    })
    try:
        ca = base64.b64decode(ca_b64, validate=True)
    except ValueError as error:
        raise PrepareError("RDS CA is invalid Base64") from error
    if b"-----BEGIN CERTIFICATE-----" not in ca:
        raise PrepareError("RDS CA is not PEM")
    ca_path = secrets / "volcengine-rds-ca.pem"
    ca_path.write_bytes(ca)
    ca_path.chmod(0o444)
    write_env(output / ".deployment.env", {
        "CANDIDATE_COMMIT": CANDIDATE, "PRODUCTION_HOST": PRODUCTION_HOST,
        "PRODUCTION_DATABASE": PRODUCTION_DATABASE, **IMAGES,
    })
    write_env(output / "edge.env", {
        "STAGING_HOST": "staging-vnext.muchenai.com", "PRODUCTION_HOST": PRODUCTION_HOST,
        "ACME_EMAIL": acme_email,
    })
    print("WP15_PRODUCTION_BUNDLE=READY secret_values_printed=false")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rds-host", required=True)
    parser.add_argument("--rds-port", type=int, required=True)
    args = parser.parse_args()
    try:
        prepare(args.output, args.rds_host, args.rds_port)
    except (OSError, PrepareError) as error:
        raise SystemExit(f"WP15_PREPARE_ERROR: {error}") from error


if __name__ == "__main__":
    main()
