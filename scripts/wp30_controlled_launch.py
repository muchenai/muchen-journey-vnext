#!/usr/bin/env python3
"""Read-only WP-30 controlled-launch manifest and metric validator.

The command performs no deployment, DNS, OAuth, Journey publication, invitation,
rollback, or cloud mutation. It turns missing authorization or readback evidence
into a fail-closed result instead of manufacturing launch state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from wp29_p0_rc import (
    DIGEST,
    FULL_SHA,
    MIGRATION,
    RcEvidenceError,
    SHA256,
    load_json,
    reject_sensitive_keys,
    validate_contract as validate_wp29_contract,
    validate_evidence as validate_wp29_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "wp30_controlled_launch_contract.json"
HTTPS_URL = re.compile(r"^https://[a-z0-9.-]+(?:/[a-zA-Z0-9_./-]*)?$")


class LaunchContractError(RuntimeError):
    """The launch manifest or PII-free observation is incomplete or unsafe."""


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise LaunchContractError(f"{label} must contain exactly: {', '.join(sorted(keys))}")
    return value


def validate_contract() -> dict[str, Any]:
    contract = load_json(CONTRACT_PATH)
    exact(
        contract,
        {
            "schema_version", "work_package", "state", "production_host",
            "staging_host", "organization_count", "cohort_learner_minimum",
            "cohort_learner_maximum", "required_controls", "stop_conditions",
            "required_acceptance", "production_gate",
        },
        "WP-30 contract",
    )
    if (
        contract["schema_version"] != 1
        or contract["work_package"] != "WP-30"
        or contract["state"] != "AWAITING_SIGNED_RC_AND_AUTHORIZATION"
        or contract["production_host"] != "journey.muchenai.com"
        or contract["staging_host"] != "staging-vnext.muchenai.com"
        or contract["organization_count"] != 1
        or contract["production_gate"] != "NO_GO"
        or contract["required_acceptance"] != [f"AT-WP30-{index:03d}" for index in range(1, 7)]
    ):
        raise LaunchContractError("WP-30 fixed contract changed")
    return contract


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_launch_manifest(
    manifest: dict[str, Any],
    *,
    contract: dict[str, Any],
    signed_rc_path: Path,
) -> dict[str, Any]:
    reject_sensitive_keys(manifest, "launch_manifest")
    wp29_contract = validate_wp29_contract()
    signed_rc = load_json(signed_rc_path)
    try:
        rc_binding = validate_wp29_evidence(signed_rc, wp29_contract)
    except RcEvidenceError as error:
        raise LaunchContractError(f"signed RC is invalid: {error}") from error
    exact(
        manifest,
        {
            "schema_version", "state", "release_binding", "wp29_evidence_sha256",
            "production", "cohort", "rollback", "controls", "authorizations",
            "production_gate",
        },
        "launch_manifest",
    )
    if (
        manifest["schema_version"] != 1
        or manifest["state"] != "READY_FOR_SEPARATE_AUTHORIZATIONS"
        or manifest["production_gate"] != "NO_GO"
    ):
        raise LaunchContractError("launch manifest must remain pre-mutation and production NO_GO")
    if manifest["wp29_evidence_sha256"] != file_sha256(signed_rc_path):
        raise LaunchContractError("launch manifest is not bound to the supplied signed RC")
    binding = exact(
        manifest["release_binding"],
        set(rc_binding),
        "release_binding",
    )
    if binding != rc_binding:
        raise LaunchContractError("launch release binding differs from the signed RC")
    for key in ("main_sha", "candidate_sha"):
        if FULL_SHA.fullmatch(str(binding[key])) is None:
            raise LaunchContractError(f"release_binding.{key} is invalid")
    for key in ("web_digest", "api_digest", "worker_digest"):
        if DIGEST.fullmatch(str(binding[key])) is None:
            raise LaunchContractError(f"release_binding.{key} is invalid")
    if MIGRATION.fullmatch(str(binding["migration"])) is None or SHA256.fullmatch(str(binding["openapi_sha256"])) is None:
        raise LaunchContractError("release migration or OpenAPI digest is invalid")

    production = exact(
        manifest["production"],
        {
            "host", "canonical_url", "oauth_callback", "staging_host",
            "tls_readback", "readiness_readback", "anonymous_ops_status",
            "anonymous_review_status",
        },
        "production",
    )
    if (
        production["host"] != contract["production_host"]
        or production["staging_host"] != contract["staging_host"]
        or production["canonical_url"] != f"https://{contract['production_host']}"
        or production["oauth_callback"] != f"https://{contract['production_host']}/auth/feishu/callback"
        or production["tls_readback"] != "AUTHORIZATION_REQUIRED"
        or production["readiness_readback"] != "AUTHORIZATION_REQUIRED"
        or production["anonymous_ops_status"] != 401
        or production["anonymous_review_status"] != 401
    ):
        raise LaunchContractError("production pre-authorization contract is incomplete")
    if HTTPS_URL.fullmatch(production["canonical_url"]) is None or HTTPS_URL.fullmatch(production["oauth_callback"]) is None:
        raise LaunchContractError("production URLs must use HTTPS")

    cohort = exact(
        manifest["cohort"],
        {
            "organization_count", "learner_count", "reviewer_count", "operator_count",
            "content_editor_count", "qa_support_count", "invitation_state",
        },
        "cohort",
    )
    if (
        cohort["organization_count"] != 1
        or not contract["cohort_learner_minimum"] <= cohort["learner_count"] <= contract["cohort_learner_maximum"]
        or cohort["reviewer_count"] < 2
        or cohort["operator_count"] != 1
        or cohort["content_editor_count"] != 1
        or cohort["qa_support_count"] < 1
        or cohort["invitation_state"] != "FROZEN_UNTIL_AUTHORIZATION"
    ):
        raise LaunchContractError("private cohort differs from the controlled-launch boundary")

    rollback = exact(
        manifest["rollback"],
        {"previous_release_sha", "maintenance_page_ref", "runbook_ref", "drill_state", "staging_retained"},
        "rollback",
    )
    if FULL_SHA.fullmatch(str(rollback["previous_release_sha"])) is None:
        raise LaunchContractError("rollback.previous_release_sha must be exact")
    if any(SHA256.fullmatch(str(rollback[key])) is None for key in ("maintenance_page_ref", "runbook_ref")):
        raise LaunchContractError("rollback evidence refs must be opaque sha256 values")
    if rollback["drill_state"] != "HUMAN_NOT_RUN" or rollback["staging_retained"] is not True:
        raise LaunchContractError("rollback drill must remain honest and staging retained")

    controls = exact(manifest["controls"], set(contract["required_controls"]), "controls")
    if any(value is not True for value in controls.values()):
        raise LaunchContractError("every controlled-launch safety control must be enabled")
    authorizations = exact(
        manifest["authorizations"],
        {"production_deploy", "journey_v3_publish", "private_invites", "dns_tls_oauth", "rollback_drill"},
        "authorizations",
    )
    if any(value != "NOT_GRANTED" for value in authorizations.values()):
        raise LaunchContractError("this preflight cannot consume or claim an authorization")
    return binding


def validate_observation(observation: dict[str, Any], contract: dict[str, Any]) -> str:
    reject_sensitive_keys(observation, "observation")
    exact(
        observation,
        {
            "schema_version", "date", "invited", "joined", "started", "completed",
            "support_interventions", "reviews_total", "reviews_within_sla",
            "unexpected_auth_errors", "business_fact_loss", "cross_org_access",
            "sustained_login_failure", "core_loop_interruption", "p0_events",
            "new_invites_frozen", "source_ref",
        },
        "observation",
    )
    if observation["schema_version"] != 1:
        raise LaunchContractError("observation schema_version must be 1")
    count_fields = (
        "invited", "joined", "started", "completed", "support_interventions",
        "reviews_total", "reviews_within_sla", "unexpected_auth_errors", "p0_events",
    )
    for key in count_fields:
        if not isinstance(observation[key], int) or isinstance(observation[key], bool) or observation[key] < 0:
            raise LaunchContractError(f"observation.{key} must be a non-negative integer")
    if not observation["completed"] <= observation["started"] <= observation["joined"] <= observation["invited"]:
        raise LaunchContractError("cohort metric numerators exceed their denominators")
    if observation["reviews_within_sla"] > observation["reviews_total"]:
        raise LaunchContractError("reviews_within_sla exceeds reviews_total")
    if not isinstance(observation["source_ref"], str) or SHA256.fullmatch(observation["source_ref"]) is None:
        raise LaunchContractError("observation.source_ref must be an opaque sha256 value")
    stop = (
        observation["business_fact_loss"] is True
        or observation["cross_org_access"] is True
        or observation["sustained_login_failure"] is True
        or observation["core_loop_interruption"] is True
        or observation["p0_events"] > 0
    )
    if stop and observation["new_invites_frozen"] is not True:
        raise LaunchContractError("a stop condition requires new invites to be frozen")
    return "STOP_NEW_INVITES" if stop else "CONTINUE_CONTROLLED_COHORT"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("contract-check", "preflight", "validate-observation"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--signed-rc", type=Path)
    parser.add_argument("--observation", type=Path)
    args = parser.parse_args()
    contract = validate_contract()
    if args.command == "contract-check":
        print("WP30_CONTRACT=PASS mutations=0 authorizations=DEFERRED production=NO_GO")
        return
    if args.command == "preflight":
        if args.manifest is None or args.signed_rc is None:
            raise SystemExit("WP30_PREFLIGHT=FAIL reason=--manifest and --signed-rc are required")
        binding = validate_launch_manifest(load_json(args.manifest), contract=contract, signed_rc_path=args.signed_rc)
        print(
            "WP30_PREFLIGHT=PASS state=READY_FOR_SEPARATE_AUTHORIZATIONS "
            f"candidate={binding['candidate_sha']} mutations=0 production=NO_GO"
        )
        return
    if args.observation is None:
        raise SystemExit("WP30_OBSERVATION=FAIL reason=--observation is required")
    decision = validate_observation(load_json(args.observation), contract)
    print(f"WP30_OBSERVATION=PASS decision={decision} pii=NONE")


if __name__ == "__main__":
    try:
        main()
    except (LaunchContractError, RcEvidenceError) as error:
        raise SystemExit(f"WP30=FAIL reason={error}") from error
