"""Safety tests for the bounded candidate-image preload phase."""

import gzip
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import canary_schema_cache as cache


def manifest() -> dict[str, object]:
    candidate = "a" * 40
    return {
        "schema_version": 2,
        "base_candidate": "b8a5dd580eaec72945cbe4f0e37c1152ee4645a1",
        "candidate": candidate,
        "database": "journey_next_canary_20260901_c72fea5",
        "migrations": {
            "from": "0028_canary_main_merge",
            "to": "0029_treasure_coaching_reviews",
        },
        "images": {
            "api": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:" + "1" * 64,
            "web": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:" + "2" * 64,
            "dbrestore": "ghcr.io/muchenai/muchen-journey-vnext-dbrestore@sha256:" + "3" * 64,
        },
        "old_images": {
            "api": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:" + "4" * 64,
            "web": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:" + "5" * 64,
        },
        "compatibility": "ADDITIVE_SCHEMA_THEN_IMMUTABLE_BACKFILL",
    }


def inspect_row(reference: str, candidate: str) -> bytes:
    return json.dumps(
        [{
            "Os": "linux",
            "Architecture": "amd64",
            "RepoDigests": [reference],
            "Config": {"Labels": {"org.opencontainers.image.revision": candidate}},
        }]
    ).encode()


def test_export_uses_only_three_candidate_images(tmp_path, monkeypatch, capsys):
    value = manifest()
    commands: list[list[str]] = []

    def execute(command, timeout=1800):
        commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return inspect_row(command[3], str(value["candidate"]))
        if command[:2] == ["docker", "save"]:
            Path(command[3]).write_bytes(b"synthetic archive")
        return b""

    monkeypatch.setattr(cache, "execute", execute)
    archive = tmp_path / "images.tar.gz"
    cache.export_images(value, archive)

    expected = [reference for _name, reference in cache.candidate_images(value)]
    assert [command[2] for command in commands if command[:2] == ["docker", "pull"]] == expected
    assert all(reference not in str(commands) for reference in value["old_images"].values())
    assert len([command for command in commands if command[:2] == ["docker", "tag"]]) == 3
    assert len([command for command in commands if command[:2] == ["docker", "save"]]) == 1
    assert gzip.open(archive, "rb").read() == b"synthetic archive"
    result = json.loads(capsys.readouterr().out)
    assert result["archive_format"] == "gzip"
    assert result["raw_archive_bytes"] == len(b"synthetic archive")
    assert result["archive_bytes"] == archive.stat().st_size
    assert not (tmp_path / "images.tar.gz.raw").exists()


def test_check_image_rejects_wrong_revision(monkeypatch):
    value = manifest()
    reference = value["images"]["api"]
    monkeypatch.setattr(cache, "execute", Mock(return_value=inspect_row(reference, "b" * 40)))
    with pytest.raises(cache.UpgradeError, match="IMAGE_REVISION"):
        cache.check_image("api", reference, str(value["candidate"]))


def test_compression_failure_leaves_no_partial_or_raw_archive(tmp_path, monkeypatch):
    source = tmp_path / "images.tar.gz.raw"
    destination = tmp_path / "images.tar.gz"
    source.write_bytes(b"synthetic archive")
    monkeypatch.setattr(cache.gzip, "GzipFile", Mock(side_effect=RuntimeError("compress failed")))

    with pytest.raises(RuntimeError, match="compress failed"):
        cache.compress_archive(source, destination)

    assert not source.exists()
    assert not destination.exists()


def test_import_rejects_archive_hash_before_runtime_checks(tmp_path, monkeypatch):
    archive = tmp_path / "images.tar.gz"
    archive.write_bytes(b"synthetic archive")
    upgrade = Mock()
    monkeypatch.setattr(cache, "Upgrade", Mock(return_value=upgrade))
    monkeypatch.setattr(cache.sys, "platform", "linux")
    monkeypatch.setattr(cache.os, "geteuid", Mock(return_value=0), raising=False)
    monkeypatch.setattr(cache, "__file__", str(tmp_path / "canary_schema_cache.py"))
    with pytest.raises(cache.UpgradeError, match="ARCHIVE_HASH"):
        cache.import_images(manifest(), archive, "0" * 64)
    upgrade.verify_base.assert_not_called()


@pytest.mark.skipif(os.name != "posix", reason="release locking requires POSIX flock")
def test_import_loads_exact_images_under_release_lock(tmp_path, monkeypatch):
    value = manifest()
    archive = tmp_path / "images.tar.gz"
    archive.write_bytes(b"synthetic archive")
    expected_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    upgrade = Mock(new=tmp_path / "not-prepared")
    commands: list[list[str]] = []

    def execute(command, timeout=1800):
        commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return inspect_row(command[3], str(value["candidate"]))
        return b""

    monkeypatch.setattr(cache, "Upgrade", Mock(return_value=upgrade))
    monkeypatch.setattr(cache, "execute", execute)
    monkeypatch.setattr(cache.schema, "ROOT", tmp_path)
    monkeypatch.setattr(cache, "__file__", str(tmp_path / "canary_schema_cache.py"))
    monkeypatch.setattr(cache.os, "geteuid", Mock(return_value=0))
    cache.import_images(value, archive, expected_sha)

    assert upgrade.verify_base.call_count == 2
    assert commands[0] == ["gzip", "-t", str(archive)]
    assert commands[1] == ["docker", "load", "--input", str(archive)]
    assert [command[3] for command in commands[2:]] == [
        reference for _name, reference in cache.candidate_images(value)
    ]
    assert not archive.exists()


@pytest.mark.skipif(os.name != "posix", reason="release locking requires POSIX flock")
def test_import_refuses_an_active_release_phase(tmp_path, monkeypatch):
    import fcntl

    value = manifest()
    archive = tmp_path / "images.tar.gz"
    archive.write_bytes(b"synthetic archive")
    expected_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    lock_path = tmp_path / ".schema-upgrade.lock"
    lock = lock_path.open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    upgrade = Mock(new=tmp_path / "not-prepared")
    monkeypatch.setattr(cache, "Upgrade", Mock(return_value=upgrade))
    monkeypatch.setattr(cache, "execute", Mock())
    monkeypatch.setattr(cache.schema, "ROOT", tmp_path)
    monkeypatch.setattr(cache, "__file__", str(tmp_path / "canary_schema_cache.py"))
    monkeypatch.setattr(cache.os, "geteuid", Mock(return_value=0))
    try:
        with pytest.raises(cache.UpgradeError, match="RELEASE_PHASE_ACTIVE"):
            cache.import_images(value, archive, expected_sha)
    finally:
        lock.close()
    cache.execute.assert_called_once_with(["gzip", "-t", str(archive)], timeout=300)
    assert not any(call.args[0][:2] == ["docker", "load"] for call in cache.execute.call_args_list)
    upgrade.verify_base.assert_not_called()


def test_source_has_no_runtime_or_database_mutation_commands():
    source = Path("scripts/canary_schema_cache.py").read_text()
    for forbidden in (
        '"docker", "run"',
        '"docker", "restart"',
        '"docker", "rm"',
        '"docker", "compose"',
        "os.kill",
        "/proc",
        "alembic",
        "pg_dump",
        "backfill",
    ):
        assert forbidden not in source


def test_workflow_serializes_cache_with_every_release_phase():
    source = Path(".github/workflows/canary-schema-release.yml").read_text()
    assert "group: canary-schema-upgrade-release" in source
    assert "canary-schema-image-cache" not in source
    assert "CACHE_IMAGES_$short" in source
    assert "scripts/canary_schema_cache.py export" in source
    assert "canary_schema_cache.py' import" in source
    assert "schema-image-cache.tar.gz" in source
    assert "timeout --signal=TERM --kill-after=30s 50m scp" in source
    assert "IMAGE_CACHE_TRANSFER_TIMEOUT" in source
    assert 'archive_bytes=$(stat -c %s "$archive")' in source
