#!/usr/bin/env python3
"""Discover and validate the complete repository-owned WP-31 execution closure."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


WORKFLOW = ".github/workflows/wp15-wartime-production.yml"
MANIFEST = "config/wp31_greenfield_canary_ops_manifest.json"
STATIC_ROOTS = {
    WORKFLOW,
    MANIFEST,
    "config/wp31_greenfield_canary.json",
    "config/wp31_greenfield_canary_pro_review_evidence.schema.json",
    "config/wp31_greenfield_canary_execution_authorization.schema.json",
    "scripts/wp31_ops_closure.py",
}
CANDIDATE_BOUND_REFERENCES = {
    "scripts/wp07_candidate.py",
}
PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])((?:scripts|deploy|config|infra)/[A-Za-z0-9_./-]+)"
)
PYTHON_MODULE = re.compile(r"\bpython3?\s+-m\s+(scripts(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b")
LOCAL_TERRAFORM_SOURCE = re.compile(r"\bsource\s*=\s*[\"'](\.{1,2}/[^\"']+)[\"']")


class ClosureError(RuntimeError):
    pass


def _safe_files(path: Path) -> set[Path]:
    if path.is_file() and not path.is_symlink():
        return {path}
    if not path.is_dir() or path.is_symlink():
        return set()
    return {
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
        and not candidate.is_symlink()
        and ".git" not in candidate.parts
        and ".terraform" not in candidate.parts
        and "__pycache__" not in candidate.parts
    }


def _module_path(root: Path, module: str) -> Path | None:
    candidate = root / (module.replace(".", "/") + ".py")
    if candidate.is_file() and not candidate.is_symlink():
        return candidate
    package = root / module.replace(".", "/") / "__init__.py"
    if package.is_file() and not package.is_symlink():
        return package
    return None


def _python_imports(root: Path, path: Path) -> set[Path]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as error:
        raise ClosureError(f"cannot parse Python dependency: {path.relative_to(root)}") from error
    result: set[Path] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
        for module in modules:
            if not module.startswith("scripts."):
                continue
            candidate = _module_path(root, module)
            if candidate is not None:
                result.add(candidate)
    return result


def _existing_references(root: Path, owner: Path, text: str) -> set[Path]:
    result: set[Path] = set()
    for token in PATH_TOKEN.findall(text):
        normalized = token.rstrip("./")
        if normalized in CANDIDATE_BOUND_REFERENCES:
            continue
        candidate = root / normalized
        result.update(_safe_files(candidate))
    for module in PYTHON_MODULE.findall(text):
        candidate = _module_path(root, module)
        if candidate is not None:
            result.add(candidate)
    if owner.suffix == ".tf":
        for source in LOCAL_TERRAFORM_SOURCE.findall(text):
            candidate = (owner.parent / source).resolve()
            if candidate.is_relative_to(root.resolve()):
                result.update(_safe_files(candidate))
    return result


def greenfield_workflow_text(root: Path) -> str:
    workflow = (root / WORKFLOW).read_text(encoding="utf-8")
    try:
        start = workflow.index("  greenfield_package:\n")
        end = workflow.index("  operate:\n", start)
    except ValueError as error:
        raise ClosureError("Greenfield workflow job boundary is missing") from error
    return workflow[start:end]


def discover(root: Path) -> set[str]:
    root = root.resolve()
    pending: list[Path] = []
    for raw in STATIC_ROOTS:
        pending.extend(_safe_files(root / raw))
    workflow_path = root / WORKFLOW
    pending.extend(_existing_references(root, workflow_path, greenfield_workflow_text(root)))
    discovered: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in discovered or not path.is_relative_to(root):
            continue
        discovered.add(path)
        if path.suffix == ".py":
            pending.extend(_python_imports(root, path))
        try:
            text = (
                greenfield_workflow_text(root)
                if path == workflow_path
                else path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError):
            continue
        pending.extend(_existing_references(root, path, text))
    return {str(path.relative_to(root)) for path in discovered}


def validate(root: Path, manifest_path: Path) -> dict[str, object]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_relative_to(root) or manifest_path.is_symlink():
        raise ClosureError("ops manifest path is invalid")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = value.get("files")
    if not isinstance(files, dict):
        raise ClosureError("ops manifest files map is missing")
    discovered = discover(root)
    self_path = str(manifest_path.relative_to(root))
    missing = sorted(discovered - set(files) - {self_path})
    if missing:
        raise ClosureError("unbound Greenfield dependencies: " + ",".join(missing))
    workflow = greenfield_workflow_text(root)
    candidate_binding_anchors = (
        "ref: ${{ inputs.candidate }}",
        "path: candidate",
        "git -C candidate rev-parse --verify HEAD",
        "git -C candidate status --porcelain=v1 --untracked-files=all",
    )
    if any(anchor not in workflow for anchor in candidate_binding_anchors):
        raise ClosureError("exact application candidate checkout boundary is incomplete")
    return {
        "status": "PASS",
        "discovered_dependency_count": len(discovered),
        "manifest_bound_file_count": len(files),
        "manifest_self_bound_externally": self_path in discovered,
        "candidate_bound_references": sorted(CANDIDATE_BOUND_REFERENCES),
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    manifest = (args.manifest or root / MANIFEST).resolve()
    try:
        result = validate(root, manifest)
    except (ClosureError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"WP31_OPS_CLOSURE=FAIL reason={error}")
        return 2
    print("WP31_OPS_CLOSURE=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
