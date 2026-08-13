import copy
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wp29_p0_rc import RcEvidenceError, validate_contract, validate_evidence  # noqa: E402


H40 = "a" * 40
H64 = "b" * 64


def valid_evidence() -> dict:
    contract = validate_contract()
    return {
        "schema_version": 1,
        "state": "P0_RC_SIGNED",
        "release_binding": {
            "main_sha": H40,
            "candidate_sha": "c" * 40,
            "web_digest": f"sha256:{'1' * 64}",
            "api_digest": f"sha256:{'2' * 64}",
            "worker_digest": f"sha256:{'3' * 64}",
            "migration": "0021_p0_identity_principal",
            "openapi_sha256": "4" * 64,
            "journey_version_id": "11111111-1111-4111-8111-111111111111",
            "journey_revision": 2,
            "journey_release_label": "JOURNEY_V3",
            "journey_fingerprint": "5" * 64,
        },
        "uat_window": {
            "schedule": "10:00-19:00",
            "started_at": "2026-08-06T10:00:00+08:00",
            "ended_at": "2026-08-06T19:00:00+08:00",
        },
        "roster": dict(contract["minimum_roster"]),
        "browser_checks": {key: "PASS" for key in contract["browser_checks"]},
        "acceptance": {key: "PASS" for key in contract["required_acceptance"]},
        "evidence_refs": {key: H64 for key in contract["required_acceptance"]},
        "p0_blocker_count": 0,
        "post_launch_backlog_count": 2,
        "issue_ledger_ref": "d" * 64,
        "candidate_changed_during_uat": False,
        "journey_changed_during_uat": False,
        "distinct_human_roles": True,
        "automated_simulation_used": False,
        "original_failures_preserved": True,
        "signatures": [
            {
                "role": role,
                "attestation_ref": H64,
                "signed_at": "2026-08-06T19:10:00+08:00",
            }
            for role in contract["required_signatures"]
        ],
    }


def test_wp29_accepts_only_complete_pii_free_human_rc_evidence():
    contract = validate_contract()
    binding = validate_evidence(valid_evidence(), contract)
    assert binding["candidate_sha"] == "c" * 40
    assert binding["journey_release_label"] == "JOURNEY_V3"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item.update(p0_blocker_count=1), "zero P0 blockers"),
        (lambda item: item.update(automated_simulation_used=True), "automated_simulation_used"),
        (lambda item: item["acceptance"].update({"AT-WP29-004": "NOT_RUN"}), "must be PASS"),
        (lambda item: item["roster"].update({"learners": 2}), "below the minimum"),
        (lambda item: item["release_binding"].update({"journey_release_label": "JOURNEY_V2"}), "Journey V3"),
    ],
)
def test_wp29_fails_closed_for_missing_human_or_fixed_candidate_evidence(mutate, message):
    evidence = valid_evidence()
    mutate(evidence)
    with pytest.raises(RcEvidenceError, match=message):
        validate_evidence(evidence, validate_contract())


def test_wp29_rejects_pii_and_secret_shaped_fields_even_if_extra():
    evidence = copy.deepcopy(valid_evidence())
    evidence["email"] = "person@example.invalid"
    with pytest.raises(RcEvidenceError, match="forbidden"):
        validate_evidence(evidence, validate_contract())
