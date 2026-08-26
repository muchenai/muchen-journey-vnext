#!/usr/bin/env python3
"""Promote approved module candidates into deterministic formal content packages."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

try:
    from .validate_module_content_candidates import validate as validate_candidates
except ImportError:  # Direct script execution.
    from validate_module_content_candidates import validate as validate_candidates


OWNER_ROLES = {
    "exploration-camp": "exploration_camp_owner",
    "newcomer-village": "newcomer_village_owner",
    "ai-academy": "ai_academy_owner",
    "delivery-guild": "delivery_guild_owner",
}

PRIMARY_CONTENT_SOURCE = {
    "exploration-camp": "SRC-EXP-03",
    "newcomer-village": "SRC-NV-02",
    "ai-academy": "SRC-AIA-01",
    "delivery-guild": "SRC-WIKI-04",
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


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def package_hash(package: dict[str, object]) -> str:
    payload = copy.deepcopy(package)
    payload.pop("sha256", None)
    return sha256(payload)


def approval_index(evidence: dict[str, object]) -> dict[str, dict[str, object]]:
    approvals = evidence["approvals"]
    by_module = {item["module_key"]: item for item in approvals}
    require(set(by_module) == set(OWNER_ROLES), "four exact module approvals required")
    for module_key, item in by_module.items():
        require(item["decision"] == "APPROVED", f"approval missing: {module_key}")
        require(
            item["owner_role"] == OWNER_ROLES[module_key],
            f"owner role mismatch: {module_key}",
        )
    return by_module


def validate_source_binding(binding: dict[str, object]) -> None:
    require(binding["source_ref"] == "SRC-EXP-03", "wrong exploration source")
    require(binding["visible_owner"] == "郑田源", "source owner mismatch")
    require(binding["visible_access_mode"] == "READ_ONLY", "source not read-only")
    require(
        binding["binding_kind"] == "VERSION_METADATA_BINDING_NOT_FULL_CONTENT_EXPORT",
        "binding kind must remain explicit",
    )
    require(
        binding["binding_sha256"]
        == hashlib.sha256(binding["canonical_binding"].encode("utf-8")).hexdigest(),
        "exploration source binding hash mismatch",
    )
    require(binding["accepted_by_owner_attestation"] is True, "source binding not accepted")


def build_package(
    module: dict[str, object],
    approval: dict[str, object],
    reviewer: dict[str, object],
    data_policy: dict[str, object],
) -> dict[str, object]:
    module_key = module["module_key"]
    require(
        approval["candidate_sha256"] == module["candidate_sha256"],
        f"approved candidate hash mismatch: {module_key}",
    )
    require(approval["person_name"] == module["module_owner"], f"owner mismatch: {module_key}")

    content_items = []
    for item in module["content_items"]:
        content_items.append(
            {
                "content_id": item["content_id"],
                "title": item["title"],
                "version": "1.0.0",
                "source_ref": PRIMARY_CONTENT_SOURCE[module_key],
                "owner": module["module_owner"],
                "estimated_minutes": item["estimated_minutes"],
                "visibility": ["LEARNER", "REVIEWER", "OPERATOR"],
                "data_classification": "INTERNAL",
                "sha256": sha256(item),
            }
        )

    task_versions = []
    rubrics = []
    for task in module["tasks"]:
        rubric = task["rubric"]
        task_versions.append(
            {
                "task_key": task["task_key"],
                "version": "1.0.0",
                "purpose": task["purpose"],
                "non_goals": task["non_goals"],
                "inputs": task["inputs"],
                "deliverables": task["deliverables"],
                "rubric_id": rubric["rubric_id"],
                "reviewer_pool_ref": reviewer["pool_ref"],
                "help_path": f"{reviewer['pool_ref']} → {reviewer['escalation_owner']}",
                "execution_environment": task["execution_environment"],
                "retention_policy": f"{data_policy['default_retention_days']}_DAYS",
                "sha256": sha256(task),
            }
        )
        rubrics.append(
            {
                "rubric_id": rubric["rubric_id"],
                "version": "1.0.0",
                "dimensions": rubric["dimensions"],
                "human_decision_required": True,
                "calibration_evidence_ref": (
                    f"config/module-content-candidates.v1.json#{rubric['rubric_id']}"
                ),
                "sha256": sha256(rubric),
            }
        )

    package = {
        "schema_version": "module-content-package.v1",
        "package_id": module["package_id"],
        "module_key": module_key,
        "version": "1.0.0",
        "owner": {
            "role": OWNER_ROLES[module_key],
            "person_name": approval["person_name"],
            "signed_at": approval["approval_effective_at"],
            "decision": "APPROVED",
        },
        "source_refs": module["source_refs"],
        "effective_at": approval["approval_effective_at"],
        "content_items": content_items,
        "task_versions": task_versions,
        "rubrics": rubrics,
        "reviewer_policy": {
            "pool_ref": reviewer["pool_ref"],
            "primary_reviewers": reviewer["primary_reviewers"],
            "backup_reviewers": reviewer["backup_reviewers"],
            "first_response_sla_minutes": reviewer["first_response_sla_minutes"],
            "completion_sla_minutes": reviewer["completion_sla_minutes"],
            "escalation_owner": reviewer["escalation_owner"],
        },
        "data_policy": {
            "production_write_allowed": False,
            "raw_customer_data_allowed": False,
            "ai_high_impact_decision_allowed": False,
            "visibility": data_policy["visibility"],
            "retention_policy": f"{data_policy['default_retention_days']}_DAYS",
        },
        "sha256": "PENDING",
    }
    package["sha256"] = package_hash(package)
    return package


def validate_formal_package(package: dict[str, object]) -> None:
    required = {
        "schema_version",
        "package_id",
        "module_key",
        "version",
        "owner",
        "source_refs",
        "effective_at",
        "content_items",
        "task_versions",
        "rubrics",
        "reviewer_policy",
        "data_policy",
        "sha256",
    }
    require(set(package) == required, f"package fields invalid: {package['module_key']}")
    require(package["schema_version"] == "module-content-package.v1", "bad schema version")
    require(package["owner"]["decision"] == "APPROVED", "owner not approved")
    require(package["sha256"] == package_hash(package), "formal package hash mismatch")
    require(package["content_items"], "content items missing")
    require(package["task_versions"], "task versions missing")
    require(len(package["task_versions"]) == len(package["rubrics"]), "rubric count mismatch")
    require(
        set(package["reviewer_policy"]["primary_reviewers"]).isdisjoint(
            package["reviewer_policy"]["backup_reviewers"]
        ),
        "reviewer primary and backup must differ",
    )
    for key in (
        "production_write_allowed",
        "raw_customer_data_allowed",
        "ai_high_impact_decision_allowed",
    ):
        require(package["data_policy"][key] is False, f"unsafe data policy: {key}")
    for rubric in package["rubrics"]:
        require(rubric["human_decision_required"] is True, "human rubric gate missing")


def promote(
    candidates_path: Path,
    approvals_path: Path,
    binding_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    validate_candidates(candidates_path)
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    require(
        approvals["candidate_manifest_sha256"] == candidates["manifest_sha256"],
        "approval evidence points to wrong manifest",
    )
    validate_source_binding(binding)
    by_approval = approval_index(approvals)

    output_dir.mkdir(parents=True, exist_ok=True)
    package_entries = []
    for module in candidates["modules"]:
        module_key = module["module_key"]
        package = build_package(
            module,
            by_approval[module_key],
            candidates["shared_reviewer_policy"],
            candidates["shared_data_policy"],
        )
        validate_formal_package(package)
        path = output_dir / f"{module_key}.module-content-package.v1.json"
        path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        package_entries.append(
            {
                "module_key": module_key,
                "path": f"config/module-content-packages/{path.name}",
                "package_sha256": package["sha256"],
                "file_sha256": file_sha256(path),
            }
        )

    index = {
        "schema_version": "module-content-package-index.v1",
        "state": "G1_CONTENT_BINDING_PASS",
        "candidate_manifest_sha256": candidates["manifest_sha256"],
        "approval_evidence_sha256": sha256(approvals),
        "exploration_source_binding_sha256": binding["binding_sha256"],
        "packages": package_entries,
        "production_release_authorized": False,
        "index_sha256": "PENDING",
    }
    index["index_sha256"] = sha256({k: v for k, v in index.items() if k != "index_sha256"})
    index_path = output_dir / "module-content-package-index.v1.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--approvals", type=Path, required=True)
    parser.add_argument("--source-binding", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    index = promote(args.candidates, args.approvals, args.source_binding, args.output_dir)
    print(json.dumps(index, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
