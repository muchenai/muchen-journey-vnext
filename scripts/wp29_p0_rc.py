#!/usr/bin/env python3
"""Fail-closed WP-29 RC evidence validator.

This tool cannot run human UAT, sign a release, deploy, publish a Journey,
create an invitation, or infer a human result. It only validates a private,
PII-free evidence manifest supplied after the real exercise.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "wp29_p0_rc_contract.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
MIGRATION = re.compile(r"^[0-9]{4}_[a-z0-9_]+$")
FORBIDDEN_KEYS = {
    "name", "display_name", "email", "phone", "mobile", "token", "secret",
    "answer", "submission_body", "invite_url", "oauth_code",
}


class RcEvidenceError(RuntimeError):
    """The RC contract or supplied human evidence is unsafe or incomplete."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RcEvidenceError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise RcEvidenceError(f"JSON root must be an object: {path}")
    return value


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise RcEvidenceError(f"{label} must contain exactly: {', '.join(sorted(keys))}")
    return value


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise RcEvidenceError(f"{label} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RcEvidenceError(f"{label} must be a timezone-aware ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RcEvidenceError(f"{label} must include a timezone")
    return parsed


def reject_sensitive_keys(value: Any, path: str = "evidence") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise RcEvidenceError(f"{path}.{key} is forbidden in PII-free evidence")
            reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_sensitive_keys(child, f"{path}[{index}]")


def validate_contract() -> dict[str, Any]:
    contract = load_json(CONTRACT_PATH)
    exact(
        contract,
        {
            "schema_version", "work_package", "state", "journey_release_label",
            "schedule", "minimum_roster", "required_acceptance",
            "browser_checks", "required_signatures", "allowed_issue_classes",
            "production_gate",
        },
        "WP-29 contract",
    )
    if (
        contract["schema_version"] != 1
        or contract["work_package"] != "WP-29"
        or contract["state"] != "HUMAN_UAT_NOT_RUN"
        or contract["journey_release_label"] != "JOURNEY_V3"
        or contract["schedule"] != "10:00-19:00"
        or contract["production_gate"] != "NO_GO"
    ):
        raise RcEvidenceError("WP-29 fixed contract changed")
    if contract["required_acceptance"] != [f"AT-WP29-{index:03d}" for index in range(1, 6)]:
        raise RcEvidenceError("WP-29 acceptance list changed")
    return contract


def validate_evidence(evidence: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    reject_sensitive_keys(evidence)
    exact(
        evidence,
        {
            "schema_version", "state", "release_binding", "uat_window",
            "roster", "browser_checks", "acceptance", "evidence_refs",
            "p0_blocker_count", "post_launch_backlog_count", "issue_ledger_ref",
            "candidate_changed_during_uat", "journey_changed_during_uat",
            "distinct_human_roles", "automated_simulation_used",
            "original_failures_preserved", "signatures",
        },
        "WP-29 evidence",
    )
    if evidence["schema_version"] != 1 or evidence["state"] != "P0_RC_SIGNED":
        raise RcEvidenceError("evidence must explicitly declare P0_RC_SIGNED")

    binding = exact(
        evidence["release_binding"],
        {
            "main_sha", "candidate_sha", "web_digest", "api_digest",
            "worker_digest", "migration", "openapi_sha256",
            "journey_version_id", "journey_revision", "journey_release_label",
            "journey_fingerprint",
        },
        "release_binding",
    )
    for key in ("main_sha", "candidate_sha"):
        if not isinstance(binding[key], str) or FULL_SHA.fullmatch(binding[key]) is None:
            raise RcEvidenceError(f"release_binding.{key} must be a full SHA")
    for key in ("web_digest", "api_digest", "worker_digest"):
        if not isinstance(binding[key], str) or DIGEST.fullmatch(binding[key]) is None:
            raise RcEvidenceError(f"release_binding.{key} must be a sha256 digest")
    if not isinstance(binding["migration"], str) or MIGRATION.fullmatch(binding["migration"]) is None:
        raise RcEvidenceError("release_binding.migration is invalid")
    if not isinstance(binding["openapi_sha256"], str) or SHA256.fullmatch(binding["openapi_sha256"]) is None:
        raise RcEvidenceError("release_binding.openapi_sha256 is invalid")
    try:
        UUID(str(binding["journey_version_id"]))
    except ValueError as error:
        raise RcEvidenceError("release_binding.journey_version_id must be a UUID") from error
    if (
        not isinstance(binding["journey_revision"], int)
        or isinstance(binding["journey_revision"], bool)
        or binding["journey_revision"] < 1
    ):
        raise RcEvidenceError("release_binding.journey_revision must be a positive integer")
    if binding["journey_release_label"] != contract["journey_release_label"]:
        raise RcEvidenceError("only fixed Journey V3 can enter WP-29")
    if not isinstance(binding["journey_fingerprint"], str) or SHA256.fullmatch(binding["journey_fingerprint"]) is None:
        raise RcEvidenceError("release_binding.journey_fingerprint is invalid")

    window = exact(evidence["uat_window"], {"schedule", "started_at", "ended_at"}, "uat_window")
    started_at = parse_time(window["started_at"], "uat_window.started_at")
    ended_at = parse_time(window["ended_at"], "uat_window.ended_at")
    if window["schedule"] != contract["schedule"] or ended_at <= started_at:
        raise RcEvidenceError("UAT must preserve the fixed full-day schedule and positive window")

    roster = exact(evidence["roster"], set(contract["minimum_roster"]), "roster")
    for role, minimum in contract["minimum_roster"].items():
        if not isinstance(roster[role], int) or isinstance(roster[role], bool) or roster[role] < minimum:
            raise RcEvidenceError(f"roster.{role} is below the minimum")

    expected_checks = set(contract["browser_checks"])
    checks = exact(evidence["browser_checks"], expected_checks, "browser_checks")
    if any(value != "PASS" for value in checks.values()):
        raise RcEvidenceError("every browser/accessibility check must be PASS")
    expected_acceptance = set(contract["required_acceptance"])
    acceptance = exact(evidence["acceptance"], expected_acceptance, "acceptance")
    if any(value != "PASS" for value in acceptance.values()):
        raise RcEvidenceError("every WP-29 acceptance item must be PASS")
    refs = exact(evidence["evidence_refs"], expected_acceptance, "evidence_refs")
    if any(not isinstance(value, str) or SHA256.fullmatch(value) is None for value in refs.values()):
        raise RcEvidenceError("acceptance evidence refs must be opaque sha256 values")

    if evidence["p0_blocker_count"] != 0:
        raise RcEvidenceError("P0_RC_SIGNED requires zero P0 blockers")
    if not isinstance(evidence["post_launch_backlog_count"], int) or isinstance(evidence["post_launch_backlog_count"], bool) or evidence["post_launch_backlog_count"] < 0:
        raise RcEvidenceError("post_launch_backlog_count must be a non-negative integer")
    if not isinstance(evidence["issue_ledger_ref"], str) or SHA256.fullmatch(evidence["issue_ledger_ref"]) is None:
        raise RcEvidenceError("issue_ledger_ref must be an opaque sha256 value")
    required_booleans = {
        "candidate_changed_during_uat": False,
        "journey_changed_during_uat": False,
        "distinct_human_roles": True,
        "automated_simulation_used": False,
        "original_failures_preserved": True,
    }
    for key, expected in required_booleans.items():
        if evidence[key] is not expected:
            raise RcEvidenceError(f"{key} must be {expected}")

    signatures = evidence["signatures"]
    if not isinstance(signatures, list) or len(signatures) != len(contract["required_signatures"]):
        raise RcEvidenceError("all required human signatures must be present exactly once")
    observed_roles: list[str] = []
    for index, item in enumerate(signatures):
        signature = exact(item, {"role", "attestation_ref", "signed_at"}, f"signatures[{index}]")
        observed_roles.append(signature["role"])
        if not isinstance(signature["attestation_ref"], str) or SHA256.fullmatch(signature["attestation_ref"]) is None:
            raise RcEvidenceError("signature attestation refs must be opaque sha256 values")
        parse_time(signature["signed_at"], f"signatures[{index}].signed_at")
    if observed_roles != contract["required_signatures"]:
        raise RcEvidenceError("signature roles or order differ from the fixed contract")
    return binding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("contract-check", "validate"))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    contract = validate_contract()
    if args.command == "contract-check":
        print("WP29_CONTRACT=PASS human_uat=NOT_RUN production=NO_GO")
        return
    if args.evidence is None:
        raise SystemExit("WP29_EVIDENCE=FAIL reason=--evidence is required")
    binding = validate_evidence(load_json(args.evidence), contract)
    print(
        "WP29_EVIDENCE=PASS state=P0_RC_SIGNED "
        f"candidate={binding['candidate_sha']} journey=JOURNEY_V3 production=NO_GO"
    )


if __name__ == "__main__":
    try:
        main()
    except RcEvidenceError as error:
        raise SystemExit(f"WP29_EVIDENCE=FAIL reason={error}") from error
