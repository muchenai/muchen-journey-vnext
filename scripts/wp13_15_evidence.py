#!/usr/bin/env python3
"""Fail-closed validation for WP-13 human UAT, WP-14 pilot, and WP-15 release.

This tool validates private evidence. It cannot create human outcomes, advance
wall-clock time, approve a release, or perform a production mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT / "config"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PASS = "PASS"
NOT_RUN = "NOT_RUN"


class EvidenceError(RuntimeError):
    """Evidence is malformed, inconsistent, premature, or unsafe."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"evidence must be an object: {path}")
    return value


def load_plans() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        load_json(CONFIG_ROOT / "wp13_uat_plan.json"),
        load_json(CONFIG_ROOT / "wp14_pilot_plan.json"),
        load_json(CONFIG_ROOT / "wp15_release_plan.json"),
    )


def load_uat_rebind() -> dict[str, Any]:
    return load_json(CONFIG_ROOT / "wp13_uat_rebind.json")


def exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def valid_reference(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_plans() -> dict[str, object]:
    uat, pilot, release = load_plans()
    rebind = load_uat_rebind()
    if uat != {
        "schema_version": 1,
        "environment": "staging",
        "entry_gate": {
            "alpha_p95_budget_seconds": 1.2,
            "approved_candidate_sha": "222096db506e95db887a8705b22ca4a439d0545d",
            "config_schema_version": 3,
            "decision": "CONDITIONAL_PASS_FOR_ALPHA",
            "deployment_run_id": "30616573615",
            "migration": "0014_wp12_data_lifecycle",
            "openapi_sha256": "90ea29045bba1e165d85ddaa695e2357015aff5f0346e9689376443b4965b55f",
            "production_p95_budget_seconds": 1.0,
            "wp12b_original_result": "FAIL",
            "wp12b_run_id": "30525165474",
        },
        "roster_minimums": {
            "learners": 5,
            "operators": 1,
            "qa_recorders": 1,
            "reviewers": 2,
        },
        "scenarios": [f"AT-UAT-{index:03d}" for index in range(1, 9)],
        "calibration_cases": ["CLEAR_PASS", "CLEAR_REVISION", "BOUNDARY"],
        "accessibility_checks": [
            "VIEWPORT_390",
            "VIEWPORT_768",
            "VIEWPORT_1280",
            "KEYBOARD_ONLY",
            "ZOOM_200_PERCENT",
            "APPLICABLE_ASSISTIVE_TECH",
        ],
        "required_signatures": [
            "OPERATOR",
            "PRODUCT_OWNER",
            "QA_RECORDER",
            "REVIEWER_1",
            "REVIEWER_2",
        ],
        "five_second_understanding_minimum": 0.9,
    }:
        raise EvidenceError("WP-13 plan differs from DEC-007/010/016")
    if pilot != {
        "schema_version": 1,
        "duration_days": 14,
        "checkpoints": {"D+1": 1, "D+3": 3, "D+7": 7, "D+14": 14},
        "thresholds": {
            "availability_minimum": 0.995,
            "completion_rate_minimum": 0.8,
            "current_action_understanding_minimum": 0.9,
            "duplicate_facts_maximum": 0,
            "reviews_within_two_business_days_minimum": 0.9,
            "state_conflicts_maximum": 0,
            "support_intervention_maximum": 0.2,
        },
    }:
        raise EvidenceError("WP-14 plan differs from DEC-010/013")
    checks = release.get("required_checks")
    expected_release_checks = [
        "candidate_binding",
        "production_resource_isolation",
        "managed_secrets",
        "restricted_ci_identity",
        "production_preflight",
        "physical_acl_validation",
        "real_human_uat",
        "real_pilot_observation",
        "real_external_notification",
        "external_observability_and_alert_drill",
        "off_host_backup_restore",
        "rpo_rto_validation",
        "rollback_or_maintenance_drill",
        "production_backup",
        "dual_release_approval",
        "old_system_read_only",
        "deployment_readiness_smoke",
        "production_observation_window",
    ]
    if (
        release.get("schema_version") != 1
        or release.get("required_approval_count") != 2
        or checks != expected_release_checks
    ):
        raise EvidenceError("WP-15 plan is incomplete")
    expected_rebind = {
        "schema_version": 2,
        "source_runtime_binding": {
            "web_candidate_sha": "222096db506e95db887a8705b22ca4a439d0545d",
            "api_candidate_sha": "02863d0b670ee9b00b9def3e75bc6699827f555a",
            "worker_candidate_sha": "02863d0b670ee9b00b9def3e75bc6699827f555a",
            "deployment_run_id": "30616573615",
            "migration": "0014_wp12_data_lifecycle",
            "config_schema_version": 3,
            "openapi_sha256": "90ea29045bba1e165d85ddaa695e2357015aff5f0346e9689376443b4965b55f",
            "api_status": "READY",
            "worker_stale": False,
            "ssh_ingress_closed": True,
        },
        "stopped_uat_incident": {
            "id": "UAT-WP13-002",
            "severity": "SEV2",
            "status": "REPAIR_CANDIDATE_BOUND_NOT_DEPLOYED",
            "prior_business_facts_preserved": True,
            "human_reverification_required": True,
        },
        "prior_binding_evidence": {
            "latest_deployment_attempt": {
                "run_id": "30556851235",
                "conclusion": "CANCELLED_TIMEOUT",
                "web_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "api_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
                "worker_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
                "migration": "0013_wp11_notify_observability",
                "worker_stale": True,
                "ssh_ingress_closed": True,
            },
            "latest_repair_attempt": {
                "run_id": "30595486997",
                "conclusion": "FAIL_CLOSED_PRESTATE",
                "application_or_database_mutation_executed": False,
                "ssh_ingress_closed": True,
            },
            "runtime_inventory": {
                "run_id": "30598785077",
                "workflow_head_sha": "16c50e4a0164193569fd96a59cb75229dad6906d",
                "conclusion": "SUCCESS_READ_ONLY",
                "web_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "api_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "worker_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "worker_heartbeat_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "migration": "0014_wp12_data_lifecycle",
                "config_schema_version": 3,
                "api_status": "READY",
                "worker_stale": False,
                "application_or_database_mutation_executed": False,
                "ssh_ingress_closed": True,
            },
            "runtime_repair_contract": {
                "phase": "repair-runtime",
                "confirmation": "REPAIR_RUNTIME_02863D0_FOR_WEB_222096D_STAGING",
                "web_mutation": False,
                "observed_prestate_run_id": "30598785077",
                "observed_runtime_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "api_worker_baseline": "02863d0b670ee9b00b9def3e75bc6699827f555a",
                "migration_target": "0014_wp12_data_lifecycle",
                "deployment_authorized": True,
                "authorization_consumed_run_id": "30616573615",
            },
            "successful_runtime_repair": {
                "run_id": "30616573615",
                "workflow_head_sha": "100e89494b8c42a6b04a86f5bdc26c06ab690fa7",
                "conclusion": "SUCCESS",
                "web_release": "222096db506e95db887a8705b22ca4a439d0545d",
                "api_release": "02863d0b670ee9b00b9def3e75bc6699827f555a",
                "worker_release": "02863d0b670ee9b00b9def3e75bc6699827f555a",
                "worker_heartbeat_release": "02863d0b670ee9b00b9def3e75bc6699827f555a",
                "migration": "0014_wp12_data_lifecycle",
                "config_schema_version": 3,
                "api_status": "READY",
                "worker_stale": False,
                "root_http_status": 200,
                "anonymous_ops_http_status": 401,
                "anonymous_review_http_status": 401,
                "ssh_ingress_closed": True,
                "forbidden_mutation_executed": False,
            },
        },
        "target_candidate_sha": "8f77ceec570e2ec5e9c52861fcdc27748d7bb44a",
        "candidate_gate_run_id": "30709982868",
        "candidate_manifest_sha256": "a7de07e531de4ee86562a04674d8807e4a9ce5cfc77fc8adcc98f4111809d637",
        "runtime_change_scope": "WEB_API_IDENTITY_REENTRY",
        "changed_runtime_contracts": {
            "api_tree": {
                "source_candidate_sha": "02863d0b670ee9b00b9def3e75bc6699827f555a",
                "source_tree_oid": "ddacd3a84c85ff14d88b89a80ec00decfc697b4d",
                "target_tree_oid": "7637fda7b2c6bb62280537b3b5eab0eab1f2c296",
            },
            "web_tree": {
                "source_candidate_sha": "222096db506e95db887a8705b22ca4a439d0545d",
                "source_tree_oid": "7cf05233054ccc59440b15acff927e6869d5c075",
                "target_tree_oid": "fa8550780849254b8b87e2a9fce892c6b68d72d1",
            },
            "public_contract": {
                "source_sha256": "90ea29045bba1e165d85ddaa695e2357015aff5f0346e9689376443b4965b55f",
                "target_sha256": "fe708e2c509c3cc004050e6ac6f8fc9eb21207d62e7d3482a5f8cc73b5b58d5b",
            },
        },
        "unchanged_runtime_contracts": {
            "worker_tree_oid": "e1314ea8768db383823290eb7d18068f2a01ae5b",
            "migrations_tree_oid": "c10e1597e9c701851fa74098e47a04f7f688f6ad",
            "python_lock_blob_oid": "e3997a3676800cb4e48a146689271cb712fe413e",
            "web_lock_blob_oid": "0a4f1454eceed7e80612100c813d5106a77e5738",
            "compose_blob_oid": "4ed5ffbd73b90d125fed7186927509c2161626b0",
        },
        "candidate_contract": {
            "config_schema_version": 3,
            "migration": "0014_wp12_data_lifecycle",
            "openapi_sha256": "fe708e2c509c3cc004050e6ac6f8fc9eb21207d62e7d3482a5f8cc73b5b58d5b",
            "task_versions_sha256": "c95d66f618a2b337c428d7c905f8c3d9a6cb561a5542ef2181874789fa872620",
        },
        "registry_digests": {
            "api": "sha256:553055d921f75bc7f7df0e176d5176f0546ee7f75f37e9757a0be09edf3520ff",
            "web": "sha256:401e5158fdcf7be11a3b2539fdbeb7c222ff9813267aa7c3cbcd7a2f9e24f1f5",
            "worker": "sha256:16bf2c7515d68fab164704438b23f691917213c8946a8c3dff8a4116fb3df0c7",
        },
        "inherited_wp12b_evidence": {
            "run_id": "30525165474",
            "original_result": "FAIL",
            "alpha_p95_budget_seconds": 1.2,
            "production_p95_budget_seconds": 1.0,
            "performance_inheritance_decision": "REQUIRES_REASSESSMENT_BEFORE_UAT_RESUME",
        },
        "decision": "REPAIR_CANDIDATE_BOUND_PENDING_STAGING_DEPLOY",
        "deployment_run_id": None,
        "deployment_authorized": False,
        "human_uat_resume_allowed": False,
        "wp12b_rerun_executed": False,
        "production_mutation_executed": False,
    }
    if rebind != expected_rebind:
        raise EvidenceError("WP-13 repair candidate rebind differs from the reviewed contract")
    return {
        "status": PASS,
        "wp13_scenarios": len(uat["scenarios"]),
        "wp14_duration_days": pilot["duration_days"],
        "wp15_required_checks": len(checks),
        "wp13_rebind_state": rebind["decision"],
        "wp13_rebind_resume_allowed": rebind["human_uat_resume_allowed"],
        "human_actions_executed": False,
        "production_mutation_executed": False,
    }


def ratio(metric: Any, label: str) -> float:
    values = exact_keys(metric, {"numerator", "denominator"}, label)
    numerator, denominator = values["numerator"], values["denominator"]
    if (
        not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or denominator <= 0
        or not 0 <= numerator <= denominator
    ):
        raise EvidenceError(f"{label} has an invalid numerator/denominator")
    return numerator / denominator


def candidate_sha(document: dict[str, Any], label: str) -> str:
    value = document.get("candidate_sha")
    if not isinstance(value, str) or FULL_SHA.fullmatch(value) is None:
        raise EvidenceError(f"{label} must bind a full candidate SHA")
    return value


def evaluate_uat(document: dict[str, Any]) -> dict[str, object]:
    plan, _, _ = load_plans()
    blockers: list[str] = []
    if document.get("schema_version") != 1 or document.get("environment") != "staging":
        raise EvidenceError("WP-13 evidence schema/environment is invalid")
    candidate = candidate_sha(document, "WP-13 evidence")
    if candidate != plan["entry_gate"]["approved_candidate_sha"]:
        blockers.append("candidate_drift")
    binding = exact_keys(
        document.get("release_binding"),
        {"config_schema_version", "deployment_run_id", "migration", "openapi_sha256"},
        "WP-13 release binding",
    )
    entry_gate = plan["entry_gate"]
    if binding != {
        "config_schema_version": entry_gate["config_schema_version"],
        "deployment_run_id": entry_gate["deployment_run_id"],
        "migration": entry_gate["migration"],
        "openapi_sha256": entry_gate["openapi_sha256"],
    }:
        blockers.append("candidate_binding")
    roster = exact_keys(
        document.get("roster_counts"), set(plan["roster_minimums"]), "WP-13 roster"
    )
    for role, minimum in plan["roster_minimums"].items():
        if not isinstance(roster[role], int) or roster[role] < minimum:
            blockers.append(f"roster.{role}")
    if not valid_reference(document.get("roster_reference_sha256")):
        blockers.append("roster_reference")
    for field, expected_items in (
        ("scenarios", plan["scenarios"]),
        ("calibration", plan["calibration_cases"]),
        ("accessibility", plan["accessibility_checks"]),
    ):
        values = exact_keys(document.get(field), set(expected_items), f"WP-13 {field}")
        blockers.extend(f"{field}.{item}" for item in expected_items if values[item] != PASS)
    understanding = ratio(document.get("five_second_understanding"), "WP-13 understanding")
    if understanding < plan["five_second_understanding_minimum"]:
        blockers.append("five_second_understanding")
    defects = exact_keys(document.get("open_defects"), {"sev1", "sev2"}, "WP-13 defects")
    if defects != {"sev1": 0, "sev2": 0}:
        blockers.append("sev1_sev2")
    signatures = exact_keys(
        document.get("signatures"), set(plan["required_signatures"]), "WP-13 signatures"
    )
    blockers.extend(
        f"signature.{role}"
        for role, reference in signatures.items()
        if not valid_reference(reference)
    )
    return {
        "decision": "UAT_SIGNED" if not blockers else "NO_GO",
        "candidate_sha": document["candidate_sha"],
        "blockers": sorted(set(blockers)),
        "understanding_rate": understanding,
        "human_evidence_required": True,
    }


def evaluate_pilot(
    document: dict[str, Any],
    *,
    uat: dict[str, Any],
    now: datetime,
) -> dict[str, object]:
    _, plan, _ = load_plans()
    uat_result = evaluate_uat(uat)
    blockers: list[str] = []
    if uat_result["decision"] != "UAT_SIGNED":
        blockers.append("wp13_uat")
    if document.get("schema_version") != 1:
        raise EvidenceError("WP-14 evidence schema is invalid")
    candidate = candidate_sha(document, "WP-14 evidence")
    if candidate != uat_result["candidate_sha"]:
        blockers.append("candidate_drift")
    started = parse_time(document.get("started_at"), "WP-14 started_at")
    ended = parse_time(document.get("ended_at"), "WP-14 ended_at")
    if ended - started < timedelta(days=plan["duration_days"]) or now < ended:
        blockers.append("real_14_day_window")
    checkpoints = exact_keys(
        document.get("checkpoints"), set(plan["checkpoints"]), "WP-14 checkpoints"
    )
    for name, offset in plan["checkpoints"].items():
        checkpoint = exact_keys(
            checkpoints[name], {"recorded_at", "reference_sha256", "status"}, name
        )
        recorded = parse_time(checkpoint["recorded_at"], f"{name} recorded_at")
        if (
            checkpoint["status"] != PASS
            or not valid_reference(checkpoint["reference_sha256"])
            or recorded < started + timedelta(days=offset)
            or recorded > now
        ):
            blockers.append(f"checkpoint.{name}")
    metrics = exact_keys(
        document.get("metrics"),
        {
            "availability",
            "completion_rate",
            "current_action_understanding",
            "duplicate_facts",
            "reviews_within_two_business_days",
            "state_conflicts",
            "support_intervention",
        },
        "WP-14 metrics",
    )
    measured = {
        "availability": ratio(metrics["availability"], "availability"),
        "completion_rate": ratio(metrics["completion_rate"], "completion_rate"),
        "current_action_understanding": ratio(
            metrics["current_action_understanding"], "current_action_understanding"
        ),
        "reviews_within_two_business_days": ratio(
            metrics["reviews_within_two_business_days"],
            "reviews_within_two_business_days",
        ),
        "support_intervention": ratio(
            metrics["support_intervention"], "support_intervention"
        ),
    }
    thresholds = plan["thresholds"]
    for name in (
        "availability",
        "completion_rate",
        "current_action_understanding",
        "reviews_within_two_business_days",
    ):
        if measured[name] < thresholds[f"{name}_minimum"]:
            blockers.append(name)
    if measured["support_intervention"] > thresholds["support_intervention_maximum"]:
        blockers.append("support_intervention")
    for name in ("duplicate_facts", "state_conflicts"):
        if not isinstance(metrics[name], int) or metrics[name] != 0:
            blockers.append(name)
    defects = exact_keys(
        document.get("defects"), {"sev1", "sev2", "trend"}, "WP-14 defects"
    )
    if (
        defects["sev1"] != 0
        or defects["sev2"] != 0
        or defects["trend"] not in {"STABLE", "CONVERGING"}
    ):
        blockers.append("defects")
    return {
        "decision": "PILOT_ACCEPTED" if not blockers else "STOPPED",
        "candidate_sha": candidate,
        "blockers": sorted(set(blockers)),
        "metrics": measured,
        "real_time_required": True,
    }


def evaluate_release(
    document: dict[str, Any],
    *,
    uat: dict[str, Any],
    pilot: dict[str, Any],
    now: datetime,
) -> dict[str, object]:
    _, _, plan = load_plans()
    uat_result = evaluate_uat(uat)
    pilot_result = evaluate_pilot(pilot, uat=uat, now=now)
    blockers: list[str] = []
    if document.get("schema_version") != 1 or document.get("environment") != "production":
        raise EvidenceError("WP-15 evidence schema/environment is invalid")
    candidate = candidate_sha(document, "WP-15 evidence")
    if candidate != uat_result["candidate_sha"] or candidate != pilot_result["candidate_sha"]:
        blockers.append("candidate_drift")
    checks = exact_keys(
        document.get("checks"), set(plan["required_checks"]), "WP-15 checks"
    )
    blockers.extend(name for name, status in checks.items() if status != PASS)
    approvals = document.get("approvals")
    if not isinstance(approvals, list) or len(approvals) < plan["required_approval_count"]:
        blockers.append("dual_release_approval")
    else:
        roles: set[str] = set()
        references: set[str] = set()
        for approval in approvals:
            values = exact_keys(
                approval,
                {"approved_at", "candidate_sha", "reference_sha256", "role"},
                "WP-15 approval",
            )
            approved_at = parse_time(values["approved_at"], "approval approved_at")
            if (
                values["candidate_sha"] != candidate
                or approved_at > now
                or not valid_reference(values["reference_sha256"])
                or not isinstance(values["role"], str)
                or not values["role"].strip()
            ):
                blockers.append("dual_release_approval")
            roles.add(str(values["role"]))
            references.add(str(values["reference_sha256"]))
        if len(roles) < 2 or len(references) < 2:
            blockers.append("dual_release_approval")
    if uat_result["decision"] != "UAT_SIGNED":
        blockers.append("real_human_uat")
    if pilot_result["decision"] != "PILOT_ACCEPTED":
        blockers.append("real_pilot_observation")
    return {
        "decision": "RELEASE_GO" if not blockers else "NO_GO",
        "candidate_sha": candidate,
        "blockers": sorted(set(blockers)),
        "production_mutation_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plans-check")
    uat = commands.add_parser("uat-check")
    uat.add_argument("evidence", type=Path)
    pilot = commands.add_parser("pilot-check")
    pilot.add_argument("evidence", type=Path)
    pilot.add_argument("--uat", type=Path, required=True)
    release = commands.add_parser("release-check")
    release.add_argument("evidence", type=Path)
    release.add_argument("--uat", type=Path, required=True)
    release.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    try:
        now = datetime.now(timezone.utc)
        if args.command == "plans-check":
            result = validate_plans()
        elif args.command == "uat-check":
            result = evaluate_uat(load_json(args.evidence))
        elif args.command == "pilot-check":
            result = evaluate_pilot(
                load_json(args.evidence), uat=load_json(args.uat), now=now
            )
        else:
            result = evaluate_release(
                load_json(args.evidence),
                uat=load_json(args.uat),
                pilot=load_json(args.pilot),
                now=now,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        decision = result.get("decision")
        return 0 if decision in {None, "UAT_SIGNED", "PILOT_ACCEPTED", "RELEASE_GO"} else 3
    except EvidenceError as error:
        print(f"WP13_15_EVIDENCE_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
