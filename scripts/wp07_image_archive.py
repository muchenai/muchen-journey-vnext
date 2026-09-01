#!/usr/bin/env python3
"""Create and verify candidate image archives for restricted staging networks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


COMPONENTS = ("api", "web", "worker")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_FILE = re.compile(r"(?:api|web|worker)\.tar")


class ArchiveError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(arguments: Iterable[str]) -> str:
    completed = subprocess.run(
        tuple(arguments), check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArchiveError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise ArchiveError(f"{label} must be one JSON object")
    return value


def release_images(release_manifest: Path) -> tuple[str, dict[str, Any]]:
    release = read_json(release_manifest, label="release manifest")
    commit = release.get("candidate", {}).get("commit_sha")
    images = release.get("images")
    external = release.get("external_status")
    if not isinstance(commit, str) or not FULL_SHA.fullmatch(commit):
        raise ArchiveError("release candidate SHA is invalid")
    if not isinstance(images, dict) or set(images) != set(COMPONENTS):
        raise ArchiveError("release manifest must contain exactly three images")
    if not isinstance(external, dict) or external.get("registry_push") != "VERIFIED":
        raise ArchiveError("release registry evidence is not VERIFIED")
    for component in COMPONENTS:
        item = images[component]
        if not isinstance(item, dict):
            raise ArchiveError(f"release image is invalid: {component}")
        registry_reference = item.get("registry_reference")
        registry_digest = item.get("registry_digest")
        local_digest = item.get("local_image_digest")
        expected_reference = (
            "ghcr.io/muchenai2024-creator/muchen-journey-vnext-"
            f"{component}:{commit}"
        )
        if registry_reference != expected_reference:
            raise ArchiveError(f"registry reference is not canonical: {component}")
        if not isinstance(registry_digest, str) or not DIGEST.fullmatch(registry_digest):
            raise ArchiveError(f"registry digest is invalid: {component}")
        if not isinstance(local_digest, str) or not DIGEST.fullmatch(local_digest):
            raise ArchiveError(f"local image digest is invalid: {component}")
    return commit, images


def pack(release_manifest: Path, output: Path) -> dict[str, Any]:
    commit, images = release_images(release_manifest)
    output.mkdir(parents=True, exist_ok=True)
    entries: dict[str, Any] = {}
    for component in COMPONENTS:
        item = images[component]
        reference = item["registry_reference"]
        inspected = json.loads(run(("docker", "image", "inspect", reference)))[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        if inspected.get("Id") != item["local_image_digest"]:
            raise ArchiveError(f"local image differs from release manifest: {component}")
        if labels.get("org.opencontainers.image.revision") != commit:
            raise ArchiveError(f"image revision differs from candidate: {component}")
        archive = output / f"{component}.tar"
        run(("docker", "image", "save", "--output", str(archive), reference))
        if not archive.is_file() or archive.is_symlink() or archive.stat().st_size <= 0:
            raise ArchiveError(f"image archive was not created: {component}")
        archive.chmod(0o600)
        entries[component] = {
            "file": archive.name,
            "sha256": sha256(archive),
            "size_bytes": archive.stat().st_size,
            "runtime_reference": reference,
            "local_image_digest": item["local_image_digest"],
            "registry_digest": item["registry_digest"],
        }
    manifest = {
        "schema_version": 1,
        "candidate_commit": commit,
        "images": entries,
    }
    manifest_path = output.parent / "image-archives.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path.chmod(0o600)
    verify_files(release_manifest, manifest_path, output)
    return manifest


def verify_files(
    release_manifest: Path, archive_manifest: Path, archive_root: Path
) -> dict[str, Any]:
    commit, release = release_images(release_manifest)
    archive = read_json(archive_manifest, label="archive manifest")
    entries = archive.get("images")
    if archive.get("schema_version") != 1 or archive.get("candidate_commit") != commit:
        raise ArchiveError("archive manifest candidate binding is invalid")
    if not isinstance(entries, dict) or set(entries) != set(COMPONENTS):
        raise ArchiveError("archive manifest must contain exactly three images")
    for component in COMPONENTS:
        entry = entries[component]
        source = release[component]
        if not isinstance(entry, dict):
            raise ArchiveError(f"archive image entry is invalid: {component}")
        filename = entry.get("file")
        if not isinstance(filename, str) or not SAFE_FILE.fullmatch(filename):
            raise ArchiveError(f"archive file name is invalid: {component}")
        path = archive_root / filename
        if not path.is_file() or path.is_symlink() or path.parent != archive_root:
            raise ArchiveError(f"archive file is missing or unsafe: {component}")
        if entry.get("size_bytes") != path.stat().st_size or path.stat().st_size <= 0:
            raise ArchiveError(f"archive size differs: {component}")
        if entry.get("sha256") != sha256(path):
            raise ArchiveError(f"archive hash differs: {component}")
        if entry.get("runtime_reference") != source["registry_reference"]:
            raise ArchiveError(f"archive runtime reference differs: {component}")
        if entry.get("local_image_digest") != source["local_image_digest"]:
            raise ArchiveError(f"archive local image digest differs: {component}")
        if entry.get("registry_digest") != source["registry_digest"]:
            raise ArchiveError(f"archive registry digest differs: {component}")
    return {"candidate_commit": commit, "archive_count": len(COMPONENTS)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack_command = commands.add_parser("pack")
    pack_command.add_argument("--release-manifest", type=Path, required=True)
    pack_command.add_argument("--output", type=Path, required=True)
    verify_command = commands.add_parser("verify-files")
    verify_command.add_argument("--release-manifest", type=Path, required=True)
    verify_command.add_argument("--archive-manifest", type=Path, required=True)
    verify_command.add_argument("--archive-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = pack(args.release_manifest, args.output)
            print(
                "WP07_IMAGE_ARCHIVES=READY "
                f"candidate={result['candidate_commit']} count={len(COMPONENTS)}"
            )
        else:
            result = verify_files(
                args.release_manifest, args.archive_manifest, args.archive_root
            )
            print(
                "WP07_IMAGE_ARCHIVES=VERIFIED "
                f"candidate={result['candidate_commit']} count={result['archive_count']}"
            )
    except (ArchiveError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"WP07_IMAGE_ARCHIVE_ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
