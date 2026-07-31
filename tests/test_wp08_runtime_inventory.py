from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import wp08_runtime_inventory as inventory


CANDIDATE = "2" * 40
API = "3" * 40
WORKER = "4" * 40


def test_inventory_outputs_only_safe_revision_and_health_fields(
    monkeypatch, tmp_path: Path
):
    marker = tmp_path / "DEPLOYED_CANDIDATE"
    marker.write_text(CANDIDATE)
    monkeypatch.setattr(inventory, "DEPLOYED_CANDIDATE", marker)
    monkeypatch.setattr(inventory, "_inspect_running_container", lambda _name: None)

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
        "deployed_candidate": CANDIDATE,
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
    marker = tmp_path / "DEPLOYED_CANDIDATE"
    marker.write_text(CANDIDATE)
    monkeypatch.setattr(inventory, "DEPLOYED_CANDIDATE", marker)
    monkeypatch.setattr(inventory, "_inspect_running_container", lambda _name: None)
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
    marker = tmp_path / "DEPLOYED_CANDIDATE"
    marker.write_text("5" * 40)
    monkeypatch.setattr(inventory, "DEPLOYED_CANDIDATE", marker)

    with pytest.raises(inventory.InventoryError, match="authorized candidate"):
        inventory.collect(CANDIDATE)
