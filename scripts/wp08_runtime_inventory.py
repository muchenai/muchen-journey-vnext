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
    "edge": "journey-next-staging-edge-1",
}
COMPOSE_PROJECT = "journey-next-staging"
RELEASE_ROOT = Path("/srv/journey-next-staging/releases")
DEPLOYED_CANDIDATE = Path("/srv/journey-next-staging/DEPLOYED_CANDIDATE")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
MIGRATION_REVISION = re.compile(r"^\d{4}_[a-z0-9_]+$")
RELEASE_DIRECTORY = re.compile(r"^[0-9a-f]{40}-[0-9]+$")
CONTAINER_NAME = re.compile(
    r"^journey-next-staging-(api|worker|web|edge)-[1-9][0-9]*$"
)
NETWORK_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
NETWORK_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
IMAGE_REFERENCE = re.compile(
    r"^ghcr\.io/muchenai2024-creator/muchen-journey-vnext-"
    r"(?P<service>api|worker|web|edge)@(?P<digest>sha256:[0-9a-f]{64})$"
)
UPSTREAM = re.compile(r"^[a-z][a-z0-9-]*:[1-9][0-9]{0,4}$")


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


def _inspect_running_container(name: str, expected_service: str) -> dict[str, object]:
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

    image_id = value.get("Image")
    if not isinstance(image_id, str) or not SHA256.fullmatch(image_id):
        raise InventoryError("container image ID is invalid")
    config = value.get("Config")
    if not isinstance(config, dict):
        raise InventoryError("container configuration is invalid")
    image_reference = config.get("Image")
    if not isinstance(image_reference, str):
        raise InventoryError("container image reference is missing")
    image_match = IMAGE_REFERENCE.fullmatch(image_reference)
    if image_match is None or image_match.group("service") != expected_service:
        raise InventoryError("container image reference is outside the reviewed project")

    labels = config.get("Labels")
    if not isinstance(labels, dict):
        raise InventoryError("Compose labels are missing")
    if labels.get("com.docker.compose.project") != COMPOSE_PROJECT:
        raise InventoryError("Compose project differs")
    if labels.get("com.docker.compose.service") != expected_service:
        raise InventoryError("Compose service differs")
    working_dir_raw = labels.get("com.docker.compose.project.working_dir")
    if not isinstance(working_dir_raw, str):
        raise InventoryError("Compose working directory is missing")
    working_dir = Path(working_dir_raw)
    if working_dir.parent != RELEASE_ROOT or not RELEASE_DIRECTORY.fullmatch(
        working_dir.name
    ):
        raise InventoryError("Compose working directory is outside the staging releases")
    config_files_raw = labels.get("com.docker.compose.project.config_files")
    if not isinstance(config_files_raw, str) or not config_files_raw:
        raise InventoryError("Compose config file label is missing")
    config_files: list[str] = []
    for raw_path in config_files_raw.split(","):
        path = Path(raw_path)
        if path.parent != working_dir or path.name not in {
            "compose.yaml",
            "compose.migrate.yaml",
        }:
            raise InventoryError("Compose config file is outside the release directory")
        config_files.append(path.name)

    network_settings = value.get("NetworkSettings")
    if not isinstance(network_settings, dict):
        raise InventoryError("container network settings are missing")
    raw_networks = network_settings.get("Networks")
    if not isinstance(raw_networks, dict) or not raw_networks:
        raise InventoryError("container has no runtime network")
    networks: list[dict[str, object]] = []
    for network_name, network in sorted(raw_networks.items()):
        if not isinstance(network_name, str) or not NETWORK_NAME.fullmatch(network_name):
            raise InventoryError("container network name is unsafe")
        if not isinstance(network, dict):
            raise InventoryError("container network metadata is invalid")
        raw_aliases = network.get("Aliases")
        if not isinstance(raw_aliases, list):
            raise InventoryError("container network aliases are missing")
        aliases: list[str] = []
        allowed_aliases = {name, expected_service}
        for alias in raw_aliases:
            if not isinstance(alias, str) or not NETWORK_ALIAS.fullmatch(alias):
                raise InventoryError("container network alias is unsafe")
            if alias not in allowed_aliases:
                raise InventoryError("container network alias is outside the whitelist")
            aliases.append(alias)
        networks.append({"aliases": sorted(set(aliases)), "name": network_name})

    return {
        "compose_config_files": sorted(set(config_files)),
        "compose_project": COMPOSE_PROJECT,
        "compose_release_directory": working_dir.name,
        "compose_service": expected_service,
        "container_name": name,
        "image_id": image_id,
        "image_reference_digest": image_match.group("digest"),
        "networks": networks,
        "running": True,
    }


def _project_service_counts() -> dict[str, int]:
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
            raise InventoryError("running Compose container name is outside the whitelist")
        counts[match.group(1)] += 1
    return counts


def _caddy_upstreams() -> dict[str, str]:
    caddyfile = _run(
        "docker", "exec", CONTAINERS["edge"], "cat", "/etc/caddy/Caddyfile"
    )
    hosts = {
        "{$PRODUCTION_HOST}": "production",
        "{$STAGING_HOST}": "staging",
    }
    result: dict[str, str] = {}
    active: str | None = None
    depth = 0
    for line in caddyfile.splitlines():
        stripped = line.strip()
        if depth == 0:
            for host, label in hosts.items():
                if stripped == f"{host} {{":
                    active = label
                    break
        if active is not None and stripped.startswith("reverse_proxy "):
            parts = stripped.split()
            if len(parts) != 2 or not UPSTREAM.fullmatch(parts[1]):
                raise InventoryError(f"unsafe Caddy upstream for {active}")
            result[active] = parts[1]
        depth += line.count("{") - line.count("}")
        if depth < 0:
            raise InventoryError("Caddyfile braces are unbalanced")
        if depth == 0:
            active = None
    if depth != 0 or set(result) != {"production", "staging"}:
        raise InventoryError("safe Caddy upstream inventory is incomplete")
    return result


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

    containers = {
        service: _inspect_running_container(container, service)
        for service, container in CONTAINERS.items()
    }
    service_counts = _project_service_counts()
    caddy_upstreams = _caddy_upstreams()

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
        "container_runtime": containers,
        "compose_project": COMPOSE_PROJECT,
        "compose_service_counts": service_counts,
        "compose_singleton_services": all(count == 1 for count in service_counts.values()),
        "caddy_upstreams": caddy_upstreams,
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
