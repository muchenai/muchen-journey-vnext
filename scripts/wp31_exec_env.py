#!/usr/bin/env python3
"""Execute a command with literal KEY=value files, without shell evaluation."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


_KEY = re.compile(r"[A-Z][A-Z0-9_]*")


class EnvContractError(ValueError):
    pass


def parse_assignment(raw: str) -> tuple[str, str]:
    if "\0" in raw or "\r" in raw or "\n" in raw or "=" not in raw:
        raise EnvContractError("environment assignment is malformed")
    key, value = raw.split("=", 1)
    if not _KEY.fullmatch(key):
        raise EnvContractError("environment key is invalid")
    return key, value


def read_env_file(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise EnvContractError("environment file is missing or unsafe")
    values: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for raw_line in handle:
                line = raw_line[:-1] if raw_line.endswith("\n") else raw_line
                key, value = parse_assignment(line)
                if key in values:
                    raise EnvContractError("environment file contains a duplicate key")
                values[key] = value
    except (OSError, UnicodeError) as error:
        raise EnvContractError("environment file cannot be read") from error
    if not values:
        raise EnvContractError("environment file is empty")
    return values


def merge_env_files(paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        for key, value in read_env_file(path).items():
            if key in result and result[key] != value:
                raise EnvContractError("environment files disagree on a key")
            result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", action="append", type=Path, required=True)
    parser.add_argument("--set", dest="assignments", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("WP31_EXEC_ENV=FAIL reason=command is missing", file=sys.stderr)
        return 2
    try:
        environment = dict(os.environ)
        environment.update(merge_env_files(args.env_file))
        for assignment in args.assignments:
            key, value = parse_assignment(assignment)
            environment[key] = value
        if os.name == "nt":  # Keep the parser testable on the Windows handoff host.
            return subprocess.run(command, env=environment, check=False).returncode
        os.execvpe(command[0], command, environment)
    except (EnvContractError, OSError) as error:
        print(f"WP31_EXEC_ENV=FAIL reason={error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
