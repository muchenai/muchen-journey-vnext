#!/usr/bin/env python3
"""Build a deterministic, repository-external controlled-release source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_TOP_LEVELS = {
    ".github",
    "apps",
    "config",
    "contracts",
    "deploy",
    "docs",
    "migrations",
    "scripts",
    "tests",
}
SOURCE_ROOT_FILES = {
    ".dockerignore",
    ".gitleaks.toml",
    ".gitignore",
    "Makefile",
    "README.md",
    "alembic.ini",
    "compose.yaml",
    "pyproject.toml",
    "requirements-build.lock",
    "requirements.lock",
}


class StageError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def run_git(repo: Path, *arguments: str, stdout: Any = subprocess.PIPE) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["/usr/bin/git", *arguments],
        cwd=repo,
        check=False,
        stdout=stdout,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise StageError(f"git command failed: {message or arguments[0]}")
    return result


def validate_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise StageError("inventory contains an unsafe relative path")
    return path


def is_source_path(path: PurePosixPath) -> bool:
    return path.as_posix() in SOURCE_ROOT_FILES or path.parts[0] in SOURCE_TOP_LEVELS


def load_inventory(repo: Path, inventory_path: Path) -> tuple[dict[str, Any], str]:
    if inventory_path.is_symlink() or not inventory_path.is_file():
        raise StageError("inventory must be a regular file")
    try:
        inventory_path.resolve(strict=True).relative_to(repo)
    except ValueError as exc:
        raise StageError("inventory must stay inside the repository") from exc
    try:
        value = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageError("inventory is unreadable or invalid JSON") from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("entries"), list):
        raise StageError("inventory schema is unsupported")
    counts = value.get("classification_counts")
    if not isinstance(counts, dict) or counts.get("UNKNOWN") != 0:
        raise StageError("inventory UNKNOWN count must be zero")
    return value, sha256_file(inventory_path)


def parse_porcelain_z(raw: bytes) -> list[tuple[str, str]]:
    tokens = raw.split(b"\0")
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        decoded = token.decode("utf-8", errors="strict")
        if len(decoded) < 4 or decoded[2] != " ":
            raise StageError("current Git status is unreadable")
        status, relative = decoded[:2], decoded[3:]
        if "R" in status or "C" in status:
            if index >= len(tokens) or not tokens[index]:
                raise StageError("current Git rename or copy entry is incomplete")
            index += 1
        entries.append((status, relative))
    return entries


def verify_inventory_snapshot(repo: Path, inventory_path: Path, inventory: dict[str, Any]) -> None:
    inventory_relative = inventory_path.resolve(strict=True).relative_to(repo).as_posix()
    current = parse_porcelain_z(
        run_git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    )
    current_without_self = sorted(
        (status, relative)
        for status, relative in current
        if relative != inventory_relative
    )
    expected = sorted(
        (str(entry.get("git_status", "")), str(entry.get("path", "")))
        for entry in inventory["entries"]
        if isinstance(entry, dict)
    )
    if current_without_self != expected:
        raise StageError("inventory is stale relative to the current Git worktree")

    for entry in inventory["entries"]:
        if not isinstance(entry, dict):
            raise StageError("inventory entry is invalid")
        relative = validate_relative_path(str(entry.get("path", "")))
        path = repo / relative
        file_type = entry.get("file_type")
        expected_hash = entry.get("sha256")
        if file_type == "REGULAR":
            if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_hash:
                raise StageError("inventory regular-file hash no longer matches")
        elif file_type == "SYMLINK_NOT_FOLLOWED":
            if not path.is_symlink() or hashlib.sha256(
                os.readlink(path).encode("utf-8")
            ).hexdigest() != expected_hash:
                raise StageError("inventory symlink hash no longer matches")
        elif file_type == "MISSING_OR_NON_REGULAR":
            if path.exists() or path.is_symlink() or expected_hash is not None:
                raise StageError("inventory missing-file state no longer matches")
        else:
            raise StageError("inventory file type is unsupported")


def safe_extract_git_archive(archive: Path, destination: Path) -> list[dict[str, str]]:
    excluded: list[dict[str, str]] = []
    with tarfile.open(archive, mode="r:") as bundle:
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if (
                not member.name
                or path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
                or not (member.isdir() or member.isfile())
            ):
                raise StageError("git archive contains an unsafe member")
            if member.isdir():
                continue
            source = bundle.extractfile(member)
            if source is None:
                raise StageError("git archive regular file is unreadable")
            if not is_source_path(path):
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                excluded.append({"path": path.as_posix(), "baseline_sha256": digest.hexdigest()})
                continue
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, member.mode & 0o777)
            with os.fdopen(descriptor, "wb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
            os.chmod(target, member.mode & 0o777)
    return excluded


def copy_overlay(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise StageError("release overlay must be a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(f".{destination.name}.overlay-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise StageError("overlay temporary path already exists")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as target, source.open("rb") as current:
            for chunk in iter(lambda: current.read(1024 * 1024), b""):
                target.write(chunk)
        os.chmod(temporary, stat.S_IMODE(source.stat().st_mode))
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def normalize_source_directories(source_root: Path) -> None:
    directories = [source_root]
    directories.extend(path for path in source_root.rglob("*") if path.is_dir())
    for path in directories:
        if path.is_symlink():
            raise StageError("staged source directory cannot be a symlink")
        os.chmod(path, 0o755)


def tree_manifest(source_root: Path) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    for path in sorted(source_root.rglob("*")):
        relative = path.relative_to(source_root).as_posix()
        if path.is_symlink():
            raise StageError("staged source tree contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise StageError("staged source tree contains a non-regular entry")
        records.append(
            {
                "path": relative,
                "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records, hashlib.sha256(canonical_json(records)).hexdigest()


def write_exclusive_json(path: Path, value: object) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def verify_stage(output: Path) -> dict[str, Any]:
    if output.is_symlink() or not output.is_dir():
        raise StageError("stage output must be a regular directory")
    expected_top_level = {
        "COMPLETE.json",
        "source",
        "source-files.sha256.json",
        "stage-manifest.json",
    }
    if {item.name for item in output.iterdir()} != expected_top_level:
        raise StageError("stage output contains missing or unexpected entries")
    for relative in ("COMPLETE.json", "source-files.sha256.json", "stage-manifest.json"):
        path = output / relative
        if path.is_symlink() or not path.is_file():
            raise StageError("stage evidence must be regular files")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise StageError("stage evidence permissions must be 0600")
    try:
        complete = json.loads((output / "COMPLETE.json").read_text(encoding="utf-8"))
        manifest = json.loads((output / "stage-manifest.json").read_text(encoding="utf-8"))
        expected_records = json.loads(
            (output / "source-files.sha256.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageError("stage evidence is unreadable or invalid JSON") from exc
    if (
        manifest.get("schema_version") != 1
        or manifest.get("state") != "ISOLATED_SOURCE_TREE_READY"
        or manifest.get("candidate_commit_sha") is not None
        or manifest.get("release_candidate") is not False
        or manifest.get("release_authorized") is not False
        or manifest.get("production_mutation_executed") is not False
    ):
        raise StageError("stage manifest state is invalid")
    excluded_baseline = manifest.get("excluded_baseline_files")
    if (
        not isinstance(excluded_baseline, list)
        or manifest.get("excluded_baseline_file_count") != len(excluded_baseline)
        or any(
            not isinstance(item, dict)
            or set(item) != {"path", "baseline_sha256"}
            or not isinstance(item["path"], str)
            or not isinstance(item["baseline_sha256"], str)
            or len(item["baseline_sha256"]) != 64
            for item in excluded_baseline
        )
    ):
        raise StageError("excluded baseline binding is invalid")
    if complete != {
        "stage_id": manifest.get("stage_id"),
        "state": "ISOLATED_SOURCE_TREE_READY",
        "stage_manifest_sha256": sha256_file(output / "stage-manifest.json"),
    }:
        raise StageError("stage completion marker does not bind the manifest")
    if not isinstance(expected_records, list):
        raise StageError("source file manifest must be a list")
    actual_records, actual_tree_sha256 = tree_manifest(output / "source")
    source_directories = [output / "source"]
    source_directories.extend(
        path for path in (output / "source").rglob("*") if path.is_dir()
    )
    if any(
        stat.S_IMODE(path.stat().st_mode) != 0o755
        for path in source_directories
    ):
        raise StageError("staged source directory permissions drifted")
    if actual_records != expected_records:
        raise StageError("staged source files drifted")
    if (
        manifest.get("source_tree_sha256") != actual_tree_sha256
        or manifest.get("source_file_count") != len(actual_records)
    ):
        raise StageError("staged source tree binding is invalid")
    return manifest


def stage_candidate(repo: Path, inventory_path: Path, output: Path, stage_id: str) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    if run_git(repo, "rev-parse", "--show-toplevel").stdout.decode().strip() != str(repo):
        raise StageError("repo must be the exact Git worktree root")
    if output.is_symlink() or output.exists():
        raise StageError("output must not already exist")
    output = output.resolve(strict=False)
    try:
        output.relative_to(repo)
    except ValueError:
        pass
    else:
        raise StageError("output must be outside the repository")
    if not stage_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in stage_id):
        raise StageError("stage_id contains unsupported characters")

    inventory, inventory_sha256 = load_inventory(repo, inventory_path.resolve(strict=True))
    head = run_git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    branch = run_git(repo, "branch", "--show-current").stdout.decode().strip()
    if inventory.get("git_head") != head or inventory.get("branch") != branch:
        raise StageError("inventory does not match the current Git baseline")
    verify_inventory_snapshot(repo, inventory_path.resolve(strict=True), inventory)

    overlay_paths: list[str] = []
    deletion_paths: list[str] = []
    excluded_dirty: list[dict[str, str]] = []
    for entry in inventory["entries"]:
        if not isinstance(entry, dict):
            raise StageError("inventory entry is invalid")
        relative = validate_relative_path(str(entry.get("path", "")))
        classification = entry.get("classification")
        git_status = str(entry.get("git_status", ""))
        if classification == "UNKNOWN":
            raise StageError("inventory entry remains UNKNOWN")
        if git_status != "??" and classification != "RELEASE_REQUIRED":
            excluded_dirty.append(
                {"path": relative.as_posix(), "classification": str(classification)}
            )
            continue
        if classification == "RELEASE_REQUIRED" and is_source_path(relative):
            if "D" in git_status:
                deletion_paths.append(relative.as_posix())
            else:
                overlay_paths.append(relative.as_posix())
        else:
            excluded_dirty.append(
                {"path": relative.as_posix(), "classification": str(classification)}
            )

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.mkdir(mode=0o700)
    source_root = output / "source"
    source_root.mkdir(mode=0o700)
    write_exclusive_json(output / "BUILDING.json", {"stage_id": stage_id, "state": "BUILDING"})
    with tempfile.NamedTemporaryFile(dir=output, prefix="baseline-", suffix=".tar") as archive:
        run_git(repo, "archive", "--format=tar", "HEAD", stdout=archive)
        archive.flush()
        excluded_baseline = safe_extract_git_archive(Path(archive.name), source_root)

    deletion_records: list[dict[str, str]] = []
    for relative in sorted(set(deletion_paths)):
        destination = source_root / relative
        if destination.is_symlink() or not destination.is_file():
            raise StageError("release deletion must target one baseline regular file")
        deletion_records.append({"path": relative, "baseline_sha256": sha256_file(destination)})
        destination.unlink()

    overlay_records: list[dict[str, str]] = []
    for relative in sorted(set(overlay_paths)):
        source = repo / relative
        destination = source_root / relative
        copy_overlay(source, destination)
        overlay_records.append({"path": relative, "sha256": sha256_file(source)})

    normalize_source_directories(source_root)
    records, source_tree_sha256 = tree_manifest(source_root)
    manifest = {
        "schema_version": 1,
        "stage_id": stage_id,
        "state": "ISOLATED_SOURCE_TREE_READY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repository_head": head,
        "branch": branch,
        "inventory_path": inventory_path.resolve(strict=True).relative_to(repo).as_posix(),
        "inventory_sha256": inventory_sha256,
        "inventory_classification_counts": inventory["classification_counts"],
        "source_tree_sha256": source_tree_sha256,
        "source_file_count": len(records),
        "overlay_file_count": len(overlay_records),
        "overlay_files": overlay_records,
        "deleted_file_count": len(deletion_records),
        "deleted_files": deletion_records,
        "excluded_baseline_file_count": len(excluded_baseline),
        "excluded_baseline_files": excluded_baseline,
        "excluded_dirty_entry_count": len(excluded_dirty),
        "excluded_dirty_entries": excluded_dirty,
        "unknown_count": 0,
        "candidate_commit_sha": None,
        "release_candidate": False,
        "release_authorized": False,
        "production_mutation_executed": False,
    }
    write_exclusive_json(output / "source-files.sha256.json", records)
    write_exclusive_json(output / "stage-manifest.json", manifest)
    write_exclusive_json(
        output / "COMPLETE.json",
        {
            "stage_id": stage_id,
            "state": "ISOLATED_SOURCE_TREE_READY",
            "stage_manifest_sha256": sha256_file(output / "stage-manifest.json"),
        },
    )
    (output / "BUILDING.json").unlink()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stage-id")
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.verify is not None:
            if any(
                value is not None
                for value in (
                    arguments.repo,
                    arguments.inventory,
                    arguments.output,
                    arguments.stage_id,
                )
            ):
                raise StageError("--verify cannot be combined with stage creation arguments")
            manifest = verify_stage(arguments.verify.resolve(strict=True))
        else:
            if any(
                value is None
                for value in (
                    arguments.repo,
                    arguments.inventory,
                    arguments.output,
                    arguments.stage_id,
                )
            ):
                raise StageError("stage creation requires repo, inventory, output, and stage-id")
            manifest = stage_candidate(
                arguments.repo, arguments.inventory, arguments.output, arguments.stage_id
            )
    except (StageError, OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"CONTROLLED_RELEASE_STAGE=FAIL\nERROR={error}\n")
    print("CONTROLLED_RELEASE_STAGE=PASS")
    print(f"MODE={'VERIFY' if arguments.verify is not None else 'CREATE'}")
    print(f"STAGE_ID={manifest['stage_id']}")
    print(f"SOURCE_FILE_COUNT={manifest['source_file_count']}")
    print(f"OVERLAY_FILE_COUNT={manifest['overlay_file_count']}")
    print(f"DELETED_FILE_COUNT={manifest['deleted_file_count']}")
    print(f"EXCLUDED_BASELINE_FILE_COUNT={manifest['excluded_baseline_file_count']}")
    print(f"EXCLUDED_DIRTY_ENTRY_COUNT={manifest['excluded_dirty_entry_count']}")
    print(f"SOURCE_TREE_SHA256={manifest['source_tree_sha256']}")
    print("CANDIDATE_COMMIT_SHA=NOT_CREATED")
    print("RELEASE_AUTHORIZED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
