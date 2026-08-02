#!/usr/bin/env python3
"""Fail-closed contract checks for the low-cost Alpha production cutover."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp15_alpha_cutover.json"
WORKFLOW = ROOT / ".github" / "workflows" / "wp15-alpha-production.yml"
PRODUCTION_COMPOSE = ROOT / "deploy" / "production" / "compose.yaml"
PRODUCTION_DEPLOY = ROOT / "deploy" / "production" / "deploy.sh"
PRODUCTION_GRANT = ROOT / "deploy" / "production" / "grant_runtime.py"
BACKUP_RESTORE = ROOT / "deploy" / "production" / "backup_restore.sh"
STAGING_CADDY = ROOT / "deploy" / "staging" / "Caddyfile"
MAINTENANCE_CADDY = ROOT / "deploy" / "production" / "Caddyfile.maintenance"
INFRA_MAIN = ROOT / "infra" / "staging" / "main.tf"
RDS_DATABASE = ROOT / "scripts" / "wp15_rds_database.py"


class CutoverError(RuntimeError):
    pass


def require(source: str, marker: str, label: str) -> None:
    if marker not in source:
        raise CutoverError(f"{label} is missing reviewed marker: {marker}")


def load_contract(path: Path = CONTRACT) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise CutoverError(f"cannot read cutover contract: {error}") from error
    exact = {
        "schema_version": 1,
        "candidate_sha": "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
        "candidate_gate_run_id": "30709982868",
        "region": "cn-beijing",
        "production_host": "journey.muchenai.com",
        "staging_host": "staging-vnext.muchenai.com",
        "staging_database": "journey_next_staging",
        "production_database": "journey_next_production",
        "production_compose_project": "journey-next-production",
        "shared_edge_network": "journey-next-staging_default",
        "migration": "0014_wp12_data_lifecycle",
        "config_schema_version": 3,
    }
    for key, expected in exact.items():
        if value.get(key) != expected:
            raise CutoverError(f"cutover contract differs at {key}")
    tool = value.get("database_tool", {})
    digest = tool.get("expected_digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise CutoverError("database tool digest is invalid")
    if not tool.get("source", "").endswith("@" + digest):
        raise CutoverError("database tool source is not digest pinned")
    backup = value.get("backup", {})
    if backup.get("restore_target_must_be_empty") is not True:
        raise CutoverError("restore target must fail closed when non-empty")
    if backup.get("source_database_is_never_modified") is not True:
        raise CutoverError("source database immutability is not locked")
    fault = value.get("fault_domain", {})
    if fault.get("logical_runtime_and_database_isolation") is not True:
        raise CutoverError("logical staging/production isolation is required")
    if fault.get("independent_fault_domain_deferred_days") != 30:
        raise CutoverError("physical fault-domain deferral differs from DEC-019")
    return value


def validate_files(contract: dict) -> None:
    workflow = WORKFLOW.read_text()
    compose = PRODUCTION_COMPOSE.read_text()
    deploy = PRODUCTION_DEPLOY.read_text()
    grant = PRODUCTION_GRANT.read_text()
    backup = BACKUP_RESTORE.read_text()
    caddy = STAGING_CADDY.read_text()
    maintenance = MAINTENANCE_CADDY.read_text()
    infra = INFRA_MAIN.read_text()
    rds_database = RDS_DATABASE.read_text()

    for phase in (
        "preflight",
        "bootstrap-db",
        "backup-restore",
        "deploy",
        "maintenance",
        "live",
        "inspect",
    ):
        require(workflow, f"- {phase}", "production workflow")
    require(workflow, "environment: staging", "production workflow")
    require(workflow, "WP15_SSH_INGRESS=CLOSED", "production workflow")
    require(workflow, "python3 -m scripts.wp15_rds_database", "production workflow")
    require(workflow, "terraform -chdir=infra/staging import", "production workflow")
    require(workflow, "TF_VAR_approved_monthly_estimate_cny", "production workflow")
    if "terraform destroy" in workflow or "dropdb" in workflow:
        raise CutoverError("production workflow contains a destructive infrastructure/database command")
    if "aliyun" in workflow.lower() or "dns:Update" in workflow:
        raise CutoverError("deployment workflow must not mutate parent-zone DNS")
    bootstrap = workflow.split(
        "- name: Create only the empty isolated production database", 1
    )[1].split("- name: Prepare bounded SSH access", 1)[0]
    if "terraform plan" in bootstrap or "terraform apply" in bootstrap:
        raise CutoverError("database bootstrap must not plan/apply frozen infrastructure")
    for marker in (
        'DATABASE_NAME = "journey_next_production"',
        'OWNER = "journey_next_migrator"',
        '"CreateDatabase"',
        '"DescribeDatabases"',
        "EXACT_DATABASE_ALREADY_PRESENT",
    ):
        require(rds_database, marker, "production RDS bootstrap")

    require(compose, "name: journey-next-production", "production compose")
    require(compose, "journey-next-staging_default", "production compose")
    require(compose, "production-web", "production compose")
    if "ports:" in compose or "80:80" in compose or "443:443" in compose:
        raise CutoverError("production compose must not bind public ports")

    require(deploy, "APP_ENV=production", "production deploy")
    require(deploy, "journey_next_production", "production deploy")
    require(deploy, "docker compose up -d --remove-orphans --wait", "production deploy")
    require(deploy, "WP15_PRODUCTION_DEPLOY=PASS", "production deploy")
    if "python -m journey_api.seed" in deploy:
        raise CutoverError("production deploy must not seed business facts")
    require(grant, 'DATABASE = "journey_next_production"', "production runtime grant")
    if "journey_next_staging" in grant:
        raise CutoverError("production runtime grant references the staging database")

    for marker in (
        "pg_dump",
        "pg_restore",
        "--exit-on-error",
        "TARGET_DATABASE_NOT_EMPTY",
        "openssl enc -aes-256-cbc -pbkdf2",
        "manifest_hmac_sha256",
        "encrypted backup decrypt verification failed",
        'active_notification_recipients"] == 0',
        "WP15_BACKUP_RESTORE=PASS",
    ):
        require(backup, marker, "backup/restore script")
    if re.search(r"dropdb|DROP\s+DATABASE", backup, re.IGNORECASE):
        raise CutoverError("backup/restore script must never drop a database")

    require(caddy, "{$STAGING_HOST}", "edge Caddyfile")
    require(caddy, "{$PRODUCTION_HOST}", "edge Caddyfile")
    require(caddy, "reverse_proxy production-web:3000", "edge Caddyfile")
    require(maintenance, "respond", "maintenance Caddyfile")
    require(maintenance, "503", "maintenance Caddyfile")

    require(infra, 'resource "volcenginecc_rdspostgresql_database" "production"', "staging infrastructure")
    require(infra, 'db_name            = "journey_next_production"', "staging infrastructure")
    require(infra, "prevent_destroy = true", "production database")


def check() -> dict:
    contract = load_contract()
    validate_files(contract)
    return {
        "status": "PASS",
        "candidate": contract["candidate_sha"],
        "production_host": contract["production_host"],
        "staging_preserved": True,
        "production_mutation_executed": False,
    }


def main() -> None:
    try:
        result = check()
    except (OSError, CutoverError) as error:
        print(f"WP15_ALPHA_CUTOVER_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
