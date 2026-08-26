#!/usr/bin/env python3
"""Create an immutable, hash-bound inventory of the current release worktree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


OUTPUT_ROOT = Path("outputs/controller-integration/2026-09-01-controlled-release")

RELEASE_REQUIRED_EXACT = {
    "config/muchen_journey_product.json",
    "config/muchen_journey_2026_09_01_controlled_release.json",
    "docs/baselines/Muchen_Journey_2026_09_01_受控首发台账.md",
    "docs/baselines/Muchen_Journey_Owner任命与接受记录_V0.1.md",
    "docs/baselines/Muchen_Journey_Build_Contract签署决议单_V0.1.md",
    "docs/baselines/Muchen_Journey_Build_Contract签署包_V0.1.md",
    "docs/baselines/Muchen_Journey_G1共享领域模型去重审计与唯一运行纵切_V0.2.md",
    "docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.3.md",
    "docs/baselines/Muchen_Journey_产品-代码继承映射表_V0.1.md",
    "docs/baselines/Muchen_Journey_全模块开发解锁决议_V0.1.md",
    "docs/baselines/Muchen_Journey_冲突裁决清单_V0.1.md",
    "docs/baselines/OWNER_LEGACY_DISPOSITION_DECISION_REFERENCE_ONLY_NO_MIGRATION_V0.1.md",
    "docs/baselines/JOURNEY2_DOMAIN_MODEL_REBASE_PACKAGE_V0.1.md",
    "docs/baselines/build-contracts/00_Build_Contract_总索引_V0.1.md",
    "docs/baselines/build-contracts/01_Shared_People_Domain_Contract_V0.1.md",
    "docs/baselines/build-contracts/02_G2_探索营与新手村共享闭环接线_V0.1.md",
    "docs/baselines/build-contracts/03_G3_AI学院_公会_认证共享闭环接线_V0.1.md",
    "docs/baselines/build-contracts/06_G6_独立QA_UAT与发布复核合同_V0.1.md",
    "docs/baselines/build-contracts/06A_G6_2026_09_01受控首发合同_V0.1.md",
    "docs/baselines/build-contracts/07_G7_当前Golden_Path机器复核与语义校正_V0.1.md",
    "docs/baselines/build-contracts/08_G8_受控任务授权强绑定接线_V0.1.md",
    "docs/baselines/build-contracts/09_G9_AI学院与公会模块包强绑定接线_V0.1.md",
    "docs/baselines/build-contracts/BC-001_探索营_V1.0_V0.1.md",
    "docs/baselines/build-contracts/BC-002_新手村受控任务闭环_V0.1.md",
    "docs/baselines/build-contracts/BC-003_AI学院_V0.1.md",
    "docs/baselines/build-contracts/BC-004_公会_V0.1.md",
    "apps/api/journey_api/controlled_task_authorization.py",
    "apps/api/journey_api/appeal_continuity.py",
    "apps/api/journey_api/formal_result_handoff.py",
    "apps/api/journey_api/module_execution_package.py",
    "apps/api/journey_api/outcome_routes.py",
    "apps/api/journey_api/program_release_readiness.py",
    "apps/api/journey_api/routes.py",
    "apps/api/journey_api/schemas.py",
    "apps/api/journey_api/shared_domain.py",
    "apps/api/journey_api/shared_domain_projection.py",
    "apps/web/package-lock.json",
    "apps/web/package.json",
    "contracts/openapi.json",
    "scripts/muchen_candidate.py",
    "scripts/muchen_human_gate.py",
    "scripts/muchen_controlled_release_inventory.py",
    "scripts/muchen_controlled_release_stage.py",
    "tests/test_api_walking_skeleton.py",
    "tests/test_controlled_release_worktree_inventory.py",
    "tests/test_controlled_release_stage.py",
    "tests/test_current_action_tasks.py",
    "tests/test_domain.py",
    "tests/test_formal_journey_vertical_slice.py",
    "tests/test_controlled_task_authorization_contract.py",
    "tests/test_formal_result_handoff_contract.py",
    "tests/test_g2_exploration_newcomer_vertical_loop.py",
    "tests/test_module_execution_package_contract.py",
    "tests/test_program_release_readiness.py",
    "tests/test_shared_domain_projection.py",
    "tests/test_shared_people_domain_contract.py",
}

RELEASE_REQUIRED_PREFIXES = (
    "apps/web/src/app/app/maps/",
    "outputs/controller-integration/2026-09-01-controlled-release/",
    "outputs/controller-integration/JOURNEY2_DOMAIN_MODEL_REBASE_PACKAGE",
    "outputs/controller-integration/g2-exploration-newcomer-shared-loop/",
    "outputs/controller-integration/g3-ai-guild-certification-shared-loop/",
    "outputs/controller-integration/g6-independent-qa-release-readiness/",
    "outputs/controller-integration/g7-current-golden-path-reconciliation/",
    "outputs/controller-integration/shared-people-domain-g1/",
    "outputs/controller-integration/g8-controlled-task-authorization-binding/",
    "outputs/controller-integration/g9-ai-guild-module-package-binding/",
    "outputs/controller-integration/journey2-domain-model-rebase-v0.1/",
    "outputs/map-workstreams/exploration-camp/",
    "outputs/map-workstreams/newcomer-village/",
    "outputs/map-workstreams/ai-academy/",
    "outputs/map-workstreams/delivery-guild/",
    "outputs/muchen-journey-candidates/exploration-camp-",
)

RELEASE_REQUIRED_WEB = {
    "apps/web/scripts/exploration-camp-private-invite-orientation-contract.test.mjs",
    "apps/web/scripts/full-module-journey-contract.test.mjs",
    "apps/web/scripts/product-entry-contract.test.mjs",
    "apps/web/src/app/app/journey-map.tsx",
    "apps/web/src/app/app/page.tsx",
    "apps/web/src/app/app/program-overview.tsx",
    "apps/web/src/app/app/result/page.tsx",
    "apps/web/src/app/globals.css",
    "apps/web/src/app/join/private-invite-orientation.module.css",
    "apps/web/src/app/join/private-invite-orientation.tsx",
    "apps/web/src/app/page.tsx",
    "apps/web/src/lib/journey-program.ts",
    "apps/web/src/lib/muchen-journey-controlled-release.generated.json",
    "apps/web/src/lib/muchen-journey-product.generated.json",
    "apps/web/src/lib/server/api.ts",
}

CONSTRUCTION_V1_REQUIRED_EXACT = {
    "Makefile",
    "apps/api/Dockerfile",
    "apps/api/journey_api/construction_module_content.py",
    "apps/api/journey_api/construction_module_routes.py",
    "apps/api/journey_api/controlled_task_routes.py",
    "apps/api/journey_api/controlled_task_runtime.py",
    "apps/api/journey_api/formal_assignment_workflow.py",
    "apps/api/journey_api/identity_routes.py",
    "apps/api/journey_api/incentive_ledger.py",
    "apps/api/journey_api/journey_service.py",
    "apps/api/journey_api/main.py",
    "apps/api/journey_api/models.py",
    "apps/api/journey_api/next_stage_review_routes.py",
    "apps/api/journey_api/ops_routes.py",
    "apps/api/journey_api/review_routes.py",
    "apps/api/journey_api/submission_routes.py",
    "apps/api/journey_api/submission_service.py",
    "apps/web/Dockerfile",
    "apps/web/pnpm-lock.yaml",
    "apps/web/pnpm-workspace.yaml",
    "apps/worker/Dockerfile",
    "migrations/versions/0020_shared_ai_provenance.py",
    "migrations/versions/0021_incentive_ledger.py",
    "migrations/versions/0022_next_training_stage_review.py",
    "migrations/versions/0023_controlled_task_acceptance.py",
    "migrations/versions/0024_module_content_package_binding.py",
    "migrations/versions/0025_formal_result_gate.py",
    "migrations/versions/0026_identity_organization_scope.py",
    "migrations/versions/0027_next_training_stage_independent_review.py",
    "requirements-build.lock",
    "requirements.lock",
    "scripts/muchen_construction_v1_baseline.py",
    "scripts/muchen_legacy_zero_migration_gate.py",
    "scripts/wp06_ops.py",
    "tests/test_construction_module_content_package.py",
    "tests/test_construction_module_runtime.py",
    "tests/test_construction_legacy_zero_migration.py",
    "tests/test_construction_v1_baseline.py",
    "tests/test_controlled_task_acceptance_runtime.py",
    "tests/test_formal_assignment_workflow.py",
    "tests/test_formal_result_database_gate.py",
    "tests/test_core_identity_database_gate.py",
    "tests/test_incentive_ledger_runtime.py",
    "tests/test_identity_invites.py",
    "tests/test_next_training_stage_runtime.py",
    "tests/test_next_training_stage_semantics.py",
    "tests/test_ops_governance_import.py",
    "tests/test_wp06_ops_script.py",
    "tests/test_reviewer_workbench.py",
    "tests/test_supply_chain_hardening.py",
    "tests/test_wp07_candidate.py",
    "tests/test_wp26_learning_materials.py",
}

CONSTRUCTION_V1_WEB_EXACT = {
    "apps/web/scripts/wp24-formal-camp-v2-contract.test.mjs",
    "apps/web/src/app/actions.ts",
    "apps/web/src/app/app/tasks/[assignmentId]/submission-composer.tsx",
    "apps/web/src/app/ops/formal-admission-panel.tsx",
    "apps/web/src/app/ops/invite-management-panel.tsx",
    "apps/web/src/app/ops/page.tsx",
    "apps/web/src/app/review/[reviewId]/page.tsx",
    "apps/web/src/app/review/[reviewId]/review-workbench.tsx",
}

CONSTRUCTION_V1_EVIDENCE_EXACT = {
    "docs/baselines/MINI_AUTONOMOUS_CONSTRUCTION_EXECUTION_LEDGER_V1.0.md",
    "docs/baselines/Muchen_Journey_Construction_V1_Owner_Decision_Pack_V1.0.md",
    "docs/baselines/Muchen_Journey_Construction_V1_Requirement_Priority_Correction_V1.0.json",
    "docs/baselines/Muchen_Journey_Construction_V1_Requirement_Gap_Matrix_V1.0.md",
}

CONSTRUCTION_V1_EVIDENCE_PREFIXES = (
    "docs/baselines/construction-v1.0/",
    "outputs/controller-integration/construction-v1.0/",
)

DEFERRED_PREFIXES = (
    "apps/api/journey_api/appeal_continuity.py",
    "apps/api/journey_api/career_",
    "apps/api/journey_api/certification_",
    "apps/api/journey_api/cross_map_stage_entry.py",
    "apps/api/journey_api/direct_stage_entry_person_projection.py",
    "apps/api/journey_api/historical_data_audit.py",
    "apps/api/journey_api/stage_entry_",
    "apps/api/journey_api/unified_stage_entry_person_view.py",
    "config/legacy_",
    "outputs/audits/minimum-runtime-phase0/legacy-migration-shadow/",
    "outputs/controller-integration/g10-",
    "outputs/controller-integration/g11-",
    "outputs/controller-integration/g12-",
    "outputs/controller-integration/g13-",
    "outputs/controller-integration/g14-",
    "outputs/controller-integration/g15-",
    "outputs/controller-integration/g16-",
    "outputs/controller-integration/g17-",
    "outputs/controller-integration/g18-",
    "outputs/controller-integration/g19-",
    "outputs/controller-integration/g20-",
    "outputs/controller-integration/g21-",
    "outputs/controller-integration/g22-",
    "outputs/controller-integration/g23-",
    "outputs/controller-integration/g24-",
    "outputs/controller-integration/g25-",
    "outputs/controller-integration/g26-",
    "outputs/controller-integration/g27-",
    "outputs/controller-integration/g28-",
    "outputs/controller-integration/g29-",
    "outputs/controller-integration/g30-",
    "outputs/controller-integration/g31-",
    "outputs/controller-integration/g32-",
    "outputs/controller-integration/g33-",
    "outputs/controller-integration/g34-",
    "outputs/controller-integration/g35-",
    "outputs/controller-integration/g4-",
    "outputs/controller-integration/g5-",
    "outputs/map-workstreams/career-map/",
    "outputs/map-workstreams/certification-arena/",
    "outputs/launch-war-mode-20260808/",
    "outputs/muchen_journey_p0_human_retest_20260823/",
    "scripts/audit/phase0_",
    "scripts/audit/build_legacy_",
    "scripts/audit/legacy_",
    "tests/test_career_",
    "tests/test_certification_",
    "tests/test_legacy_",
    "tests/test_appeal_continuity_contract.py",
    "tests/test_cross_map_stage_entry_contract.py",
    "tests/test_direct_stage_entry_person_projection_contract.py",
    "tests/test_historical_data_audit_rehearsal.py",
    "tests/test_stage_entry_",
    "tests/test_unified_stage_entry_person_view_contract.py",
)

DEFERRED_EXACT = {
    "config/phase0_feishu_bitable_source_config_v0.1.json",
    "docs/baselines/MINI_AUTONOMOUS_LEGACY_EXECUTION_LEDGER.md",
    "docs/baselines/Muchen_Journey_G1共享领域模型去重审计_V0.2_差异摘要.md",
    "docs/baselines/Muchen_Journey_G1共享领域模型去重审计与唯一运行纵切_V0.1.md",
    "docs/baselines/Muchen_Journey_MacMini原生开发交接单_V0.1.md",
    "docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.1.md",
    "docs/baselines/Muchen_Journey_Minimum_Runtime_Changeset_V0.2.md",
    "docs/baselines/Muchen_Journey_Owner提名与接受责任决议_V0.1.md",
    "docs/baselines/Muchen_Journey_产品继承审计证据包_V0.1.md",
    "docs/baselines/Muchen_Journey_分支与Worktree处置台账_V0.1.md",
    "docs/baselines/Muchen_Journey_历史数据盘点与迁移审计_V0.1.md",
    "docs/baselines/Muchen_Journey_技术运行基线冻结清单_V0.1.md",
    "docs/baselines/Muchen_Journey_现网-候选差异审计_V0.1.md",
    "docs/baselines/TEMPORARY_FEISHU_APP_REVOCATION_CHECKLIST_V0.1.md",
    "docs/baselines/build-contracts/04_G4_Career_Map证据解释与Growth_Plan闭环_V0.1.md",
    "docs/baselines/build-contracts/05_G5_历史数据审计与只读迁移演练_V0.1.md",
    "docs/baselines/build-contracts/BC-005_认证竞技场_V0.1.md",
    "docs/baselines/build-contracts/BC-006_Career_Map_V0.1.md",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_path(path: str) -> tuple[str, str, str]:
    if path in CONSTRUCTION_V1_EVIDENCE_EXACT or path.startswith(
        CONSTRUCTION_V1_EVIDENCE_PREFIXES
    ):
        return "RELEASE_REQUIRED", "EVIDENCE_ONLY", "muchen-journey-program-control"
    if path in CONSTRUCTION_V1_REQUIRED_EXACT:
        return "RELEASE_REQUIRED", "IN_SCOPE_CANDIDATE", "muchen-journey-program-control"
    if path in CONSTRUCTION_V1_WEB_EXACT:
        return "RELEASE_REQUIRED", "REWORK_REQUIRED", "muchen-journey-program-control"
    if path in RELEASE_REQUIRED_EXACT or path in RELEASE_REQUIRED_WEB:
        readiness = "REWORK_REQUIRED" if path in RELEASE_REQUIRED_WEB else "IN_SCOPE_CANDIDATE"
        return "RELEASE_REQUIRED", readiness, "muchen-journey-program-control"
    if path.startswith(RELEASE_REQUIRED_PREFIXES):
        return "RELEASE_REQUIRED", "EVIDENCE_ONLY", "muchen-journey-program-control"
    if "LEGACY_REFERENCE_ARCHIVE" in path or "REFERENCE_ONLY_NO_MIGRATION" in path:
        return "RELEASE_REQUIRED", "EVIDENCE_ONLY", "data-owner"
    if path in DEFERRED_EXACT or path.startswith(DEFERRED_PREFIXES):
        return "POST_RELEASE_DEFERRED", "FROZEN_REFERENCE", "post-release-owner"
    if path.startswith("docs/baselines/Muchen_Journey_Phase0_") or path.startswith(
        "docs/baselines/PHASE0_"
    ) or path.startswith("docs/baselines/PRO_PHASE0_"):
        return "POST_RELEASE_DEFERRED", "FROZEN_REFERENCE", "data-owner"
    if path.startswith("docs/baselines/build-contracts/"):
        return "POST_RELEASE_DEFERRED", "FROZEN_REFERENCE", "post-release-owner"
    if path.startswith("outputs/audits/minimum-runtime-phase0/"):
        return "POST_RELEASE_DEFERRED", "FROZEN_REFERENCE", "data-owner"
    return "UNKNOWN", "NEEDS_OWNER_ATTRIBUTION", "unassigned"


def run_git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", *args], cwd=repo, check=True, stdout=subprocess.PIPE
    ).stdout


def parse_porcelain_z(raw: bytes) -> list[tuple[str, str]]:
    tokens = raw.split(b"\0")
    result: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        decoded = token.decode("utf-8", errors="strict")
        if len(decoded) < 4 or decoded[2] != " ":
            raise ValueError("unexpected git porcelain entry")
        status, path = decoded[:2], decoded[3:]
        if "R" in status or "C" in status:
            if index >= len(tokens) or not tokens[index]:
                raise ValueError("rename/copy entry missing second path")
            index += 1
        result.append((status, path))
    return result


def build_inventory(repo: Path, output: Path, snapshot_id: str) -> dict[str, object]:
    resolved_repo = repo.resolve(strict=True)
    resolved_output = output.resolve(strict=False)
    allowed_root = (resolved_repo / OUTPUT_ROOT).resolve(strict=False)
    try:
        resolved_output.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("output must stay under controlled release output root") from exc
    if resolved_output.exists() or resolved_output.is_symlink():
        raise FileExistsError("output already exists")
    if not snapshot_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in snapshot_id):
        raise ValueError("snapshot_id must use lowercase letters, numbers, dash, or underscore")

    entries: list[dict[str, object]] = []
    counts = {"RELEASE_REQUIRED": 0, "POST_RELEASE_DEFERRED": 0, "UNKNOWN": 0}
    status_entries = parse_porcelain_z(
        run_git(resolved_repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )
    for status, relative in status_entries:
        path = resolved_repo / relative
        classification, readiness, owner = classify_path(relative)
        counts[classification] += 1
        record: dict[str, object] = {
            "path": relative,
            "git_status": status,
            "classification": classification,
            "readiness": readiness,
            "suggested_owner": owner,
        }
        if path.is_symlink():
            record.update(
                {
                    "file_type": "SYMLINK_NOT_FOLLOWED",
                    "sha256": sha256_bytes(os.readlink(path).encode("utf-8")),
                    "size_bytes": len(os.readlink(path).encode("utf-8")),
                }
            )
        elif path.is_file():
            record.update(
                {
                    "file_type": "REGULAR",
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        else:
            record.update(
                {
                    "file_type": "MISSING_OR_NON_REGULAR",
                    "sha256": None,
                    "size_bytes": None,
                }
            )
        entries.append(record)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_head": run_git(resolved_repo, "rev-parse", "HEAD").decode().strip(),
        "branch": run_git(resolved_repo, "branch", "--show-current").decode().strip(),
        "porcelain_status_entry_count": len(status_entries),
        "classification_counts": counts,
        "classification_values": ["RELEASE_REQUIRED", "POST_RELEASE_DEFERRED", "UNKNOWN"],
        "ignored_files_enumerated": False,
        "output_self_included": False,
        "entries": sorted(entries, key=lambda item: str(item["path"])),
    }
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(resolved_output, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        target.write("\n")
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_inventory(args.repo, args.output, args.snapshot_id)
    except (FileExistsError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("WORKTREE_ATTRIBUTION=FAIL")
        print(f"ERROR={type(exc).__name__}")
        return 2
    print("WORKTREE_ATTRIBUTION=PASS")
    print(f"SNAPSHOT_ID={manifest['snapshot_id']}")
    print(f"STATUS_ENTRY_COUNT={manifest['porcelain_status_entry_count']}")
    for key, value in manifest["classification_counts"].items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
