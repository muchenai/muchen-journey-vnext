#!/usr/bin/env python3
"""Fail-closed GHCR namespace rebind evidence for one frozen candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/wp31_ghcr_org_rebind.json"
COMPONENTS = ("api", "web", "worker")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
EXPECTED_CANDIDATE = "1633ec4eabe381da3b56500c323005c0f363c0d9"
EXPECTED_SOURCE_MANIFEST = (
    "566f6a60baf6cb2e8e279503489b70036edb071fc891d0653f77abd04f2f7db5"
)
EXPECTED_CANDIDATE_TREE = "6066a35e39bd104cf4eb24e77c1edbe9d041c24d"


class RebindError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RebindError(f"required regular file is missing: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RebindError(f"JSON object expected: {path.name}")
    return value


def write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise RebindError(f"refusing to replace evidence: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def load_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    value = read_json(path)
    if value.get("schema_version") != 1:
        raise RebindError("contract schema differs")
    expected = {
        "operation": "GHCR_ORGANIZATION_NAMESPACE_REBIND_BY_FROZEN_CANDIDATE_REBUILD",
        "rebind_mode": "FROZEN_CANDIDATE_REBUILD",
        "application_candidate_sha": EXPECTED_CANDIDATE,
        "application_candidate_tree": EXPECTED_CANDIDATE_TREE,
        "source_artifact_run_id": "33141698913",
        "source_artifact_name": f"wp07-candidate-{EXPECTED_CANDIDATE}",
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST,
        "confirmation": "REBIND_1633EC4_GHCR_MUCHENAI",
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise RebindError("immutable contract value differs")
    images = value.get("images")
    if not isinstance(images, dict) or tuple(sorted(images)) != tuple(sorted(COMPONENTS)):
        raise RebindError("contract image set differs")
    for component in COMPONENTS:
        item = images[component]
        if not isinstance(item, dict):
            raise RebindError(f"invalid image contract: {component}")
        source = item.get("source_repository")
        target = item.get("target_repository")
        digest = item.get("source_digest")
        expected_source = (
            f"ghcr.io/muchenai2024-creator/muchen-journey-vnext-{component}"
        )
        expected_target = f"ghcr.io/muchenai/muchen-journey-vnext-{component}"
        if source != expected_source or target != expected_target:
            raise RebindError(f"registry namespace binding differs: {component}")
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise RebindError(f"source digest is invalid: {component}")
    if value.get("scope") != {
        "worker_start_authorized": False,
        "deployment_authorized": False,
        "production_database_write_authorized": False,
        "dns_edge_cloud_mutation_authorized": False,
        "release_go": False,
    }:
        raise RebindError("operation scope differs")
    tools = value.get("tools")
    if not isinstance(tools, dict) or any(
        not isinstance(tools.get(name), str) or "@sha256:" not in tools[name]
        for name in ("syft_image", "trivy_image")
    ):
        raise RebindError("tool images are not digest pinned")
    policy = value.get("cve_policy")
    if policy != {
        "severities": ["HIGH", "CRITICAL"],
        "maximum_high": 0,
        "maximum_critical": 0,
        "ignore_unfixed": False,
    }:
        raise RebindError("CVE policy differs")
    return value


def target_reference(contract: dict[str, Any], component: str) -> str:
    return f"{contract['images'][component]['target_repository']}:{EXPECTED_CANDIDATE}"


def check_source_manifest(contract: dict[str, Any], path: Path) -> dict[str, Any]:
    if sha256(path) != contract["source_manifest_sha256"]:
        raise RebindError("source release manifest hash differs")
    value = read_json(path)
    if value.get("candidate", {}).get("commit_sha") != EXPECTED_CANDIDATE:
        raise RebindError("source manifest candidate differs")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != set(COMPONENTS):
        raise RebindError("source manifest image set differs")
    for component in COMPONENTS:
        expected = contract["images"][component]
        actual = images[component]
        if not isinstance(actual, dict):
            raise RebindError(f"source manifest image is invalid: {component}")
        expected_tag = f"{expected['source_repository']}:{EXPECTED_CANDIDATE}"
        if actual.get("registry_reference") != expected_tag:
            raise RebindError(f"source registry reference differs: {component}")
        if actual.get("registry_digest") != expected["source_digest"]:
            raise RebindError(f"source registry digest differs: {component}")
        if actual.get("revision_label") != EXPECTED_CANDIDATE:
            raise RebindError(f"source revision label differs: {component}")
    return value


def run_bytes(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, capture_output=True, check=check)


def remote_digest(reference: str) -> str:
    result = run_bytes(["docker", "buildx", "imagetools", "inspect", "--raw", reference])
    raw = result.stdout
    value = json.loads(raw)
    if value.get("schemaVersion") != 2:
        raise RebindError("remote registry returned an invalid manifest")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    immutable = reference.rsplit(":", 1)[0] + "@" + digest
    immutable_raw = run_bytes(
        ["docker", "buildx", "imagetools", "inspect", "--raw", immutable]
    ).stdout
    if "sha256:" + hashlib.sha256(immutable_raw).hexdigest() != digest:
        raise RebindError("immutable registry digest verification failed")
    return digest


def targets_absent(contract: dict[str, Any]) -> dict[str, Any]:
    for component in COMPONENTS:
        target = target_reference(contract, component)
        result = run_bytes(
            ["docker", "buildx", "imagetools", "inspect", target], check=False
        )
        if result.returncode == 0:
            raise RebindError(f"target commit tag already exists: {component}")
        failure = (result.stdout + result.stderr).decode("utf-8", errors="replace").lower()
        if not any(
            marker in failure
            for marker in ("not found", "manifest unknown", "name unknown")
        ):
            raise RebindError(f"cannot prove target tag absence: {component}")
    return {"status": "PASS", "target_tags": "ABSENT"}


def inspect_targets(contract: dict[str, Any], output: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "candidate_sha": EXPECTED_CANDIDATE,
        "images": {},
    }
    for component in COMPONENTS:
        expected = contract["images"][component]
        target = target_reference(contract, component)
        digest = remote_digest(target)
        inspected = json.loads(
            run_bytes(["docker", "image", "inspect", target]).stdout
        )[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        revision = labels.get("org.opencontainers.image.revision")
        if revision != EXPECTED_CANDIDATE:
            raise RebindError(f"target revision label differs: {component}")
        if not DIGEST.fullmatch(digest):
            raise RebindError(f"target digest is invalid: {component}")
        result["images"][component] = {
            "prior_immutable_reference": (
                f"{expected['source_repository']}@{expected['source_digest']}"
            ),
            "prior_digest": expected["source_digest"],
            "target_reference": target,
            "target_digest": digest,
            "digest_equal_to_prior": digest == expected["source_digest"],
            "revision_label": revision,
            "local_image_id": inspected.get("Id"),
        }
    write_json_exclusive(output, result)
    return result


def cve_counts(value: dict[str, Any]) -> tuple[int, int]:
    high = critical = 0
    results = value.get("Results") or []
    if not isinstance(results, list):
        raise RebindError("Trivy results are invalid")
    for result in results:
        if not isinstance(result, dict):
            raise RebindError("Trivy result entry is invalid")
        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            raise RebindError("Trivy vulnerabilities are invalid")
        for vulnerability in vulnerabilities:
            severity = vulnerability.get("Severity") if isinstance(vulnerability, dict) else None
            high += severity == "HIGH"
            critical += severity == "CRITICAL"
    return high, critical


def build_manifest(
    contract: dict[str, Any],
    source_manifest_path: Path,
    target_facts_path: Path,
    evidence_dir: Path,
    output: Path,
) -> dict[str, Any]:
    source = check_source_manifest(contract, source_manifest_path)
    facts = read_json(target_facts_path)
    if facts.get("candidate_sha") != EXPECTED_CANDIDATE:
        raise RebindError("target facts candidate differs")
    fact_images = facts.get("images")
    if not isinstance(fact_images, dict) or set(fact_images) != set(COMPONENTS):
        raise RebindError("target facts image set differs")
    images: dict[str, Any] = {}
    for component in COMPONENTS:
        expected = contract["images"][component]
        fact = fact_images[component]
        if not isinstance(fact, dict):
            raise RebindError(f"target facts are invalid: {component}")
        if (
            fact.get("prior_digest") != expected["source_digest"]
            or fact.get("target_reference") != target_reference(contract, component)
            or not isinstance(fact.get("target_digest"), str)
            or not DIGEST.fullmatch(fact["target_digest"])
            or fact.get("digest_equal_to_prior")
            != (fact["target_digest"] == expected["source_digest"])
            or fact.get("revision_label") != EXPECTED_CANDIDATE
        ):
            raise RebindError(f"target fact binding differs: {component}")
        sbom_path = evidence_dir / f"{component}.spdx.json"
        trivy_path = evidence_dir / f"{component}.trivy.json"
        sbom = read_json(sbom_path)
        trivy = read_json(trivy_path)
        if not str(sbom.get("spdxVersion", "")).startswith("SPDX-"):
            raise RebindError(f"SBOM is not SPDX JSON: {component}")
        high, critical = cve_counts(trivy)
        cve_pass = (
            high <= contract["cve_policy"]["maximum_high"]
            and critical <= contract["cve_policy"]["maximum_critical"]
        )
        images[component] = {
            **fact,
            "sbom": {
                "format": "SPDX-JSON",
                "path": sbom_path.name,
                "sha256": sha256(sbom_path),
            },
            "cve": {
                "scanner": "Trivy",
                "path": trivy_path.name,
                "sha256": sha256(trivy_path),
                "high": high,
                "critical": critical,
                "status": "PASS" if cve_pass else "FAIL",
            },
        }
    db_path = evidence_dir / "trivy-db-metadata.json"
    read_json(db_path)
    value = {
        "schema_version": 1,
        "operation": contract["operation"],
        "status": "EVIDENCE_COMPLETE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "application_candidate_sha": EXPECTED_CANDIDATE,
        "application_candidate_tree": contract["application_candidate_tree"],
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "ops_commit_sha": os.environ.get("GITHUB_SHA"),
            "ops_ref": os.environ.get("GITHUB_REF"),
        },
        "source_release_manifest": {
            "path": source_manifest_path.name,
            "sha256": sha256(source_manifest_path),
            "artifact_run_id": contract["source_artifact_run_id"],
        },
        "images": images,
        "tools": contract["tools"],
        "cve_policy": contract["cve_policy"],
        "cve_gate": {
            "status": (
                "PASS"
                if all(item["cve"]["status"] == "PASS" for item in images.values())
                else "FAIL"
            ),
            "required_before_production_release": True,
        },
        "trivy_database": {
            "path": db_path.name,
            "sha256": sha256(db_path),
        },
        "production_effects": {
            "deployment": False,
            "production_database_write": False,
            "dns_edge_cloud_mutation": False,
            "worker_start": False,
            "historical_migration": False,
            "release": False,
        },
    }
    write_json_exclusive(output, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source-check")
    source.add_argument("--manifest", type=Path, required=True)
    commands.add_parser("targets-absent")
    inspect = commands.add_parser("inspect-targets")
    inspect.add_argument("--output", type=Path, required=True)
    manifest = commands.add_parser("build-manifest")
    manifest.add_argument("--source-manifest", type=Path, required=True)
    manifest.add_argument("--target-facts", type=Path, required=True)
    manifest.add_argument("--evidence-dir", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    commands.add_parser("contract-check")
    args = parser.parse_args()
    try:
        contract = load_contract(args.contract)
        if args.command == "contract-check":
            result = {"status": "PASS", "operation": contract["operation"]}
        elif args.command == "source-check":
            check_source_manifest(contract, args.manifest)
            result = {"status": "PASS", "source_manifest_sha256": sha256(args.manifest)}
        elif args.command == "targets-absent":
            result = targets_absent(contract)
        elif args.command == "inspect-targets":
            result = inspect_targets(contract, args.output)
        else:
            result = build_manifest(
                contract,
                args.source_manifest,
                args.target_facts,
                args.evidence_dir,
                args.output,
            )
    except (
        RebindError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"WP31_GHCR_ORG_REBIND=FAIL reason={error}")
        return 2
    print("WP31_GHCR_ORG_REBIND=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
