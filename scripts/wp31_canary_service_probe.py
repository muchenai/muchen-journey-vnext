#!/usr/bin/env python3
"""Read-only host probe: exit 0 present, 1 absent, 2 unknown; no raw Docker output."""

import subprocess
import sys


PROJECTS = ("journey-next-greenfield-canary", "journey-next-production-canary")
FORMAT = '{{.Names}}|{{.Label "com.docker.compose.project"}}'


def service_present(output: str) -> bool:
    present = False
    for line in output.splitlines():
        if line.count("|") != 1:
            raise ValueError("invalid container metadata")
        name, project = line.split("|")
        if not name or any(char.isspace() for char in name):
            raise ValueError("invalid container metadata")
        if project in PROJECTS or any(name.startswith(prefix + "-") for prefix in PROJECTS):
            present = True
    return present


def main() -> int:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", FORMAT],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return 0 if service_present(result.stdout) else 1
    except (OSError, subprocess.SubprocessError, ValueError):
        print("WP31_CANARY_SERVICE_PROBE=UNKNOWN", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
