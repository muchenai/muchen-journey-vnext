#!/usr/bin/env python3
"""Remove one exact failed pre-start WP-08 release without touching runtime state."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path


CANDIDATE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"
FAILED_RUN_ID = "30808632624"
RELEASE_ROOT = Path("/srv/journey-next-staging")
EXPECTED_TOP_LEVEL = {
    ".deployment.env",
    "Caddyfile",
    "compose.migrate.yaml",
    "compose.yaml",
    "deploy.sh",
    "grant_runtime.py",
    "secrets",
}
EXPECTED_SECRET_FILES = {
    "api.env",
    "edge.env",
    "migration.env",
    "volcengine-rds-ca.pem",
    "web.env",
    "worker.env",
}


class CleanupError(RuntimeError):
    pass


def read_env_value(path: Path, key: str) -> str:
    prefix = f"{key}="
    values = [
        line.removeprefix(prefix)
        for line in path.read_text().splitlines()
        if line.startswith(prefix)
    ]
    if len(values) != 1 or not values[0]:
        raise CleanupError(f"failed release has no unique {key}")
    return values[0]


def docker_working_directories() -> set[Path]:
    result = subprocess.run(
        ["docker", "ps", "-aq"],
        check=True,
        text=True,
        capture_output=True,
    )
    container_ids = result.stdout.split()
    if not container_ids:
        return set()
    inspected = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}',
            *container_ids,
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return {
        Path(line).resolve(strict=False)
        for line in inspected.stdout.splitlines()
        if line and line != "<no value>"
    }


def validate_tree(target: Path) -> list[Path]:
    if {entry.name for entry in target.iterdir()} != EXPECTED_TOP_LEVEL:
        raise CleanupError("failed release contents differ from the reviewed bundle")
    secrets = target / "secrets"
    if not secrets.is_dir() or secrets.is_symlink():
        raise CleanupError("failed release secrets directory is unsafe")
    if {entry.name for entry in secrets.iterdir()} != EXPECTED_SECRET_FILES:
        raise CleanupError("failed release secret files differ from the reviewed bundle")
    secret_files: list[Path] = []
    for entry in target.rglob("*"):
        if entry.is_symlink():
            raise CleanupError("failed release contains a symbolic link")
        mode = entry.stat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise CleanupError("failed release contains a non-regular file")
        if entry.stat().st_nlink != 1:
            raise CleanupError("failed release contains a hard-linked file")
        if entry == target / ".deployment.env" or entry.parent == secrets:
            secret_files.append(entry)
    return secret_files


def cleanup_release(
    candidate: str,
    run_id: str,
    *,
    root: Path = RELEASE_ROOT,
    require_root: bool = True,
    working_directories: set[Path] | None = None,
) -> int:
    if candidate != CANDIDATE or run_id != FAILED_RUN_ID:
        raise CleanupError("candidate or failed run does not match the one-time contract")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate) or not run_id.isdecimal():
        raise CleanupError("candidate or failed run identifier is invalid")
    if require_root and os.geteuid() != 0:
        raise CleanupError("failed release cleanup must run as root")
    if not root.is_dir() or root.is_symlink():
        raise CleanupError("release root is not one real directory")

    root = root.resolve(strict=True)
    target = root / "releases" / f"{candidate}-{run_id}"
    if not target.is_dir() or target.is_symlink():
        raise CleanupError("exact failed release directory is absent or unsafe")
    if target.resolve(strict=True) != target:
        raise CleanupError("failed release resolved outside its exact path")

    current = root / "current"
    if not current.is_symlink() or current.resolve(strict=True) == target:
        raise CleanupError("current release safety check failed")
    previous = root / "PREVIOUS_RELEASE"
    if previous.exists():
        if not previous.is_file() or previous.is_symlink():
            raise CleanupError("previous release marker is unsafe")
        previous_path = Path(previous.read_text().strip()).resolve(strict=False)
        if previous_path == target:
            raise CleanupError("failed release is still a rollback target")
    deployed = root / "DEPLOYED_CANDIDATE"
    if not deployed.is_file() or deployed.is_symlink():
        raise CleanupError("deployed candidate marker is absent or unsafe")
    if deployed.read_text().strip() == candidate:
        raise CleanupError("failed candidate is marked as deployed")

    deployment_env = target / ".deployment.env"
    if not deployment_env.is_file() or deployment_env.is_symlink():
        raise CleanupError("failed release deployment contract is unsafe")
    if read_env_value(deployment_env, "CANDIDATE_COMMIT") != candidate:
        raise CleanupError("failed release candidate marker differs")

    secret_files = validate_tree(target)
    active_directories = (
        docker_working_directories()
        if working_directories is None
        else {path.resolve(strict=False) for path in working_directories}
    )
    if target in active_directories:
        raise CleanupError("a Docker container still references the failed release")
    if shutil.which("shred") is None:
        raise CleanupError("secure file removal command is unavailable")

    for path in secret_files:
        subprocess.run(["shred", "-u", "--", str(path)], check=True)
    shutil.rmtree(target)
    if target.exists() or target.is_symlink():
        raise CleanupError("failed release directory still exists after cleanup")
    return len(secret_files)


def main() -> None:
    if len(sys.argv) != 3:
        print("WP08_FAILED_RELEASE_CLEANUP_ERROR: expected candidate and run ID", file=sys.stderr)
        raise SystemExit(2)
    try:
        count = cleanup_release(sys.argv[1], sys.argv[2])
    except (CleanupError, OSError, subprocess.CalledProcessError) as error:
        print(f"WP08_FAILED_RELEASE_CLEANUP_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(
        "WP08_FAILED_RELEASE_CLEANUP=PASS"
        f" candidate={CANDIDATE} run_id={FAILED_RUN_ID} shredded_files={count}"
    )


if __name__ == "__main__":
    main()
