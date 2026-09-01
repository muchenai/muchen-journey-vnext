#!/usr/bin/env python3
"""Validate the contract-only Exploration Camp remediation package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_WRITES = {
    "apps/web/src/app/join/page.tsx",
    "apps/web/src/app/join/invite-token-exchange-form.tsx",
    "apps/web/src/app/join/private-invite-orientation.tsx",
    "apps/web/src/app/join/private-invite-orientation.module.css",
    "apps/web/scripts/exploration-camp-private-invite-orientation-contract.test.mjs",
}

PROTECTED = {
    "apps/web/src/app/page.tsx",
    "apps/web/scripts/product-entry-contract.test.mjs",
    "apps/web/src/app/globals.css",
    "apps/web/src/app/actions.ts",
    "apps/web/src/lib/server/api.ts",
    "contracts/openapi.json",
}


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    base = repo / "outputs/map-workstreams/exploration-camp/remediation-v2"
    errors: list[str] = []

    product = load(repo / "config/muchen_journey_product.json")
    contract = load(base / "contract.json")
    write_set = load(base / "runtime-write-set.json")
    handoff = load(base / "handoff.json")
    current = product.get("current_golden_path", {})

    if contract.get("kind") != "IMPLEMENTATION_READY_CONTRACT_ONLY":
        errors.append("kind must remain IMPLEMENTATION_READY_CONTRACT_ONLY")
    if contract.get("status") != "RUNTIME_NOT_IMPLEMENTED":
        errors.append("status must remain RUNTIME_NOT_IMPLEMENTED")
    if contract.get("creates_second_golden_path") is not False:
        errors.append("remediation must not create a second golden path")
    if not isinstance(current, dict) or contract.get("golden_path_id") != current.get("id"):
        errors.append("remediation must bind the authoritative current golden path")
    if contract.get("exact_path") != {
        "starts_at": current.get("starts_at"),
        "ends_at": current.get("ends_at"),
        "routes": current.get("routes"),
    }:
        errors.append("exact path must match the authoritative contract")

    candidate_state = contract.get("candidate_state", {})
    if not isinstance(candidate_state, dict):
        errors.append("candidate_state must be an object")
    else:
        if candidate_state.get("ready_for_human") is not False:
            errors.append("contract-only package cannot be READY_FOR_HUMAN")
        if candidate_state.get("human_gate_inferred") is not False:
            errors.append("human gate must remain uninferred")
        if candidate_state.get("release_authorized") is not False:
            errors.append("release must remain unauthorized")
        if candidate_state.get("production_mutation_executed") is not False:
            errors.append("production mutation must remain false")

    writes = {
        item.get("path")
        for item in write_set.get("writes", [])
        if isinstance(item, dict)
    }
    if writes != EXPECTED_WRITES:
        errors.append("runtime write set differs from the approved five files")
    if writes & PROTECTED:
        errors.append("runtime write set overlaps protected shared files")
    declared_protected = set(write_set.get("must_not_write", []))
    if not PROTECTED.issubset(declared_protected):
        errors.append("protected file list is incomplete")

    if handoff.get("evaluator_verdict") != "BLOCKED_NO_RUNNABLE_TARGET":
        errors.append("preimplementation evaluator must remain blocked without a runtime target")
    if handoff.get("ready_for_human") is not False:
        errors.append("handoff cannot mark a contract-only package READY_FOR_HUMAN")
    if set(handoff.get("controller_runtime_writes", [])) != EXPECTED_WRITES:
        errors.append("handoff runtime writes differ from the approved five files")

    required = [
        repo / "docs/maps/exploration-camp/private-invite-orientation-remediation-v2.md",
        base / "content-structure.md",
        base / "compatibility-and-migration.md",
        base / "acceptance.md",
        base / "controller-runtime-patch.md",
        base / "runtime-write-set.json",
        base / "evaluator-report.md",
        base / "handoff.json",
    ]
    for path in required:
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"missing remediation artifact: {path.relative_to(repo)}")

    if errors:
        print("EXPLORATION_CAMP_REMEDIATION_V2=FAIL")
        for error in errors:
            print(f"ERROR={error}")
        return 2

    print("EXPLORATION_CAMP_REMEDIATION_V2=PASS")
    print("GOLDEN_PATH_COUNT_ADDED=0")
    print("RUNTIME_IMPLEMENTED=false")
    print("READY_FOR_HUMAN=false")
    print("EXPECTED_EVALUATOR=BLOCKED_NO_RUNNABLE_TARGET")
    print("PRODUCTION_MUTATION_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
