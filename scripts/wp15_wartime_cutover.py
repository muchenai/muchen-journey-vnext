#!/usr/bin/env python3
"""Fail-closed static contract for the minimal WP-15 wartime cutover."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp15_wartime_cutover.json"
WORKFLOW = ROOT / ".github" / "workflows" / "wp15-wartime-production.yml"
PREPARE = ROOT / "scripts" / "wp15_prepare_wartime.py"
BACKUP = ROOT / "deploy" / "production" / "wartime_backup_restore.sh"
DEPLOY = ROOT / "deploy" / "production" / "wartime_deploy.sh"
ROLLBACK = ROOT / "deploy" / "production" / "wartime_rollback.sh"
INVENTORY = ROOT / "scripts" / "wp15_production_inventory.py"
SURFACE = ROOT / "scripts" / "wp15_public_surface.py"
EDGE = ROOT / "deploy" / "production" / "wartime_edge_route.sh"
MAINTENANCE = ROOT / "deploy" / "production" / "Caddyfile.maintenance"


class WartimeCutoverError(RuntimeError):
    pass


def require(source: str, marker: str, label: str) -> None:
    if marker not in source:
        raise WartimeCutoverError(f"{label} is missing reviewed marker: {marker}")


def load_contract(path: Path = CONTRACT) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise WartimeCutoverError(f"cannot read wartime cutover contract: {error}") from error
    exact = {
        "schema_version": 1,
        "status": "CONTROLLED_ALPHA_CUTOVER",
        "candidate_sha": "ff53052847a268d025bceb93c3eab37986d50219",
        "candidate_gate_run_id": "31340959377",
        "region": "cn-beijing",
        "production_host": "journey.muchenai.com",
        "staging_host": "staging-vnext.muchenai.com",
        "staging_database": "journey_next_staging",
        "production_database": "journey_next_cutover_20260810",
        "rollback_database": "journey_next_restore_20260803",
        "preserved_failed_restore_database": "journey_next_production",
        "production_compose_project": "journey-next-production",
        "shared_edge_network": "journey-next-staging_default",
        "migration": "0019_wp30_invitation_control",
        "config_schema_version": 3,
    }
    for key, expected in exact.items():
        if value.get(key) != expected:
            raise WartimeCutoverError(f"wartime cutover contract differs at {key}")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != {"api", "web", "worker"}:
        raise WartimeCutoverError("wartime image set differs")
    for service, image in images.items():
        if not isinstance(image, str) or not re.fullmatch(
            rf"ghcr\.io/muchenai2024-creator/muchen-journey-vnext-{service}@sha256:[0-9a-f]{{64}}",
            image,
        ):
            raise WartimeCutoverError(f"{service} image is not exactly digest pinned")
    backup = value.get("backup")
    if not isinstance(backup, dict) or any(
        backup.get(key) is not True
        for key in (
            "restore_target_must_be_empty",
            "source_database_is_never_modified",
            "active_notification_recipients_must_be_zero",
        )
    ):
        raise WartimeCutoverError("wartime backup safety contract differs")
    rollback = value.get("rollback")
    if not isinstance(rollback, dict) or rollback.get("dns_mutation_required") is not False:
        raise WartimeCutoverError("wartime rollback must not depend on DNS mutation")
    return value


def validate_files() -> None:
    workflow = WORKFLOW.read_text()
    prepare = PREPARE.read_text()
    backup = BACKUP.read_text()
    deploy = DEPLOY.read_text()
    rollback = ROLLBACK.read_text()
    inventory = INVENTORY.read_text()
    surface = SURFACE.read_text()
    edge = EDGE.read_text()
    maintenance = MAINTENANCE.read_text()

    for phase in (
        "preflight",
        "backup-restore",
        "deploy",
        "inspect",
        "rollback",
        "maintenance",
        "live",
    ):
        require(workflow, f"- {phase}", "wartime workflow")
    for marker in (
        "run-id: 31340959377",
        "wp07-candidate-ff53052847a268d025bceb93c3eab37986d50219",
        "journey_next_cutover_20260810",
        "attempts=12",
        "scripts/wp15_public_surface.py",
        "WP15_WARTIME_SSH_INGRESS=CLOSED",
        "WP15_WARTIME_OFF_HOST_BACKUP=PASS",
        "Roll back automatically after failed deployment acceptance",
        'select(.address == "volcenginecc_rdspostgresql_instance.staging")',
        "steps.frozen.outputs.rds_instance_id",
    ):
        require(workflow, marker, "wartime workflow")
    if "output -raw rds_instance_id" in workflow:
        raise WartimeCutoverError("RDS instance ID must come from the frozen state resource")
    forbidden = (
        "terraform plan",
        "terraform apply",
        "terraform destroy",
        "dns:Update",
        "aliyun",
        "journey_api.seed",
        "WP-12B",
    )
    for marker in forbidden:
        if marker.lower() in workflow.lower():
            raise WartimeCutoverError(f"wartime workflow contains forbidden operation: {marker}")

    for marker in (
        "journey_next_cutover_20260810",
        "FEISHU_OAUTH_REDIRECT_URI",
        "/auth/feishu/callback",
        "NOTIFICATION_RESULT_URL",
        "/app/result",
        '"ATTACHMENTS_ENABLED": "false"',
    ):
        require(prepare, marker, "wartime bundle")
    for marker in (
        "TARGET_DATABASE_NOT_EMPTY",
        "source business facts changed during backup",
        "active_notification_recipients",
        "openssl enc -aes-256-cbc -pbkdf2",
        "encrypted backup decrypt verification failed",
        "trap cleanup_plaintext EXIT",
        "0019_wp30_invitation_control",
    ):
        require(backup, marker, "wartime backup")
    if re.search(r"dropdb|DROP\s+DATABASE", backup, re.IGNORECASE):
        raise WartimeCutoverError("wartime backup must never drop a database")
    for marker in (
        "BACKUP_RUN_ID",
        "manifest_hmac_sha256",
        "restored target changed after backup proof",
        "wartime_rollback.sh",
        "PREVIOUS_RELEASE",
        "alembic upgrade head",
        "WP15_WARTIME_DEPLOY=PASS",
    ):
        require(deploy, marker, "wartime deploy")
    if "journey_api.seed" in deploy:
        raise WartimeCutoverError("wartime deploy must not seed business facts")
    for marker in (
        "journey_next_restore_20260803",
        "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
        "8e56e759152efcbf17f4373f2132e02a8762af81",
        "WP15_WARTIME_ROLLBACK=PASS",
    ):
        require(rollback, marker, "wartime rollback")
    for marker in (
        '"baseline"',
        '"cutover"',
        "active_notification_recipients",
        "pending_outbox_events",
        "production-web:3000",
        "PII-free, read-only inventory",
    ):
        require(inventory, marker, "wartime inventory")
    for marker in (
        "WP15_SURFACE_CHECK",
        "content_login_cta",
        "feishu_oauth",
        "accounts.feishu.cn",
        "/auth/feishu/callback",
    ):
        require(surface, marker, "wartime public surface")
    require(edge, "WP15_WARTIME_EDGE_ROLLBACK=ATTEMPTED", "wartime edge route")
    require(maintenance, "reverse_proxy journey-next-staging-web-1:3000", "maintenance Caddyfile")
    require(maintenance, "503", "maintenance Caddyfile")


def check() -> dict[str, object]:
    contract = load_contract()
    validate_files()
    return {
        "status": "PASS",
        "candidate": contract["candidate_sha"],
        "production_host": contract["production_host"],
        "production_go": False,
        "production_mutation_executed": False,
    }


def main() -> None:
    try:
        result = check()
    except (OSError, WartimeCutoverError) as error:
        print(f"WP15_WARTIME_CUTOVER_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
