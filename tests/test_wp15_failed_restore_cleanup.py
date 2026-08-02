from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.wp15_failed_restore_cleanup import CleanupError, run
from scripts.wp15_failed_restore_inventory import inventory


def facts(*, changed: bool = False) -> dict:
    return {
        "migration": "0014_wp12_data_lifecycle",
        "schema_sha256": ("b" if changed else "a") * 64,
        "counts": {"submissions": 3 if changed else 2, "reviews": 1},
        "content_fingerprints": {
            "submissions": "different" if changed else "same",
            "reviews": "same",
        },
        "active_notification_recipients": 0,
    }


def arguments(tmp_path: Path) -> Namespace:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text(json.dumps(facts()))
    target.write_text(json.dumps(facts(changed=True)))
    return Namespace(
        backup_root=str(tmp_path / "backups"),
        source_facts=str(source),
        target_facts=str(target),
        output=str(tmp_path / "result.json"),
        failed_workflow_run_id="30753376010",
        created_after="2026-08-02T15:00:37Z",
        created_before="2026-08-02T15:02:06Z",
    )


def failed_directory(tmp_path: Path) -> Path:
    path = tmp_path / "backups" / "20260802T150130Z"
    path.mkdir(parents=True)
    (path / "journey-next.dump").write_bytes(b"plaintext backup")
    (path / "source-facts.json").write_text("{}")
    (path / "target-facts.json").write_text("{}")
    return path


def test_compares_only_pii_free_facts_and_removes_plaintext(tmp_path: Path) -> None:
    args = arguments(tmp_path)
    path = failed_directory(tmp_path)

    result = run(args)

    assert result["facts"]["schema_equal"] is False
    assert result["facts"]["count_differences"] == {
        "submissions": {"source": 2, "target": 3}
    }
    assert result["facts"]["fingerprint_mismatch_tables"] == ["submissions"]
    assert result["cleanup"]["plaintext_dump_removed"] == 1
    assert result["cleanup"]["database_mutation_executed"] is False
    assert not (path / "journey-next.dump").exists()
    assert (path / "source-facts.json").exists()
    assert json.loads(Path(args.output).read_text()) == result


def test_refuses_ambiguous_failed_directories_without_deleting(tmp_path: Path) -> None:
    args = arguments(tmp_path)
    first = failed_directory(tmp_path)
    second = tmp_path / "backups" / "20260802T150145Z"
    second.mkdir()
    (second / "journey-next.dump").write_bytes(b"second")

    with pytest.raises(CleanupError, match="exactly one"):
        run(args)

    assert (first / "journey-next.dump").exists()
    assert (second / "journey-next.dump").exists()


def test_inventory_reports_missing_target_facts_without_opening_dump(tmp_path: Path) -> None:
    first = failed_directory(tmp_path)
    second = tmp_path / "backups" / "20260802T140000Z"
    second.mkdir()
    (second / "journey-next.dump").write_bytes(b"older plaintext")
    for directory in (first, second):
        (directory / "source-facts.json").write_text(json.dumps(facts()))
        (directory / "target-facts.json").unlink(missing_ok=True)

    result = inventory(tmp_path / "backups")

    assert [item["facts_status"] for item in result["artifacts"]] == [
        "MISSING_TARGET_FACTS",
        "MISSING_TARGET_FACTS",
    ]
    assert all(item["facts"] is None for item in result["artifacts"])
    assert result["files_deleted"] == 0


def test_refuses_plaintext_outside_authorized_window_without_deleting(tmp_path: Path) -> None:
    args = arguments(tmp_path)
    authorized = failed_directory(tmp_path)
    other = tmp_path / "backups" / "20260802T140000Z"
    other.mkdir()
    (other / "journey-next.dump").write_bytes(b"older")

    with pytest.raises(CleanupError, match="outside the authorized directory"):
        run(args)

    assert (authorized / "journey-next.dump").exists()
    assert (other / "journey-next.dump").exists()


def test_refuses_symlink_without_touching_target(tmp_path: Path) -> None:
    args = arguments(tmp_path)
    path = failed_directory(tmp_path)
    outside = tmp_path / "outside.dump"
    outside.write_bytes(b"keep")
    (path / "journey-next.dump").unlink()
    (path / "journey-next.dump").symlink_to(outside)

    with pytest.raises(CleanupError, match="exactly one"):
        run(args)

    assert outside.read_bytes() == b"keep"


def test_refuses_invalid_facts_before_deleting(tmp_path: Path) -> None:
    args = arguments(tmp_path)
    path = failed_directory(tmp_path)
    Path(args.target_facts).write_text('{"unexpected": true}')

    with pytest.raises(CleanupError, match="facts contract differs"):
        run(args)

    assert (path / "journey-next.dump").exists()


def test_inventory_reports_two_artifacts_without_reading_or_deleting_dumps(
    tmp_path: Path,
) -> None:
    first = failed_directory(tmp_path)
    second = tmp_path / "backups" / "20260802T140000Z"
    second.mkdir()
    (second / "journey-next.dump").write_bytes(b"older plaintext")
    for directory in (first, second):
        (directory / "source-facts.json").write_text(json.dumps(facts()))
        (directory / "target-facts.json").write_text(json.dumps(facts(changed=True)))

    result = inventory(tmp_path / "backups")

    assert result["artifact_count"] == 2
    assert result["dump_contents_read"] is False
    assert result["files_deleted"] == 0
    assert [item["directory_timestamp"] for item in result["artifacts"]] == [
        "20260802T140000Z",
        "20260802T150130Z",
    ]
    assert (first / "journey-next.dump").exists()
    assert (second / "journey-next.dump").exists()
