#!/usr/bin/env python3
"""PII-free, read-only inventory of the current staging runtime revisions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


CONTAINERS = {
    "api": "journey-next-staging-api-1",
    "worker": "journey-next-staging-worker-1",
    "web": "journey-next-staging-web-1",
}
DEPLOYED_CANDIDATE = Path("/srv/journey-next-staging/DEPLOYED_CANDIDATE")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MIGRATION_REVISION = re.compile(r"^\d{4}_[a-z0-9_]+$")


class InventoryError(RuntimeError):
    """Raised when a safe, unambiguous runtime inventory cannot be produced."""


def _run(*command: str) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _inspect_running_container(name: str) -> None:
    raw = _run("docker", "inspect", name)
    values = json.loads(raw)
    if not isinstance(values, list) or len(values) != 1:
        raise InventoryError("container inspect result is ambiguous")
    value = values[0]
    if not isinstance(value, dict):
        raise InventoryError("container inspect result is invalid")
    if value.get("Name", "").lstrip("/") != name:
        raise InventoryError("container identity differs")
    if value.get("State", {}).get("Running") is not True:
        raise InventoryError("container is not running")


def _container_json(container: str, code: str) -> dict[str, Any]:
    raw = _run("docker", "exec", container, "python", "-c", code)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise InventoryError("container inventory result is invalid")
    return payload


def _require_release(value: object, label: str) -> str:
    if not isinstance(value, str) or not FULL_SHA.fullmatch(value):
        raise InventoryError(f"{label} is not a full release SHA")
    return value


def collect(candidate: str) -> dict[str, object]:
    if not FULL_SHA.fullmatch(candidate):
        raise InventoryError("candidate must be a full release SHA")
    deployed = DEPLOYED_CANDIDATE.read_text().strip()
    _require_release(deployed, "deployed candidate marker")
    if deployed != candidate:
        raise InventoryError("deployed candidate differs from authorized candidate")

    for container in CONTAINERS.values():
        _inspect_running_container(container)

    api = _container_json(
        CONTAINERS["api"],
        r'''
import json
import urllib.request
from sqlalchemy import text
from journey_api.config import get_settings
from journey_api.db import SessionLocal

session = SessionLocal()
try:
    revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
finally:
    session.close()
settings = get_settings()
health = json.loads(urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3).read())
print(json.dumps({
    "release": settings.app_release,
    "config_schema_version": settings.config_schema_version,
    "migration_revision": revision,
    "health_status": health.get("status"),
    "health_release": health.get("release"),
}, separators=(",", ":"), sort_keys=True))
''',
    )
    worker = _container_json(
        CONTAINERS["worker"],
        r'''
import json
import os
from datetime import UTC, datetime, timedelta
from sqlalchemy import text
from journey_api.db import SessionLocal

session = SessionLocal()
try:
    row = session.execute(text(
        "SELECT release,last_seen_at FROM worker_heartbeats "
        "WHERE worker_name='notification-worker'"
    )).one_or_none()
finally:
    session.close()
print(json.dumps({
    "release": os.environ.get("APP_RELEASE"),
    "heartbeat_release": None if row is None else row.release,
    "stale": None if row is None else row.last_seen_at < datetime.now(UTC) - timedelta(seconds=20),
}, separators=(",", ":"), sort_keys=True))
''',
    )
    web_release = _run(
        "docker",
        "exec",
        CONTAINERS["web"],
        "node",
        "-e",
        'process.stdout.write(process.env.APP_RELEASE || "")',
    )

    result: dict[str, object] = {
        "api_health_release": _require_release(
            api.get("health_release"), "API health release"
        ),
        "api_health_status": api.get("health_status"),
        "api_release": _require_release(api.get("release"), "API release"),
        "config_schema_version": api.get("config_schema_version"),
        "deployed_candidate": deployed,
        "heartbeat_release": _require_release(
            worker.get("heartbeat_release"), "heartbeat release"
        ),
        "migration_revision": api.get("migration_revision"),
        "web_release": _require_release(web_release, "Web release"),
        "worker_release": _require_release(worker.get("release"), "Worker release"),
        "worker_stale": worker.get("stale"),
    }
    if result["api_health_status"] != "ok":
        raise InventoryError("API readiness status is not ok")
    if result["api_health_release"] != result["api_release"]:
        raise InventoryError("API readiness release differs from API configuration")
    if (
        isinstance(result["config_schema_version"], bool)
        or not isinstance(result["config_schema_version"], int)
        or result["config_schema_version"] < 1
    ):
        raise InventoryError("config schema version is invalid")
    migration = result["migration_revision"]
    if not isinstance(migration, str) or not MIGRATION_REVISION.fullmatch(migration):
        raise InventoryError("migration revision is invalid")
    if not isinstance(result["worker_stale"], bool):
        raise InventoryError("worker heartbeat freshness is unavailable")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    result = collect(args.candidate)
    print("WP08_RUNTIME_INVENTORY=" + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
