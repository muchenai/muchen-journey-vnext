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

CHUNK_BYTES = 16 * 1024 * 1024


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


def split_archive(
    path: Path,
    chunks_dir: Path,
    manifest_sha256: str,
    candidate: str,
    chunk_bytes: int = CHUNK_BYTES,
) -> Path:
    """Split one verified compressed archive into independently verifiable chunks."""
    require(path.is_file() and not path.is_symlink(), "ARCHIVE_UNSAFE_FILE")
    require(0 < chunk_bytes <= CHUNK_BYTES, "CHUNK_SIZE")
    require(not chunks_dir.exists() and not chunks_dir.is_symlink(), "CHUNKS_DIRECTORY_EXISTS")
    chunks_dir.mkdir(mode=0o700)
    chunks: list[dict[str, object]] = []
    with path.open("rb") as source:
        index = 0
        while data := source.read(chunk_bytes):
            name = f"chunk-{index:04d}.bin"
            chunk_path = chunks_dir / name
            with chunk_path.open("xb") as output:
                output.write(data)
            chunks.append(
                {
                    "name": name,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            index += 1
    require(bool(chunks), "CHUNKS_EMPTY")
    chunks_manifest = chunks_dir / "chunks.json"
    value = {
        "schema_version": 1,
        "release_manifest_sha256": manifest_sha256,
        "candidate": candidate,
        "archive_name": path.name,
        "archive_sha256": archive_digest(path),
        "archive_bytes": path.stat().st_size,
        "chunk_bytes": chunk_bytes,
        "chunks": chunks,
    }
    with chunks_manifest.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, sort_keys=True, separators=(",", ":"))
        output.write("\n")
    path.unlink()
    print(
        json.dumps(
            {
                "cache_split": "PASS",
                "archive_sha256": value["archive_sha256"],
                "archive_bytes": value["archive_bytes"],
                "chunk_bytes": chunk_bytes,
                "chunk_count": len(chunks),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return chunks_manifest


def assemble_archive(
    chunks_manifest: Path,
    chunks_dir: Path,
    destination: Path,
    manifest_sha256: str,
    candidate: str,
) -> tuple[str, list[Path]]:
    """Validate every chunk and assemble the exact original compressed archive."""
    require(chunks_manifest.is_file() and not chunks_manifest.is_symlink(), "CHUNKS_MANIFEST_FILE")
    require(chunks_dir.is_dir() and not chunks_dir.is_symlink(), "CHUNKS_DIRECTORY")
    require(not destination.exists() and not destination.is_symlink(), "ARCHIVE_EXISTS")
    value = json.loads(chunks_manifest.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "CHUNKS_SCHEMA")
    require(value.get("schema_version") == 1, "CHUNKS_SCHEMA")
    require(value.get("release_manifest_sha256") == manifest_sha256, "CHUNKS_RELEASE_MANIFEST")
    require(value.get("candidate") == candidate, "CHUNKS_CANDIDATE")
    require(value.get("archive_name") == destination.name, "CHUNKS_ARCHIVE_NAME")
    expected_sha = value.get("archive_sha256")
    expected_bytes = value.get("archive_bytes")
    chunk_size = value.get("chunk_bytes")
    rows = value.get("chunks")
    require(
        isinstance(expected_sha, str)
        and len(expected_sha) == 64
        and all(character in "0123456789abcdef" for character in expected_sha),
        "CHUNKS_ARCHIVE_HASH",
    )
    require(isinstance(expected_bytes, int) and expected_bytes > 0, "CHUNKS_ARCHIVE_BYTES")
    require(isinstance(chunk_size, int) and 0 < chunk_size <= CHUNK_BYTES, "CHUNK_SIZE")
    require(isinstance(rows, list) and 0 < len(rows) <= 4096, "CHUNKS_LIST")
    expected_names = {f"chunk-{index:04d}.bin" for index in range(len(rows))}
    allowed_names = set(expected_names)
    if chunks_manifest.resolve().parent == chunks_dir.resolve():
        allowed_names.add(chunks_manifest.name)
    require({entry.name for entry in chunks_dir.iterdir()} == allowed_names, "CHUNKS_DIRECTORY_CONTENTS")
    chunk_paths: list[Path] = []
    written = 0
    digest = hashlib.sha256()
    try:
        with destination.open("xb") as output:
            for index, row in enumerate(rows):
                require(isinstance(row, dict), "CHUNK_ROW")
                name = row.get("name")
                size = row.get("bytes")
                chunk_sha = row.get("sha256")
                require(name == f"chunk-{index:04d}.bin", "CHUNK_NAME")
                require(isinstance(size, int) and 0 < size <= chunk_size, "CHUNK_BYTES")
                require(
                    isinstance(chunk_sha, str)
                    and len(chunk_sha) == 64
                    and all(character in "0123456789abcdef" for character in chunk_sha),
                    "CHUNK_HASH",
                )
                chunk_path = chunks_dir / name
                require(chunk_path.is_file() and not chunk_path.is_symlink(), "CHUNK_FILE")
                require(chunk_path.stat().st_size == size, "CHUNK_BYTES")
                require(archive_digest(chunk_path) == chunk_sha, "CHUNK_HASH")
                data = chunk_path.read_bytes()
                output.write(data)
                digest.update(data)
                written += len(data)
                chunk_paths.append(chunk_path)
        require(written == expected_bytes, "CHUNKS_ARCHIVE_BYTES")
        require(digest.hexdigest() == expected_sha, "CHUNKS_ARCHIVE_HASH")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return expected_sha, chunk_paths


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


def inspect_cached_image(reference: str, candidate: str, name: str) -> dict[str, object]:
    tag = reference.split("@", 1)[0] + ":schema-cache-" + candidate + "-" + name

    def inspect(value: str) -> dict[str, object] | None:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", value],
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise UpgradeError("CACHE_DIAGNOSTIC_TIMEOUT") from None
        if result.returncode:
            return None
        rows = json.loads(result.stdout)
        require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict), "CACHE_DIAGNOSTIC_IMAGE")
        return rows[0]

    original = inspect(reference)
    cached = inspect(tag)
    cached_platform_ok = bool(
        cached and cached.get("Os") == "linux" and cached.get("Architecture") == "amd64"
    )
    labels = cached.get("Config", {}).get("Labels", {}) if cached else {}
    cached_revision_ok = bool(
        cached
        and (
            name == "dbrestore"
            or (isinstance(labels, dict) and labels.get("org.opencontainers.image.revision") == candidate)
        )
    )
    return {
        "name": name,
        "original_reference_present": original is not None,
        "cache_tag_present": cached is not None,
        "cache_platform_ok": cached_platform_ok,
        "cache_revision_ok": cached_revision_ok,
    }


def diagnose_import(
    manifest: dict[str, object],
    chunks_manifest: Path,
    archive: Path,
    manifest_sha256: str,
) -> None:
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    source_dir = archive.resolve().parent
    runs_dir = (schema.ROOT / "schema-upgrade-runs").resolve()
    require(source_dir.parent == runs_dir and source_dir.name.endswith("-1-cache-images"), "CACHE_DIAGNOSTIC_SOURCE")
    require(not source_dir.is_symlink(), "CACHE_DIAGNOSTIC_SOURCE")
    require(chunks_manifest.resolve().parent == source_dir, "CACHE_DIAGNOSTIC_MANIFEST_DIRECTORY")
    require(archive.is_file() and not archive.is_symlink(), "ARCHIVE_UNSAFE_FILE")
    require(chunks_manifest.is_file() and not chunks_manifest.is_symlink(), "CHUNKS_MANIFEST_FILE")
    value = json.loads(chunks_manifest.read_text(encoding="utf-8"))
    require(value.get("release_manifest_sha256") == manifest_sha256, "CHUNKS_RELEASE_MANIFEST")
    require(value.get("candidate") == manifest["candidate"], "CHUNKS_CANDIDATE")
    expected_sha = value.get("archive_sha256")
    require(isinstance(expected_sha, str) and archive_digest(archive) == expected_sha, "CHUNKS_ARCHIVE_HASH")
    try:
        gzip_result = subprocess.run(
            ["gzip", "-t", str(archive)],
            capture_output=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise UpgradeError("CACHE_DIAGNOSTIC_TIMEOUT") from None
    images = [
        inspect_cached_image(reference, str(manifest["candidate"]), name)
        for name, reference in candidate_images(manifest)
    ]
    print(
        json.dumps(
            {
                "cache_diagnostic": "PASS",
                "candidate": manifest["candidate"],
                "archive_sha256_valid": True,
                "gzip_valid": gzip_result.returncode == 0,
                "images": images,
                "containers_changed": False,
                "database_changed": False,
                "release_changed": False,
            },
            sort_keys=True,
        ),
        flush=True,
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


def import_chunked_images(
    manifest: dict[str, object],
    chunks_manifest: Path,
    chunks_dir: Path,
    archive: Path,
    manifest_sha256: str,
) -> None:
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    script_dir = Path(__file__).resolve().parent
    require(chunks_manifest.resolve().parent == script_dir, "CHUNKS_MANIFEST_DIRECTORY")
    require(chunks_dir.resolve().parent == script_dir, "CHUNKS_WRONG_DIRECTORY")
    expected_sha, chunk_paths = assemble_archive(
        chunks_manifest,
        chunks_dir,
        archive,
        manifest_sha256,
        str(manifest["candidate"]),
    )
    import_images(manifest, archive, expected_sha)
    for chunk_path in chunk_paths:
        chunk_path.unlink()
    chunks_dir.rmdir()
    chunks_manifest.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("export", "split", "import", "import-chunks", "diagnose-import")
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--chunks-dir", type=Path)
    parser.add_argument("--chunks-manifest", type=Path)
    parser.add_argument("--chunk-bytes", type=int, default=CHUNK_BYTES)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest.resolve(), args.manifest_sha256)
    if args.mode == "export":
        export_images(manifest, args.archive)
    elif args.mode == "split":
        require(args.chunks_dir is not None, "CHUNKS_DIRECTORY_REQUIRED")
        split_archive(
            args.archive,
            args.chunks_dir,
            args.manifest_sha256,
            str(manifest["candidate"]),
            args.chunk_bytes,
        )
    elif args.mode == "import-chunks":
        require(args.chunks_dir is not None, "CHUNKS_DIRECTORY_REQUIRED")
        require(args.chunks_manifest is not None, "CHUNKS_MANIFEST_REQUIRED")
        import_chunked_images(
            manifest,
            args.chunks_manifest,
            args.chunks_dir,
            args.archive,
            args.manifest_sha256,
        )
    elif args.mode == "diagnose-import":
        require(args.chunks_manifest is not None, "CHUNKS_MANIFEST_REQUIRED")
        diagnose_import(manifest, args.chunks_manifest, args.archive, args.manifest_sha256)
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
