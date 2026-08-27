#!/usr/bin/env python3
"""Create and verify the one exact WP-15 production database via RDS API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.wp08_dns_record import canonical_query, signed_headers


API_HOST = "rds-postgresql.cn-beijing.volcengineapi.com"
API_REGION = "cn-beijing"
API_SERVICE = "rds_postgresql"
API_VERSION = "2022-01-01"
DATABASE_NAME = "journey_next_production"
RESTORE_DATABASE_NAME = "journey_next_restore_20260803"
WARTIME_DATABASE_NAME = "journey_next_cutover_20260810"
GREENFIELD_CANARY_DATABASE_NAME = "journey_next_canary_20260827_1bccbbf"
ALLOWED_DATABASES = {
    DATABASE_NAME,
    RESTORE_DATABASE_NAME,
    WARTIME_DATABASE_NAME,
    GREENFIELD_CANARY_DATABASE_NAME,
}
OWNER = "journey_next_migrator"
CHARACTER_SET = "utf8"
COLLATE = "C.UTF-8"
C_TYPE = "C.UTF-8"
INSTANCE_ID = re.compile(r"^postgres-[A-Za-z0-9]{8,64}$")


class ProductionDatabaseError(RuntimeError):
    pass


def _request(
    action: str,
    body_value: dict[str, object],
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
) -> dict[str, object]:
    if action not in {"CreateDatabase", "DescribeDatabases"}:
        raise ProductionDatabaseError("unsupported RDS action")
    parameters = {"Action": action, "Version": API_VERSION}
    body = json.dumps(body_value, separators=(",", ":")).encode()
    request = Request(
        f"https://{API_HOST}/?{canonical_query(parameters)}",
        data=body,
        headers=signed_headers(
            parameters,
            access_key,
            secret_key,
            service=API_SERVICE,
            region=API_REGION,
            host=API_HOST,
            method="POST",
            body=body,
            content_type="application/json",
            session_token=session_token,
        ),
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS host
            raw = response.read(1_000_001)
    except HTTPError as error:
        try:
            payload = json.loads(error.read(1_000_001))
            metadata = payload.get("ResponseMetadata", {})
            api_error = metadata.get("Error", {}) if isinstance(metadata, dict) else {}
            code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            code = "UNKNOWN"
        raise ProductionDatabaseError(f"RDS API rejected {action} ({code})") from error
    except URLError as error:
        raise ProductionDatabaseError(f"RDS API request failed for {action}") from error
    if len(raw) > 1_000_000:
        raise ProductionDatabaseError("RDS API response exceeded the safety limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionDatabaseError("RDS API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ProductionDatabaseError("RDS API response must be an object")
    metadata = payload.get("ResponseMetadata")
    if isinstance(metadata, dict) and metadata.get("Error"):
        api_error = metadata["Error"]
        code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        raise ProductionDatabaseError(f"RDS API rejected {action} ({code})")
    result = payload.get("Result")
    return result if isinstance(result, dict) else {}


def _database(result: dict[str, object], database_name: str = DATABASE_NAME) -> dict[str, object] | None:
    databases = result.get("Databases")
    if databases is None:
        return None
    if not isinstance(databases, list):
        raise ProductionDatabaseError("RDS database list is invalid")
    matches = [
        item
        for item in databases
        if isinstance(item, dict) and item.get("DBName") == database_name
    ]
    if len(matches) > 1:
        raise ProductionDatabaseError("RDS returned duplicate production databases")
    return matches[0] if matches else None


def validate_database(database: dict[str, object], database_name: str = DATABASE_NAME) -> None:
    expected = {
        "DBName": database_name,
        "CharacterSetName": CHARACTER_SET,
        "Collate": COLLATE,
        "CType": C_TYPE,
        "Owner": OWNER,
        "DBStatus": "Available",
    }
    mismatches = [key for key, value in expected.items() if database.get(key) != value]
    if mismatches:
        raise ProductionDatabaseError(
            "production database does not match the frozen contract: "
            + ",".join(sorted(mismatches))
        )


def create_and_verify(
    instance_id: str,
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
    attempts: int = 20,
    interval_seconds: float = 3.0,
    sleeper: Callable[[float], None] = time.sleep,
    database_name: str = DATABASE_NAME,
) -> str:
    if not INSTANCE_ID.fullmatch(instance_id):
        raise ProductionDatabaseError("RDS instance identifier is invalid")
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if database_name not in ALLOWED_DATABASES:
        raise ProductionDatabaseError("database is outside the reviewed allowlist")
    lookup = {"InstanceId": instance_id, "DBName": database_name}
    existing = _database(
        _request(
            "DescribeDatabases",
            lookup,
            access_key,
            secret_key,
            session_token=session_token,
        ),
        database_name,
    )
    if existing is not None:
        validate_database(existing, database_name)
        return "EXACT_DATABASE_ALREADY_PRESENT"

    _request(
        "CreateDatabase",
        {
            **lookup,
            "CharacterSetName": CHARACTER_SET,
            "Collate": COLLATE,
            "CType": C_TYPE,
            "Owner": OWNER,
        },
        access_key,
        secret_key,
        session_token=session_token,
    )
    for attempt in range(1, attempts + 1):
        database = _database(
            _request(
                "DescribeDatabases",
                lookup,
                access_key,
                secret_key,
                session_token=session_token,
            ),
            database_name,
        )
        if database is not None and database.get("DBStatus") == "Available":
            validate_database(database, database_name)
            return "CREATED_AND_VERIFIED"
        if attempt < attempts:
            sleeper(interval_seconds)
    raise ProductionDatabaseError("production database did not become available in time")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--database", choices=sorted(ALLOWED_DATABASES), default=DATABASE_NAME)
    args = parser.parse_args()
    access_key = os.environ.get("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.environ.get("VOLCENGINE_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise ProductionDatabaseError("Volcengine workflow credentials are missing")
    outcome = create_and_verify(
        args.instance_id,
        access_key,
        secret_key,
        session_token=os.environ.get("VOLCENGINE_SESSION_TOKEN", ""),
        database_name=args.database,
    )
    print(f"WP15_PRODUCTION_DATABASE=PASS outcome={outcome}")


if __name__ == "__main__":
    try:
        main()
    except ProductionDatabaseError as error:
        print(f"WP15_PRODUCTION_DATABASE_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
