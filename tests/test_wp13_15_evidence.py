import copy
from datetime import datetime, timedelta, timezone

from scripts.wp13_15_evidence import (
    evaluate_pilot,
    evaluate_release,
    evaluate_uat,
    load_uat_rebind,
    validate_plans,
)


SHA = "02863d0b670ee9b00b9def3e75bc6699827f555a"
REF = "b" * 64


def passing_uat():
    return {
        "schema_version": 1,
        "environment": "staging",
        "candidate_sha": SHA,
        "release_binding": {
            "config_schema_version": 3,
            "deployment_run_id": "30519669770",
            "migration": "0014_wp12_data_lifecycle",
            "openapi_sha256": "90ea29045bba1e165d85ddaa695e2357015aff5f0346e9689376443b4965b55f",
        },
        "roster_counts": {
            "learners": 5,
            "operators": 1,
            "qa_recorders": 1,
            "reviewers": 2,
        },
        "roster_reference_sha256": REF,
        "scenarios": {f"AT-UAT-{index:03d}": "PASS" for index in range(1, 9)},
        "calibration": {
            "CLEAR_PASS": "PASS",
            "CLEAR_REVISION": "PASS",
            "BOUNDARY": "PASS",
        },
        "accessibility": {
            "VIEWPORT_390": "PASS",
            "VIEWPORT_768": "PASS",
            "VIEWPORT_1280": "PASS",
            "KEYBOARD_ONLY": "PASS",
            "ZOOM_200_PERCENT": "PASS",
            "APPLICABLE_ASSISTIVE_TECH": "PASS",
        },
        "five_second_understanding": {"numerator": 9, "denominator": 10},
        "open_defects": {"sev1": 0, "sev2": 0},
        "signatures": {
            "OPERATOR": "1" * 64,
            "PRODUCT_OWNER": "2" * 64,
            "QA_RECORDER": "3" * 64,
            "REVIEWER_1": "4" * 64,
            "REVIEWER_2": "5" * 64,
        },
    }


def passing_pilot(now):
    start = now - timedelta(days=15)
    return {
        "schema_version": 1,
        "candidate_sha": SHA,
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(days=14)).isoformat(),
        "checkpoints": {
            name: {
                "recorded_at": (start + timedelta(days=offset)).isoformat(),
                "reference_sha256": f"{offset:x}" * 64,
                "status": "PASS",
            }
            for name, offset in {"D+1": 1, "D+3": 3, "D+7": 7, "D+14": 14}.items()
        },
        "metrics": {
            "availability": {"numerator": 999, "denominator": 1000},
            "completion_rate": {"numerator": 4, "denominator": 5},
            "current_action_understanding": {"numerator": 9, "denominator": 10},
            "reviews_within_two_business_days": {"numerator": 9, "denominator": 10},
            "support_intervention": {"numerator": 1, "denominator": 5},
            "duplicate_facts": 0,
            "state_conflicts": 0,
        },
        "defects": {"sev1": 0, "sev2": 0, "trend": "CONVERGING"},
    }


def passing_release():
    from scripts.wp13_15_evidence import load_plans

    required = load_plans()[2]["required_checks"]
    return {
        "schema_version": 1,
        "environment": "production",
        "candidate_sha": SHA,
        "checks": {name: "PASS" for name in required},
        "approvals": [
            {
                "approved_at": "2026-07-01T00:00:00+00:00",
                "candidate_sha": SHA,
                "reference_sha256": "8" * 64,
                "role": "SECURITY",
            },
            {
                "approved_at": "2026-07-01T00:01:00+00:00",
                "candidate_sha": SHA,
                "reference_sha256": "9" * 64,
                "role": "OPS",
            },
        ],
    }


def test_plans_are_exact_and_no_action_is_executed():
    result = validate_plans()
    assert result["status"] == "PASS"
    assert (
        result["wp13_rebind_state"]
        == "RUNTIME_REPAIR_PRESTATE_VERIFIED_UAT_REJECTED"
    )
    assert result["wp13_rebind_resume_allowed"] is False
    assert result["human_actions_executed"] is False
    assert result["production_mutation_executed"] is False


def test_candidate_rebind_is_fail_closed_until_a_real_deployment_is_bound():
    rebind = load_uat_rebind()
    assert rebind["target_candidate_sha"] == "222096db506e95db887a8705b22ca4a439d0545d"
    assert rebind["runtime_change_scope"] == "WEB_UI_ONLY"
    assert rebind["deployment_run_id"] is None
    assert rebind["human_uat_resume_allowed"] is False
    assert rebind["latest_deployment_attempt"] == {
        "run_id": "30556851235",
        "conclusion": "CANCELLED_TIMEOUT",
        "web_release": "222096db506e95db887a8705b22ca4a439d0545d",
        "api_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
        "worker_release": "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
        "migration": "0013_wp11_notify_observability",
        "worker_stale": True,
        "ssh_ingress_closed": True,
    }
    assert rebind["runtime_repair_contract"] == {
        "phase": "repair-runtime",
        "confirmation": "REPAIR_RUNTIME_02863D0_FOR_WEB_222096D_STAGING",
        "web_mutation": False,
        "api_worker_baseline": "02863d0b670ee9b00b9def3e75bc6699827f555a",
        "migration_target": "0014_wp12_data_lifecycle",
        "observed_prestate_run_id": "30598785077",
        "observed_runtime_release": "222096db506e95db887a8705b22ca4a439d0545d",
        "deployment_authorized": False,
    }
    assert rebind["wp12b_rerun_executed"] is False
    assert rebind["production_mutation_executed"] is False


def test_uat_requires_every_human_status_threshold_and_signature():
    assert evaluate_uat(passing_uat())["decision"] == "UAT_SIGNED"
    failed = passing_uat()
    failed["scenarios"]["AT-UAT-006"] = "NOT_RUN"
    failed["five_second_understanding"] = {"numerator": 8, "denominator": 10}
    failed["signatures"]["REVIEWER_2"] = None
    result = evaluate_uat(failed)
    assert result["decision"] == "NO_GO"
    assert {
        "scenarios.AT-UAT-006",
        "five_second_understanding",
        "signature.REVIEWER_2",
    }.issubset(set(result["blockers"]))


def test_uat_rejects_candidate_drift_from_alpha_entry_gate():
    failed = passing_uat()
    failed["candidate_sha"] = "a" * 40
    result = evaluate_uat(failed)
    assert result["decision"] == "NO_GO"
    assert "candidate_drift" in result["blockers"]


def test_uat_rejects_release_binding_drift_from_alpha_entry_gate():
    failed = passing_uat()
    failed["release_binding"]["deployment_run_id"] = "different-run"
    result = evaluate_uat(failed)
    assert result["decision"] == "NO_GO"
    assert "candidate_binding" in result["blockers"]


def test_pilot_cannot_pass_before_real_14_days_or_with_bad_denominators():
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    assert evaluate_pilot(passing_pilot(now), uat=passing_uat(), now=now)[
        "decision"
    ] == "PILOT_ACCEPTED"
    early = passing_pilot(now)
    early["started_at"] = (now - timedelta(days=3)).isoformat()
    early["ended_at"] = (now + timedelta(days=11)).isoformat()
    result = evaluate_pilot(early, uat=passing_uat(), now=now)
    assert result["decision"] == "STOPPED"
    assert "real_14_day_window" in result["blockers"]


def test_release_requires_same_candidate_all_checks_and_two_distinct_approvals():
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    pilot = passing_pilot(now)
    assert evaluate_release(
        passing_release(), uat=passing_uat(), pilot=pilot, now=now
    )["decision"] == "RELEASE_GO"
    failed = passing_release()
    failed["checks"]["off_host_backup_restore"] = "NOT_RUN"
    failed["approvals"][1] = copy.deepcopy(failed["approvals"][0])
    result = evaluate_release(failed, uat=passing_uat(), pilot=pilot, now=now)
    assert result["decision"] == "NO_GO"
    assert {"off_host_backup_restore", "dual_release_approval"}.issubset(
        set(result["blockers"])
    )
