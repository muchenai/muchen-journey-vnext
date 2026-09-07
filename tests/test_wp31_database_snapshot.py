from __future__ import annotations

import importlib
import os
import stat
from pathlib import Path
from types import ModuleType

import pytest


SNAPSHOT_ID = "00000003-0000001B-1"


class FakeResult:
    def __init__(self, value: str) -> None:
        self.value = value

    def scalar_one(self) -> str:
        return self.value


class FakeConnection:
    def __init__(self, snapshot_id: str = SNAPSHOT_ID, read_only: str = "on") -> None:
        self.snapshot_id = snapshot_id
        self.read_only = read_only
        self.statements: list[str] = []
        self.parameters: list[tuple[str, ...] | None] = []
        self.rollback_count = 0

    def rollback(self) -> None:
        self.rollback_count += 1

    def exec_driver_sql(
        self, statement: str, parameters: tuple[str, ...] | None = None
    ) -> FakeResult:
        self.statements.append(statement)
        self.parameters.append(parameters)
        if statement == "SHOW transaction_read_only":
            return FakeResult(self.read_only)
        if statement == "SELECT pg_export_snapshot()":
            return FakeResult(self.snapshot_id)
        return FakeResult("")


def snapshot_module() -> ModuleType:
    return importlib.import_module("scripts.wp31_database_snapshot")


def write_release(path: Path) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    os.chmod(path, 0o600)


def test_export_and_import_snapshot_transaction_order() -> None:
    snapshot = snapshot_module()
    exported = FakeConnection(snapshot_id=SNAPSHOT_ID)
    assert snapshot.export_snapshot(exported) == SNAPSHOT_ID
    assert exported.statements == [
        "BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE",
        "SHOW transaction_read_only",
        "SELECT pg_export_snapshot()",
    ]

    imported = FakeConnection()
    snapshot.import_snapshot(imported, SNAPSHOT_ID)
    assert imported.statements == [
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
        "SET TRANSACTION SNAPSHOT %s",
    ]
    assert imported.parameters == [None, (SNAPSHOT_ID,)]


@pytest.mark.parametrize("value", ["", "abc", "x'; SELECT 1; --", "00000003/0000001B/1"])
def test_snapshot_id_rejects_non_postgresql_format(value: str) -> None:
    snapshot = snapshot_module()
    with pytest.raises(snapshot.SnapshotError, match="identifier is invalid"):
        snapshot.validate_snapshot_id(value)


def test_holder_releases_snapshot_without_disclosing_identifier(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = snapshot_module()
    exchange = tmp_path / "exchange"
    exchange.mkdir(mode=0o700)
    connection = FakeConnection(snapshot_id=SNAPSHOT_ID)
    open_calls: list[tuple[str, int, int]] = []
    real_open = os.open

    def record_open(path: os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        open_calls.append((Path(path).name, flags, mode))
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", record_open)

    def release_snapshot(_: float) -> None:
        write_release(exchange / "snapshot-release")

    snapshot.hold_snapshot(
        connection,
        exchange,
        timeout_seconds=1,
        sleep=release_snapshot,
    )

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "WP31_DATABASE_SNAPSHOT=READY",
        "WP31_DATABASE_SNAPSHOT=RELEASED",
    ]
    assert captured.err == ""
    assert SNAPSHOT_ID not in captured.out
    assert (exchange / "snapshot-id").read_text() == SNAPSHOT_ID + "\n"
    assert [(name, mode) for name, _, mode in open_calls] == [
        ("snapshot-id", 0o600),
        ("snapshot-release", 0o600),
    ]
    assert all(flags & os.O_CREAT and flags & os.O_EXCL for _, flags, _ in open_calls)
    if os.name != "nt":
        assert stat.S_IMODE((exchange / "snapshot-id").stat().st_mode) == 0o600
        assert stat.S_IMODE((exchange / "snapshot-release").stat().st_mode) == 0o600
    assert connection.rollback_count == 2


def test_holder_timeout_is_bounded_and_rolls_back(tmp_path: Path) -> None:
    snapshot = snapshot_module()
    exchange = tmp_path / "exchange"
    exchange.mkdir(mode=0o700)
    connection = FakeConnection(snapshot_id=SNAPSHOT_ID)
    now = 0.0
    slept: list[float] = []

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    with pytest.raises(snapshot.SnapshotError, match="release timed out"):
        snapshot.hold_snapshot(
            connection,
            exchange,
            timeout_seconds=0.25,
            sleep=sleep,
            monotonic=monotonic,
        )

    assert sum(slept) == pytest.approx(0.25)
    assert connection.rollback_count == 2


def test_holder_rejects_non_regular_release_and_rolls_back(tmp_path: Path) -> None:
    snapshot = snapshot_module()
    exchange = tmp_path / "exchange"
    exchange.mkdir(mode=0o700)
    connection = FakeConnection(snapshot_id=SNAPSHOT_ID)

    def create_directory_release(_: float) -> None:
        (exchange / "snapshot-release").mkdir()

    with pytest.raises(snapshot.SnapshotError, match="release file is invalid"):
        snapshot.hold_snapshot(
            connection,
            exchange,
            timeout_seconds=1,
            sleep=create_directory_release,
        )

    assert connection.rollback_count == 2


def test_holder_rolls_back_when_export_fails(tmp_path: Path) -> None:
    snapshot = snapshot_module()
    exchange = tmp_path / "exchange"
    exchange.mkdir(mode=0o700)
    connection = FakeConnection(snapshot_id="invalid")

    with pytest.raises(snapshot.SnapshotError, match="identifier is invalid"):
        snapshot.hold_snapshot(connection, exchange, timeout_seconds=1)

    assert connection.rollback_count == 2
    assert not (exchange / "snapshot-id").exists()
