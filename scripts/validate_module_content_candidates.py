#!/usr/bin/env python3
"""Fail-closed validation for the Construction V1 module content candidates."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


EXPECTED_MODULES = {
    "exploration-camp": {"content_items": 4, "tasks": 3, "owner": "郑田源"},
    "newcomer-village": {"content_items": 2, "tasks": 2, "owner": "屠元琦"},
    "ai-academy": {"content_items": 3, "tasks": 1, "owner": "段超群"},
    "delivery-guild": {"content_items": 2, "tasks": 1, "owner": "段超群"},
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def module_hash(module: dict[str, object]) -> str:
    payload = copy.deepcopy(module)
    payload.pop("candidate_sha256", None)
    return sha256(payload)


def manifest_hash(manifest: dict[str, object]) -> str:
    payload = copy.deepcopy(manifest)
    payload.pop("manifest_sha256", None)
    return sha256(payload)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    require(
        manifest.get("schema_version") == "module-content-candidates.v1",
        "unexpected schema_version",
    )
    require(
        manifest.get("status")
        == "PRODUCT_OWNER_SUPPLEMENT_COMPLETE_PENDING_MODULE_OWNER_HASH_SIGNATURE",
        "candidate status must preserve personal signature gate",
    )

    reviewer = manifest["shared_reviewer_policy"]
    primary = reviewer["primary_reviewers"]
    backup = reviewer["backup_reviewers"]
    require(primary == ["万雨欣"], "unexpected primary reviewer")
    require(backup == ["屠元琦"], "unexpected backup reviewer")
    require(set(primary).isdisjoint(backup), "primary and backup reviewer must differ")
    require(reviewer["weekly_capacity_people"] == 25, "weekly capacity must be 25")
    for key in (
        "first_response_sla_minutes",
        "completion_sla_minutes",
        "revision_response_sla_minutes",
    ):
        require(isinstance(reviewer[key], int) and reviewer[key] > 0, f"invalid {key}")

    data_policy = manifest["shared_data_policy"]
    for key in (
        "production_write_allowed",
        "raw_customer_data_allowed",
        "ai_high_impact_decision_allowed",
    ):
        require(data_policy[key] is False, f"{key} must remain false")

    modules = manifest["modules"]
    by_key = {item["module_key"]: item for item in modules}
    require(len(modules) == 4, "exactly four modules required")
    require(set(by_key) == set(EXPECTED_MODULES), "module set mismatch")

    task_keys: set[str] = set()
    for module_key, expected in EXPECTED_MODULES.items():
        module = by_key[module_key]
        require(module["module_owner"] == expected["owner"], f"owner mismatch: {module_key}")
        require(
            module["owner_hash_signature_state"] == "PENDING_PERSONAL_HASH_ACCEPTANCE",
            f"machine must not sign for owner: {module_key}",
        )
        require(len(module["source_refs"]) >= 2, f"source_refs missing: {module_key}")
        require(
            len(module["content_items"]) == expected["content_items"],
            f"content count mismatch: {module_key}",
        )
        require(len(module["tasks"]) == expected["tasks"], f"task count mismatch: {module_key}")
        require(
            module["candidate_sha256"] == module_hash(module),
            f"candidate hash mismatch: {module_key}",
        )
        for task in module["tasks"]:
            task_key = task["task_key"]
            require(task_key not in task_keys, f"duplicate task_key: {task_key}")
            task_keys.add(task_key)
            require(len(task["purpose"]) >= 10, f"purpose too short: {task_key}")
            require(task["non_goals"], f"non_goals missing: {task_key}")
            require(task["inputs"], f"inputs missing: {task_key}")
            require(task["deliverables"], f"deliverables missing: {task_key}")
            require(task["estimated_minutes"] > 0, f"estimated_minutes invalid: {task_key}")
            require(
                task["execution_environment"] in {"SIMULATION", "CONTROLLED_REAL_TASK"},
                f"execution_environment invalid: {task_key}",
            )
            if task["execution_environment"] == "CONTROLLED_REAL_TASK":
                require(
                    bool(task.get("controlled_task_authorization_ref")),
                    f"controlled task authorization missing: {task_key}",
                )
            rubric = task["rubric"]
            require(rubric["dimensions"], f"rubric dimensions missing: {task_key}")
            require(rubric["human_decision_required"] is True, f"human gate missing: {task_key}")
            reward = task["reward_policy"]
            require(reward["talent_conclusion_effect"] == "NONE", f"points affect talent: {task_key}")

    require(
        manifest["manifest_sha256"] == manifest_hash(manifest),
        "manifest hash mismatch",
    )
    require("PENDING_COMPUTATION" not in path.read_text(encoding="utf-8"), "hash placeholder remains")

    signatures = manifest["required_human_signatures"]
    require(len(signatures) == 3, "exactly three personal signature records required")
    require(
        {item["person_name"] for item in signatures} == {"郑田源", "屠元琦", "段超群"},
        "signature roster mismatch",
    )
    return {
        "status": "PASS",
        "modules": len(modules),
        "tasks": len(task_keys),
        "content_items": sum(len(item["content_items"]) for item in modules),
        "owner_hash_signatures": "PENDING_3_PEOPLE_4_MODULES",
        "production_mutation_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.manifest), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
