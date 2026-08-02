#!/usr/bin/env python3
"""Repair the one empty WP-15 production public schema owner via RDS API."""

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
SCHEMA_NAME = "public"
OWNER = "journey_next_migrator"
EXPECTED_PREVIOUS_OWNER = "pg_rds_superuser"
INSTANCE_ID = re.compile(r"^postgres-[A-Za-z0-9]{8,64}$")


class ProductionSchemaOwnerError(RuntimeError):
    pass


def _request(
    action: str,
    body_value: dict[str, object],
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
) -> dict[str, object]:
    if action not in {"DescribeSchemas", "ModifySchemaOwner"}:
        raise ProductionSchemaOwnerError("unsupported RDS action")
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
        raise ProductionSchemaOwnerError(f"RDS API rejected {action} ({code})") from error
    except URLError as error:
        raise ProductionSchemaOwnerError(f"RDS API request failed for {action}") from error
    if len(raw) > 1_000_000:
        raise ProductionSchemaOwnerError("RDS API response exceeded the safety limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionSchemaOwnerError("RDS API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ProductionSchemaOwnerError("RDS API response must be an object")
    metadata = payload.get("ResponseMetadata")
    if isinstance(metadata, dict) and metadata.get("Error"):
        api_error = metadata["Error"]
        code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        raise ProductionSchemaOwnerError(f"RDS API rejected {action} ({code})")
    result = payload.get("Result")
    return result if isinstance(result, dict) else {}


def _schema(result: dict[str, object]) -> dict[str, object]:
    schemas = result.get("Schemas")
    if not isinstance(schemas, list):
        raise ProductionSchemaOwnerError("RDS schema list is invalid")
    matches = [
        item
        for item in schemas
        if isinstance(item, dict)
        and item.get("DBName") == DATABASE_NAME
        and item.get("SchemaName") == SCHEMA_NAME
    ]
    if len(matches) != 1:
        raise ProductionSchemaOwnerError("expected exactly one production public schema")
    return matches[0]


def repair_and_verify(
    instance_id: str,
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
    attempts: int = 20,
    interval_seconds: float = 3.0,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    if not INSTANCE_ID.fullmatch(instance_id):
        raise ProductionSchemaOwnerError("RDS instance identifier is invalid")
    if attempts < 1:
        raise ValueError("attempts must be positive")
    lookup = {
        "InstanceId": instance_id,
        "DBName": DATABASE_NAME,
        "PageNumber": 1,
        "PageSize": 100,
    }
    current = _schema(
        _request(
            "DescribeSchemas",
            lookup,
            access_key,
            secret_key,
            session_token=session_token,
        )
    )
    current_owner = current.get("Owner")
    if current_owner == OWNER:
        return "EXACT_OWNER_ALREADY_PRESENT"
    if current_owner != EXPECTED_PREVIOUS_OWNER:
        raise ProductionSchemaOwnerError("production public schema owner changed unexpectedly")

    _request(
        "ModifySchemaOwner",
        {
            "InstanceId": instance_id,
            "SchemaInfo": [
                {"DBName": DATABASE_NAME, "SchemaName": SCHEMA_NAME, "Owner": OWNER}
            ],
        },
        access_key,
        secret_key,
        session_token=session_token,
    )
    for attempt in range(1, attempts + 1):
        updated = _schema(
            _request(
                "DescribeSchemas",
                lookup,
                access_key,
                secret_key,
                session_token=session_token,
            )
        )
        if updated.get("Owner") == OWNER:
            return "OWNER_REPAIRED_AND_VERIFIED"
        if attempt < attempts:
            sleeper(interval_seconds)
    raise ProductionSchemaOwnerError("production public schema owner did not converge in time")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    access_key = os.environ.get("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.environ.get("VOLCENGINE_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise ProductionSchemaOwnerError("Volcengine workflow credentials are missing")
    outcome = repair_and_verify(
        args.instance_id,
        access_key,
        secret_key,
        session_token=os.environ.get("VOLCENGINE_SESSION_TOKEN", ""),
    )
    print(f"WP15_PRODUCTION_SCHEMA_OWNER=PASS outcome={outcome}")


if __name__ == "__main__":
    try:
        main()
    except ProductionSchemaOwnerError as error:
        print(f"WP15_PRODUCTION_SCHEMA_OWNER_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
