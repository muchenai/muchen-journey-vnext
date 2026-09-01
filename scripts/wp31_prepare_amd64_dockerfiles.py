#!/usr/bin/env python3
"""Verify reviewed architecture-aware Dockerfiles for the frozen amd64 build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


CANDIDATE = "c72fea573bf6ee1f85b4ca5cef9b80f729ee2c5f"
FILES = {
    "api": ("apps/api/Dockerfile", "275b3a0fb72a5739583e4300595032b99efd37119351874a3baa1ed75d2e246f"),
    "worker": ("apps/worker/Dockerfile", "73c527d7c7dd901483a7bf17519ffe094cad4a6cf648caf00d3c7e55de702eb9"),
    "web": ("apps/web/Dockerfile", "6b14531b8573f06ba240e82353297104519e8a3a579264fbe6a6f6d270519a60"),
}


class Amd64DockerfileError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def transform(source: bytes) -> bytes:
    text = source.decode("utf-8")
    required = (
        "ARG TARGETARCH",
        "amd64) alpine_arch=x86_64;",
        "arm64) alpine_arch=aarch64;",
        'Unsupported TARGETARCH: ${TARGETARCH}',
    )
    if any(text.count(marker) != 1 for marker in required):
        raise Amd64DockerfileError("frozen Dockerfile architecture contract drifted")
    return source


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise Amd64DockerfileError("frozen candidate Git verification failed")
    return result.stdout.strip()


def prepare(candidate_root: Path, output: Path) -> dict[str, object]:
    candidate_root = candidate_root.resolve()
    output = output.resolve()
    if git(candidate_root, "rev-parse", "--verify", "HEAD") != CANDIDATE:
        raise Amd64DockerfileError("application candidate SHA does not match")
    if git(candidate_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise Amd64DockerfileError("application candidate must be clean")
    if output.exists() or output.is_symlink():
        raise Amd64DockerfileError("output must not already exist")
    output.mkdir(mode=0o700, parents=True)

    files: dict[str, dict[str, str]] = {}
    try:
        for service, (relative, expected_source_hash) in FILES.items():
            source = (candidate_root / relative).read_bytes()
            source_hash = sha256_bytes(source)
            if source_hash != expected_source_hash:
                raise Amd64DockerfileError(f"frozen {service} Dockerfile hash drifted")
            derived = transform(source)
            target = output / f"Dockerfile.{service}.amd64"
            with target.open("xb") as handle:
                handle.write(derived)
            os.chmod(target, 0o600)
            files[service] = {
                "source_path": relative,
                "source_sha256": source_hash,
                "derived_path": target.name,
                "derived_sha256": sha256_bytes(derived),
            }
        manifest = {
            "schema_version": 1,
            "application_candidate_sha": CANDIDATE,
            "target_platform": "linux/amd64",
            "semantic_change": False,
            "files": files,
        }
        manifest_path = output / "build-definition-manifest.json"
        with manifest_path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(manifest_path, 0o600)
        return manifest
    except Exception:
        for path in output.iterdir():
            path.unlink()
        output.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.candidate_root, args.output)
    except (Amd64DockerfileError, OSError, UnicodeDecodeError) as error:
        print(f"WP31_AMD64_BUILD_DEFINITION=FAIL reason={error}")
        return 2
    print(
        "WP31_AMD64_BUILD_DEFINITION=PASS "
        f"candidate={result['application_candidate_sha']} target=linux/amd64 semantic_change=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
