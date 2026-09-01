#!/usr/bin/env python3
"""Validate Construction V1 and produce a hash-bound dirty-tree ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DISPOSITIONS = (
    "KEEP",
    "ADAPT",
    "ARCHIVE",
    "DROP_FROM_CANDIDATE",
    "OWNER_REVIEW_REQUIRED",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _porcelain_entries(raw: bytes) -> list[tuple[str, str]]:
    tokens = raw.split(b"\0")
    entries: list[tuple[str, str]] = []
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
                raise ValueError("rename/copy entry missing source path")
            index += 1
        entries.append((status, path))
    return entries


def _metadata(
    disposition: str,
    requirement_ids: tuple[str, ...],
    source: str,
) -> tuple[str, tuple[str, ...], str, str, str, str, str]:
    if disposition == "KEEP":
        return (
            disposition,
            requirement_ids,
            source,
            "Preserve bytes and bind hash into the Construction V1 evidence chain.",
            "Package checksum and contract validation; affected regression where applicable.",
            "Hash drift invalidates the baseline or its evidence binding.",
            "IN_SCOPE_CANDIDATE",
        )
    if disposition == "ADAPT":
        return (
            disposition,
            requirement_ids,
            source,
            "Retain useful implementation, reconcile semantics to Construction V1, then run positive, negative, and affected regression tests.",
            "Requirement-specific positive and negative tests plus affected API/Web/Worker regression.",
            "Existing behavior may conflict with the new public state language or release scope.",
            "REWORK_REQUIRED",
        )
    if disposition == "ARCHIVE":
        return (
            disposition,
            requirement_ids,
            source,
            "Preserve as immutable reference evidence; exclude it from runtime images and product routes.",
            "Candidate manifest exclusion and secret/privacy scan.",
            "Reference evidence could be mistaken for current runtime or release PASS.",
            "EVIDENCE_ONLY",
        )
    if disposition == "DROP_FROM_CANDIDATE":
        return (
            disposition,
            requirement_ids,
            source,
            "Do not delete; explicitly exclude deferred logic from build, routes, migrations, OpenAPI, navigation, and release artifacts.",
            "Deferred-surface absence tests and candidate manifest exclusion.",
            "Deferred behavior could leak into the four-module controlled candidate.",
            "EXCLUDED_FROM_CANDIDATE",
        )
    return (
        "OWNER_REVIEW_REQUIRED",
        requirement_ids,
        source,
        "Preserve unchanged until product ownership and candidate disposition are established.",
        "No candidate inclusion before explicit classification and relevant regression coverage.",
        "Unknown provenance or product behavior could expand scope.",
        "BLOCKED_CLASSIFICATION",
    )


def classify_construction_path(
    path: str,
) -> tuple[str, tuple[str, ...], str, str, str, str, str]:
    """Classify one dirty file against the Construction V1 release boundary."""
    if path.startswith("docs/baselines/construction-v1.0/") or path == (
        "docs/baselines/MINI_AUTONOMOUS_CONSTRUCTION_EXECUTION_LEDGER_V1.0.md"
    ):
        return _metadata("KEEP", ("TECH-001",), "CONSTRUCTION_PACKAGE_V1.0")

    deferred_markers = (
        "certification",
        "career_",
        "career-map",
        "cross_map_stage_entry",
        "direct_stage_entry",
        "stage_entry_",
        "unified_stage_entry",
        "legacy_migration",
        "legacy_23_table",
        "g10-",
        "g11-",
        "g12-",
        "g13-",
        "g14-",
        "g15-",
        "g16-",
        "g17-",
        "g18-",
        "g19-",
        "g20-",
        "g21-",
        "g22-",
        "g23-",
        "g24-",
        "g25-",
        "g26-",
        "g27-",
        "g28-",
        "g29-",
        "g30-",
        "g31-",
        "g32-",
        "g33-",
        "g34-",
        "g35-",
    )
    if any(marker in path.lower() for marker in deferred_markers):
        return _metadata(
            "DROP_FROM_CANDIDATE",
            ("REL-001", "TECH-001"),
            "CONSTRUCTION_V1_DEFERRED_SCOPE",
        )

    if path.startswith("outputs/audits/") or path.startswith(
        "scripts/audit/phase0_"
    ) or path.startswith("docs/baselines/Muchen_Journey_Phase0_") or path.startswith(
        "docs/baselines/PHASE0_"
    ) or path.startswith("docs/baselines/PRO_PHASE0_"):
        return _metadata(
            "ARCHIVE", ("DATA-001",), "LEGACY_REFERENCE_ONLY_DECISION"
        )

    if path.startswith("outputs/") or path.endswith(".tar.gz") or path.endswith(
        ".tar.gz.sha256"
    ):
        return _metadata(
            "ARCHIVE", ("TECH-001",), "EXISTING_MACHINE_EVIDENCE_CANDIDATE"
        )

    if path.startswith("docs/baselines/build-contracts/") or path.startswith(
        "docs/baselines/"
    ):
        return _metadata(
            "ARCHIVE", ("TECH-001",), "PRE_CONSTRUCTION_BASELINE_REFERENCE"
        )

    if path in {
        "config/muchen_journey_2026_09_01_controlled_release.json",
        "config/muchen_journey_product.json",
    }:
        return _metadata(
            "ADAPT", ("DATA-001", "TECH-001", "REL-001"), "CONSTRUCTION_PACKAGE_V1.0"
        )

    if path.startswith("config/legacy_") or path.startswith(
        "config/phase0_"
    ):
        return _metadata(
            "DROP_FROM_CANDIDATE", ("DATA-001", "REL-001"), "LEGACY_REFERENCE_ONLY_DECISION"
        )

    if "controlled_task_authorization" in path:
        return _metadata("ADAPT", ("NV-002", "CORE-004"), "SRC-OWNER-01/SRC-NV-01")
    if "appeal" in path:
        return _metadata("ADAPT", ("GOV-005",), "SRC-OWNER-01/SRC-GOV-01")
    if "shared_domain" in path or "formal_result" in path:
        return _metadata(
            "ADAPT",
            ("GOV-001", "GOV-003", "GOV-004", "GOV-005"),
            "SRC-OWNER-01/SRC-GOV-01",
        )
    if path.startswith("apps/web/"):
        return _metadata(
            "ADAPT", ("CORE-002", "GOV-003", "REL-001"), "CONSTRUCTION_PACKAGE_V1.0"
        )
    if path.startswith("apps/api/") or path.startswith("tests/"):
        return _metadata(
            "ADAPT",
            ("GOV-002", "CORE-001", "CORE-003", "CORE-004", "CORE-005"),
            "SRC-TECH-01/CONSTRUCTION_PACKAGE_V1.0",
        )
    if path.startswith("scripts/") or path == "contracts/openapi.json":
        return _metadata(
            "ADAPT", ("TECH-001", "TECH-002"), "SRC-TECH-01"
        )

    return _metadata(
        "OWNER_REVIEW_REQUIRED", ("TECH-001",), "UNATTRIBUTED_DIRTY_TREE_ASSET"
    )


def validate_construction_package(package: Path) -> dict[str, object]:
    package = package.resolve(strict=True)
    sums = package / "SHA256SUMS"
    if not sums.is_file():
        raise ValueError("SHA256SUMS is missing")
    checked: list[str] = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ValueError("invalid SHA256SUMS entry") from exc
        target = (package / relative).resolve(strict=True)
        try:
            target.relative_to(package)
        except ValueError as exc:
            raise ValueError("checksum target escapes package") from exc
        actual = sha256_file(target)
        if actual != expected:
            raise ValueError(f"checksum mismatch: {relative}")
        checked.append(relative)

    machine = package / "05_机器合同"
    parsed = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(machine.glob("*.json"))
    }
    requirements = parsed["requirements.v1.json"]["requirements"]
    requirement_ids = [item["id"] for item in requirements]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("duplicate requirement id")
    known = set(requirement_ids)
    trace = parsed["traceability.v1.json"]
    references: list[str] = []
    for mapping_name in ("source_to_requirements", "module_to_requirements"):
        for values in trace[mapping_name].values():
            references.extend(values)
    for conflict in trace["conflict_resolutions"]:
        references.extend(conflict["requirement_ids"])
    unknown = sorted(set(references) - known)
    if unknown:
        raise ValueError(f"unknown traceability requirement ids: {unknown}")
    unmapped = sorted(known - set(references))
    if unmapped:
        raise ValueError(f"unmapped requirement ids: {unmapped}")
    return {
        "status": "PASS",
        "checksummed_files": len(checked),
        "json_files": len(parsed),
        "requirements": len(requirements),
        "p0_requirements": sum(item.get("priority") == "P0" for item in requirements),
        "p1_requirements": sum(item.get("priority") == "P1" for item in requirements),
        "traceability_references": len(references),
    }


def build_worktree_ledger(repo: Path, snapshot_id: str) -> dict[str, object]:
    repo = repo.resolve(strict=True)
    status_entries = _porcelain_entries(
        _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )
    entries: list[dict[str, object]] = []
    counts = {key: 0 for key in DISPOSITIONS}
    for status, relative in status_entries:
        target = repo / relative
        if target.is_symlink():
            file_type = "SYMLINK"
            sha256 = hashlib.sha256(os.readlink(target).encode("utf-8")).hexdigest()
            size = len(os.readlink(target).encode("utf-8"))
        elif target.is_file():
            file_type = "REGULAR"
            sha256 = sha256_file(target)
            size = target.stat().st_size
        elif not target.exists():
            file_type = "DELETED"
            sha256 = None
            size = 0
        else:
            raise ValueError(f"unsupported dirty-tree entry type: {relative}")
        (
            disposition,
            requirement_ids,
            source,
            implementation_plan,
            tests,
            risk,
            candidate_status,
        ) = classify_construction_path(relative)
        counts[disposition] += 1
        entries.append(
            {
                "path": relative,
                "git_status": status,
                "file_type": file_type,
                "sha256": sha256,
                "size_bytes": size,
                "disposition": disposition,
                "requirement_ids": list(requirement_ids),
                "source": source,
                "implementation_plan": implementation_plan,
                "tests": tests,
                "risk": risk,
                "candidate_status": candidate_status,
            }
        )
    return {
        "schema_version": "construction-worktree-ledger.v1",
        "snapshot_id": snapshot_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_head": _git(repo, "rev-parse", "HEAD").decode().strip(),
        "branch": _git(repo, "branch", "--show-current").decode().strip(),
        "porcelain_file_entry_count": len(entries),
        "ignored_files_enumerated": False,
        "disposition_counts": counts,
        "entries": entries,
    }


def render_ledger_markdown(
    manifest: dict[str, object], package_validation: dict[str, object]
) -> str:
    counts = manifest["disposition_counts"]
    assert isinstance(counts, dict)
    lines = [
        "# MINI AUTONOMOUS CONSTRUCTION EXECUTION LEDGER V1.0",
        "",
        "> 状态：`W0_BASELINE_RECONCILIATION / NOT_A_RELEASE_CANDIDATE / NO_PRODUCTION_MUTATION`  ",
        f"> 快照：`{manifest['snapshot_id']}`；HEAD：`{manifest['git_head']}`；分支：`{manifest['branch']}`  ",
        "> 本台账记录生成瞬间的逐文件 dirty-tree；生成后的台账/manifest 自身不递归纳入自身 hash。",
        "",
        "## 合同校验",
        "",
        f"- SHA256SUMS：PASS（{package_validation['checksummed_files']} files）",
        f"- JSON：PASS（{package_validation['json_files']} files）",
        f"- Requirement：{package_validation['requirements']} total / {package_validation['p0_requirements']} P0 / {package_validation['p1_requirements']} P1；ID 唯一且追踪引用闭合",
        "- 机器校验不替代 Owner 内容、人类 UAT、独立复核或 Release GO。",
        "",
        "## 处置总览",
        "",
        f"逐文件状态条目：{manifest['porcelain_file_entry_count']}；KEEP={counts['KEEP']}，ADAPT={counts['ADAPT']}，ARCHIVE={counts['ARCHIVE']}，DROP_FROM_CANDIDATE={counts['DROP_FROM_CANDIDATE']}，OWNER_REVIEW_REQUIRED={counts['OWNER_REVIEW_REQUIRED']}。",
        "",
        "`DROP_FROM_CANDIDATE` 不表示删除；只表示从四模块候选的路由、构建、迁移、OpenAPI、导航和运行镜像中排除。",
        "",
        "## 逐文件台账",
        "",
        "| Path | Git | SHA-256 | Requirement IDs | Source | Disposition | Implementation plan | Tests | Risk | Candidate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    entries = manifest["entries"]
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, dict)
        escape = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{escape(entry['path'])}`",
                    f"`{escape(entry['git_status'])}`",
                    f"`{escape(entry['sha256'])}`",
                    ", ".join(f"`{item}`" for item in entry["requirement_ids"]),
                    escape(entry["source"]),
                    f"`{escape(entry['disposition'])}`",
                    escape(entry["implementation_plan"]),
                    escape(entry["tests"]),
                    escape(entry["risk"]),
                    f"`{escape(entry['candidate_status'])}`",
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## 当前 Gate",
        "",
        "- `G0_PRODUCT_CONTRACT`: package hash valid；Owner 内容绑定仍按合同单独等待。",
        "- `G1_CONTENT_BINDING`: NOT_RUN。",
        "- `G2_MACHINE_CONTRACT`: NOT_RUN_ON_FINAL_CANDIDATE。",
        "- `G3+`: NOT_RUN；`RELEASE_NOT_AUTHORIZED`。",
        "- 下一自主工作：完成 Requirement gap matrix，随后选择最小共享 P0 纵切。",
        "",
    ]
    return "\n".join(lines)


def _exclusive_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(data)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--ledger-out", type=Path, required=True)
    args = parser.parse_args(argv)
    repo = args.repo.resolve(strict=True)
    package = repo / "docs/baselines/construction-v1.0"
    validation = validate_construction_package(package)
    manifest = build_worktree_ledger(repo, args.snapshot_id)
    manifest_out = args.manifest_out.resolve(strict=False)
    ledger_out = args.ledger_out.resolve(strict=False)
    for target in (manifest_out, ledger_out):
        try:
            target.relative_to(repo)
        except ValueError as exc:
            raise ValueError("output must remain inside repository") from exc
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"output already exists: {target}")
    _exclusive_write(
        manifest_out,
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    _exclusive_write(ledger_out, render_ledger_markdown(manifest, validation).encode("utf-8"))
    print(json.dumps({"validation": validation, "ledger": manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
