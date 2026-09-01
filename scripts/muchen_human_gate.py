#!/usr/bin/env python3
"""Validate real-person evidence for the frozen Exploration Camp candidate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import median
from typing import Any


PARTICIPANT_REF = re.compile(r"^[A-Z0-9_-]{3,32}$")
EVIDENCE_REF = re.compile(r"^[A-Za-z0-9_./-]{3,200}$")
REAL_EVIDENCE_KIND = "REAL_TARGET_LEARNER_HUMAN_EVIDENCE"
REQUIRED_HUMAN_GATES = {
    "orientation-10-seconds",
    "first-action-60-seconds",
    "clarity-and-continuation",
    "zero-facilitator-rescue",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def bounded_number(value: Any, minimum: float, maximum: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and minimum <= value <= maximum


def validate_contract(product: dict[str, Any]) -> list[str]:
    path = product.get("current_golden_path")
    if not isinstance(path, dict):
        return ["product contract has no current_golden_path"]
    ids = {
        item.get("id")
        for item in path.get("human_acceptance", [])
        if isinstance(item, dict)
    }
    if ids != REQUIRED_HUMAN_GATES:
        return ["human gate ids differ from the supported frozen-candidate protocol"]
    return []


def validate_pending(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if evidence.get("evidence_kind") != "NONE":
        errors.append("NOT_RUN evidence_kind must be NONE")
    if evidence.get("participants") != []:
        errors.append("NOT_RUN participants must be empty")
    if evidence.get("raw_evidence_refs") != []:
        errors.append("NOT_RUN raw_evidence_refs must be empty")
    return errors


def validate_protocol(protocol: Any) -> list[str]:
    if not isinstance(protocol, dict):
        return ["protocol must be an object"]
    expected = {
        "target_participant_count": 3,
        "unprompted": True,
        "facilitator_rescue_allowed": False,
        "orientation_limit_seconds": 10,
        "first_action_limit_seconds": 60,
        "minimum_median_rating": 4,
        "maximum_total_interventions": 0,
    }
    return [f"protocol.{key} must be {value}" for key, value in expected.items() if protocol.get(key) != value]


def validate_completed(evidence: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
    errors = validate_protocol(evidence.get("protocol"))
    if evidence.get("evidence_kind") != REAL_EVIDENCE_KIND:
        errors.append(f"COMPLETE evidence_kind must be {REAL_EVIDENCE_KIND}")
    participants = evidence.get("participants")
    refs = evidence.get("raw_evidence_refs")
    if not isinstance(participants, list) or len(participants) != 3:
        errors.append("COMPLETE evidence must contain exactly 3 participants")
        participants = []
    if not isinstance(refs, list) or not refs:
        errors.append("COMPLETE evidence must contain non-sensitive raw_evidence_refs")
        refs = []
    elif len(refs) != len(set(refs)):
        errors.append("raw_evidence_refs must be unique")
    for ref in refs:
        if not isinstance(ref, str) or not EVIDENCE_REF.fullmatch(ref) or ref.startswith("/") or ".." in Path(ref).parts:
            errors.append("raw_evidence_refs must be bounded repository-style identifiers")

    participant_refs: list[str] = []
    for index, participant in enumerate(participants):
        prefix = f"participants[{index}]"
        if not isinstance(participant, dict):
            errors.append(f"{prefix} must be an object")
            continue
        participant_ref = participant.get("participant_ref")
        if not isinstance(participant_ref, str) or not PARTICIPANT_REF.fullmatch(participant_ref):
            errors.append(f"{prefix}.participant_ref must be a pseudonymous bounded id")
        else:
            participant_refs.append(participant_ref)
        if participant.get("target_profile_confirmed") is not True:
            errors.append(f"{prefix}.target_profile_confirmed must be true")
        if participant.get("unprompted") is not True:
            errors.append(f"{prefix}.unprompted must be true")
        if not bounded_number(participant.get("orientation_seconds"), 0, 600):
            errors.append(f"{prefix}.orientation_seconds must be between 0 and 600")
        if not bounded_number(participant.get("first_material_seconds"), 0, 1800):
            errors.append(f"{prefix}.first_material_seconds must be between 0 and 1800")
        for key in ("progress_clarity", "willingness_to_continue"):
            value = participant.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                errors.append(f"{prefix}.{key} must be an integer from 1 to 5")
        interventions = participant.get("facilitator_interventions")
        if not isinstance(interventions, int) or isinstance(interventions, bool) or interventions < 0:
            errors.append(f"{prefix}.facilitator_interventions must be a non-negative integer")
        evidence_ref = participant.get("evidence_ref")
        if evidence_ref not in refs:
            errors.append(f"{prefix}.evidence_ref must reference raw_evidence_refs")
    if len(participant_refs) != len(set(participant_refs)):
        errors.append("participant_ref values must be unique")
    if errors:
        return errors, None

    orientation_passes = sum(item["orientation_seconds"] <= 10 for item in participants)
    first_action_passes = sum(item["first_material_seconds"] <= 60 for item in participants)
    clarity_median = float(median(item["progress_clarity"] for item in participants))
    continuation_median = float(median(item["willingness_to_continue"] for item in participants))
    interventions = sum(item["facilitator_interventions"] for item in participants)
    result = {
        "orientation_passes": orientation_passes,
        "first_action_passes": first_action_passes,
        "clarity_median": clarity_median,
        "continuation_median": continuation_median,
        "total_interventions": interventions,
    }
    return [], result


def evaluate(evidence: dict[str, Any], product: dict[str, Any], candidate: dict[str, Any]) -> tuple[str, list[str], dict[str, Any] | None]:
    errors = validate_contract(product)
    if evidence.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if evidence.get("candidate_id") != candidate.get("candidate_id"):
        errors.append("candidate_id differs from the frozen candidate")
    if evidence.get("golden_path") != candidate.get("golden_path"):
        errors.append("golden_path differs from the frozen candidate")
    state = evidence.get("state")
    if state == "NOT_RUN":
        errors.extend(validate_protocol(evidence.get("protocol")))
        errors.extend(validate_pending(evidence))
        return ("INVALID" if errors else "AWAITING_HUMAN"), errors, None
    if state != "COMPLETE":
        errors.append("state must be NOT_RUN or COMPLETE")
        return "INVALID", errors, None
    completed_errors, result = validate_completed(evidence)
    errors.extend(completed_errors)
    if errors or result is None:
        return "INVALID", errors, None
    passed = (
        result["orientation_passes"] == 3
        and result["first_action_passes"] == 3
        and result["clarity_median"] >= 4
        and result["continuation_median"] >= 4
        and result["total_interventions"] == 0
    )
    return ("HUMAN_PASS_CURRENT_GOLDEN_PATH" if passed else "HUMAN_FAIL"), [], result


def self_test(product: dict[str, Any], candidate: dict[str, Any]) -> None:
    protocol = {
        "target_participant_count": 3,
        "unprompted": True,
        "facilitator_rescue_allowed": False,
        "orientation_limit_seconds": 10,
        "first_action_limit_seconds": 60,
        "minimum_median_rating": 4,
        "maximum_total_interventions": 0,
    }
    participants = [
        {
            "participant_ref": f"P0{index}",
            "target_profile_confirmed": True,
            "unprompted": True,
            "orientation_seconds": 8,
            "first_material_seconds": 52,
            "progress_clarity": 4,
            "willingness_to_continue": 4,
            "facilitator_interventions": 0,
            "evidence_ref": f"evidence/human/p0{index}",
        }
        for index in range(1, 4)
    ]
    passing = {
        "schema_version": 1,
        "candidate_id": candidate["candidate_id"],
        "golden_path": candidate["golden_path"],
        "state": "COMPLETE",
        "evidence_kind": REAL_EVIDENCE_KIND,
        "protocol": protocol,
        "participants": participants,
        "raw_evidence_refs": [item["evidence_ref"] for item in participants],
    }
    verdict, errors, _ = evaluate(passing, product, candidate)
    assert verdict == "HUMAN_PASS_CURRENT_GOLDEN_PATH" and not errors
    failing = json.loads(json.dumps(passing))
    failing["participants"][0]["orientation_seconds"] = 11
    verdict, errors, _ = evaluate(failing, product, candidate)
    assert verdict == "HUMAN_FAIL" and not errors
    synthetic = json.loads(json.dumps(passing))
    synthetic["evidence_kind"] = "SYNTHETIC_MACHINE_TEST_NOT_HUMAN_EVIDENCE"
    verdict, errors, _ = evaluate(synthetic, product, candidate)
    assert verdict == "INVALID" and errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="?")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--candidate",
        default="outputs/muchen-journey-candidates/exploration-camp-first-meaningful-action-20260823-r1.json",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    product = load_json(repo / "config/muchen_journey_product.json")
    candidate = load_json(repo / args.candidate)
    if args.self_test:
        self_test(product, candidate)
        print("HUMAN_GATE_SELF_TEST=PASS")
        print("SYNTHETIC_EVIDENCE_ACCEPTED=false")
        return 0
    if not args.evidence:
        parser.error("evidence is required unless --self-test is used")
    evidence_path = (repo / args.evidence).resolve()
    try:
        evidence_path.relative_to(repo)
    except ValueError:
        print("HUMAN_GATE=INVALID\nERROR=evidence must stay inside repository")
        return 2
    evidence = load_json(evidence_path)
    verdict, errors, result = evaluate(evidence, product, candidate)
    print(f"HUMAN_GATE={verdict}")
    if result:
        for key, value in result.items():
            print(f"{key.upper()}={value}")
    for error in errors:
        print(f"ERROR={error}")
    print("PRODUCTION_MUTATION_EXECUTED=false")
    return 0 if verdict in {"AWAITING_HUMAN", "HUMAN_PASS_CURRENT_GOLDEN_PATH", "HUMAN_FAIL"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
