#!/usr/bin/env python3
"""Fail-closed WP-08 staging contract and private evidence helper."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp08_staging.json"
WEB_ONLY_CONTRACT = ROOT / "config" / "wp08_web_only.json"
WORKFLOW = ROOT / ".github" / "workflows" / "staging.yml"
EDGE_MIRROR_WORKFLOW = ROOT / ".github" / "workflows" / "wp08-edge-mirror.yml"
WP09_BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "wp09-operator-bootstrap.yml"
INFRA_MAIN = ROOT / "infra" / "staging" / "main.tf"
INFRA_VERSIONS = ROOT / "infra" / "staging" / "versions.tf"
DEPLOY_SCRIPT = ROOT / "deploy" / "staging" / "deploy.sh"
RUNTIME_INVENTORY_SCRIPT = ROOT / "scripts" / "wp08_runtime_inventory.py"
PUBLICATION_DIAGNOSTIC_SCRIPT = ROOT / "scripts" / "wp19_publication_diagnostic.py"
FAILED_RELEASE_CLEANUP_SCRIPT = ROOT / "scripts" / "wp08_failed_release_cleanup.py"
EDGE_ROUTE_REPAIR_SCRIPT = ROOT / "scripts" / "wp08_edge_route_repair.py"
STAGING_COMPOSE = ROOT / "deploy" / "staging" / "compose.yaml"
STAGING_CADDYFILE = ROOT / "deploy" / "staging" / "Caddyfile"
WEB_READINESS_ROUTE = (
    ROOT / "apps" / "web" / "src" / "app" / "health" / "ready" / "route.ts"
)
WEB_PROXY = ROOT / "apps" / "web" / "src" / "proxy.ts"
WEB_LAYOUT = ROOT / "apps" / "web" / "src" / "app" / "layout.tsx"
PRIVATE_EVIDENCE = ROOT / "evidence" / "private" / "wp08"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
EDGE_IMAGE = (
    "ghcr.io/muchenai2024-creator/muchen-journey-vnext-edge@"
    "sha256:b7c239fee65c44ac1dccfa76f88253f87e4d7a8ca27b92e419c86a967ecff171"
)


class StagingError(RuntimeError):
    pass


def load_contract(path: Path = CONTRACT) -> dict[str, object]:
    data = json.loads(path.read_text())
    required = {
        "provider",
        "region_id",
        "billing_mode",
        "monthly_budget_cny",
        "approved_monthly_estimate_cny",
        "candidate_commit",
        "candidate_artifact_run_id",
        "candidate_image_digests",
        "staging_origin",
        "resource_prefix",
    }
    missing = required - data.keys()
    if missing:
        raise StagingError(f"contract missing keys: {','.join(sorted(missing))}")
    if data["provider"] != "volcengine":
        raise StagingError("WP-08 provider must be volcengine")
    if data["region_id"] != "cn-beijing":
        raise StagingError("WP-08 region must be cn-beijing")
    if data["billing_mode"] != "PostPaid":
        raise StagingError("WP-08 billing must be PostPaid")
    if data["monthly_budget_cny"] != 800:
        raise StagingError("WP-08 budget must be exactly CNY 800")
    if not FULL_SHA.fullmatch(str(data["candidate_commit"])):
        raise StagingError("candidate_commit must be one full lowercase SHA")
    run_id = data["candidate_artifact_run_id"]
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise StagingError("candidate_artifact_run_id must be a positive integer")
    digests = data["candidate_image_digests"]
    if not isinstance(digests, dict) or set(digests) != {"api", "web", "worker"}:
        raise StagingError("candidate_image_digests must contain api, web, and worker")
    if any(
        not isinstance(value, str) or not DIGEST.fullmatch(value)
        for value in digests.values()
    ):
        raise StagingError("candidate_image_digests contains an invalid digest")
    origin = urlparse(str(data["staging_origin"]))
    if origin.scheme != "https" or origin.netloc != "staging-vnext.muchenai.com" or origin.path:
        raise StagingError("unexpected staging origin")
    if data["resource_prefix"] != "journey-next-staging":
        raise StagingError("unexpected resource prefix")
    latest_cost = data.get("latest_cost_evidence")
    if latest_cost is not None:
        if not isinstance(latest_cost, dict):
            raise StagingError("latest_cost_evidence must be an object")
        status = latest_cost.get("status")
        if status not in {
            "OVER_BUDGET_NO_DEPLOY",
            "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED",
            "WITHIN_BUDGET_APPROVED",
        }:
            raise StagingError("latest cost evidence has an unsupported status")
        subtotal = latest_cost.get(
            "subtotal_before_tos_and_traffic_cny",
            latest_cost.get("subtotal_before_tos_backup_and_traffic_cny"),
        )
        if isinstance(subtotal, bool) or not isinstance(subtotal, (int, float)):
            raise StagingError("latest cost subtotal must be numeric")
        if status == "OVER_BUDGET_NO_DEPLOY":
            if subtotal <= data["monthly_budget_cny"]:
                raise StagingError("over-budget evidence must exceed the authorized ceiling")
            if data["approved_monthly_estimate_cny"] is not None:
                raise StagingError("an over-budget quote cannot be approved for apply")
        elif status == "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED":
            if subtotal > data["monthly_budget_cny"]:
                raise StagingError("within-budget baseline exceeds the authorized ceiling")
            if data["approved_monthly_estimate_cny"] is not None:
                raise StagingError("quote-refresh baseline cannot be approved for apply")
        else:
            forecast = latest_cost.get("approved_monthly_forecast_cny")
            if isinstance(forecast, bool) or not isinstance(forecast, (int, float)):
                raise StagingError("approved monthly forecast must be numeric")
            if forecast < subtotal or forecast > data["monthly_budget_cny"]:
                raise StagingError("approved monthly forecast is outside the budget contract")
            if data["approved_monthly_estimate_cny"] != forecast:
                raise StagingError("approved estimate and latest cost forecast differ")
    return data


def validate_files() -> None:
    required = [
        "infra/staging/versions.tf",
        "infra/staging/variables.tf",
        "infra/staging/main.tf",
        "infra/staging/outputs.tf",
        "deploy/staging/compose.yaml",
        "deploy/staging/compose.migrate.yaml",
        "deploy/staging/Caddyfile",
        "deploy/staging/grant_runtime.py",
        "deploy/staging/deploy.sh",
        "apps/web/src/app/health/ready/route.ts",
        "apps/web/src/lib/auth/cookies.ts",
        "apps/web/src/proxy.ts",
        "apps/web/src/app/layout.tsx",
        "scripts/wp08_web_runtime_check.py",
        "scripts/wp08_plan_guard.py",
        "scripts/wp08_dns_record.py",
        "scripts/wp08_rds_network_audit.py",
        "scripts/wp08_security_group.py",
        "scripts/wp08_runtime_inventory.py",
        "scripts/wp19_publication_diagnostic.py",
        "scripts/wp08_failed_release_cleanup.py",
        "scripts/wp08_edge_route_repair.py",
        "scripts/wp08_web_only.py",
        "config/wp08_web_only.json",
        ".github/workflows/wp08-edge-mirror.yml",
    ]
    for relative in required:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise StagingError(f"required regular file missing: {relative}")
    mode = stat.S_IMODE((ROOT / "deploy/staging/deploy.sh").stat().st_mode)
    if mode != 0o755:
        raise StagingError("deploy/staging/deploy.sh must be mode 0755")
    cleanup_mode = stat.S_IMODE(FAILED_RELEASE_CLEANUP_SCRIPT.stat().st_mode)
    if cleanup_mode != 0o755:
        raise StagingError("scripts/wp08_failed_release_cleanup.py must be mode 0755")
    repair_mode = stat.S_IMODE(EDGE_ROUTE_REPAIR_SCRIPT.stat().st_mode)
    if repair_mode != 0o755:
        raise StagingError("scripts/wp08_edge_route_repair.py must be mode 0755")
    validate_deploy_script()
    validate_runtime_inventory_script()
    validate_publication_diagnostic_script()
    validate_failed_release_cleanup_script()
    validate_edge_route_repair_script()
    validate_staging_compose()


def validate_runtime_inventory_script(path: Path = RUNTIME_INVENTORY_SCRIPT) -> None:
    source = path.read_text()
    required = (
        '"docker", "inspect"',
        '"docker", "exec"',
        '"docker",\n        "ps"',
        '"com.docker.compose.project"',
        '"com.docker.compose.project.working_dir"',
        '"NetworkSettings"',
        '"/etc/caddy/Caddyfile"',
        '"image_reference_digest"',
        '"compose_service_counts"',
        '"caddy_upstreams"',
        "SELECT version_num FROM alembic_version",
        "SELECT release,last_seen_at FROM worker_heartbeats",
        "WP08_RUNTIME_INVENTORY=",
        '"deployed_components"',
        '"deployed_candidate"',
        '"component_marker_matches"',
        '"component_markers_match_runtime"',
        '"marker_relationships"',
        '"marker_relationships_consistent"',
    )
    if any(marker not in source for marker in required):
        raise StagingError("runtime inventory script is incomplete")
    forbidden = (
        "docker compose up",
        "docker pull",
        "docker restart",
        "docker stop",
        "docker kill",
        "docker rm",
        "docker network connect",
        "docker network disconnect",
        "alembic upgrade",
        "journey_api.seed",
        "grant_runtime",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "terraform ",
    )
    if any(marker in source for marker in forbidden):
        raise StagingError("runtime inventory script exceeds its read-only boundary")


def validate_publication_diagnostic_script(
    path: Path = PUBLICATION_DIAGNOSTIC_SCRIPT,
) -> None:
    source = path.read_text()
    required = (
        'AUTHORIZED_CANDIDATE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"',
        'WINDOW_START = "2026-08-04T01:20:00Z"',
        'WINDOW_END = "2026-08-04T01:30:30Z"',
        '"docker",\n        "inspect"',
        '"docker",\n        "logs"',
        'PUBLICATION_PATH = "/api/v1/ops/formal-journeys/publish"',
        '"read_only": True',
        "WP19_PUBLICATION_DIAGNOSTIC=",
        "raw log lines",
    )
    if any(marker not in source for marker in required):
        raise StagingError("formal Journey publication diagnostic is incomplete")
    forbidden = (
        '"docker", "exec"',
        '"docker", "pull"',
        '"docker", "restart"',
        '"docker", "stop"',
        '"docker", "kill"',
        '"docker", "rm"',
        "docker compose",
        "alembic upgrade",
        "journey_api.seed",
        "grant_runtime",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "terraform ",
        ".write_text(",
        ".write_bytes(",
        ".unlink(",
    )
    if any(marker in source for marker in forbidden):
        raise StagingError(
            "formal Journey publication diagnostic exceeds its read-only boundary"
        )


def validate_failed_release_cleanup_script(
    path: Path = FAILED_RELEASE_CLEANUP_SCRIPT,
) -> None:
    source = path.read_text()
    required = (
        'CANDIDATE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"',
        'FAILED_RUN_ID = "30808632624"',
        'RELEASE_ROOT = Path("/srv/journey-next-staging")',
        'root / "releases" / f"{candidate}-{run_id}"',
        'current.resolve(strict=True) == target',
        'previous = root / "PREVIOUS_RELEASE"',
        'deployed = root / "DEPLOYED_CANDIDATE"',
        'read_env_value(deployment_env, "CANDIDATE_COMMIT")',
        'com.docker.compose.project.working_dir',
        '["shred", "-u", "--", str(path)]',
        "shutil.rmtree(target)",
        "WP08_FAILED_RELEASE_CLEANUP=PASS",
    )
    if any(marker not in source for marker in required):
        raise StagingError("failed release cleanup script is incomplete")
    forbidden = (
        "terraform ",
        "alembic ",
        "docker compose up",
        "docker pull",
        "journey_api.seed",
    )
    if any(marker in source for marker in forbidden):
        raise StagingError("failed release cleanup exceeds its exact deletion boundary")


def validate_edge_route_repair_script(
    path: Path = EDGE_ROUTE_REPAIR_SCRIPT,
) -> None:
    source = path.read_text()
    required = (
        'CANDIDATE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"',
        'PRODUCTION_RELEASE = "8e56e759152efcbf17f4373f2132e02a8762af81"',
        'EDGE_CONTAINER = "journey-next-staging-edge-1"',
        'STAGING_WEB_CONTAINER = "journey-next-staging-web-1"',
        'PRODUCTION_WEB_CONTAINER = "journey-next-production-web-1"',
        'STATE_ROOT = Path("/run")',
        '"reverse_proxy journey-next-staging-web-1:3000"',
        '"reverse_proxy production-web:3000"',
        '"caddy",\n            "validate"',
        '"--no-deps"',
        '"--force-recreate"',
        '"--pull"',
        '"never"',
        'backup = state / "Caddyfile.before"',
        '_write_in_place(current_path, current)',
        'def rollback_repair(',
        'shutil.rmtree(state)',
        'WP08_EDGE_ROUTE_REPAIR=PASS',
    )
    if any(marker not in source for marker in required):
        raise StagingError("Edge route repair script is incomplete")
    forbidden = (
        "docker pull",
        "docker compose down",
        "docker stop",
        "docker restart",
        "docker network",
        "terraform ",
        "alembic ",
        "journey_api.seed",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    )
    if any(marker in source for marker in forbidden):
        raise StagingError("Edge route repair exceeds its Edge-only boundary")


def validate_edge_mirror_workflow(path: Path = EDGE_MIRROR_WORKFLOW) -> None:
    workflow = path.read_text()
    required = (
        "workflow_dispatch:",
        "packages: write",
        "inputs.confirmation == 'MIRROR_CADDY_2_10_2_TO_GHCR'",
        "docker/login-action@4907a6ddec9925e35a0a9e82d7399ccc52663121",
        "docker.io/library/caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d",
        "ghcr.io/muchenai2024-creator/muchen-journey-vnext-edge:caddy-2.10.2-alpine-4c6e91c6ed0e",
        'docker buildx imagetools inspect "$target@$digest"',
    )
    if any(marker not in workflow for marker in required):
        raise StagingError("WP-08 edge mirror workflow is incomplete")
    if "\n  push:" in workflow or "\n  pull_request:" in workflow:
        raise StagingError("WP-08 edge mirror must be manual only")


def validate_staging_compose(path: Path = STAGING_COMPOSE) -> None:
    compose = path.read_text()
    for component in ("API", "WEB", "WORKER"):
        if f"image: ${{{component}_RUNTIME_IMAGE:" not in compose:
            raise StagingError("staging application images must use verified runtime references")
    if f"image: {EDGE_IMAGE}" not in compose:
        raise StagingError("staging edge must use the verified project GHCR digest")
    if "image: caddy:" in compose or "docker.io/library/caddy" in compose:
        raise StagingError("staging edge must not pull Caddy from Docker Hub")
    if "http://localhost:3000/health/ready" not in compose:
        raise StagingError("staging Web healthcheck must use the readiness route")
    if "http://localhost:3000/ops" in compose:
        raise StagingError("staging Web healthcheck must not use an authenticated route")
    caddy = STAGING_CADDYFILE.read_text()
    if "log_skip /auth/feishu*" not in caddy:
        raise StagingError("staging edge must suppress OAuth callback query logs")
    lines = {line.strip() for line in caddy.splitlines()}
    if "reverse_proxy journey-next-staging-web-1:3000" not in lines:
        raise StagingError("staging edge must use its unique Web network alias")
    if "reverse_proxy web:3000" in lines:
        raise StagingError("staging edge must not use the ambiguous shared Web alias")
    if "reverse_proxy production-web:3000" not in lines:
        raise StagingError("production edge upstream must remain unchanged")

    readiness = WEB_READINESS_ROUTE.read_text()
    if 'status: "ready"' not in readiness or '"Cache-Control": "no-store"' not in readiness:
        raise StagingError("Web readiness route must be minimal and non-cacheable")
    proxy = WEB_PROXY.read_text()
    if 'code: "AUTH_REQUIRED"' not in proxy or "{ status: 401 }" not in proxy:
        raise StagingError("anonymous /ops requests must fail closed with HTTP 401")
    if 'requestHeaders.set("Content-Security-Policy", policy)' not in proxy:
        raise StagingError("Next.js must receive the per-request CSP nonce")
    layout = WEB_LAYOUT.read_text()
    if 'import { connection } from "next/server"' not in layout or "await connection()" not in layout:
        raise StagingError("nonce-protected pages must be dynamically rendered")


def validate_deploy_script(path: Path = DEPLOY_SCRIPT) -> None:
    script = path.read_text()
    if "journey_api.seed" in script:
        raise StagingError("staging deploy must not seed fixture business facts")
    if 'SECRETS="$PWD/secrets"' not in script:
        raise StagingError("staging deploy must read release-local secrets")
    if 'SECRETS="$ROOT/secrets"' in script:
        raise StagingError("staging deploy must not read the obsolete global secret path")
    compose_check = (
        "docker compose -f compose.yaml -f compose.migrate.yaml config --quiet"
    )
    archive_loads = (
        "python3 ./wp07_image_archive.py verify-files",
        'load_verified_archive api "$API_RUNTIME_IMAGE" "$API_LOCAL_IMAGE_DIGEST"',
        'load_verified_archive web "$WEB_RUNTIME_IMAGE" "$WEB_LOCAL_IMAGE_DIGEST"',
        'load_verified_archive worker "$WORKER_RUNTIME_IMAGE" "$WORKER_LOCAL_IMAGE_DIGEST"',
    )
    container_ca_check = (
        "Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()"
    )
    migration = (
        "docker compose -f compose.yaml -f compose.migrate.yaml "
        "run --rm --no-deps api alembic upgrade head"
    )
    if any(
        command not in script
        for command in (compose_check, *archive_loads, container_ca_check, migration)
    ):
        raise StagingError("staging deploy preflight commands are incomplete")
    if not (
        script.index(compose_check)
        < script.index(archive_loads[0])
        < script.index(archive_loads[1])
        < script.index(archive_loads[2])
        < script.index(archive_loads[3])
        < script.index(container_ca_check)
        < script.index(migration)
    ):
        raise StagingError(
            "staging deploy must validate Compose, load all verified images, and verify "
            "container CA readability before database migration"
        )
    bounded_pull_contract = (
        "pull_with_bounded_retry()",
        "for attempt in 1 2 3",
        "timeout --signal=TERM --kill-after=30s 8m",
        "TRANSIENT_NETWORK",
        "COMMAND_TIMEOUT",
        "NON_RETRYABLE",
        "WP08_IMAGE_PULL",
        "pull_with_bounded_retry web-only docker pull",
        "pull_with_bounded_retry runtime-api docker pull",
        "pull_with_bounded_retry runtime-worker docker pull",
    )
    if any(marker not in script for marker in bounded_pull_contract):
        raise StagingError(
            "staging image pulls must use the observable three-attempt bounded retry contract"
        )
    loop_match = re.search(r"for attempt in ([^;\n]+)", script)
    if loop_match is None or loop_match.group(1).split() != ["1", "2", "3"]:
        raise StagingError(
            "staging image pulls must use the observable three-attempt bounded retry contract"
        )
    if "timeout --signal=TERM --kill-after=30s 8m docker pull" in script:
        raise StagingError("staging image pulls must not bypass the bounded retry helper")
    first_release_cleanup = (
        "WP08_ROLLBACK=STOP_FAILED_FIRST_RELEASE",
        "docker compose down --remove-orphans",
    )
    if any(marker not in script for marker in first_release_cleanup):
        raise StagingError("failed first deployment must stop partial application containers")
    web_only_markers = (
        '[[ "${DEPLOY_MODE:-}" == "full" || "${DEPLOY_MODE:-}" == "web-only" || "${DEPLOY_MODE:-}" == "runtime-repair" ]]',
        "verify_web_only_runtime",
        "verify_runtime_repair_prestate",
        'pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"',
        'pull_with_bounded_retry runtime-api docker pull "$API_IMAGE"',
        'alembic upgrade 0014_wp12_data_lifecycle',
        "docker compose up -d --no-deps --wait --wait-timeout 180 web",
        "WP08_WEB_ONLY_ROLLBACK=START",
        "WP08_RUNTIME_REPAIR_ROLLBACK=START",
        "WP08_RUNTIME_REPAIR=PASS",
        "DEPLOYED_CANDIDATE.tmp",
        "DEPLOYED_COMPONENTS.json",
        "validate_component_marker_shape",
        "full_sha.fullmatch(value)",
        "WP08_WEB_ONLY_DEPLOY=PASS",
    )
    if any(marker not in script for marker in web_only_markers):
        raise StagingError("bounded Web-only deployment contract is incomplete")
    stale_marker_assertions = (
        'components["api"] == baseline',
        'components["worker"] == baseline',
    )
    if any(marker in script for marker in stale_marker_assertions):
        raise StagingError(
            "Web-only deployment must verify the live runtime instead of trusting stale markers"
        )
    web_only_start = script.find('if [[ "$DEPLOY_MODE" == "web-only" ]]')
    marker_shape_check = script.find(
        'validate_component_marker_shape "$ROOT/DEPLOYED_COMPONENTS.json"',
        web_only_start,
    )
    live_runtime_check = script.find(
        'verify_web_only_runtime "$previous"', web_only_start
    )
    web_image_pull = script.find(
        'pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"', web_only_start
    )
    if not (
        web_only_start >= 0
        and web_only_start < marker_shape_check < live_runtime_check < web_image_pull
    ):
        raise StagingError(
            "Web-only deployment must validate marker shape and live runtime before pulling Web"
        )
    repair_start = script.find('if [[ "$DEPLOY_MODE" == "runtime-repair" ]]')
    repair_end = script.find("\nfi", repair_start)
    if repair_start < 0 or repair_end < 0:
        raise StagingError("runtime repair branch is missing")
    repair = script[repair_start:repair_end]
    repair_required = (
        "verify_runtime_repair_prestate",
        'pull_with_bounded_retry runtime-api docker pull "$API_IMAGE"',
        'pull_with_bounded_retry runtime-worker docker pull "$WORKER_IMAGE"',
        "alembic upgrade 0014_wp12_data_lifecycle",
        "python /tmp/grant_runtime.py",
        "--wait-timeout 180 api",
        "--wait-timeout 180 worker",
        "verify_web_only_runtime",
        "write_component_markers",
    )
    if any(marker not in repair for marker in repair_required):
        raise StagingError("runtime repair branch is incomplete")
    repair_forbidden = (
        'pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"',
        "--wait-timeout 180 web",
        "journey_api.seed",
        "terraform ",
        "wp12b",
    )
    if any(marker in repair for marker in repair_forbidden):
        raise StagingError("runtime repair exceeds the reviewed mutation boundary")


def validate_infrastructure() -> None:
    versions = INFRA_VERSIONS.read_text()
    main = INFRA_MAIN.read_text()
    required_versions = ('source  = "hashicorp/random"', 'version = "3.7.2"')
    for marker in required_versions:
        if marker not in versions:
            raise StagingError(f"staging providers are missing bootstrap marker: {marker}")
    required_main = (
        'resource "random_password" "ecs_bootstrap"',
        'length           = 30',
        'override_special = "!@#%^&*_-+=?"',
        'password                  = random_password.ecs_bootstrap.result',
        'PasswordAuthentication no',
        'KbdInteractiveAuthentication no',
        'PermitRootLogin prohibit-password',
        'stopped_mode              = "KeepCharging"',
        "prevent_destroy = true",
        "depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]",
        "depends_on = [volcenginecc_rdspostgresql_db_account.migration]",
    )
    for marker in required_main:
        if marker not in main:
            raise StagingError(f"staging infrastructure is missing bootstrap marker: {marker}")
    if main.count("random_password.ecs_bootstrap.result") != 1:
        raise StagingError("ECS bootstrap password must have exactly one non-output consumer")
    if "key_pair_name" in main.lower():
        raise StagingError("staging ECS must not depend on an account-level KeyPair")
    if main.count(
        "depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]"
    ) != 1:
        raise StagingError("migration account must wait for the RDS SSL mutation")
    if main.count(
        "depends_on = [volcenginecc_rdspostgresql_db_account.migration]"
    ) != 1:
        raise StagingError("runtime account must wait for the migration account mutation")
    ecs_start = main.find('resource "volcenginecc_ecs_instance" "app"')
    ecs_end = main.find('\nresource "', ecs_start + 1)
    if ecs_start < 0:
        raise StagingError("staging ECS resource is missing")
    ecs = main[ecs_start : ecs_end if ecs_end >= 0 else None]
    ignore_match = re.search(r"ignore_changes\s*=\s*\[(.*?)\]", ecs, re.DOTALL)
    if ignore_match is None:
        raise StagingError("staging ECS creation-only ignore list is missing")
    ignored = {
        line.strip().rstrip(",")
        for line in ignore_match.group(1).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    expected_ignored = {
        "eip_address.bandwidth_mbps",
        "eip_address.charge_type",
        "eip_address.isp",
        "eip_address.release_with_instance",
        "image.security_enhancement_strategy",
        "install_run_command_agent",
        "password",
        "system_volume.delete_with_instance",
        "system_volume.size",
        "system_volume.volume_type",
        "user_data",
    }
    if ignored != expected_ignored:
        raise StagingError("staging ECS creation-only ignore list differs from the reviewed set")
    allowlist_start = main.find('resource "volcenginecc_rdspostgresql_allow_list" "app"')
    allowlist_end = main.find('\nresource "', allowlist_start + 1)
    if allowlist_start < 0 or allowlist_end < 0:
        raise StagingError("staging RDS allowlist resource is missing")
    allowlist = main[allowlist_start:allowlist_end]
    if "depends_on = [volcenginecc_ecs_instance.app]" not in allowlist:
        raise StagingError("RDS allowlist must wait for the ECS security-group attachment")
    if re.search(r"\bip_list\s*=", allowlist):
        raise StagingError("AssociateEcsIp allowlist binding must not configure ip_list")
    if not re.search(
        r"ignore_changes\s*=\s*\[\s*security_group_bind_infos\s*\]", allowlist
    ):
        raise StagingError(
            "AssociateEcsIp nested binding must be immutable after creation"
        )


def validate_candidate(data: dict[str, object]) -> None:
    manifest_path = ROOT / "artifacts" / "wp07-candidate" / "release-manifest.json"
    if not manifest_path.is_file():
        raise StagingError("local canonical WP-07 candidate manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    candidate = manifest.get("candidate", {})
    if candidate.get("commit_sha") != data["candidate_commit"]:
        raise StagingError("WP-08 contract and WP-07 candidate manifest differ")
    external = manifest.get("external_status", {})
    if external.get("registry_push") != "VERIFIED":
        raise StagingError("candidate registry push is not VERIFIED")
    if external.get("deployment") != "NOT_RUN":
        raise StagingError("candidate deployment must remain NOT_RUN before WP-08 apply")
    images = manifest.get("images", {})
    expected_digests = data["candidate_image_digests"]
    if not isinstance(images, dict) or not isinstance(expected_digests, dict):
        raise StagingError("candidate image evidence is incomplete")
    for component in ("api", "web", "worker"):
        item = images.get(component, {})
        if (
            not isinstance(item, dict)
            or item.get("registry_digest") != expected_digests[component]
        ):
            raise StagingError(f"{component} digest differs from the canonical candidate artifact")

    commit = str(data["candidate_commit"])
    run_id = str(data["candidate_artifact_run_id"])
    prepare = (ROOT / "scripts" / "wp08_prepare_deploy.py").read_text()
    deploy = DEPLOY_SCRIPT.read_text()
    workflow = WORKFLOW.read_text()
    variables = (ROOT / "infra" / "staging" / "variables.tf").read_text()
    web_only = json.loads(WEB_ONLY_CONTRACT.read_text())
    if (
        web_only.get("status") == "ACTIVE"
        and web_only.get("candidate_commit") == commit
    ):
        if web_only.get("candidate_artifact_run_id") != data["candidate_artifact_run_id"]:
            raise StagingError("active Web-only artifact differs from WP-08")
        if web_only.get("web_image_digest") != expected_digests["web"]:
            raise StagingError("active Web-only digest differs from WP-08")
        baseline = str(web_only["runtime_baseline"]["candidate_commit"])
        confirmation = (
            f"DEPLOY_WEB_{commit[:7].upper()}_ON_"
            f"{baseline[:7].upper()}_STAGING"
        )
        baseline_markers = (
            baseline,
            str(web_only["runtime_baseline"]["api_image_digest"]),
            str(web_only["runtime_baseline"]["worker_image_digest"]),
        )
        for marker in baseline_markers:
            if marker not in prepare or marker not in deploy:
                raise StagingError(
                    "active Web-only runtime baseline differs from deploy bundle"
                )
    else:
        confirmation = f"DEPLOY_{commit[:7].upper()}_TO_VOLCENGINE_STAGING"
    required_markers = (
        (prepare, commit, "deploy bundle candidate"),
        (deploy, commit, "deploy preflight candidate"),
        (variables, commit, "Terraform candidate"),
        (workflow, commit, "workflow candidate"),
        (workflow, f"wp07-candidate-{commit}", "workflow artifact name"),
        (workflow, f"run-id: {run_id}", "workflow artifact run"),
        (workflow, confirmation, "workflow confirmation"),
    )
    for source, marker, label in required_markers:
        if marker not in source:
            raise StagingError(f"{label} differs from the machine contract")
    runtime_image_builder = 'f"{component.lower()}:{CANDIDATE}"'
    if runtime_image_builder not in prepare:
        raise StagingError("archive runtime image builder differs from the machine contract")
    for component in ("api", "web", "worker"):
        digest = str(expected_digests[component])
        local_digest = str(images[component]["local_image_digest"])
        immutable = (
            "ghcr.io/muchenai2024-creator/muchen-journey-vnext-"
            f"{component}@{digest}"
        )
        if (
            immutable not in prepare
            or digest not in deploy
            or local_digest not in prepare
            or local_digest not in deploy
        ):
            raise StagingError(f"{component} deploy binding differs from the machine contract")


def validate_cost(data: dict[str, object], *, require_quote: bool) -> None:
    estimate = data["approved_monthly_estimate_cny"]
    if estimate is None:
        if require_quote:
            latest_cost = data.get("latest_cost_evidence")
            if isinstance(latest_cost, dict) and latest_cost.get("status") == "OVER_BUDGET_NO_DEPLOY":
                raise StagingError(
                    "latest official quote exceeds the authorized budget; new authorization is required"
                )
            if (
                isinstance(latest_cost, dict)
                and latest_cost.get("status")
                == "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED"
            ):
                raise StagingError(
                    "same-day total quote must be refreshed after budget reauthorization"
                )
            raise StagingError("same-day official monthly estimate is not recorded")
        return
    if isinstance(estimate, bool) or not isinstance(estimate, (int, float)):
        raise StagingError("approved monthly estimate must be numeric or null")
    if estimate <= 0 or estimate > data["monthly_budget_cny"]:
        raise StagingError("approved monthly estimate exceeds the authorized budget")


def check(phase: str) -> None:
    data = load_contract()
    validate_files()
    validate_infrastructure()
    validate_candidate(data)
    validate_cost(data, require_quote=phase == "apply")
    print(
        "WP08_STAGING_CONTRACT=PASS"
        f" phase={phase} candidate={data['candidate_commit']}"
        f" region={data['region_id']} budget_cny={data['monthly_budget_cny']}"
        f" estimate_cny={data['approved_monthly_estimate_cny']}"
    )


def validate_workflow(path: Path = WORKFLOW) -> None:
    validate_infrastructure()
    validate_publication_diagnostic_script()
    workflow = path.read_text()
    jobs_start = workflow.find("jobs:\n")
    guard_end = workflow.find("    runs-on:", jobs_start)
    web_only = json.loads(WEB_ONLY_CONTRACT.read_text())
    active_web_only = web_only.get("status") == "ACTIVE"
    if jobs_start >= 0 and guard_end >= 0:
        job_guard = workflow[jobs_start:guard_end]
        retired_dispatches = [
            "inputs.phase == 'provision'",
            "inputs.phase == 'repair-runtime'",
        ]
        if not active_web_only:
            retired_dispatches.append("inputs.phase == 'deploy-web'")
        if any(marker in job_guard for marker in retired_dispatches):
            raise StagingError(
                "controlled Alpha candidate must not dispatch retired mutation phases"
            )
    phase_sequence = (
        "- audit\n          - deploy-web\n          - inspect-runtime"
        if active_web_only
        else "- audit\n          - deploy\n          - inspect-runtime"
    )
    deployment_confirmation = (
        "inputs.confirmation == 'DEPLOY_WEB_D55732B_ON_9E8A806_STAGING'"
        if active_web_only
        else "inputs.confirmation == 'DEPLOY_EB7C40B_TO_VOLCENGINE_STAGING'"
    )
    required = (
        phase_sequence,
        deployment_confirmation,
        "          - cleanup-failed-release",
        "inputs.confirmation == 'AUDIT_WP08_RDS_NETWORK'",
        "inputs.confirmation == 'CLEANUP_FAILED_RELEASE_EF0A512_30808632624'",
        "id: terraform_init",
        "if: inputs.phase == 'audit'",
        "python3 -m scripts.wp08_rds_network_audit",
        "terraform -chdir=infra/staging state pull",
        "if: inputs.phase == 'provision'",
        "id: frozen_infrastructure",
        "terraform output -raw staging_public_ip",
        "if: always() && (inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime' || inputs.phase == 'inspect-runtime' || inputs.phase == 'diagnose-publication' || inputs.phase == 'repair-edge-route' || inputs.phase == 'cleanup-failed-release') && steps.frozen_infrastructure.outputs.security_group_id != ''",
        "terraform show -json",
        "scripts/wp08_plan_guard.py",
        "scripts/wp08_dns_record.py",
        "scripts.wp08_security_group open",
        "scripts.wp08_security_group close",
        'terraform import "$address" "$expected_id"',
        "terraform state pull | jq -er",
        'terraform apply -auto-approve "$plan_file"',
        '-var="deploy_cidr=127.0.0.1/32"',
        "origin=https://staging-vnext.muchenai.com",
        '"$origin/health/ready"',
        '"$origin/ops"',
        '"$origin/review"',
        '"$origin/content"',
        '"$origin/content/login"',
        "'%{http_code}'",
        '= "401"',
        '= "303"',
        'test "$content_location" = "/content/login"',
        "^cache-control: .*no-store",
        "使用飞书进入",
        "WP08_SURFACE_CHECK",
        "WP08_SURFACE_ATTEMPT",
        'attempts=12',
        'for attempt in $(seq 1 "$attempts")',
        'next_in_seconds=5',
        '--connect-timeout 2',
        '--max-time 3',
        '-o ServerAliveInterval=15',
        '-o ServerAliveCountMax=4',
        '-o TCPKeepAlive=yes',
        "expired_reviewer=explicit-relogin",
        'if [[ "${{ inputs.phase }}" == "deploy" ]]; then',
        'git cat-file -e "$candidate:apps/web/src/app/health/ready/route.ts"',
        'git show "$candidate:deploy/staging/compose.yaml"',
        'git show "$candidate:apps/web/src/proxy.ts"',
        'git show "$candidate:apps/web/src/lib/server/oauth-proxy.ts"',
        'git show "$candidate:scripts/wp08_web_runtime_check.py"',
        'git show "$candidate:apps/worker/journey_worker/main.py"',
        'git show "$candidate:scripts/wp08_prepare_deploy.py"',
        "scripts/wp07_image_archive.py verify-files",
        "artifacts/wp07-candidate/image-archives.json",
        "artifacts/wp07-candidate/images/api.tar",
        "WP08_BUNDLE_TRANSFER=START transport=ssh-compressed",
        "WP08_BUNDLE_TRANSFER=PASS transport=ssh-compressed",
        "timeout --signal=TERM --kill-after=30s 20m ssh",
        "WP08_BUNDLE_TRANSFER=FAIL cleanup=exact-release",
        "timeout --signal=TERM --kill-after=30s 2m ssh",
        'rm -rf -- \'$release\'',
        '"DB_POOL_SIZE": "20"',
        '"DB_MAX_OVERFLOW": "5"',
        '"DB_POOL_SIZE": "2"',
        '"DB_MAX_OVERFLOW": "1"',
        'git cat-file -e "$candidate:docs/runbooks/WP11_STAGING_INTEGRATIONS.md"',
        'git cat-file -e "$candidate:scripts/wp12b_load.py"',
        'git cat-file -e "$candidate:apps/api/journey_api/wp12b_synthetic.py"',
        'git cat-file -e "$candidate:config/wp12b_multitenant_load.json"',
        '"runtime.snapshot"',
        "active_recipient_exists",
        'NOTIFICATION_RESULT_URL": f"https://{STAGING_HOST}/app/result"',
        'pathname === "/ops" || pathname.startsWith("/ops/")',
        "isReviewRoute && !isReviewLogin && !hasSession",
        'git show "$candidate:apps/web/src/app/review/login/page.tsx"',
        "进入主管评审",
        "isContentRoute && !isContentLogin && !hasSession",
        'git show "$candidate:apps/web/src/app/content/login/page.tsx"',
        'git show "$candidate:apps/web/src/app/ops/invite-management-panel.tsx"',
        "formatJourneyOptionLabel(journey)",
        'git show "$candidate:.github/workflows/staging.yml"',
        "anonymous_content=login-page",
        "oauth_redirect=root-relative-content",
        "INSPECT_RUNTIME_EB7C40B_STAGING",
        "scripts/wp08_runtime_inventory.py",
        "DIAGNOSE_FORMAL_JOURNEY_EF0A512_STAGING",
        "scripts/wp19_publication_diagnostic.py",
        "REPAIR_EDGE_ROUTE_EF0A512_STAGING",
        "scripts/wp08_edge_route_repair.py",
        "id: edge_repair_apply",
        "Verify deterministic staging and preserved production routes",
        "Roll back Edge route after failed verification",
        "steps.edge_repair_apply.outcome == 'success'",
        "steps.edge_repair_apply.outcome == 'failure'",
        "Remove successful Edge repair state",
        "https://journey.muchenai.com/health/ready",
        "8e56e759152efcbf17f4373f2132e02a8762af81",
        "if: inputs.phase == 'cleanup-failed-release'",
        "scripts/wp08_failed_release_cleanup.py",
        "'30808632624'",
        'if [[ "${{ inputs.phase }}" == "deploy-web" || "${{ inputs.phase }}" == "repair-runtime" ]]; then',
        "python3 scripts/wp08_web_only.py check",
        '--mode "$mode"',
        "mode=runtime-repair",
    )
    for marker in required:
        if marker not in workflow:
            raise StagingError(f"staging workflow is missing bootstrap marker: {marker}")
    if workflow.count("if: inputs.phase == 'deploy'") != 5:
        raise StagingError("staging workflow deploy-only step count must be exactly 5")
    if workflow.count("if: inputs.phase == 'provision'") != 2:
        raise StagingError("staging workflow provision-only step count must be exactly 2")
    if workflow.count("if: inputs.phase == 'audit'") != 1:
        raise StagingError("staging workflow audit-only step count must be exactly 1")
    if workflow.count("if: inputs.phase == 'inspect-runtime'") != 1:
        raise StagingError("staging workflow runtime inventory step count must be exactly 1")
    if workflow.count("if: inputs.phase == 'diagnose-publication'") != 1:
        raise StagingError("formal Journey diagnostic step count must be exactly 1")
    if workflow.count("if: inputs.phase == 'repair-edge-route'") != 2:
        raise StagingError("staging workflow Edge repair success path must have exactly 2 steps")
    if workflow.count("if: inputs.phase == 'cleanup-failed-release'") != 1:
        raise StagingError("staging workflow failed-release cleanup step count must be exactly 1")
    if (
        workflow.count("git cat-file -e") != 5
        or workflow.count('git show "$candidate:') != 21
    ):
        raise StagingError(
            "deploy must verify the Web, bounded database pool, WP-11, and WP-12B contracts "
            "inside the candidate source"
        )
    if workflow.count("scripts/wp08_plan_guard.py") != 1:
        raise StagingError("every WP-08 apply path must have one destructive-plan guard")
    if workflow.count("scripts/wp08_dns_record.py") != 1:
        raise StagingError("WP-08 must identify the existing DNS record exactly once")
    if workflow.count("python3 -m scripts.wp08_rds_network_audit") != 1:
        raise StagingError("WP-08 must audit the frozen RDS network binding exactly once")
    if workflow.count('terraform import "$address" "$expected_id"') != 1:
        raise StagingError("WP-08 DNS reconciliation must have exactly one import path")
    if workflow.count("terraform state pull | jq -er") != 1:
        raise StagingError("WP-08 must verify the existing DNS state identity exactly once")
    if workflow.count("scripts.wp08_security_group") != 2:
        raise StagingError("WP-08 must directly open and close one exact SSH rule")
    if "-target=volcenginecc_vpc_security_group.app" in workflow:
        raise StagingError("WP-08 must not update the nested security group rule set")
    if "terraform apply -auto-approve -var=" in workflow:
        raise StagingError("WP-08 apply must consume a reviewed and guarded saved plan")
    guard_positions = [
        match.start() for match in re.finditer(r"scripts/wp08_plan_guard\.py", workflow)
    ]
    apply_positions = [match.start() for match in re.finditer(r"terraform apply", workflow)]
    if len(apply_positions) != 1 or guard_positions[0] > apply_positions[0]:
        raise StagingError("WP-08 destructive-plan guard must run before every apply")
    apply_step_start = workflow.find("- name: Apply reviewed infrastructure")
    apply_step_end = workflow.find("\n      - name:", apply_step_start + 1)
    if apply_step_start < 0 or apply_step_end < 0:
        raise StagingError("staging provision step is missing")
    apply_step = workflow[apply_step_start:apply_step_end]
    if "if: inputs.phase == 'provision'" not in apply_step:
        raise StagingError("Terraform apply must be provision-only")
    frozen_step_start = workflow.find("- name: Read frozen Alpha pilot infrastructure")
    frozen_step_end = workflow.find("\n      - name:", frozen_step_start + 1)
    if frozen_step_start < 0 or frozen_step_end < 0:
        raise StagingError("frozen Alpha pilot state reader is missing")
    frozen_step = workflow[frozen_step_start:frozen_step_end]
    for forbidden in ("terraform plan", "terraform apply", "terraform import", "wp08_dns_record.py"):
        if forbidden in frozen_step:
            raise StagingError("Alpha pilot deploy must not reconcile infrastructure")
    audit_step_start = workflow.find("- name: Audit frozen ECS to RDS allowlist binding")
    audit_step_end = workflow.find("\n      - name:", audit_step_start + 1)
    if audit_step_start < 0 or audit_step_end < 0:
        raise StagingError("staging read-only RDS network audit step is missing")
    audit_step = workflow[audit_step_start:audit_step_end]
    for forbidden in ("terraform plan", "terraform apply", "terraform import", "wp08_security_group"):
        if forbidden in audit_step:
            raise StagingError("RDS network audit must remain read-only")
    inventory_step_start = workflow.find("- name: Execute PII-free runtime inventory")
    inventory_step_end = workflow.find("\n      - name:", inventory_step_start + 1)
    if inventory_step_start < 0 or inventory_step_end < 0:
        raise StagingError("staging runtime inventory step is missing")
    inventory_step = workflow[inventory_step_start:inventory_step_end]
    for forbidden in (
        "terraform plan",
        "terraform apply",
        "terraform import",
        "docker pull",
        "deploy.sh",
        "grant_runtime",
        "wp12b",
    ):
        if forbidden in inventory_step:
            raise StagingError("runtime inventory must remain read-only")
    diagnostic_step_start = workflow.find("- name: Diagnose failed formal Journey publication")
    diagnostic_step_end = workflow.find("\n      - name:", diagnostic_step_start + 1)
    if diagnostic_step_start < 0 or diagnostic_step_end < 0:
        raise StagingError("formal Journey publication diagnostic step is missing")
    diagnostic_step = workflow[diagnostic_step_start:diagnostic_step_end]
    for forbidden in (
        "terraform plan",
        "terraform apply",
        "terraform import",
        "docker pull",
        "deploy.sh",
        "grant_runtime",
        "alembic",
        "wp12b",
        "journey_api.seed",
        "docker exec",
    ):
        if forbidden in diagnostic_step:
            raise StagingError("formal Journey publication diagnostic exceeds its read-only boundary")
    edge_step_start = workflow.find("- name: Apply reviewed Edge route repair")
    edge_step_end = workflow.find("\n      - name:", edge_step_start + 1)
    if edge_step_start < 0 or edge_step_end < 0:
        raise StagingError("reviewed Edge route repair step is missing")
    edge_step = workflow[edge_step_start:edge_step_end]
    for forbidden in (
        "terraform plan",
        "terraform apply",
        "terraform import",
        "docker pull",
        "deploy.sh",
        "grant_runtime",
        "alembic",
        "wp12b",
        "journey_api.seed",
    ):
        if forbidden in edge_step:
            raise StagingError("Edge route repair exceeds its reviewed boundary")
    cleanup_step_start = workflow.find("- name: Remove exact failed pre-start release")
    cleanup_step_end = workflow.find("\n      - name:", cleanup_step_start + 1)
    if cleanup_step_start < 0 or cleanup_step_end < 0:
        raise StagingError("exact failed-release cleanup step is missing")
    cleanup_step = workflow[cleanup_step_start:cleanup_step_end]
    for forbidden in (
        "terraform plan",
        "terraform apply",
        "terraform import",
        "docker pull",
        "deploy.sh",
        "grant_runtime",
        "alembic",
        "wp12b",
    ):
        if forbidden in cleanup_step:
            raise StagingError("failed-release cleanup exceeds its reviewed boundary")
    deployment_mode = "web-only" if active_web_only else "bounded-full-deploy"
    retired_modes = "provision,runtime-repair" if active_web_only else "provision,web-only,runtime-repair"
    print(
        "WP08_STAGING_WORKFLOW=PASS"
        f" dispatch=audit,{deployment_mode},runtime-inventory,publication-diagnostic,edge-route-repair,exact-failed-release-cleanup"
        f" retired={retired_modes}"
    )


def validate_wp09_bootstrap_workflow(path: Path = WP09_BOOTSTRAP_WORKFLOW) -> None:
    workflow = path.read_text()
    bootstrap_candidate = "26d56010125024ca2dbc6e85f7dfeb59857f93dd"
    current_candidate = str(load_contract()["candidate_commit"])
    if current_candidate == bootstrap_candidate:
        raise StagingError(
            "consumed WP-09 first-Operator bootstrap candidate must remain retired"
        )
    confirmation = "CREATE_15M_OPERATOR_LINK_26D5601"
    required = (
        "workflow_dispatch:",
        bootstrap_candidate,
        confirmation,
        "recipient_public_key_b64",
        "group: wp08-volcengine-staging",
        "environment: staging",
        "terraform output -raw staging_public_ip",
        "terraform output -raw staging_security_group_id",
        "python3 -m scripts.wp08_security_group open",
        "python3 -m scripts.wp08_security_group close",
        "cat /srv/journey-next-staging/DEPLOYED_CANDIDATE",
        "python -m journey_api.wp09_bootstrap",
        "--expires-in-minutes 15",
        "--confirm CREATE_STAGING_OPERATOR_LINK",
        "openssl pkeyutl -encrypt",
        "rsa_padding_mode:oaep",
        "rsa_oaep_md:sha256",
        "rsa_mgf1_md:sha256",
        "wp09-operator-link.json.enc",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        "if: always() && steps.frozen_infrastructure.outputs.security_group_id != ''",
    )
    for marker in required:
        if marker not in workflow:
            raise StagingError(f"WP-09 bootstrap workflow is missing marker: {marker}")
    forbidden = (
        "terraform plan",
        "terraform apply",
        "terraform import",
        "echo \"$bootstrap_json\"",
        "cat \"$RUNNER_TEMP/wp09-operator-link.json.enc\"",
    )
    for marker in forbidden:
        if marker in workflow:
            raise StagingError(f"WP-09 bootstrap workflow contains forbidden marker: {marker}")
    if not re.search(r"^\s*retention-days:\s*1\s*$", workflow, re.MULTILINE):
        raise StagingError("WP-09 bootstrap ciphertext retention must be exactly one day")
    if workflow.count("scripts.wp08_security_group") != 2:
        raise StagingError("WP-09 bootstrap must open and close one exact SSH rule")
    if workflow.count("journey_api.wp09_bootstrap") != 1:
        raise StagingError("WP-09 bootstrap link must be created exactly once")
    if workflow.count("actions/upload-artifact@") != 1:
        raise StagingError("WP-09 bootstrap must upload exactly one ciphertext artifact")
    deployment_env = workflow.find(". ./.deployment.env")
    operator_lookup = workflow.find("operator_id=$(docker compose exec")
    if deployment_env < 0 or operator_lookup < 0 or deployment_env >= operator_lookup:
        raise StagingError(
            "WP-09 bootstrap must load the deployed image environment before Compose"
        )
    if workflow.count("< /dev/null") != 2:
        raise StagingError(
            "WP-09 bootstrap Compose calls must not consume the remote script stdin"
        )
    print(
        "WP09_OPERATOR_BOOTSTRAP_WORKFLOW=PASS state=retired"
        " encrypted_artifact=RSA4096_OAEP_SHA256"
    )


def command_output(*args: str) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def record_evidence(status: str, reference: str) -> None:
    if status not in {"APPLIED", "DEPLOYED", "VERIFIED", "FAILED"}:
        raise StagingError("unsupported evidence status")
    if not re.fullmatch(r"[A-Z0-9_-]{3,80}", reference):
        raise StagingError("reference must be one non-sensitive identifier")
    data = load_contract()
    PRIVATE_EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE_EVIDENCE.chmod(0o700)
    payload = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "candidate_commit": data["candidate_commit"],
        "repository_head": command_output("git", "rev-parse", "HEAD"),
        "region_id": data["region_id"],
        "staging_origin": data["staging_origin"],
        "status": status,
        "reference": reference,
        "contains_pii": False,
        "contains_secrets": False,
    }
    target = PRIVATE_EVIDENCE / f"physical-{status.lower()}.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(target)
    target.chmod(0o600)
    print(f"WP08_PRIVATE_EVIDENCE={target.relative_to(ROOT)} status={status}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--phase", choices=("readiness", "apply"), required=True)
    subparsers.add_parser("workflow-check")
    evidence_parser = subparsers.add_parser("record")
    evidence_parser.add_argument("--status", required=True)
    evidence_parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            check(args.phase)
        elif args.command == "workflow-check":
            validate_workflow()
            validate_edge_mirror_workflow()
            validate_wp09_bootstrap_workflow()
        else:
            record_evidence(args.status, args.reference)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, StagingError) as error:
        print(f"WP08_STAGING_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
