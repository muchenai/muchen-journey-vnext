#!/usr/bin/env python3
"""Verify that a frozen local Muchen Journey candidate has not drifted."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(repo: Path, manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if manifest.get("state") != "AWAITING_HUMAN":
        errors.append("candidate state must be AWAITING_HUMAN")
    if manifest.get("machine_verdict") != "READY_FOR_HUMAN":
        errors.append("machine verdict must be READY_FOR_HUMAN")
    if manifest.get("human_gate") != "NOT_RUN":
        errors.append("human gate must remain NOT_RUN")
    if manifest.get("release_authorized") is not False:
        errors.append("release_authorized must be false")
    if manifest.get("production_mutation_executed") is not False:
        errors.append("production_mutation_executed must be false")

    frozen_files = manifest.get("frozen_files")
    if not isinstance(frozen_files, dict) or not frozen_files:
        return [*errors, "frozen_files must be a non-empty object"]
    for relative, expected in frozen_files.items():
        path = repo / relative
        if not path.is_file():
            errors.append(f"missing frozen file: {relative}")
            continue
        actual = sha256(path)
        if actual != expected:
            errors.append(f"frozen file drifted: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    manifest_path = (repo / args.manifest).resolve()
    try:
        manifest_path.relative_to(repo)
    except ValueError:
        print("CANDIDATE_FREEZE=FAIL\nERROR=manifest must stay inside repository")
        return 2
    errors = verify(repo, manifest_path)
    if errors:
        print("CANDIDATE_FREEZE=FAIL")
        for error in errors:
            print(f"ERROR={error}")
        return 2
    print("CANDIDATE_FREEZE=PASS")
    print("STATE=AWAITING_HUMAN")
    print("HUMAN_GATE=NOT_RUN")
    print("RELEASE_AUTHORIZED=false")
    print("PRODUCTION_MUTATION_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
