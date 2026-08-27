#!/usr/bin/env python3
"""Fail-closed contract and independent-review gate for WP-31 Canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/wp31_greenfield_canary.json"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
DIGEST_IMAGE = re.compile(r"ghcr\.io/muchenai2024-creator/[a-z0-9-]+@sha256:[0-9a-f]{64}")


class CanaryContractError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load() -> dict[str, object]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise CanaryContractError("schema version differs")
    if value.get("environment") != "PRODUCTION_CANARY_UAT":
        raise CanaryContractError("environment differs")
    candidate = value.get("application_candidate_sha")
    if candidate != "1bccbbf1706a8216892f5b9b512b1e27ce784101":
        raise CanaryContractError("candidate differs")
    if value.get("migration_head") != "0027_next_stage_review":
        raise CanaryContractError("migration differs")
    if value.get("source_database") == value.get("isolated_canary_database"):
        raise CanaryContractError("canary database is not isolated")
    scope = value.get("scope")
    if not isinstance(scope, dict) or scope != {
        "max_allowlisted_learners": 8,
        "fixture_identity": False,
        "worker_started": False,
        "legacy_migration_authorized": False,
        "release_go": False,
    }:
        raise CanaryContractError("scope differs")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != {"api", "web", "worker_evidence_only"}:
        raise CanaryContractError("image set differs")
    if any(not isinstance(item, str) or not DIGEST_IMAGE.fullmatch(item) for item in images.values()):
        raise CanaryContractError("image is not digest-pinned")
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    required = (
        "greenfield-package",
        "greenfield-preflight",
        "greenfield-backup-restore",
        "greenfield-deploy",
        "greenfield-inspect",
        "greenfield-rollback",
        "PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW",
    )
    if any(item not in workflow for item in required):
        raise CanaryContractError("workflow is not connected to every reviewed phase")
    return value


def review_check(provided_sha256: str) -> dict[str, object]:
    value = load()
    review = value.get("pro_review")
    if not isinstance(review, dict) or review.get("status") != "PASS":
        raise CanaryContractError("independent Pro review is not PASS")
    evidence_path = review.get("evidence_path")
    expected_hash = review.get("evidence_sha256")
    if not isinstance(evidence_path, str) or not isinstance(expected_hash, str):
        raise CanaryContractError("Pro review evidence binding is incomplete")
    if provided_sha256 != expected_hash or not re.fullmatch(r"[0-9a-f]{64}", provided_sha256):
        raise CanaryContractError("provided Pro evidence hash differs")
    path = (ROOT / evidence_path).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or path.is_symlink():
        raise CanaryContractError("Pro review evidence path is invalid")
    if sha256(path) != expected_hash:
        raise CanaryContractError("Pro review evidence bytes drifted")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if evidence.get("review_status") != "PASS":
        raise CanaryContractError("Pro evidence status differs")
    reviewed_ops = review.get("reviewed_ops_commit_sha")
    if not isinstance(reviewed_ops, str) or not FULL_SHA.fullmatch(reviewed_ops):
        raise CanaryContractError("reviewed operations SHA is invalid")
    expected = {
        "application_candidate_sha": value["application_candidate_sha"],
        "reviewed_ops_commit_sha": reviewed_ops,
        "package_manifest_sha256": value["package_manifest_sha256"],
    }
    if any(evidence.get(key) != item for key, item in expected.items()):
        raise CanaryContractError("Pro evidence binding differs")
    if not evidence.get("reviewer") or not evidence.get("reviewed_at_utc"):
        raise CanaryContractError("Pro reviewer identity or time is missing")
    return {"status": "PASS", **expected, "pro_review_evidence_sha256": expected_hash}


def package_check(path: Path) -> dict[str, object]:
    value = load()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if sha256(path) != value["package_manifest_sha256"]:
        raise CanaryContractError("package manifest hash differs")
    if manifest.get("candidate", {}).get("commit_sha") != value["application_candidate_sha"]:
        raise CanaryContractError("package candidate differs")
    if manifest.get("migration", {}).get("head") != value["migration_head"]:
        raise CanaryContractError("package migration differs")
    for service in ("api", "web", "worker"):
        key = service if service != "worker" else "worker_evidence_only"
        expected = str(value["images"][key]).split("@", 1)[1]
        if manifest.get("images", {}).get(service, {}).get("registry_digest") != expected:
            raise CanaryContractError(f"package {service} digest differs")
    return {"status": "PASS", "package_manifest_sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract-check")
    review = commands.add_parser("review-check")
    review.add_argument("--evidence-sha256", required=True)
    package = commands.add_parser("package-check")
    package.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "contract-check":
            result = {"status": "PASS", "pro_review_status": load()["pro_review"]["status"]}
        elif args.command == "review-check":
            result = review_check(args.evidence_sha256)
        else:
            result = package_check(args.manifest)
    except (CanaryContractError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"WP31_GREENFIELD_CANARY=FAIL reason={error}")
        return 2
    print("WP31_GREENFIELD_CANARY=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
