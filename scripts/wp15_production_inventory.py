#!/usr/bin/env python3
"""PII-free, read-only inventory for the exact WP-15 production runtime."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


CONTAINERS = {
    "api": "journey-next-production-api-1",
    "worker": "journey-next-production-worker-1",
    "web": "journey-next-production-web-1",
}
EDGE = "journey-next-staging-edge-1"
COMPOSE_PROJECT = "journey-next-production"
RELEASE_ROOT = Path("/srv/journey-next-production/releases")
DEPLOYED_CANDIDATE = Path("/srv/journey-next-production/DEPLOYED_CANDIDATE")
DEPLOYED_WEB_CANDIDATE = Path("/srv/journey-next-production/DEPLOYED_WEB_CANDIDATE")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
MIGRATION_REVISION = re.compile(r"^\d{4}_[a-z0-9_]+$")
RELEASE_DIRECTORY = re.compile(r"^[0-9a-f]{40}-[1-9][0-9]*$")
CONTAINER_NAME = re.compile(r"^journey-next-production-(api|worker|web)-[1-9][0-9]*$")
IMAGE_REFERENCE = re.compile(
    r"^ghcr\.io/muchenai2024-creator/muchen-journey-vnext-"
    r"(?P<service>api|worker|web)@(?P<digest>sha256:[0-9a-f]{64})$"
)

PROFILES = {
    "baseline": {
        "marker": "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
        "web_marker": "8e56e759152efcbf17f4373f2132e02a8762af81",
        "backend": "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
        "worker": "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
        "web": "8e56e759152efcbf17f4373f2132e02a8762af81",
        "migration": "0014_wp12_data_lifecycle",
        "database": "journey_next_restore_20260803",
        "images": {
            "api": "sha256:553055d921f75bc7f7df0e176d5176f0546ee7f75f37e9757a0be09edf3520ff",
            "web": "sha256:c86b4a443ecdc9160c5cb59b742c5c7882ea46aaf401e0a487d3bdad11d86d6f",
            "worker": "sha256:16bf2c7515d68fab164704438b23f691917213c8946a8c3dff8a4116fb3df0c7",
        },
    },
    "cutover": {
        "marker": "ff53052847a268d025bceb93c3eab37986d50219",
        "web_marker": "ff53052847a268d025bceb93c3eab37986d50219",
        "backend": "ff53052847a268d025bceb93c3eab37986d50219",
        "worker": "ff53052847a268d025bceb93c3eab37986d50219",
        "web": "ff53052847a268d025bceb93c3eab37986d50219",
        "migration": "0019_wp30_invitation_control",
        "database": "journey_next_cutover_20260810",
        "images": {
            "api": "sha256:2a053bad89bea8c06daba6e929af49a4804cc06a2321e49e93858f1f4fda6a6c",
            "web": "sha256:a3335542f74d09f4bc394119cee81ba7b866edc6ef041f3f4444949d271e2aee",
            "worker": "sha256:2ef3cd1b05c545810929a3136ac8259042f6b6c586ccb8c59af90c579bfd9f38",
        },
    },
}


class ProductionInventoryError(RuntimeError):
    pass


def _run(*command: str) -> str:
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=30
    )
    return completed.stdout.strip()


def _container_json(container: str, code: str) -> dict[str, Any]:
    raw = _run("docker", "exec", container, "python", "-c", code)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ProductionInventoryError("container inventory result is invalid")
    return payload


def _inspect_container(service: str, expected_digest: str) -> dict[str, object]:
    name = CONTAINERS[service]
    raw = json.loads(_run("docker", "inspect", name))
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise ProductionInventoryError("container inspect result is ambiguous")
    value = raw[0]
    if value.get("Name", "").lstrip("/") != name or value.get("State", {}).get("Running") is not True:
        raise ProductionInventoryError(f"{service} container is not the expected running instance")
    config = value.get("Config")
    if not isinstance(config, dict):
        raise ProductionInventoryError("container configuration is invalid")
    reference = config.get("Image")
    if not isinstance(reference, str):
        raise ProductionInventoryError("container image reference is missing")
    match = IMAGE_REFERENCE.fullmatch(reference)
    if match is None or match.group("service") != service or match.group("digest") != expected_digest:
        raise ProductionInventoryError(f"{service} image differs from the frozen profile")
    labels = config.get("Labels")
    if not isinstance(labels, dict):
        raise ProductionInventoryError("Compose labels are missing")
    if labels.get("com.docker.compose.project") != COMPOSE_PROJECT:
        raise ProductionInventoryError("Compose project differs")
    if labels.get("com.docker.compose.service") != service:
        raise ProductionInventoryError("Compose service differs")
    working_dir_raw = labels.get("com.docker.compose.project.working_dir")
    if not isinstance(working_dir_raw, str):
        raise ProductionInventoryError("Compose working directory is missing")
    working_dir = Path(working_dir_raw)
    if working_dir.parent != RELEASE_ROOT or not RELEASE_DIRECTORY.fullmatch(working_dir.name):
        raise ProductionInventoryError("Compose working directory is outside production releases")
    networks = value.get("NetworkSettings", {}).get("Networks")
    if not isinstance(networks, dict) or not networks:
        raise ProductionInventoryError("container network metadata is missing")
    aliases: list[str] = []
    for metadata in networks.values():
        if not isinstance(metadata, dict) or not isinstance(metadata.get("Aliases"), list):
            raise ProductionInventoryError("container aliases are missing")
        aliases.extend(alias for alias in metadata["Aliases"] if isinstance(alias, str))
    required_alias = "production-api" if service == "api" else "production-web" if service == "web" else service
    if required_alias not in aliases:
        raise ProductionInventoryError(f"{service} required network alias is missing")
    return {
        "compose_release_directory": working_dir.name,
        "image_digest": match.group("digest"),
        "required_alias": required_alias,
        "running": True,
    }


def _service_counts() -> dict[str, int]:
    raw = _run(
        "docker",
        "ps",
        "--filter",
        f"label=com.docker.compose.project={COMPOSE_PROJECT}",
        "--format",
        "{{.Names}}",
    )
    counts = {service: 0 for service in CONTAINERS}
    for name in raw.splitlines():
        match = CONTAINER_NAME.fullmatch(name)
        if match is None:
            raise ProductionInventoryError("running production container is outside whitelist")
        counts[match.group(1)] += 1
    return counts


def _production_upstream() -> str:
    caddyfile = _run("docker", "exec", EDGE, "cat", "/etc/caddy/Caddyfile")
    active = False
    depth = 0
    upstreams: list[str] = []
    for line in caddyfile.splitlines():
        stripped = line.strip()
        if depth == 0 and stripped == "{$PRODUCTION_HOST} {":
            active = True
        if active and stripped.startswith("reverse_proxy "):
            upstreams.append(stripped.removeprefix("reverse_proxy "))
        depth += line.count("{") - line.count("}")
        if depth == 0:
            active = False
    if upstreams != ["production-web:3000"]:
        raise ProductionInventoryError("production Caddy upstream differs")
    return upstreams[0]


def collect(profile_name: str) -> dict[str, object]:
    profile = PROFILES[profile_name]
    marker = DEPLOYED_CANDIDATE.read_text().strip()
    web_marker = DEPLOYED_WEB_CANDIDATE.read_text().strip()
    if marker != profile["marker"] or web_marker != profile["web_marker"]:
        raise ProductionInventoryError("production release markers differ from profile")
    containers = {
        service: _inspect_container(service, profile["images"][service])
        for service in CONTAINERS
    }
    counts = _service_counts()
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
    migration = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    database = session.execute(text("SELECT current_database()" )).scalar_one()
    recipients = session.execute(text("SELECT count(*) FROM notification_endpoints WHERE status='ACTIVE'" )).scalar_one()
    outbox = session.execute(text("SELECT count(*) FROM outbox_events WHERE status IN ('PENDING','PROCESSING','FAILED')" )).scalar_one()
finally:
    session.close()
settings = get_settings()
health = json.loads(urllib.request.urlopen("http://localhost:8000/health/ready", timeout=3).read())
print(json.dumps({
    "release": settings.app_release,
    "config_schema_version": settings.config_schema_version,
    "migration": migration,
    "database": database,
    "active_notification_recipients": recipients,
    "pending_outbox_events": outbox,
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
        "SELECT release,last_seen_at FROM worker_heartbeats WHERE worker_name='notification-worker'"
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
        "docker", "exec", CONTAINERS["web"], "node", "-e",
        'process.stdout.write(process.env.APP_RELEASE || "")',
    )
    exact = {
        "backend": api.get("release"),
        "worker": worker.get("release"),
        "web": web_release,
        "migration": api.get("migration"),
        "database": api.get("database"),
    }
    for key, actual in exact.items():
        if actual != profile[key]:
            raise ProductionInventoryError(f"{key} differs from the frozen profile")
    if api.get("health_status") != "ok" or api.get("health_release") != profile["backend"]:
        raise ProductionInventoryError("API health differs")
    if worker.get("heartbeat_release") != profile["worker"] or worker.get("stale") is not False:
        raise ProductionInventoryError("Worker heartbeat differs")
    if api.get("config_schema_version") != 3:
        raise ProductionInventoryError("config schema version differs")
    if api.get("active_notification_recipients") != 0:
        raise ProductionInventoryError("active notification recipients must remain zero")
    if not isinstance(api.get("pending_outbox_events"), int) or api["pending_outbox_events"] < 0:
        raise ProductionInventoryError("pending outbox count is invalid")
    if not MIGRATION_REVISION.fullmatch(str(api.get("migration", ""))):
        raise ProductionInventoryError("migration revision is invalid")
    return {
        "active_notification_recipients": 0,
        "api_release": api["release"],
        "compose_project": COMPOSE_PROJECT,
        "compose_service_counts": counts,
        "compose_singleton_services": all(count == 1 for count in counts.values()),
        "config_schema_version": 3,
        "container_runtime": containers,
        "database": api["database"],
        "deployed_candidate": marker,
        "deployed_web_candidate": web_marker,
        "heartbeat_release": worker["heartbeat_release"],
        "migration": api["migration"],
        "pending_outbox_events": api["pending_outbox_events"],
        "production_upstream": _production_upstream(),
        "profile": profile_name,
        "web_release": web_release,
        "worker_release": worker["release"],
        "worker_stale": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    args = parser.parse_args()
    result = collect(args.profile)
    print("WP15_PRODUCTION_INVENTORY=" + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
