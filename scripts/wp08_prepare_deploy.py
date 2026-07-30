#!/usr/bin/env python3
"""Prepare mode-0600 staging env files without printing secret values."""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import quote


CANDIDATE = "222096db506e95db887a8705b22ca4a439d0545d"
STAGING_HOST = "staging-vnext.muchenai.com"
IMAGES = {
    "API_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@sha256:6c98bdf2b4bead95618a4d9ef7116af79fa75b242af05079653056fc81dcbb13",
    "WEB_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:a940420f58eb6ef085926c442996f40b66b6870136272c565bfb9b1c2656d1c2",
    "WORKER_IMAGE": "ghcr.io/muchenai2024-creator/muchen-journey-vnext-worker@sha256:2d505fa9a3e4d37a38cded5ea2789274192eafde039ec05bdc5f9a44957525b7",
}
SECRET_NAMES = (
    "WP08_MIGRATION_DB_PASSWORD",
    "WP08_RUNTIME_DB_PASSWORD",
    "WP08_SESSION_SECRET",
    "WP08_INVITE_SECRET",
    "WP08_IMPORT_SIGNING_KEY",
    "WP09_IDENTITY_SUBJECT_SECRET",
    "WP09_FEISHU_APP_ID",
    "WP09_FEISHU_APP_SECRET",
    "WP11_NOTIFICATION_RECIPIENT_KEY",
    "WP11_FEISHU_APP_ID",
    "WP11_FEISHU_APP_SECRET",
    "WP08_RDS_CA_PEM_B64",
)


class PrepareError(RuntimeError):
    pass


def required_environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in (*SECRET_NAMES, "WP08_ACME_EMAIL"):
        value = os.getenv(name, "")
        if not value:
            raise PrepareError(f"required environment variable is absent: {name}")
        if "\n" in value or "\r" in value:
            raise PrepareError(f"environment variable contains a newline: {name}")
        values[name] = value
    independent = {
        values["WP08_MIGRATION_DB_PASSWORD"],
        values["WP08_RUNTIME_DB_PASSWORD"],
        values["WP08_SESSION_SECRET"],
        values["WP08_INVITE_SECRET"],
        values["WP08_IMPORT_SIGNING_KEY"],
        values["WP09_IDENTITY_SUBJECT_SECRET"],
        values["WP09_FEISHU_APP_SECRET"],
        values["WP11_NOTIFICATION_RECIPIENT_KEY"],
        values["WP11_FEISHU_APP_SECRET"],
    }
    if len(independent) != 9:
        raise PrepareError("database and application secrets must all be independent")
    minimum_length_secrets = (
        "WP08_SESSION_SECRET",
        "WP08_INVITE_SECRET",
        "WP08_IMPORT_SIGNING_KEY",
        "WP09_IDENTITY_SUBJECT_SECRET",
    )
    for name in minimum_length_secrets:
        if len(values[name]) < 32:
            raise PrepareError(f"{name} must contain at least 32 characters")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", values["WP09_FEISHU_APP_ID"]):
        raise PrepareError("WP09_FEISHU_APP_ID is invalid")
    if len(values["WP09_FEISHU_APP_SECRET"]) < 16:
        raise PrepareError("WP09_FEISHU_APP_SECRET must contain at least 16 characters")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", values["WP11_FEISHU_APP_ID"]):
        raise PrepareError("WP11_FEISHU_APP_ID is invalid")
    if values["WP11_FEISHU_APP_ID"] == values["WP09_FEISHU_APP_ID"]:
        raise PrepareError("WP11 Feishu notification app must be independent")
    if len(values["WP11_FEISHU_APP_SECRET"]) < 16:
        raise PrepareError("WP11_FEISHU_APP_SECRET must contain at least 16 characters")
    try:
        encoded_recipient_key = values["WP11_NOTIFICATION_RECIPIENT_KEY"]
        recipient_key = base64.b64decode(
            (
                encoded_recipient_key
                + "=" * (-len(encoded_recipient_key) % 4)
            ).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeEncodeError, binascii.Error) as error:
        raise PrepareError(
            "WP11_NOTIFICATION_RECIPIENT_KEY must be URL-safe Base64"
        ) from error
    if len(recipient_key) != 32:
        raise PrepareError(
            "WP11_NOTIFICATION_RECIPIENT_KEY must decode to exactly 32 bytes"
        )
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["WP08_ACME_EMAIL"]):
        raise PrepareError("WP08_ACME_EMAIL is invalid")
    return values


def dsn(user: str, password: str, host: str, port: int) -> str:
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/journey_next_staging"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )


def write_env(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise PrepareError(f"invalid env key: {key}")
        if "\n" in value or "\r" in value:
            raise PrepareError(f"env value contains newline: {key}")
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)


def prepare(output: Path, host: str, port: int) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or host in {"localhost", "127.0.0.1"}:
        raise PrepareError("RDS host must be one non-local DNS name")
    if port < 1 or port > 65535:
        raise PrepareError("RDS port is invalid")
    values = required_environment()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    secrets = output / "secrets"
    secrets.mkdir(mode=0o700)

    runtime_url = dsn(
        "journey_next_runtime", values["WP08_RUNTIME_DB_PASSWORD"], host, port
    )
    migration_url = dsn(
        "journey_next_migrator", values["WP08_MIGRATION_DB_PASSWORD"], host, port
    )
    shared_api = {
        "APP_ENV": "staging",
        "APP_RELEASE": CANDIDATE,
        "CONFIG_SCHEMA_VERSION": "3",
        "ALLOWED_HOSTS": f"{STAGING_HOST},api,localhost,127.0.0.1",
        "ALLOW_FIXTURE_IDENTITY": "false",
        "SESSION_SECRET": values["WP08_SESSION_SECRET"],
        "INVITE_SECRET": values["WP08_INVITE_SECRET"],
        "IMPORT_SIGNING_KEY": values["WP08_IMPORT_SIGNING_KEY"],
        "IDENTITY_SUBJECT_SECRET": values["WP09_IDENTITY_SUBJECT_SECRET"],
        "FEISHU_OAUTH_ENABLED": "true",
        "FEISHU_APP_ID": values["WP09_FEISHU_APP_ID"],
        "FEISHU_APP_SECRET": values["WP09_FEISHU_APP_SECRET"],
        "FEISHU_OAUTH_REDIRECT_URI": f"https://{STAGING_HOST}/auth/feishu/callback",
        "ATTACHMENTS_ENABLED": "false",
        "NOTIFICATION_CHANNEL": "FEISHU",
        "NOTIFICATION_RECIPIENTS_ENABLED": "true",
        "NOTIFICATION_RECIPIENT_KEY": values["WP11_NOTIFICATION_RECIPIENT_KEY"],
        "DB_POOL_SIZE": "20",
        "DB_MAX_OVERFLOW": "5",
        "DB_POOL_TIMEOUT_SECONDS": "5",
    }
    write_env(secrets / "api.env", {**shared_api, "DATABASE_URL": runtime_url})
    write_env(secrets / "migration.env", {**shared_api, "DATABASE_URL": migration_url})
    write_env(
        secrets / "worker.env",
        {
            "APP_ENV": "staging",
            "APP_RELEASE": CANDIDATE,
            "DATABASE_URL": runtime_url,
            "NOTIFICATION_ADAPTER": "FEISHU",
            "NOTIFICATION_RECIPIENT_KEY": values[
                "WP11_NOTIFICATION_RECIPIENT_KEY"
            ],
            "FEISHU_NOTIFICATION_APP_ID": values["WP11_FEISHU_APP_ID"],
            "FEISHU_NOTIFICATION_APP_SECRET": values[
                "WP11_FEISHU_APP_SECRET"
            ],
            "NOTIFICATION_RESULT_URL": f"https://{STAGING_HOST}/app/result",
            "NOTIFICATION_PROVIDER_TIMEOUT_SECONDS": "10",
            "OBSERVABILITY_SNAPSHOT_SECONDS": "60",
            "DB_POOL_SIZE": "2",
            "DB_MAX_OVERFLOW": "1",
            "DB_POOL_TIMEOUT_SECONDS": "5",
            "NOTIFICATION_MAX_ATTEMPTS": "3",
            "NOTIFICATION_RETRY_BASE_SECONDS": "5",
            "OUTBOX_LEASE_SECONDS": "30",
            "WORKER_POLL_SECONDS": "2",
        },
    )
    write_env(
        secrets / "web.env",
        {
            "APP_ENV": "staging",
            "APP_RELEASE": CANDIDATE,
            "CONFIG_SCHEMA_VERSION": "3",
            "API_INTERNAL_URL": "http://api:8000",
            "ALLOW_FIXTURE_IDENTITY": "false",
        },
    )
    write_env(
        secrets / "edge.env",
        {
            "STAGING_HOST": STAGING_HOST,
            "ACME_EMAIL": values["WP08_ACME_EMAIL"],
        },
    )
    try:
        ca_bytes = base64.b64decode(values["WP08_RDS_CA_PEM_B64"], validate=True)
    except ValueError as error:
        raise PrepareError("WP08_RDS_CA_PEM_B64 is not valid base64") from error
    if b"-----BEGIN CERTIFICATE-----" not in ca_bytes or b"-----END CERTIFICATE-----" not in ca_bytes:
        raise PrepareError("decoded RDS CA is not PEM")
    ca_path = secrets / "volcengine-rds-ca.pem"
    ca_path.write_bytes(ca_bytes)
    # The CA certificate is public trust material and must be readable by the
    # non-root API/worker user inside the bind-mounted container.
    ca_path.chmod(0o444)
    write_env(
        output / ".deployment.env",
        {
            "CANDIDATE_COMMIT": CANDIDATE,
            "STAGING_HOST": STAGING_HOST,
            **IMAGES,
        },
    )
    private_paths = (
        secrets / "api.env",
        secrets / "migration.env",
        secrets / "worker.env",
        secrets / "web.env",
        secrets / "edge.env",
        output / ".deployment.env",
    )
    expected_secret_paths = {*private_paths[:-1], ca_path}
    if set(secrets.iterdir()) != expected_secret_paths:
        raise PrepareError("deploy bundle contains an unexpected secret file")
    for path in private_paths:
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise PrepareError(f"incorrect mode for {path.name}")
    if stat.S_IMODE(ca_path.stat().st_mode) != 0o444:
        raise PrepareError("incorrect mode for volcengine-rds-ca.pem")
    print(f"WP08_DEPLOY_BUNDLE=READY path={output} secret_files=6")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rds-host", required=True)
    parser.add_argument("--rds-port", type=int, required=True)
    args = parser.parse_args()
    try:
        prepare(args.output, args.rds_host, args.rds_port)
    except (OSError, PrepareError) as error:
        print(f"WP08_PREPARE_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
