#!/usr/bin/env python3
"""Derive reviewed amd64 Dockerfiles without changing the frozen app tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


CANDIDATE = "1bccbbf1706a8216892f5b9b512b1e27ce784101"
FILES = {
    "api": ("apps/api/Dockerfile", "81e2747a7bfb8f43a6cff73e876932aedfe6f8e521edd6700d22929f8da172bb"),
    "worker": ("apps/worker/Dockerfile", "3ca9e68781e13400d8a8e2a53c4fe61eada70ae3085faf0dcf8494495e41ae96"),
    "web": ("apps/web/Dockerfile", "e017758fd5f77d91cfdbead45a817566d1dde4cd1d2e73ebabf2194eadebe5e6"),
}
REPLACEMENTS = {
    "sha256:35b892813c23664a3592e4fc8c12a03538a22c579057655361c7043305272a9a":
        "sha256:161223a16f042b8e469e9441291e071464fd91d4f4bbe6f496ee8d0abd4e0701",
    "sha256:d6ec970cc10e01539e41626f720c4e0ac69016eaa2079a10ef776ffd3243db5b":
        "sha256:aca521e5ae4a321322a9d47ed64a1775f5ab1ffd215d1e9fc0433c58f7bfd037",
    "sha256:0d12f4f145ec045dd19e8465bd3cb07b08197f96a3776641511dc2bec53cc0b7":
        "sha256:e18c561e6a8fb744b42fe000f4a8cdfcc38e7956e62a6ab44b0a0580db948450",
    "/main/aarch64/": "/main/x86_64/",
}


class Amd64DockerfileError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def transform(source: bytes) -> bytes:
    text = source.decode("utf-8")
    for old, new in REPLACEMENTS.items():
        expected = 3 if old == "/main/aarch64/" else 1
        if text.count(old) != expected:
            raise Amd64DockerfileError(f"frozen Dockerfile replacement count drifted: {old}")
        text = text.replace(old, new)
    if "aarch64" in text:
        raise Amd64DockerfileError("derived Dockerfile still contains aarch64")
    return text.encode("utf-8")


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
