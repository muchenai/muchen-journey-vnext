#!/usr/bin/env python3
"""Write a non-sensitive diagnostic record for the WP-31 lifecycle guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA_VERSION = 1
STATUSES = frozenset({"NOT_STARTED", "OBSERVED", "FAILED", "PASSED"})
FAILURE_CATEGORIES = frozenset(
    {
        "SSH_CURRENT_RELEASE_PROBE",
        "SSH_CANARY_SERVICE_PROBE",
        "RDS_DATABASE_EXISTS_PROBE",
        "GITHUB_WORKFLOW_RUNS_PROBE",
        "GUARD_EVALUATION",
        "GUARD_REJECTED",
    }
)


class LifecycleDiagnosticError(ValueError):
    """Raised when a diagnostic would contain an unsafe or invalid value."""


def _optional_bool(value: object, name: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise LifecycleDiagnosticError(f"{name} must be boolean or null")
    return value


def _optional_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LifecycleDiagnosticError("workflow run count must be a non-negative integer or null")
    return value


def _optional_exit_code(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise LifecycleDiagnosticError("exit code must be an integer from 0 through 255 or null")
    return value


def _validate_state(status: str, failure_category: str) -> None:
    if status not in STATUSES:
        raise LifecycleDiagnosticError("diagnostic status is not allowlisted")
    if status == "NOT_STARTED" and failure_category != "NOT_STARTED":
        raise LifecycleDiagnosticError("initial diagnostic category is invalid")
    if status == "OBSERVED" and failure_category != "NONE":
        raise LifecycleDiagnosticError("observed diagnostic category is invalid")
    if status == "PASSED" and failure_category != "NONE":
        raise LifecycleDiagnosticError("passed diagnostic category is invalid")
    if status == "FAILED" and failure_category not in FAILURE_CATEGORIES:
        raise LifecycleDiagnosticError("failure category is not allowlisted")
    if status != "NOT_STARTED" and failure_category == "NOT_STARTED":
        raise LifecycleDiagnosticError("not-started category is only valid for initial records")


def _write(
    path: Path,
    *,
    status: str,
    failure_category: str,
    exit_code: int | None,
    database_exists: bool | None,
    canary_service_active: bool | None,
    current_release_reference: bool | None,
    workflow_runs_in_progress: int | None,
) -> dict[str, object]:
    _validate_state(status, failure_category)
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "failure_category": failure_category,
        "exit_code": _optional_exit_code(exit_code),
        "database_exists": _optional_bool(database_exists, "database_exists"),
        "canary_service_active": _optional_bool(
            canary_service_active, "canary_service_active"
        ),
        "current_release_reference": _optional_bool(
            current_release_reference, "current_release_reference"
        ),
        "workflow_runs_in_progress": _optional_count(workflow_runs_in_progress),
    }
    if path.is_symlink():
        raise LifecycleDiagnosticError("diagnostic path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(body, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    path.chmod(0o600)
    return body


def write_initial(path: Path) -> dict[str, object]:
    return _write(
        path,
        status="NOT_STARTED",
        failure_category="NOT_STARTED",
        exit_code=None,
        database_exists=None,
        canary_service_active=None,
        current_release_reference=None,
        workflow_runs_in_progress=None,
    )


def write_failure(path: Path, *, category: str, exit_code: int) -> dict[str, object]:
    return _write(
        path,
        status="FAILED",
        failure_category=category,
        exit_code=exit_code,
        database_exists=None,
        canary_service_active=None,
        current_release_reference=None,
        workflow_runs_in_progress=None,
    )


def write_observations(
    path: Path,
    *,
    status: str,
    failure_category: str,
    database_exists: bool | None,
    canary_service_active: bool | None,
    current_release_reference: bool | None,
    workflow_runs_in_progress: int | None,
    exit_code: int | None,
) -> dict[str, object]:
    return _write(
        path,
        status=status,
        failure_category=failure_category,
        exit_code=exit_code,
        database_exists=database_exists,
        canary_service_active=canary_service_active,
        current_release_reference=current_release_reference,
        workflow_runs_in_progress=workflow_runs_in_progress,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--path", type=Path, required=True)

    failure_parser = subparsers.add_parser("failure")
    failure_parser.add_argument("--path", type=Path, required=True)
    failure_parser.add_argument("--category", choices=sorted(FAILURE_CATEGORIES), required=True)
    failure_parser.add_argument("--exit-code", type=int, required=True)

    args = parser.parse_args()
    try:
        if args.command == "init":
            write_initial(args.path)
        else:
            write_failure(args.path, category=args.category, exit_code=args.exit_code)
    except (OSError, LifecycleDiagnosticError) as error:
        print(f"WP31_CANARY_LIFECYCLE_DIAGNOSTIC=FAIL reason={error}")
        return 2
    print("WP31_CANARY_LIFECYCLE_DIAGNOSTIC=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
