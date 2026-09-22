"""Narrow allowlist for Learner write limits; unchanged schema/auth core.

This is not a general-purpose migration compatibility claim. Any other application,
dependency, configuration or Dockerfile change requires a new reviewed policy.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

BASE = "29c0473c488dd9f2d35ca40aec32e505169d4a72"
SOURCE_BASE = BASE
ALLOWED_RUNTIME_CHANGES = {
    "apps/api/journey_api/main.py",
    "apps/api/journey_api/submission_routes.py",
    "apps/api/journey_api/learner_write_limits.py",
    "apps/web/scripts/learner-loop-contract.test.mjs",
    "apps/web/src/app/actions.ts",
    "apps/web/src/app/app/tasks/[assignmentId]/submission-composer.tsx",
    "apps/web/src/lib/server/api.ts",
    "apps/web/src/lib/use-write-cooldown.ts",
    "contracts/openapi.json",
}
PROTECTED_ROOTS = ("apps/", "migrations/", "contracts/", "config/", "requirements", "pyproject.toml", "alembic.ini")


def validate_changes(paths):
    denied = [p for p in paths if p.startswith(PROTECTED_ROOTS) and p not in ALLOWED_RUNTIME_CHANGES]
    if denied:
        raise ValueError("Application-only compatibility rejected: " + ", ".join(denied))


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def verify(candidate):
    if not re.fullmatch(r"[0-9a-f]{40}", candidate) or candidate == BASE:
        raise ValueError("A new exact candidate SHA is required")
    if git("rev-parse", "HEAD") != candidate or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Candidate checkout must be exact and clean")
    git("merge-base", "--is-ancestor", SOURCE_BASE, candidate)
    paths = git("diff", "--name-only", SOURCE_BASE, candidate).splitlines()
    validate_changes(paths)
    return {"base_candidate": BASE, "source_base": SOURCE_BASE, "candidate": candidate,
            "compatibility": "NO_SCHEMA_OR_IDENTITY_CHANGE",
            "schema_tree": git("rev-parse", candidate + ":migrations"),
            "changed_runtime_files": [p for p in paths if p in ALLOWED_RUNTIME_CHANGES]}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = verify(args.candidate)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("APP_UPGRADE_COMPATIBILITY=PASS")
