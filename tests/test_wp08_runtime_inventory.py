from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import wp08_runtime_inventory as inventory


CANDIDATE = "2" * 40
API = "3" * 40
WORKER = "4" * 40
IMAGE_ID = "a" * 64
IMAGE_DIGEST = "b" * 64


def install_component_markers(monkeypatch, tmp_path: Path, *, web: str = CANDIDATE):
    runtime_marker = tmp_path / "DEPLOYED_CANDIDATE"
    web_marker = tmp_path / "DEPLOYED_WEB_CANDIDATE"
    components_marker = tmp_path / "DEPLOYED_COMPONENTS.json"
    runtime_marker.write_text(API)
    web_marker.write_text(web)
    components_marker.write_text(
        json.dumps({"web": web, "api": API, "worker": API})
    )
    monkeypatch.setattr(inventory, "DEPLOYED_CANDIDATE", runtime_marker)
    monkeypatch.setattr(inventory, "DEPLOYED_WEB_CANDIDATE", web_marker)
    monkeypatch.setattr(inventory, "DEPLOYED_COMPONENTS", components_marker)


def safe_container_metadata(service: str) -> dict[str, object]:
    return {
        "compose_config_files": ["compose.yaml"],
        "compose_project": inventory.COMPOSE_PROJECT,
        "compose_release_directory": f"{CANDIDATE}-12345",
        "compose_service": service,
        "container_name": inventory.CONTAINERS[service],
        "image_id": f"sha256:{IMAGE_ID}",
        "image_reference_digest": f"sha256:{IMAGE_DIGEST}",
        "networks": [
            {
                "aliases": [inventory.CONTAINERS[service], service],
                "name": "journey-next-staging_default",
            }
        ],
        "running": True,
    }


def test_inventory_outputs_only_safe_revision_and_health_fields(
    monkeypatch, tmp_path: Path
):
    install_component_markers(monkeypatch, tmp_path)
    monkeypatch.setattr(
        inventory,
        "_inspect_running_container",
        lambda _name, service: safe_container_metadata(service),
    )
    monkeypatch.setattr(
        inventory,
        "_project_service_counts",
        lambda: {service: 1 for service in inventory.CONTAINERS},
    )
    monkeypatch.setattr(
        inventory,
        "_caddy_upstreams",
        lambda: {
            "production": "production-web:3000",
            "staging": "journey-next-staging-web-1:3000",
        },
    )

    def container_json(container: str, _code: str):
        if container == inventory.CONTAINERS["api"]:
            return {
                "release": API,
                "config_schema_version": 3,
                "migration_revision": "0013_wp11_notify_observability",
                "health_status": "ok",
                "health_release": API,
            }
        return {
            "release": WORKER,
            "heartbeat_release": API,
            "stale": True,
        }

    monkeypatch.setattr(inventory, "_container_json", container_json)
    monkeypatch.setattr(inventory, "_run", lambda *_args: CANDIDATE)

    result = inventory.collect(CANDIDATE)

    assert result == {
        "api_health_release": API,
        "api_health_status": "ok",
        "api_release": API,
        "config_schema_version": 3,
        "container_runtime": {
            service: safe_container_metadata(service)
            for service in inventory.CONTAINERS
        },
        "compose_project": inventory.COMPOSE_PROJECT,
        "compose_service_counts": {
            service: 1 for service in inventory.CONTAINERS
        },
        "compose_singleton_services": True,
        "component_marker_matches": {"api": True, "web": True, "worker": False},
        "component_markers_match_runtime": False,
        "caddy_upstreams": {
            "production": "production-web:3000",
            "staging": "journey-next-staging-web-1:3000",
        },
        "deployed_components": {"web": CANDIDATE, "api": API, "worker": API},
        "heartbeat_release": API,
        "migration_revision": "0013_wp11_notify_observability",
        "web_release": CANDIDATE,
        "worker_release": WORKER,
        "worker_stale": True,
    }
    encoded = json.dumps(result)
    for forbidden in ("token", "password", "cookie", "organization_id", "user_id"):
        assert forbidden not in encoded


def test_inventory_rejects_missing_or_malformed_revision_evidence(
    monkeypatch, tmp_path: Path
):
    install_component_markers(monkeypatch, tmp_path)
    monkeypatch.setattr(
        inventory,
        "_inspect_running_container",
        lambda _name, service: safe_container_metadata(service),
    )
    monkeypatch.setattr(
        inventory,
        "_project_service_counts",
        lambda: {service: 1 for service in inventory.CONTAINERS},
    )
    monkeypatch.setattr(
        inventory,
        "_caddy_upstreams",
        lambda: {
            "production": "production-web:3000",
            "staging": "journey-next-staging-web-1:3000",
        },
    )
    monkeypatch.setattr(
        inventory,
        "_container_json",
        lambda container, _code: (
            {
                "release": API,
                "config_schema_version": 3,
                "migration_revision": "unexpected",
                "health_status": "ok",
                "health_release": API,
            }
            if container == inventory.CONTAINERS["api"]
            else {"release": WORKER, "heartbeat_release": None, "stale": None}
        ),
    )
    monkeypatch.setattr(inventory, "_run", lambda *_args: CANDIDATE)

    with pytest.raises(inventory.InventoryError, match="heartbeat release"):
        inventory.collect(CANDIDATE)


def test_inventory_requires_authorized_deployed_candidate(monkeypatch, tmp_path: Path):
    install_component_markers(monkeypatch, tmp_path, web="5" * 40)

    with pytest.raises(inventory.InventoryError, match="Web candidate differs"):
        inventory.collect(CANDIDATE)


def test_component_markers_reject_runtime_component_mismatch(monkeypatch, tmp_path: Path):
    install_component_markers(monkeypatch, tmp_path)
    inventory.DEPLOYED_COMPONENTS.write_text(
        json.dumps({"web": CANDIDATE, "api": API, "worker": WORKER})
    )

    with pytest.raises(inventory.InventoryError, match="API/Worker markers"):
        inventory.collect(CANDIDATE)


def test_container_metadata_is_whitelisted_and_redacts_runtime_secrets(monkeypatch):
    name = inventory.CONTAINERS["web"]
    raw = json.dumps(
        [
            {
                "Name": f"/{name}",
                "State": {"Running": True},
                "Image": f"sha256:{IMAGE_ID}",
                "Config": {
                    "Image": (
                        "ghcr.io/muchenai2024-creator/"
                        "muchen-journey-vnext-web@sha256:"
                        f"{IMAGE_DIGEST}"
                    ),
                    "Env": ["SESSION_SECRET=never-output-this"],
                    "Labels": {
                        "com.docker.compose.project": inventory.COMPOSE_PROJECT,
                        "com.docker.compose.service": "web",
                        "com.docker.compose.project.working_dir": (
                            f"/srv/journey-next-staging/releases/{CANDIDATE}-12345"
                        ),
                        "com.docker.compose.project.config_files": (
                            f"/srv/journey-next-staging/releases/{CANDIDATE}-12345/compose.yaml"
                        ),
                    },
                },
                "Mounts": [{"Source": "/secret/path"}],
                "NetworkSettings": {
                    "IPAddress": "10.88.10.242",
                    "Networks": {
                        "journey-next-staging_default": {
                            "Aliases": [name, "web"],
                            "IPAddress": "172.20.0.4",
                        }
                    },
                },
            }
        ]
    )
    monkeypatch.setattr(inventory, "_run", lambda *_args: raw)

    result = inventory._inspect_running_container(name, "web")

    assert result == safe_container_metadata("web")
    encoded = json.dumps(result)
    assert "never-output-this" not in encoded
    assert "/secret/path" not in encoded
    assert "10.88.10.242" not in encoded
    assert "172.20.0.4" not in encoded


def test_project_service_counts_detects_duplicate_web_without_outputting_ids(
    monkeypatch,
):
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda *_args: "\n".join(
            [
                inventory.CONTAINERS["api"],
                inventory.CONTAINERS["worker"],
                inventory.CONTAINERS["web"],
                "journey-next-staging-web-2",
                inventory.CONTAINERS["edge"],
            ]
        ),
    )

    assert inventory._project_service_counts() == {
        "api": 1,
        "worker": 1,
        "web": 2,
        "edge": 1,
    }


def test_container_metadata_rejects_unreviewed_network_alias(monkeypatch):
    name = inventory.CONTAINERS["web"]
    raw = json.dumps(
        [
            {
                "Name": f"/{name}",
                "State": {"Running": True},
                "Image": f"sha256:{IMAGE_ID}",
                "Config": {
                    "Image": (
                        "ghcr.io/muchenai2024-creator/"
                        "muchen-journey-vnext-web@sha256:"
                        f"{IMAGE_DIGEST}"
                    ),
                    "Labels": {
                        "com.docker.compose.project": inventory.COMPOSE_PROJECT,
                        "com.docker.compose.service": "web",
                        "com.docker.compose.project.working_dir": (
                            f"/srv/journey-next-staging/releases/{CANDIDATE}-12345"
                        ),
                        "com.docker.compose.project.config_files": (
                            f"/srv/journey-next-staging/releases/{CANDIDATE}-12345/compose.yaml"
                        ),
                    },
                },
                "NetworkSettings": {
                    "Networks": {
                        "journey-next-staging_default": {
                            "Aliases": [name, "web", "unreviewed-backend"]
                        }
                    }
                },
            }
        ]
    )
    monkeypatch.setattr(inventory, "_run", lambda *_args: raw)

    with pytest.raises(inventory.InventoryError, match="outside the whitelist"):
        inventory._inspect_running_container(name, "web")


def test_caddy_inventory_outputs_only_safe_upstreams(monkeypatch):
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda *_args: """
{$STAGING_HOST} {
  reverse_proxy journey-next-staging-web-1:3000
}
{$PRODUCTION_HOST} {
  reverse_proxy production-web:3000
}
""",
    )

    assert inventory._caddy_upstreams() == {
        "production": "production-web:3000",
        "staging": "journey-next-staging-web-1:3000",
    }


def test_caddy_inventory_does_not_cross_host_blocks(monkeypatch):
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda *_args: """
{$STAGING_HOST} {
  encode gzip
}
{$PRODUCTION_HOST} {
  reverse_proxy production-web:3000
}
""",
    )

    with pytest.raises(inventory.InventoryError, match="incomplete"):
        inventory._caddy_upstreams()
