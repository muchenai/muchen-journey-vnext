#!/usr/bin/env python3
"""Read-only V2 execution-control preflight for the Muchen Journey candidate repo."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


BASE_SHA = "7c57a2f7fa16eacdf2a3a6e2a8bfd594d00460f1"
BRANCH = "codex/construction-v1-candidate-prep-20260826"
CONTROL_DIR = Path("docs/baselines/execution-control-v2.0")
PRODUCT = Path("config/muchen_journey_product.json")
RELEASE = Path("config/muchen_journey_2026_09_01_controlled_release.json")
PACKAGE_INDEX = Path("config/module-content-packages/module-content-package-index.v1.json")


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def load(repo: Path, relative: Path) -> dict[str, object]:
    value = json.loads((repo / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return value


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_checksums(repo: Path, errors: list[str]) -> None:
    checksum_path = repo / CONTROL_DIR / "SHA256SUMS"
    if not checksum_path.exists():
        errors.append("V2 SHA256SUMS missing")
        return
    for raw in checksum_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        target = repo / CONTROL_DIR / relative
        if not target.is_file() or file_sha256(target) != expected:
            errors.append(f"V2 checksum mismatch: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    errors: list[str] = []

    if not (repo / ".git").exists() and not run(repo, "git", "rev-parse", "--git-dir").stdout.strip():
        errors.append("repo is not a Git worktree")

    branch = run(repo, "git", "branch", "--show-current").stdout.strip()
    head = run(repo, "git", "rev-parse", "HEAD").stdout.strip()
    dirty = run(repo, "git", "status", "--porcelain").stdout.strip()
    ancestor = run(repo, "git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD")

    if branch != BRANCH:
        errors.append(f"wrong branch: {branch}")
    if len(head) != 40:
        errors.append("full HEAD unavailable")
    if dirty:
        errors.append("worktree is dirty")
    if ancestor.returncode != 0:
        errors.append("V2 base commit is not an ancestor of HEAD")

    try:
        product = load(repo, PRODUCT)
        release = load(repo, RELEASE)
        package_index = load(repo, PACKAGE_INDEX)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(str(exc))
        product = release = package_index = {}

    if product.get("schema_version") != 2:
        errors.append("approved product contract must remain schema_version 2")
    if release.get("content_binding", {}).get("state") != "G1_CONTENT_BINDING_PASS":
        errors.append("G1 content binding is not PASS")
    if release.get("candidate_binding", {}).get("state") != "NOT_FROZEN":
        errors.append("candidate must be NOT_FROZEN at V2 start")
    if release.get("release_authorized") is not False:
        errors.append("release authorization must remain false")
    if release.get("production_mutation_executed") is not False:
        errors.append("production mutation must remain false")
    if package_index.get("state") != "G1_CONTENT_BINDING_PASS":
        errors.append("formal package index is not in G1 PASS state")

    validate_checksums(repo, errors)

    result = {
        "status": "READY_FOR_V2_EXECUTION" if not errors else "FAIL_CLOSED",
        "branch": branch,
        "head": head,
        "base_commit_is_ancestor": ancestor.returncode == 0,
        "worktree_clean": not dirty,
        "product_schema_version": product.get("schema_version"),
        "g1_content_binding": release.get("content_binding", {}).get("state"),
        "candidate_state": release.get("candidate_binding", {}).get("state"),
        "release_authorized": release.get("release_authorized"),
        "production_mutation_executed": release.get("production_mutation_executed"),
        "known_runtime_package_state": "FAIL_0_OF_4_REQUIRES_V2_02",
        "known_ops_plugin_state": "SCHEMA_COMPATIBILITY_BLOCKED_DO_NOT_DOWNGRADE_PRODUCT",
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
