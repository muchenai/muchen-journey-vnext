#!/usr/bin/env python3
"""Fail-closed, read-only lifecycle guard for the isolated Canary database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CANARY_DATABASE = "journey_next_canary_20260901_c72fea5"


class DatabaseGuardError(RuntimeError):
    pass


def load_facts(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise DatabaseGuardError("facts file must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DatabaseGuardError("facts must be a JSON object")
    return value


def safe_to_rebuild(facts: dict[str, object]) -> bool:
    """Return true only when an existing DB has no active references."""
    if facts.get("database_name") != CANARY_DATABASE:
        return False
    if facts.get("database_exists") is not True:
        return False
    if facts.get("canary_service_active") is not False:
        return False
    if facts.get("current_release_reference") is not False:
        return False
    if facts.get("workflow_runs_in_progress") != 0:
        return False
    return True


def safe_to_create(facts: dict[str, object]) -> bool:
    """Allow first-time creation only when no service/workflow/release uses it."""
    if facts.get("database_name") != CANARY_DATABASE:
        return False
    if facts.get("canary_service_active") is not False:
        return False
    if facts.get("current_release_reference") is not False:
        return False
    if facts.get("workflow_runs_in_progress") != 0:
        return False
    return facts.get("database_exists") in {True, False}


def check(path: Path, operation: str) -> dict[str, object]:
    facts = load_facts(path)
    safe = safe_to_rebuild(facts) if operation == "rebuild" else safe_to_create(facts)
    result = {
        "schema_version": 1,
        "operation": operation,
        "database_name": facts.get("database_name"),
        "database_exists": facts.get("database_exists"),
        "canary_service_active": facts.get("canary_service_active"),
        "current_release_reference": facts.get("current_release_reference"),
        "workflow_runs_in_progress": facts.get("workflow_runs_in_progress"),
        "safe": safe,
    }
    if not safe:
        raise DatabaseGuardError(json.dumps(result, sort_keys=True))
    return result


def facts_from_read_only_observations(
    *,
    database_exists: bool,
    canary_service_active: bool,
    current_release_reference: bool,
    workflow_runs_in_progress: int,
) -> dict[str, object]:
    """Normalize observations collected by the workflow's read-only probes."""
    if not isinstance(workflow_runs_in_progress, int) or workflow_runs_in_progress < 0:
        raise DatabaseGuardError("workflow run count is invalid")
    return {
        "database_name": CANARY_DATABASE,
        "database_exists": database_exists,
        "canary_service_active": canary_service_active,
        "current_release_reference": current_release_reference,
        "workflow_runs_in_progress": workflow_runs_in_progress,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--operation", choices=("create", "rebuild"), default="create")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.facts, args.operation), sort_keys=True))
    except (OSError, ValueError, DatabaseGuardError) as error:
        print(f"WP31_CANARY_DATABASE_GUARD=FAIL reason={error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
