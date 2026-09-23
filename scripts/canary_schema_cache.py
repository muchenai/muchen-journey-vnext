"""Preload the three immutable candidate images without changing runtime state."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_schema_upgrade as schema
from canary_schema_upgrade import Upgrade, UpgradeError, load_manifest, require


def execute(command: list[str], timeout: int = 1800) -> bytes:
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UpgradeError("IMAGE_CACHE_COMMAND_TIMEOUT") from None
    require(result.returncode == 0, "IMAGE_CACHE_COMMAND_FAILED")
    return result.stdout


def archive_digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "ARCHIVE_UNSAFE_FILE")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def compress_archive(source: Path, destination: Path) -> tuple[int, int]:
    """Compress a docker-save archive without overwriting an existing target."""
    require(source.is_file() and not source.is_symlink(), "RAW_ARCHIVE_UNSAFE_FILE")
    require(not destination.exists() and not destination.is_symlink(), "ARCHIVE_EXISTS")
    raw_bytes = source.stat().st_size
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=1,
                fileobj=outgoing,
                mtime=0,
            ) as compressed:
                shutil.copyfileobj(incoming, compressed, length=1024 * 1024)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        source.unlink(missing_ok=True)
    return raw_bytes, destination.stat().st_size


def candidate_images(manifest: dict[str, object]) -> list[tuple[str, str]]:
    images = manifest["images"]
    require(isinstance(images, dict), "IMAGE_FIELDS")
    return [(name, str(images[name])) for name in ("api", "web", "dbrestore")]


def check_image(name: str, reference: str, candidate: str) -> None:
    row = json.loads(execute(["docker", "image", "inspect", reference], timeout=60))[0]
    require(row["Os"] == "linux" and row["Architecture"] == "amd64", "IMAGE_PLATFORM")
    require(reference in row.get("RepoDigests", []), "IMAGE_DIGEST")
    if name in {"api", "web"}:
        require(
            row["Config"]["Labels"].get("org.opencontainers.image.revision") == candidate,
            "IMAGE_REVISION",
        )


def export_images(manifest: dict[str, object], path: Path) -> None:
    require(not path.exists() and not path.is_symlink(), "ARCHIVE_EXISTS")
    raw_path = path.with_name(path.name + ".raw")
    require(not raw_path.exists() and not raw_path.is_symlink(), "RAW_ARCHIVE_EXISTS")
    candidate = str(manifest["candidate"])
    tags: list[str] = []
    for name, reference in candidate_images(manifest):
        execute(["docker", "pull", reference])
        check_image(name, reference, candidate)
        tag = reference.split("@", 1)[0] + ":schema-cache-" + candidate + "-" + name
        execute(["docker", "tag", reference, tag], timeout=60)
        tags.append(tag)
    try:
        execute(["docker", "save", "--output", str(raw_path), *tags])
        raw_bytes, archive_bytes = compress_archive(raw_path, path)
    finally:
        raw_path.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "cache_export": "PASS",
                "archive_sha256": archive_digest(path),
                "archive_format": "gzip",
                "archive_bytes": archive_bytes,
                "raw_archive_bytes": raw_bytes,
                "image_count": len(tags),
            },
            sort_keys=True,
        ),
        flush=True,
    )


def import_images(manifest: dict[str, object], path: Path, expected_sha: str) -> None:
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(path.resolve().parent == Path(__file__).resolve().parent, "ARCHIVE_WRONG_DIRECTORY")
    require(
        len(expected_sha) == 64
        and all(character in "0123456789abcdef" for character in expected_sha)
        and archive_digest(path) == expected_sha,
        "ARCHIVE_HASH",
    )
    execute(["gzip", "-t", str(path)], timeout=300)
    upgrade = Upgrade(manifest, Path(__file__).resolve().parent)
    os.umask(0o077)
    import fcntl

    descriptor = os.open(
        schema.ROOT / ".schema-upgrade.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpgradeError("RELEASE_PHASE_ACTIVE") from None
        upgrade.verify_base()
        require(not upgrade.new.exists() and not upgrade.new.is_symlink(), "PREPARATION_ALREADY_CREATED")
        execute(["docker", "load", "--input", str(path)])
        for name, reference in candidate_images(manifest):
            check_image(name, reference, str(manifest["candidate"]))
        upgrade.verify_base()
        path.unlink()
    print(
        json.dumps(
            {
                "cache_import": "PASS",
                "candidate": manifest["candidate"],
                "image_count": 3,
                "containers_changed": False,
                "database_changed": False,
                "release_changed": False,
                "archive_removed": True,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("export", "import"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest.resolve(), args.manifest_sha256)
    if args.mode == "export":
        export_images(manifest, args.archive)
    else:
        import_images(manifest, args.archive, args.archive_sha256 or "")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "cache_result": "STOP",
                    "category": str(error)
                    if isinstance(error, UpgradeError)
                    else type(error).__name__,
                    "do_not_retry_blindly": True,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        raise SystemExit(1)
