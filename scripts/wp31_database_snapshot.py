#!/usr/bin/env python3
"""Export and hold one PostgreSQL snapshot for Canary backup verification."""

from __future__ import annotations

import argparse
import math
import os
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path


SNAPSHOT_ID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9A-Fa-f]+$")
POLL_SECONDS = 0.1


class SnapshotError(RuntimeError):
    """Raised when a safe synchronized PostgreSQL snapshot cannot be held."""


def validate_snapshot_id(value: str) -> str:
    if not isinstance(value, str) or SNAPSHOT_ID.fullmatch(value) is None:
        raise SnapshotError("snapshot identifier is invalid")
    return value


def export_snapshot(connection: object) -> str:
    connection.rollback()
    connection.exec_driver_sql(
        "BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE"
    )
    if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise SnapshotError("snapshot exporter is not read-only")
    return validate_snapshot_id(
        connection.exec_driver_sql("SELECT pg_export_snapshot()").scalar_one()
    )


def import_snapshot(connection: object, snapshot_id: str) -> None:
    value = validate_snapshot_id(snapshot_id)
    connection.rollback()
    connection.exec_driver_sql(
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    )
    connection.exec_driver_sql(f"SET TRANSACTION SNAPSHOT '{value}'")


def _resolve_exchange_dir(value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    try:
        if path.is_symlink() or not path.is_dir():
            raise SnapshotError("snapshot exchange directory is invalid")
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise SnapshotError("snapshot exchange directory is invalid") from error
    if not resolved.is_dir():
        raise SnapshotError("snapshot exchange directory is invalid")
    return resolved


def _write_snapshot_id(path: Path, snapshot_id: str) -> None:
    pending = path.with_name(".snapshot-id.pending")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(pending, flags, 0o600)
    except OSError as error:
        raise SnapshotError("snapshot identifier file cannot be created") from error
    try:
        try:
            os.write(descriptor, (snapshot_id + "\n").encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(pending, 0o600)
        os.link(pending, path)
    except OSError as error:
        raise SnapshotError("snapshot identifier file cannot be published") from error
    finally:
        try:
            pending.unlink()
        except OSError:
            pass


def hold_snapshot(
    connection: object,
    exchange_dir: str | os.PathLike[str],
    timeout_seconds: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    try:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise SnapshotError("snapshot release timeout is invalid")
        exchange = _resolve_exchange_dir(exchange_dir)
        identifier_path = exchange / "snapshot-id"
        release_path = exchange / "snapshot-release"
        if release_path.exists() or release_path.is_symlink():
            raise SnapshotError("snapshot release file already exists")

        snapshot_id = export_snapshot(connection)
        _write_snapshot_id(identifier_path, snapshot_id)
        print("WP31_DATABASE_SNAPSHOT=READY", flush=True)

        deadline = monotonic() + timeout_seconds
        while True:
            if release_path.is_symlink():
                raise SnapshotError("snapshot release file is invalid")
            if release_path.exists():
                if not release_path.is_file():
                    raise SnapshotError("snapshot release file is invalid")
                print("WP31_DATABASE_SNAPSHOT=RELEASED", flush=True)
                return
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise SnapshotError("snapshot release timed out")
            sleep(min(POLL_SECONDS, remaining))
    finally:
        connection.rollback()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange-dir", required=True)
    parser.add_argument("--timeout-seconds", required=True, type=float)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = None
    try:
        from journey_api.config import get_settings
        from sqlalchemy import create_engine

        engine = create_engine(get_settings().database_url)
        with engine.connect() as connection:
            hold_snapshot(connection, args.exchange_dir, args.timeout_seconds)
    except Exception as error:
        print(
            f"WP31_DATABASE_SNAPSHOT=FAIL error_type={type(error).__name__}",
            flush=True,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
