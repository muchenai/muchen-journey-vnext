from pathlib import Path

import pytest

from scripts import wp15_production_inventory as inventory


def test_container_inventory_accepts_only_current_symlink_to_exact_release(
    monkeypatch, tmp_path: Path
) -> None:
    release_root = tmp_path / "releases"
    release = release_root / f"{inventory.PROFILES['cutover']['marker']}-31342063864"
    release.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(release)
    monkeypatch.setattr(inventory, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(inventory, "CURRENT_RELEASE", current)
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda *_args: __import__("json").dumps(
            [
                {
                    "Name": "/journey-next-production-api-1",
                    "State": {"Running": True},
                    "Config": {
                        "Image": (
                            "ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@"
                            + inventory.PROFILES["cutover"]["images"]["api"]
                        ),
                        "Labels": {
                            "com.docker.compose.project": inventory.COMPOSE_PROJECT,
                            "com.docker.compose.service": "api",
                            "com.docker.compose.project.working_dir": str(current),
                        },
                    },
                    "NetworkSettings": {
                        "Networks": {"edge": {"Aliases": ["production-api"]}}
                    },
                }
            ]
        ),
    )
    result = inventory._inspect_container(
        "api", inventory.PROFILES["cutover"]["images"]["api"]
    )
    assert result["compose_release_directory"] == release.name


def test_container_inventory_rejects_current_symlink_outside_release_root(
    monkeypatch, tmp_path: Path
) -> None:
    release_root = tmp_path / "releases"
    release_root.mkdir()
    outside = tmp_path / f"{inventory.PROFILES['cutover']['marker']}-31342063864"
    outside.mkdir()
    current = tmp_path / "current"
    current.symlink_to(outside)
    monkeypatch.setattr(inventory, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(inventory, "CURRENT_RELEASE", current)
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda *_args: __import__("json").dumps(
            [
                {
                    "Name": "/journey-next-production-api-1",
                    "State": {"Running": True},
                    "Config": {
                        "Image": (
                            "ghcr.io/muchenai2024-creator/muchen-journey-vnext-api@"
                            + inventory.PROFILES["cutover"]["images"]["api"]
                        ),
                        "Labels": {
                            "com.docker.compose.project": inventory.COMPOSE_PROJECT,
                            "com.docker.compose.service": "api",
                            "com.docker.compose.project.working_dir": str(current),
                        },
                    },
                    "NetworkSettings": {
                        "Networks": {"edge": {"Aliases": ["production-api"]}}
                    },
                }
            ]
        ),
    )
    with pytest.raises(inventory.ProductionInventoryError, match="outside"):
        inventory._inspect_container(
            "api", inventory.PROFILES["cutover"]["images"]["api"]
        )


def test_cutover_inventory_outputs_only_pii_free_runtime_facts(monkeypatch, tmp_path: Path) -> None:
    profile = inventory.PROFILES["cutover"]
    marker = tmp_path / "DEPLOYED_CANDIDATE"
    web_marker = tmp_path / "DEPLOYED_WEB_CANDIDATE"
    marker.write_text(profile["marker"])
    web_marker.write_text(profile["web_marker"])
    monkeypatch.setattr(inventory, "DEPLOYED_CANDIDATE", marker)
    monkeypatch.setattr(inventory, "DEPLOYED_WEB_CANDIDATE", web_marker)
    monkeypatch.setattr(
        inventory,
        "_inspect_container",
        lambda service, digest: {
            "compose_release_directory": f"{profile['marker']}-31342063864",
            "image_digest": digest,
            "required_alias": "production-api" if service == "api" else "production-web" if service == "web" else "worker",
            "running": True,
        },
    )
    monkeypatch.setattr(inventory, "_service_counts", lambda: {service: 1 for service in inventory.CONTAINERS})
    monkeypatch.setattr(inventory, "_production_upstream", lambda: "production-web:3000")
    monkeypatch.setattr(inventory, "_run", lambda *_args: profile["web"])

    def container_json(container: str, _code: str):
        if container == inventory.CONTAINERS["api"]:
            return {
                "release": profile["backend"],
                "config_schema_version": 3,
                "migration": profile["migration"],
                "database": profile["database"],
                "active_notification_recipients": 0,
                "pending_outbox_events": 0,
                "health_status": "ok",
                "health_release": profile["backend"],
            }
        return {"release": profile["worker"], "heartbeat_release": profile["worker"], "stale": False}

    monkeypatch.setattr(inventory, "_container_json", container_json)
    result = inventory.collect("cutover")
    assert result["active_notification_recipients"] == 0
    assert result["migration"] == "0019_wp30_invitation_control"
    assert result["compose_singleton_services"] is True
    encoded = str(result).lower()
    for forbidden in ("password", "cookie", "token", "organization_id", "user_id"):
        assert forbidden not in encoded


def test_inventory_rejects_any_active_notification_recipient(monkeypatch, tmp_path: Path) -> None:
    profile = inventory.PROFILES["cutover"]
    marker = tmp_path / "candidate"
    web_marker = tmp_path / "web"
    marker.write_text(profile["marker"])
    web_marker.write_text(profile["web_marker"])
    monkeypatch.setattr(inventory, "DEPLOYED_CANDIDATE", marker)
    monkeypatch.setattr(inventory, "DEPLOYED_WEB_CANDIDATE", web_marker)
    monkeypatch.setattr(inventory, "_inspect_container", lambda *_args: {})
    monkeypatch.setattr(inventory, "_service_counts", lambda: {service: 1 for service in inventory.CONTAINERS})
    monkeypatch.setattr(inventory, "_run", lambda *_args: profile["web"])
    monkeypatch.setattr(
        inventory,
        "_container_json",
        lambda container, _code: (
            {
                "release": profile["backend"], "config_schema_version": 3,
                "migration": profile["migration"], "database": profile["database"],
                "active_notification_recipients": 1, "pending_outbox_events": 0,
                "health_status": "ok", "health_release": profile["backend"],
            }
            if container == inventory.CONTAINERS["api"]
            else {"release": profile["worker"], "heartbeat_release": profile["worker"], "stale": False}
        ),
    )
    with pytest.raises(inventory.ProductionInventoryError, match="recipients"):
        inventory.collect("cutover")
