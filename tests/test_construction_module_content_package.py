from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from journey_api.construction_module_content import (
    ConstructionModuleContentPackage,
    canonical_document_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "config" / "module-content-packages"


def _formal_package(module_key: str = "ai-academy") -> dict[str, object]:
    path = PACKAGE_DIR / f"{module_key}.module-content-package.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _signed_package(*, module_key: str = "ai-academy") -> dict[str, object]:
    owner_role = {
        "ai-academy": "ai_academy_owner",
        "delivery-guild": "delivery_guild_owner",
    }[module_key]
    content_item: dict[str, object] = {
        "content_id": "first-unit",
        "title": "合成机器测试单元",
        "version": "1",
        "source_ref": "SRC-AIA-01" if module_key == "ai-academy" else "SRC-GOV-01",
        "owner": "合成内容 Owner",
        "estimated_minutes": 30,
        "visibility": ["LEARNER", "REVIEWER"],
        "data_classification": "INTERNAL",
    }
    content_item["sha256"] = canonical_document_sha256(content_item)
    task: dict[str, object] = {
        "task_key": "AIA-SYNTHETIC-001" if module_key == "ai-academy" else "DLG-SYNTHETIC-001",
        "version": "1",
        "purpose": "仅用于验证内容包绑定，不代表 Owner 已批准真实内容。",
        "non_goals": ["不执行生产作业"],
        "inputs": ["合成输入"],
        "deliverables": ["合成练习记录"],
        "rubric_id": "rubric-synthetic-v1",
        "reviewer_pool_ref": "reviewer-pool-synthetic-v1",
        "help_path": "help/synthetic-only",
        "execution_environment": "SIMULATION",
        "retention_policy": "synthetic-test-only",
    }
    task["sha256"] = canonical_document_sha256(task)
    rubric: dict[str, object] = {
        "rubric_id": "rubric-synthetic-v1",
        "version": "1",
        "dimensions": ["证据可定位"],
        "human_decision_required": True,
        "calibration_evidence_ref": "evidence/synthetic-calibration",
    }
    rubric["sha256"] = canonical_document_sha256(rubric)
    package: dict[str, object] = {
        "schema_version": "module-content-package.v1",
        "package_id": f"{module_key}.synthetic.001",
        "module_key": module_key,
        "version": "1",
        "owner": {
            "role": owner_role,
            "person_name": "合成模块 Owner",
            "signed_at": "2026-08-26T01:00:00Z",
            "decision": "APPROVED",
        },
        "source_refs": ["SRC-AIA-01" if module_key == "ai-academy" else "SRC-GOV-01"],
        "effective_at": "2026-08-26T02:00:00Z",
        "expires_at": None,
        "content_items": [content_item],
        "task_versions": [task],
        "rubrics": [rubric],
        "reviewer_policy": {
            "pool_ref": "reviewer-pool-synthetic-v1",
            "primary_reviewers": ["合成主 Reviewer"],
            "backup_reviewers": ["合成备 Reviewer"],
            "first_response_sla_minutes": 60,
            "completion_sla_minutes": 1440,
            "escalation_owner": "合成升级 Owner",
        },
        "data_policy": {
            "production_write_allowed": False,
            "raw_customer_data_allowed": False,
            "ai_high_impact_decision_allowed": False,
            "visibility": ["PERSON", "ASSIGNED_REVIEWERS"],
            "retention_policy": "synthetic-test-only",
        },
    }
    package["sha256"] = canonical_document_sha256(package)
    return package


@pytest.mark.parametrize("module_key", ["ai-academy", "delivery-guild"])
def test_owner_signed_package_binds_every_nested_digest(module_key: str):
    package = ConstructionModuleContentPackage.model_validate(
        _signed_package(module_key=module_key)
    )

    assert package.module_key == module_key
    assert package.owner.decision == "APPROVED"
    assert package.data_policy.production_write_allowed is False


def test_four_formal_packages_pass_runtime_and_every_hash_layer():
    paths = sorted(PACKAGE_DIR.glob("*.module-content-package.v1.json"))

    assert len(paths) == 4
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        package = ConstructionModuleContentPackage.model_validate(document)
        assert package.sha256 == canonical_document_sha256(document)
        for collection in ("content_items", "task_versions", "rubrics"):
            for item in document[collection]:
                assert item["sha256"] == canonical_document_sha256(item)


@pytest.mark.parametrize(
    ("collection", "field", "value"),
    [
        ("content_items", "title", "篡改后的正式内容标题"),
        ("task_versions", "purpose", "篡改后的正式任务用途，不得通过嵌套 hash 校验。"),
        ("rubrics", "dimensions", ["篡改后的评分维度"]),
    ],
)
def test_formal_package_rejects_every_nested_hash_drift(
    collection: str, field: str, value: object
):
    document = _formal_package()
    document[collection][0][field] = value
    document["sha256"] = canonical_document_sha256(document)

    with pytest.raises(ValidationError, match=collection):
        ConstructionModuleContentPackage.model_validate(document)


def test_formal_package_rejects_root_owner_reviewer_and_policy_drift():
    root_drift = _formal_package()
    root_drift["reviewer_policy"]["completion_sla_minutes"] -= 1
    with pytest.raises(ValidationError, match="package sha256"):
        ConstructionModuleContentPackage.model_validate(root_drift)

    wrong_owner = _formal_package()
    wrong_owner["owner"]["role"] = "delivery_guild_owner"
    wrong_owner["sha256"] = canonical_document_sha256(wrong_owner)
    with pytest.raises(ValidationError, match="owner role"):
        ConstructionModuleContentPackage.model_validate(wrong_owner)

    overlap = _formal_package()
    overlap["reviewer_policy"]["backup_reviewers"] = overlap["reviewer_policy"][
        "primary_reviewers"
    ]
    overlap["sha256"] = canonical_document_sha256(overlap)
    with pytest.raises(ValidationError, match="must be separate"):
        ConstructionModuleContentPackage.model_validate(overlap)

    unsafe = _formal_package()
    unsafe["data_policy"]["production_write_allowed"] = True
    unsafe["sha256"] = canonical_document_sha256(unsafe)
    with pytest.raises(ValidationError):
        ConstructionModuleContentPackage.model_validate(unsafe)


def test_package_fails_closed_on_nested_or_top_level_hash_drift():
    nested_drift = _signed_package()
    nested_drift["task_versions"][0]["deliverables"] = ["被改写的交付物"]
    nested_drift["sha256"] = canonical_document_sha256(nested_drift)
    with pytest.raises(ValidationError, match="task_versions.*sha256"):
        ConstructionModuleContentPackage.model_validate(nested_drift)

    top_drift = _signed_package()
    top_drift["reviewer_policy"]["completion_sla_minutes"] = 1200
    with pytest.raises(ValidationError, match="package sha256"):
        ConstructionModuleContentPackage.model_validate(top_drift)


def test_package_rejects_wrong_owner_role_and_reviewer_overlap():
    wrong_owner = _signed_package()
    wrong_owner["owner"]["role"] = "delivery_guild_owner"
    wrong_owner["sha256"] = canonical_document_sha256(wrong_owner)
    with pytest.raises(ValidationError, match="owner role"):
        ConstructionModuleContentPackage.model_validate(wrong_owner)

    overlap = _signed_package()
    overlap["reviewer_policy"]["backup_reviewers"] = ["合成主 Reviewer"]
    overlap["sha256"] = canonical_document_sha256(overlap)
    with pytest.raises(ValidationError, match="must be separate"):
        ConstructionModuleContentPackage.model_validate(overlap)


def test_package_rejects_production_write_and_missing_real_task_authorization():
    production_write = _signed_package()
    production_write["data_policy"]["production_write_allowed"] = True
    production_write["sha256"] = canonical_document_sha256(production_write)
    with pytest.raises(ValidationError):
        ConstructionModuleContentPackage.model_validate(production_write)

    real_task = _signed_package()
    real_task["task_versions"][0]["execution_environment"] = "CONTROLLED_REAL_TASK"
    real_task["task_versions"][0]["sha256"] = canonical_document_sha256(
        real_task["task_versions"][0]
    )
    real_task["sha256"] = canonical_document_sha256(real_task)
    with pytest.raises(ValidationError, match="controlled task authorization"):
        ConstructionModuleContentPackage.model_validate(real_task)


def test_package_rejects_unknown_fields_and_non_authoritative_owner_decision():
    extra = _signed_package()
    extra["runtime_discovery"] = True
    extra["sha256"] = canonical_document_sha256(extra)
    with pytest.raises(ValidationError):
        ConstructionModuleContentPackage.model_validate(extra)

    pending = deepcopy(_signed_package())
    pending["owner"]["decision"] = "PENDING_OWNER_SIGNATURE"
    pending["sha256"] = canonical_document_sha256(pending)
    with pytest.raises(ValidationError):
        ConstructionModuleContentPackage.model_validate(pending)
