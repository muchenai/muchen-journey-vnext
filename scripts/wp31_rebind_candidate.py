#!/usr/bin/env python3
"""Apply a verified candidate binding to the reviewed Canary consumers."""

from __future__ import annotations

import re
import argparse
import json
import hashlib
from pathlib import Path

try:
    from scripts import wp31_candidate_binding
except (ImportError, ModuleNotFoundError):  # direct invocation from the scripts directory
    import wp31_candidate_binding


class RebindError(ValueError):
    pass


def branch_name(package_run_id: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]{5,19}", package_run_id):
        raise RebindError("package workflow run ID is invalid")
    return f"codex/canary-rebind-{package_run_id}"


def rebind(root: Path, binding_path: Path) -> list[str]:
    binding = wp31_candidate_binding.verify_binding(binding_path, require_supply_chain=True)
    candidate = str(binding["application_candidate_sha"])
    package_run = str(binding["package_workflow_run_id"])
    manifest_sha = str(binding["release_manifest_sha256"])
    contract_path = root / "config/wp31_greenfield_canary.json"
    if contract_path.is_symlink() or not contract_path.is_file():
        raise RebindError("Canary contract is missing")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RebindError("Canary contract is not valid JSON") from error
    old_candidate = contract.get("application_candidate_sha")
    old_run = contract.get("package_workflow_run_id")
    old_manifest_sha = contract.get("package_manifest_sha256")
    old_images = contract.get("images")
    if not isinstance(old_candidate, str) or not isinstance(old_run, str) or not isinstance(old_manifest_sha, str):
        raise RebindError("Canary contract binding fields are invalid")
    if not isinstance(old_images, dict):
        raise RebindError("Canary contract images are invalid")

    contract["application_candidate_sha"] = candidate
    contract["package_workflow_run_id"] = package_run
    contract["package_manifest_sha256"] = manifest_sha
    images = binding["images"]
    contract["images"] = {
        "api": f"{images['api']['registry_reference'].rsplit(':', 1)[0]}@{images['api']['registry_digest']}",
        "web": f"{images['web']['registry_reference'].rsplit(':', 1)[0]}@{images['web']['registry_digest']}",
        "worker_evidence_only": f"{images['worker']['registry_reference'].rsplit(':', 1)[0]}@{images['worker']['registry_digest']}",
    }
    changed: list[str] = []

    binding_target = root / "config/wp31_candidate_binding.json"
    rendered_binding = wp31_candidate_binding.serialize(binding)
    if not binding_target.is_file() or binding_target.read_bytes() != rendered_binding:
        binding_target.write_bytes(rendered_binding)
        changed.append("config/wp31_candidate_binding.json")

    def write_json(path: Path, value: object, relative: str) -> None:
        rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if path.read_text(encoding="utf-8") != rendered:
            path.write_text(rendered, encoding="utf-8")
            changed.append(relative)

    write_json(contract_path, contract, "config/wp31_greenfield_canary.json")
    replacements = {
        old_candidate: candidate,
        old_run: package_run,
        old_manifest_sha: manifest_sha,
        str(old_images.get("api", "")): contract["images"]["api"],
        str(old_images.get("web", "")): contract["images"]["web"],
        str(old_images.get("worker_evidence_only", "")): contract["images"]["worker_evidence_only"],
    }
    old_marker = old_candidate[:7].upper()
    new_marker = candidate[:7].upper()
    replacements[old_marker] = new_marker
    targets = (
        ("config/wp31_greenfield_canary_execution_authorization.schema.json", root / "config/wp31_greenfield_canary_execution_authorization.schema.json"),
        ("config/wp31_greenfield_canary_pro_review_evidence.schema.json", root / "config/wp31_greenfield_canary_pro_review_evidence.schema.json"),
        ("scripts/wp31_greenfield_canary.py", root / "scripts/wp31_greenfield_canary.py"),
        ("scripts/wp31_identity_bootstrap.py", root / "scripts/wp31_identity_bootstrap.py"),
        ("scripts/wp31_prepare_greenfield_canary.py", root / "scripts/wp31_prepare_greenfield_canary.py"),
        ("tests/test_wp31_identity_bootstrap.py", root / "tests/test_wp31_identity_bootstrap.py"),
        (".github/workflows/wp15-wartime-production.yml", root / ".github/workflows/wp15-wartime-production.yml"),
    )
    for relative, path in targets:
        if path.is_symlink() or not path.is_file():
            raise RebindError(f"required binding consumer is missing: {relative}")
        original = path.read_text(encoding="utf-8")
        rendered = original
        for old, new in replacements.items():
            if old:
                rendered = rendered.replace(old, new)
        if rendered != original:
            path.write_text(rendered, encoding="utf-8")
            changed.append(relative)

    ops_path = root / "config/wp31_greenfield_canary_ops_manifest.json"
    if ops_path.is_symlink() or not ops_path.is_file():
        raise RebindError("Ops manifest is missing")
    ops = json.loads(ops_path.read_text(encoding="utf-8"))
    files = ops.get("files")
    if not isinstance(files, dict):
        raise RebindError("Ops manifest files are invalid")
    ops["application_candidate_sha"] = candidate
    for relative in (
        ".github/workflows/wp31-candidate-rebind.yml",
        "config/wp31_candidate_binding.json",
        "scripts/wp31_candidate_binding.py",
        "scripts/wp31_canary_database_guard.py",
        "scripts/wp31_rebind_candidate.py",
        "tests/test_wp31_candidate_binding.py",
        "tests/test_wp31_binding_consumers.py",
        "tests/test_wp31_canary_database_guard.py",
        "tests/test_wp31_rebind_candidate.py",
        "tests/test_wp31_rebind_workflow.py",
    ):
        files.setdefault(relative, "")
    for relative in files:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise RebindError(f"Ops manifest file is missing: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(ops_path, ops, "config/wp31_greenfield_canary_ops_manifest.json")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    args = parser.parse_args()
    try:
        changed = rebind(args.root, args.binding)
        print(f"WP31_REBIND=PASS changed={len(changed)}")
        return 0
    except (RebindError, OSError, ValueError, TypeError, KeyError) as error:
        print(f"WP31_REBIND=FAIL reason={error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
