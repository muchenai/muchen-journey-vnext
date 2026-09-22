"""Narrow allowlist for review history and text limits; unchanged schema/auth core.

This is not a general-purpose migration compatibility claim. Any other application,
dependency, configuration or Dockerfile change requires a new reviewed policy.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

BASE = "9d1ce3d897a6b409dc621fe305ec428e0039f367"
SOURCE_BASE = BASE
ALLOWED_RUNTIME_CHANGES = {
    "apps/api/journey_api/review_routes.py",
    "apps/api/journey_api/schemas.py",
    "apps/web/scripts/canary-invite-action.test.mjs",
    "apps/web/scripts/resilience-a11y-contract.test.mjs",
    "apps/web/scripts/reviewer-ops-contract.test.mjs",
    "apps/web/scripts/submission-feedback-contract.test.mjs",
    "apps/web/src/app/actions.ts",
    "apps/web/src/app/app/tasks/[assignmentId]/submission-composer.tsx",
    "apps/web/src/app/character-progress.tsx",
    "apps/web/src/app/globals.css",
    "apps/web/src/app/review/[reviewId]/page.tsx",
    "apps/web/src/app/review/[reviewId]/review-workbench.tsx",
    "apps/web/src/app/review/page.tsx",
    "apps/web/src/lib/server/api.ts",
    "apps/web/src/lib/text-length.ts",
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
