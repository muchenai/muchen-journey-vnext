"""Narrow allowlist for explicit Learner logout feedback; unchanged schema/auth core.

This is not a general-purpose migration compatibility claim. Any other application,
dependency, configuration or Dockerfile change requires a new reviewed policy.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

BASE = "0e49004294763adfabae0130b13d4878b964c8c3"
SOURCE_BASE = BASE
ALLOWED_CHANGES = {
    "apps/web/scripts/logout-session-feedback-contract.test.mjs",
    "apps/web/src/app/actions.ts",
    "apps/web/src/app/app/logout-control.tsx",
    "apps/web/src/app/app/page.tsx",
    "apps/web/src/app/content/page.tsx",
    "apps/web/src/app/globals.css",
    "apps/web/src/app/page.tsx",
    "scripts/canary_app_compatibility.py",
    "scripts/canary_app_upgrade.py",
    "scripts/logout_feedback_browser.cjs",
    "tests/test_canary_app_compatibility.py",
    "tests/test_canary_app_upgrade.py",
    "tests/test_identity_invites.py",
}
ALLOWED_RUNTIME_CHANGES = {
    "apps/web/src/app/actions.ts",
    "apps/web/src/app/app/logout-control.tsx",
    "apps/web/src/app/app/page.tsx",
    "apps/web/src/app/content/page.tsx",
    "apps/web/src/app/globals.css",
    "apps/web/src/app/page.tsx",
}


def validate_changes(paths):
    denied = [path for path in paths if path not in ALLOWED_CHANGES]
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
    return {
        "base_candidate": BASE,
        "source_base": SOURCE_BASE,
        "candidate": candidate,
        "compatibility": "NO_SCHEMA_OR_IDENTITY_CHANGE",
        "schema_tree": git("rev-parse", candidate + ":migrations"),
        "changed_runtime_files": [path for path in paths if path in ALLOWED_RUNTIME_CHANGES],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.candidate)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    print("APP_UPGRADE_COMPATIBILITY=PASS")
