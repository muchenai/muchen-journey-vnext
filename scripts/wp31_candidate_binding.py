#!/usr/bin/env python3
"""Build and validate the non-sensitive candidate binding artifact."""

from __future__ import annotations

import hashlib
import argparse
import json
import re
from pathlib import Path


class BindingError(ValueError):
    pass


_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]{5,19}$")
_SERVICES = ("api", "web", "worker")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_binding(manifest: Path, package_run_id: str) -> dict[str, object]:
    if not _RUN_ID.fullmatch(package_run_id):
        raise BindingError("package workflow run ID is invalid")
    if manifest.is_symlink() or not manifest.is_file():
        raise BindingError("release manifest must be a regular file")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BindingError("release manifest is not valid JSON") from error
    if not isinstance(value, dict):
        raise BindingError("release manifest must be an object")
    candidate = value.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("source_tree_clean"):
        raise BindingError("candidate source tree is not clean")
    candidate_sha = candidate.get("commit_sha")
    if not isinstance(candidate_sha, str) or not _SHA.fullmatch(candidate_sha):
        raise BindingError("candidate SHA is invalid")
    external = value.get("external_status")
    if not isinstance(external, dict) or external.get("registry_push") != "VERIFIED":
        raise BindingError("registry push is not verified")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != set(_SERVICES):
        raise BindingError("release manifest image set differs")

    def artifact_path(reference: object, label: str) -> Path:
        if not isinstance(reference, str) or Path(reference).name != f"{label}.spdx.json":
            raise BindingError(f"{label} SBOM path is invalid")
        direct = manifest.parent / reference
        sibling = manifest.parent / Path(reference).name
        if direct.is_file() and not direct.is_symlink():
            return direct
        if sibling.is_file() and not sibling.is_symlink():
            return sibling
        raise BindingError(f"{label} SBOM file is missing")

    bound_images: dict[str, dict[str, str]] = {}
    for service in _SERVICES:
        item = images[service]
        if not isinstance(item, dict):
            raise BindingError(f"{service} image entry is invalid")
        expected_reference = f"ghcr.io/muchenai/muchen-journey-vnext-{service}:{candidate_sha}"
        if item.get("registry_reference") != expected_reference:
            raise BindingError(f"{service} registry reference is invalid")
        registry_digest = item.get("registry_digest")
        if not isinstance(registry_digest, str) or not _SHA256.fullmatch(registry_digest):
            raise BindingError(f"{service} registry digest is invalid")
        sbom = item.get("sbom")
        if not isinstance(sbom, dict):
            raise BindingError(f"{service} SBOM entry is invalid")
        sbom_path = artifact_path(sbom.get("path"), service)
        declared_sha = sbom.get("sha256")
        actual_sha = sha256(sbom_path)
        if declared_sha != actual_sha:
            raise BindingError(f"{service} SBOM SHA-256 differs")
        bound_images[service] = {
            "registry_reference": expected_reference,
            "registry_digest": registry_digest,
            "sbom_path": f"artifacts/wp07-candidate/{service}.spdx.json",
            "sbom_sha256": actual_sha,
        }

    build_definition = manifest.parent / "amd64-build-definition-manifest.json"
    if build_definition.is_symlink() or not build_definition.is_file():
        raise BindingError("amd64 build definition manifest is missing")
    return {
        "schema_version": 1,
        "application_candidate_sha": candidate_sha,
        "package_workflow_run_id": package_run_id,
        "release_manifest_sha256": sha256(manifest),
        "images": bound_images,
        "build_definition_manifest_sha256": sha256(build_definition),
    }


def serialize(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def verify_binding(path: Path, *, require_supply_chain: bool = False) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise BindingError("candidate binding must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BindingError("candidate binding is not valid JSON") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise BindingError("candidate binding schema differs")
    if not isinstance(value.get("application_candidate_sha"), str) or not _SHA.fullmatch(
        value["application_candidate_sha"]
    ):
        raise BindingError("candidate binding SHA is invalid")
    if not isinstance(value.get("package_workflow_run_id"), str) or not _RUN_ID.fullmatch(
        value["package_workflow_run_id"]
    ):
        raise BindingError("candidate binding run ID is invalid")
    if not isinstance(value.get("release_manifest_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["release_manifest_sha256"]
    ):
        raise BindingError("candidate binding manifest SHA is invalid")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != set(_SERVICES):
        raise BindingError("candidate binding image set differs")
    for service in _SERVICES:
        item = images[service]
        if not isinstance(item, dict) or not _SHA256.fullmatch(str(item.get("registry_digest", ""))):
            raise BindingError(f"{service} candidate binding digest is invalid")
        if require_supply_chain and not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sbom_sha256", ""))):
            raise BindingError(f"{service} candidate binding SBOM SHA is invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", type=Path, required=True)
    generate.add_argument("--package-run-id", required=True)
    generate.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--binding", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            value = build_binding(args.manifest, args.package_run_id)
            args.output.write_bytes(serialize(value))
        else:
            verify_binding(args.binding, require_supply_chain=True)
        print("WP31_CANDIDATE_BINDING=PASS")
        return 0
    except (BindingError, OSError, ValueError, TypeError) as error:
        print(f"WP31_CANDIDATE_BINDING=FAIL reason={error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
