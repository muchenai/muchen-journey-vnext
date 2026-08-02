#!/usr/bin/env python3
"""Compare PII-free restore facts and remove one bounded plaintext dump.

This command is intentionally tied to the failed WP-15 restore window.  It
fails closed unless exactly one direct backup directory contains the expected
plaintext artifact and no encrypted/manifest artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIMESTAMP = re.compile(r"^\d{8}T\d{6}Z$")
FACT_KEYS = {
    "migration",
    "schema_sha256",
    "counts",
    "content_fingerprints",
    "active_notification_recipients",
}


class CleanupError(RuntimeError):
    pass


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CleanupError(f"invalid UTC boundary: {value}") from error
    if parsed.tzinfo is None:
        raise CleanupError("UTC boundary must include a timezone")
    return parsed.astimezone(timezone.utc)


def directory_timestamp(path: Path) -> datetime:
    if not TIMESTAMP.fullmatch(path.name):
        raise CleanupError(f"unexpected backup directory name: {path.name}")
    return datetime.strptime(path.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def regular_file(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(value.st_mode) and not path.is_symlink()


def load_facts(path: Path) -> dict[str, Any]:
    if not regular_file(path):
        raise CleanupError(f"facts file is missing or unsafe: {path.name}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise CleanupError(f"cannot read PII-free facts: {path.name}") from error
    if not isinstance(value, dict) or set(value) != FACT_KEYS:
        raise CleanupError(f"facts contract differs: {path.name}")
    if not isinstance(value["migration"], str):
        raise CleanupError(f"migration fact is invalid: {path.name}")
    if not re.fullmatch(r"[0-9a-f]{64}", value["schema_sha256"]):
        raise CleanupError(f"schema hash is invalid: {path.name}")
    for key in ("counts", "content_fingerprints"):
        if not isinstance(value[key], dict) or not all(
            isinstance(name, str) and name.replace("_", "").isalnum()
            for name in value[key]
        ):
            raise CleanupError(f"{key} fact is invalid: {path.name}")
    if not isinstance(value["active_notification_recipients"], int):
        raise CleanupError(f"notification count is invalid: {path.name}")
    return value


def find_failed_directory(root: Path, after: datetime, before: datetime) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise CleanupError("backup root is missing or unsafe")
    matches: list[Path] = []
    for path in root.iterdir():
        if not path.is_dir() or path.is_symlink() or not TIMESTAMP.fullmatch(path.name):
            continue
        created = directory_timestamp(path)
        if not after <= created <= before:
            continue
        if (
            regular_file(path / "journey-next.dump")
            and not (path / "journey-next.dump.enc").exists()
            and not (path / "backup-manifest.json").exists()
        ):
            matches.append(path)
    if len(matches) != 1:
        raise CleanupError(
            f"expected exactly one failed plaintext backup in the authorized window; found {len(matches)}"
        )
    candidate = matches[0]
    if candidate.parent.resolve() != root.resolve():
        raise CleanupError("failed backup escaped the authorized root")
    return candidate


def compare(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    table_names = sorted(set(source["counts"]) | set(target["counts"]))
    count_differences = {
        table: {"source": source["counts"].get(table), "target": target["counts"].get(table)}
        for table in table_names
        if source["counts"].get(table) != target["counts"].get(table)
    }
    fingerprint_tables = sorted(
        table
        for table in set(source["content_fingerprints"]) | set(target["content_fingerprints"])
        if source["content_fingerprints"].get(table)
        != target["content_fingerprints"].get(table)
    )
    return {
        "migration": {
            "equal": source["migration"] == target["migration"],
            "source": source["migration"],
            "target": target["migration"],
        },
        "schema_equal": source["schema_sha256"] == target["schema_sha256"],
        "count_differences": count_differences,
        "fingerprint_mismatch_tables": fingerprint_tables,
        "active_notification_recipients": {
            "equal": source["active_notification_recipients"]
            == target["active_notification_recipients"],
            "source": source["active_notification_recipients"],
            "target": target["active_notification_recipients"],
        },
    }


def remove_plaintext(candidate: Path) -> tuple[int, int, int]:
    plain = candidate / "journey-next.dump"
    verify = candidate / "journey-next.verify.dump"
    if not regular_file(plain):
        raise CleanupError("authorized plaintext dump disappeared or became unsafe")
    if verify.exists() and not regular_file(verify):
        raise CleanupError("verify dump is unsafe")
    root = candidate.parent
    all_plaintext = {
        path.resolve()
        for pattern in ("*/journey-next.dump", "*/journey-next.verify.dump")
        for path in root.glob(pattern)
        if regular_file(path)
    }
    authorized = {plain.resolve()}
    if verify.exists():
        authorized.add(verify.resolve())
    if all_plaintext != authorized:
        raise CleanupError(
            f"unexpected plaintext dump files exist outside the authorized directory: "
            f"{len(all_plaintext - authorized)}"
        )
    plain_bytes = plain.stat().st_size
    removed_plain = 0
    removed_verify = 0
    plain.unlink()
    removed_plain = 1
    if verify.exists():
        verify.unlink()
        removed_verify = 1
    directory_fd = os.open(candidate, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    if plain.exists() or verify.exists():
        raise CleanupError("plaintext cleanup verification failed")
    return removed_plain, removed_verify, plain_bytes


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.backup_root)
    after = parse_utc(args.created_after)
    before = parse_utc(args.created_before)
    if after > before:
        raise CleanupError("authorized time window is reversed")
    source = load_facts(Path(args.source_facts))
    target = load_facts(Path(args.target_facts))
    candidate = find_failed_directory(root, after, before)
    diff = compare(source, target)
    removed_plain, removed_verify, plain_bytes = remove_plaintext(candidate)
    remaining = [
        str(path.relative_to(root))
        for path in root.glob("*/journey-next*.dump")
        if regular_file(path)
    ]
    if remaining:
        raise CleanupError(f"plaintext dump files remain: {len(remaining)}")
    result = {
        "schema_version": 1,
        "failed_workflow_run_id": args.failed_workflow_run_id,
        "failed_backup_directory": candidate.name,
        "facts": diff,
        "cleanup": {
            "plaintext_dump_removed": removed_plain,
            "verify_dump_removed": removed_verify,
            "plaintext_bytes_removed": plain_bytes,
            "plaintext_dumps_remaining": 0,
            "facts_files_preserved": True,
            "database_mutation_executed": False,
        },
    }
    output = Path(args.output)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    os.chmod(output, 0o600)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", required=True)
    parser.add_argument("--source-facts", required=True)
    parser.add_argument("--target-facts", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--failed-workflow-run-id", required=True)
    parser.add_argument("--created-after", required=True)
    parser.add_argument("--created-before", required=True)
    return parser


def main() -> None:
    try:
        result = run(build_parser().parse_args())
    except CleanupError as error:
        print(f"WP15_FAILED_RESTORE_CLEANUP_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print("WP15_FAILED_RESTORE_DIFF=" + json.dumps(result["facts"], sort_keys=True))
    print(
        "WP15_FAILED_RESTORE_CLEANUP=PASS "
        f"run_id={result['failed_workflow_run_id']} "
        f"directory={result['failed_backup_directory']} "
        f"plaintext_bytes_removed={result['cleanup']['plaintext_bytes_removed']} "
        "plaintext_dumps_remaining=0 database_mutation=false"
    )


if __name__ == "__main__":
    main()
