import hashlib
import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from test_wp29_p0_rc import valid_evidence  # noqa: E402
from wp30_controlled_launch import (  # noqa: E402
    LaunchContractError,
    validate_contract,
    validate_launch_manifest,
    validate_observation,
)


def write_signed_rc(tmp_path: Path) -> tuple[Path, dict]:
    evidence = valid_evidence()
    path = tmp_path / "signed-rc.json"
    path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
    return path, evidence


def valid_manifest(signed_rc_path: Path, signed_rc: dict) -> dict:
    return {
        "schema_version": 1,
        "state": "READY_FOR_SEPARATE_AUTHORIZATIONS",
        "release_binding": signed_rc["release_binding"],
        "wp29_evidence_sha256": hashlib.sha256(signed_rc_path.read_bytes()).hexdigest(),
        "production": {
            "host": "journey.muchenai.com",
            "canonical_url": "https://journey.muchenai.com",
            "oauth_callback": "https://journey.muchenai.com/auth/feishu/callback",
            "staging_host": "staging-vnext.muchenai.com",
            "tls_readback": "AUTHORIZATION_REQUIRED",
            "readiness_readback": "AUTHORIZATION_REQUIRED",
            "anonymous_ops_status": 401,
            "anonymous_review_status": 401,
        },
        "cohort": {
            "organization_count": 1,
            "learner_count": 5,
            "reviewer_count": 2,
            "operator_count": 1,
            "content_editor_count": 1,
            "qa_support_count": 1,
            "invitation_state": "FROZEN_UNTIL_AUTHORIZATION",
        },
        "rollback": {
            "previous_release_sha": "e" * 40,
            "maintenance_page_ref": "f" * 64,
            "runbook_ref": "0" * 64,
            "drill_state": "HUMAN_NOT_RUN",
            "staging_retained": True,
        },
        "controls": {key: True for key in validate_contract()["required_controls"]},
        "authorizations": {
            "production_deploy": "NOT_GRANTED",
            "journey_v3_publish": "NOT_GRANTED",
            "private_invites": "NOT_GRANTED",
            "dns_tls_oauth": "NOT_GRANTED",
            "rollback_drill": "NOT_GRANTED",
        },
        "production_gate": "NO_GO",
    }


def test_wp30_preflight_binds_signed_rc_without_consuming_authority(tmp_path):
    path, rc = write_signed_rc(tmp_path)
    binding = validate_launch_manifest(
        valid_manifest(path, rc), contract=validate_contract(), signed_rc_path=path
    )
    assert binding["candidate_sha"] == rc["release_binding"]["candidate_sha"]


def test_wp30_rejects_ungranted_action_marked_as_authorized(tmp_path):
    path, rc = write_signed_rc(tmp_path)
    manifest = valid_manifest(path, rc)
    manifest["authorizations"]["production_deploy"] = "GRANTED"
    with pytest.raises(LaunchContractError, match="cannot consume or claim"):
        validate_launch_manifest(manifest, contract=validate_contract(), signed_rc_path=path)


def observation(**overrides) -> dict:
    value = {
        "schema_version": 1,
        "date": "2026-08-10",
        "invited": 5,
        "joined": 5,
        "started": 4,
        "completed": 3,
        "support_interventions": 1,
        "reviews_total": 3,
        "reviews_within_sla": 3,
        "unexpected_auth_errors": 0,
        "business_fact_loss": False,
        "cross_org_access": False,
        "sustained_login_failure": False,
        "core_loop_interruption": False,
        "p0_events": 0,
        "new_invites_frozen": False,
        "source_ref": "9" * 64,
    }
    value.update(overrides)
    return value


def test_wp30_daily_observation_remains_pii_free_and_denominator_based():
    assert validate_observation(observation(), validate_contract()) == "CONTINUE_CONTROLLED_COHORT"


def test_wp30_stop_condition_requires_invite_freeze():
    with pytest.raises(LaunchContractError, match="requires new invites"):
        validate_observation(observation(p0_events=1), validate_contract())
    assert (
        validate_observation(observation(p0_events=1, new_invites_frozen=True), validate_contract())
        == "STOP_NEW_INVITES"
    )
