#!/usr/bin/env python3
"""Read-only validator for the AI Academy three-person human gate package."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


EXPECTED_CANDIDATE_ID = "ai-academy-first-explainable-practice-evidence-20260823-r1"
EXPECTED_COMMIT = "2e9561968d35676d09b3eacfe06b994276846e27"
EXPECTED_GOLDEN_PATH_ID = "ai-academy-first-explainable-practice-evidence"
EXPECTED_CRITERIA = [
    "goal-requirement-connection",
    "method-recall",
    "meaningful-first-practice",
    "evidence-boundary-comprehension",
    "clarity-and-continuation",
    "zero-facilitator-rescue",
]
METHOD_PARTS = {"outcome", "context", "constraints", "verification"}


class PackageError(ValueError):
    """Raised when a package cannot support a valid human-gate result."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PackageError(f"{path} must contain a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def require_identity(document: dict[str, Any], label: str) -> None:
    require(document.get("candidate_id") == EXPECTED_CANDIDATE_ID, f"{label}: candidate_id mismatch")
    require(document.get("candidate_commit") == EXPECTED_COMMIT, f"{label}: candidate_commit mismatch")
    require(document.get("golden_path_id") == EXPECTED_GOLDEN_PATH_ID, f"{label}: golden_path_id mismatch")


def require_contract(contract: dict[str, Any]) -> None:
    path = contract.get("active_golden_path", {})
    require(contract.get("status") == "READY_FOR_HUMAN", "contract must remain READY_FOR_HUMAN")
    require(path.get("id") == EXPECTED_GOLDEN_PATH_ID, "contract golden path mismatch")
    require(contract.get("machine_evaluation", {}).get("candidate_frozen") is True, "contract candidate must remain frozen")
    ids = [criterion.get("id") for criterion in path.get("human_acceptance", [])]
    require(ids == EXPECTED_CRITERIA, "contract human criteria changed or reordered")


def is_blank_text(value: Any) -> bool:
    return value is None


def require_not_run_session(session: dict[str, Any], slot: str) -> None:
    require(session.get("status") == "NOT_RUN", f"{slot}: status must be NOT_RUN")
    require(all(value is None for value in session.get("eligibility", {}).values()), f"{slot}: eligibility must be blank")
    require(all(value is None for value in session.get("timing_raw_seconds", {}).values()), f"{slot}: timings must be blank")
    connection = session.get("goal_requirement_connection", {})
    require(all(is_blank_text(value) for value in connection.values()), f"{slot}: connection observation must be blank")
    recall = session.get("method_recall", {})
    require(recall.get("named_parts") == [], f"{slot}: method recall must be blank")
    require(recall.get("captured_before_practice") is None, f"{slot}: method timing flag must be blank")
    practice = session.get("meaningful_first_practice", {})
    require(all(value is None for value in practice.values()), f"{slot}: practice observation must be blank")
    content = session.get("content_value", {})
    require(all(value is None for value in content.values()), f"{slot}: content value must be blank")
    boundary = session.get("evidence_boundary", {})
    require(all(value is None for value in boundary.values()), f"{slot}: evidence boundary must be blank")
    require(all(value is None for value in session.get("ratings_1_to_5", {}).values()), f"{slot}: ratings must be blank")
    facilitator = session.get("facilitator", {})
    require(facilitator.get("intervention_count") is None, f"{slot}: intervention count must be blank")
    require(facilitator.get("interventions") == [], f"{slot}: interventions must be blank")
    require(session.get("participant_safe_notes") is None, f"{slot}: notes must be blank")


def validate_not_run(records: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    sessions = records.get("sessions")
    require(isinstance(sessions, list) and len(sessions) == 3, "records must contain exactly three sessions")
    require([session.get("participant_slot") for session in sessions] == ["P1", "P2", "P3"], "participant slots must be P1, P2, P3")
    for session in sessions:
        require_not_run_session(session, session.get("participant_slot", "unknown"))

    require(result.get("status") == "NOT_RUN", "result status must be NOT_RUN")
    require(result.get("verdict") is None, "NOT_RUN result cannot contain a verdict")
    require(result.get("participant_count") == 0, "NOT_RUN participant_count must be 0")
    require(result.get("human_evidence_present") is False, "NOT_RUN cannot claim human evidence")
    criteria = result.get("criteria", [])
    require([item.get("id") for item in criteria] == EXPECTED_CRITERIA, "result criteria mismatch")
    require(all(item.get("status") == "NOT_RUN" and item.get("observed") is None for item in criteria), "all criteria must remain NOT_RUN and blank")
    diagnostic = result.get("content_value_diagnostic", {})
    require(diagnostic.get("status") == "NOT_RUN" and diagnostic.get("median_rating_1_to_5") is None, "content value must remain NOT_RUN")
    require(result.get("integration_authorized") is False, "integration cannot be authorized")
    require(result.get("release_authorized") is False, "release cannot be authorized")
    return {"status": "NOT_RUN", "verdict": None, "criteria": {criterion: "NOT_RUN" for criterion in EXPECTED_CRITERIA}}


def require_bool(value: Any, field: str) -> bool:
    require(type(value) is bool, f"{field} must be boolean")
    return value


def require_number(value: Any, field: str) -> float:
    require(type(value) in (int, float) and not isinstance(value, bool) and value >= 0, f"{field} must be a non-negative number")
    return float(value)


def require_rating(value: Any, field: str) -> int:
    require(type(value) is int and 1 <= value <= 5, f"{field} must be an integer from 1 to 5")
    return value


def require_text(value: Any, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field} must contain a de-identified observation")
    return value.strip()


def evaluate_completed_session(session: dict[str, Any]) -> dict[str, Any]:
    slot = session.get("participant_slot", "unknown")
    require(session.get("status") == "COMPLETED", f"{slot}: status must be COMPLETED")
    eligibility = session.get("eligibility", {})
    require(require_bool(eligibility.get("target_learner_profile_match"), f"{slot}.eligibility.target_learner_profile_match"), f"{slot}: participant must match target learner profile")
    require(not require_bool(eligibility.get("prior_design_involvement"), f"{slot}.eligibility.prior_design_involvement"), f"{slot}: prior design participants are invalid")
    require(require_bool(eligibility.get("independent_clean_browser_session"), f"{slot}.eligibility.independent_clean_browser_session"), f"{slot}: clean independent session required")

    timings = session.get("timing_raw_seconds", {})
    connection_seconds = require_number(timings.get("goal_requirement_connection_statement"), f"{slot}.timing.goal_requirement_connection_statement")
    milestones = [
        connection_seconds,
        require_number(timings.get("learning_input_opened"), f"{slot}.timing.learning_input_opened"),
        require_number(timings.get("practice_started"), f"{slot}.timing.practice_started"),
        require_number(timings.get("evidence_visible"), f"{slot}.timing.evidence_visible"),
        require_number(timings.get("session_total"), f"{slot}.timing.session_total"),
    ]
    require(milestones == sorted(milestones), f"{slot}: timing milestones must be monotonic")

    connection = session.get("goal_requirement_connection", {})
    require_text(connection.get("paraphrase_deidentified"), f"{slot}.goal_requirement_connection.paraphrase_deidentified")
    connection_confirmed = require_bool(connection.get("observer_confirms_connection"), f"{slot}.goal_requirement_connection.observer_confirms_connection")

    recall = session.get("method_recall", {})
    named_parts = recall.get("named_parts")
    require(isinstance(named_parts, list) and len(named_parts) == len(set(named_parts)), f"{slot}: named_parts must be a unique list")
    require(set(named_parts).issubset(METHOD_PARTS), f"{slot}: named_parts contains an unknown method part")
    recall_before_practice = require_bool(recall.get("captured_before_practice"), f"{slot}.method_recall.captured_before_practice")

    practice = session.get("meaningful_first_practice", {})
    independently_completed = require_bool(practice.get("completed_independently"), f"{slot}.practice.completed_independently")
    would_reuse = require_bool(practice.get("would_reuse_for_similar_work"), f"{slot}.practice.would_reuse_for_similar_work")
    require_text(practice.get("reuse_reason_deidentified"), f"{slot}.practice.reuse_reason_deidentified")

    content = session.get("content_value", {})
    content_rating = require_rating(content.get("rating_1_to_5"), f"{slot}.content_value.rating_1_to_5")
    require_text(content.get("reason_deidentified"), f"{slot}.content_value.reason_deidentified")

    boundary = session.get("evidence_boundary", {})
    require_text(boundary.get("what_record_proves_deidentified"), f"{slot}.evidence_boundary.what_record_proves_deidentified")
    require_text(boundary.get("what_record_does_not_prove_deidentified"), f"{slot}.evidence_boundary.what_record_does_not_prove_deidentified")
    boundary_confirmed = require_bool(boundary.get("observer_confirms_both_boundaries"), f"{slot}.evidence_boundary.observer_confirms_both_boundaries")

    ratings = session.get("ratings_1_to_5", {})
    goal_clarity = require_rating(ratings.get("goal_clarity"), f"{slot}.ratings.goal_clarity")
    evidence_clarity = require_rating(ratings.get("evidence_clarity"), f"{slot}.ratings.evidence_clarity")
    willingness = require_rating(ratings.get("willingness_to_continue"), f"{slot}.ratings.willingness_to_continue")

    facilitator = session.get("facilitator", {})
    interventions = facilitator.get("interventions")
    require(isinstance(interventions, list), f"{slot}: interventions must be a list")
    intervention_count = facilitator.get("intervention_count")
    require(type(intervention_count) is int and intervention_count >= 0, f"{slot}: intervention_count must be a non-negative integer")
    require(intervention_count == len(interventions), f"{slot}: intervention_count must equal interventions length")
    for index, intervention in enumerate(interventions):
        require(isinstance(intervention, dict), f"{slot}: intervention {index} must be an object")
        require_number(intervention.get("elapsed_seconds"), f"{slot}.interventions[{index}].elapsed_seconds")
        require_text(intervention.get("type"), f"{slot}.interventions[{index}].type")
        require_text(intervention.get("description_deidentified"), f"{slot}.interventions[{index}].description_deidentified")

    return {
        "connection_pass": connection_seconds <= 20 and connection_confirmed,
        "method_recall_pass": len(named_parts) >= 3 and recall_before_practice,
        "meaningful_practice_pass": independently_completed and would_reuse and intervention_count == 0,
        "evidence_boundary_pass": boundary_confirmed,
        "goal_clarity": goal_clarity,
        "evidence_clarity": evidence_clarity,
        "willingness": willingness,
        "content_value": content_rating,
        "intervention_count": intervention_count,
    }


def evaluate_completed(records: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    sessions = records.get("sessions")
    require(isinstance(sessions, list) and len(sessions) == 3, "records must contain exactly three sessions")
    require([session.get("participant_slot") for session in sessions] == ["P1", "P2", "P3"], "participant slots must be P1, P2, P3")
    observations = [evaluate_completed_session(session) for session in sessions]
    medians = {
        "goal_clarity": statistics.median(item["goal_clarity"] for item in observations),
        "evidence_clarity": statistics.median(item["evidence_clarity"] for item in observations),
        "willingness_to_continue": statistics.median(item["willingness"] for item in observations),
    }
    computed = {
        "goal-requirement-connection": all(item["connection_pass"] for item in observations),
        "method-recall": all(item["method_recall_pass"] for item in observations),
        "meaningful-first-practice": all(item["meaningful_practice_pass"] for item in observations),
        "evidence-boundary-comprehension": all(item["evidence_boundary_pass"] for item in observations),
        "clarity-and-continuation": all(value >= 4 for value in medians.values()),
        "zero-facilitator-rescue": sum(item["intervention_count"] for item in observations) == 0,
    }
    verdict = "HUMAN_PASS_CURRENT_GOLDEN_PATH" if all(computed.values()) else "HUMAN_FAIL"

    require(result.get("status") == "COMPLETED", "completed records require completed result")
    require(result.get("verdict") == verdict, f"result verdict must be {verdict}")
    require(result.get("participant_count") == 3, "completed participant_count must be 3")
    require(result.get("human_evidence_present") is True, "completed result must acknowledge human evidence")
    criteria = result.get("criteria", [])
    require([item.get("id") for item in criteria] == EXPECTED_CRITERIA, "result criteria mismatch")
    for item in criteria:
        expected_status = "PASS" if computed[item["id"]] else "FAIL"
        require(item.get("status") == expected_status, f"{item['id']}: status must be {expected_status}")
        require(item.get("observed") is not None, f"{item['id']}: observed summary is required")
    diagnostic = result.get("content_value_diagnostic", {})
    require(diagnostic.get("status") == "RECORDED", "content value diagnostic must be RECORDED")
    expected_content_median = statistics.median(item["content_value"] for item in observations)
    require(diagnostic.get("median_rating_1_to_5") == expected_content_median, "content value median mismatch")
    require(result.get("integration_authorized") is False, "human result cannot authorize integration")
    require(result.get("release_authorized") is False, "human result cannot authorize release")
    return {
        "status": "COMPLETED",
        "verdict": verdict,
        "criteria": {criterion: "PASS" if passed else "FAIL" for criterion, passed in computed.items()},
        "medians": medians,
        "content_value_median": expected_content_median,
    }


def validate(records: dict[str, Any], result: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require_contract(contract)
    require_identity(records, "records")
    require_identity(result, "result")
    require(records.get("schema_version") == 1, "records schema_version must be 1")
    require(result.get("schema_version") == 1, "result schema_version must be 1")
    require(records.get("protocol", {}).get("participants_required") == 3, "protocol must require three participants")
    require(records.get("protocol", {}).get("candidate_must_remain_frozen") is True, "protocol must keep candidate frozen")
    require(records.get("privacy", {}).get("direct_identifiers_allowed") is False, "direct identifiers must be prohibited")
    require(records.get("privacy", {}).get("real_business_content_allowed") is False, "real business content must be prohibited")
    require(records.get("privacy", {}).get("learner_practice_original_text_allowed") is False, "learner practice original text must be prohibited")
    status = records.get("status")
    require(status in {"NOT_RUN", "COMPLETED"}, "records status must be NOT_RUN or COMPLETED")
    return validate_not_run(records, result) if status == "NOT_RUN" else evaluate_completed(records, result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="three-person record package JSON")
    parser.add_argument("--result", type=Path, required=True, help="human result JSON")
    parser.add_argument("--contract", type=Path, required=True, help="frozen AI Academy contract JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = validate(load_json(args.records), load_json(args.result), load_json(args.contract))
    except PackageError as exc:
        print("HUMAN_VALIDATION_PACKAGE=FAIL")
        print(f"ERROR={exc}")
        return 2
    print("HUMAN_VALIDATION_PACKAGE=PASS")
    print(f"HUMAN_VALIDATION_STATUS={report['status']}")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
