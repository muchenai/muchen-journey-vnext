#!/usr/bin/env python3
"""Inventory plaintext restore artifacts without reading their contents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts.wp15_failed_restore_cleanup import (
    CleanupError,
    TIMESTAMP,
    compare,
    load_facts,
    regular_file,
)


def inventory(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise CleanupError("backup root is missing or unsafe")
    artifacts = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or directory.is_symlink() or not TIMESTAMP.fullmatch(directory.name):
            continue
        dump = directory / "journey-next.dump"
        if dump.exists() and not regular_file(dump):
            raise CleanupError(f"plaintext dump is unsafe: {directory.name}")
        if not regular_file(dump):
            continue
        source = directory / "source-facts.json"
        target = directory / "target-facts.json"
        for facts_file in (source, target):
            if facts_file.exists() and not regular_file(facts_file):
                raise CleanupError(f"facts file is unsafe: {directory.name}/{facts_file.name}")
        facts_status = "COMPLETE"
        facts = None
        if not source.exists():
            facts_status = "MISSING_SOURCE_FACTS"
        elif not target.exists():
            facts_status = "MISSING_TARGET_FACTS"
        else:
            facts = compare(load_facts(source), load_facts(target))
        artifacts.append(
            {
                "directory_timestamp": directory.name,
                "plaintext_bytes": dump.stat().st_size,
                "facts_status": facts_status,
                "facts": facts,
            }
        )
    if len(artifacts) != 2:
        raise CleanupError(f"expected exactly two plaintext restore artifacts; found {len(artifacts)}")
    return {
        "schema_version": 1,
        "artifact_count": 2,
        "artifacts": artifacts,
        "dump_contents_read": False,
        "database_connected": False,
        "files_deleted": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inventory(args.backup_root)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        os.chmod(args.output, 0o600)
    except (CleanupError, OSError) as error:
        print(f"WP15_FAILED_RESTORE_INVENTORY_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print("WP15_FAILED_RESTORE_INVENTORY=" + json.dumps(result, sort_keys=True))
    print("WP15_FAILED_RESTORE_INVENTORY=PASS artifacts=2 mutation=false")


if __name__ == "__main__":
    main()
