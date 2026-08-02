#!/usr/bin/env python3
"""Delete only the two plaintext dumps proven by WP-15 inventory evidence."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.wp15_failed_restore_cleanup import CleanupError, regular_file


AUTHORIZED = {
    "20260802T104651Z": 6_838_622,
    "20260802T150149Z": 6_838_889,
}


def cleanup(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise CleanupError("backup root is missing or unsafe")
    found = {}
    for dump in root.glob("*/journey-next*.dump"):
        if not regular_file(dump) or dump.name != "journey-next.dump":
            raise CleanupError(f"unexpected or unsafe plaintext artifact: {dump.parent.name}/{dump.name}")
        found[dump.parent.name] = dump.stat().st_size
    if found != AUTHORIZED:
        raise CleanupError(f"plaintext inventory differs from authorization: {found}")
    removed = []
    for directory, size in AUTHORIZED.items():
        dump = root / directory / "journey-next.dump"
        if not regular_file(dump) or dump.stat().st_size != size:
            raise CleanupError(f"authorized artifact changed before deletion: {directory}")
        dump.unlink()
        directory_fd = os.open(dump.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        removed.append({"directory_timestamp": directory, "plaintext_bytes": size})
    remaining = [path for path in root.glob("*/journey-next*.dump") if path.exists()]
    if remaining:
        raise CleanupError(f"plaintext artifacts remain after cleanup: {len(remaining)}")
    return {
        "schema_version": 1,
        "removed": removed,
        "plaintext_bytes_removed": sum(AUTHORIZED.values()),
        "plaintext_artifacts_remaining": 0,
        "facts_files_preserved": True,
        "database_mutation_executed": False,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: wp15_known_plaintext_cleanup.py BACKUP_ROOT")
    try:
        result = cleanup(Path(sys.argv[1]))
    except (CleanupError, OSError) as error:
        print(f"WP15_KNOWN_PLAINTEXT_CLEANUP_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print("WP15_KNOWN_PLAINTEXT_CLEANUP=" + json.dumps(result, sort_keys=True))
    print("WP15_KNOWN_PLAINTEXT_CLEANUP=PASS artifacts=2 remaining=0 database_mutation=false")


if __name__ == "__main__":
    main()
