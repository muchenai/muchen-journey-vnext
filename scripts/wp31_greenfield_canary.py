#!/usr/bin/env python3
"""Fail-closed contract, immutable ops-tree, and independent-review gate for WP-31."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/wp31_greenfield_canary.json"
OPS_MANIFEST = ROOT / "config/wp31_greenfield_canary_ops_manifest.json"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
DIGEST_IMAGE = re.compile(
    r"ghcr\.io/muchenai2024-creator/[a-z0-9-]+@sha256:[0-9a-f]{64}"
)
EXPECTED_CANDIDATE = "1bccbbf1706a8216892f5b9b512b1e27ce784101"
EXPECTED_ROLLBACK = "ff53052847a268d025bceb93c3eab37986d50219"


class CanaryContractError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise CanaryContractError(f"required regular file is missing: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanaryContractError(f"JSON object expected: {path.name}")
    return value


def load() -> dict[str, object]:
    value = _json_file(CONTRACT)
    if value.get("schema_version") != 2:
        raise CanaryContractError("schema version differs")
    expected_scalars = {
        "environment": "PRODUCTION_CANARY_UAT",
        "application_candidate_sha": EXPECTED_CANDIDATE,
        "package_workflow_run_id": "33062342289",
        "package_manifest_sha256": (
            "49f95c33131932e113cc8bcdf252ff647a4d21782ce353d1b2038ffc75960eb1"
        ),
        "migration_head": "0027_next_stage_review",
        "production_host": "journey.muchenai.com",
        "source_database": "journey_next_cutover_20260810",
        "isolated_canary_database": "journey_next_canary_20260827_1bccbbf",
    }
    if any(value.get(key) != expected for key, expected in expected_scalars.items()):
        raise CanaryContractError("immutable contract value differs")
    if value.get("source_database") == value.get("isolated_canary_database"):
        raise CanaryContractError("canary database is not isolated")
    scope = value.get("scope")
    if not isinstance(scope, dict) or scope != {
        "max_allowlisted_learners": 8,
        "fixture_identity": False,
        "worker_started": False,
        "legacy_migration_authorized": False,
        "production_job_execution_authorized": False,
        "release_go": False,
    }:
        raise CanaryContractError("scope differs")
    images = value.get("images")
    if not isinstance(images, dict) or set(images) != {"api", "web", "worker_evidence_only"}:
        raise CanaryContractError("image set differs")
    if any(not isinstance(item, str) or not DIGEST_IMAGE.fullmatch(item) for item in images.values()):
        raise CanaryContractError("image is not digest-pinned")
    rollback = value.get("rollback")
    if not isinstance(rollback, dict) or rollback.get("candidate_sha") != EXPECTED_ROLLBACK:
        raise CanaryContractError("rollback candidate differs")
    if rollback.get("database") != value["source_database"]:
        raise CanaryContractError("rollback database differs")
    if value.get("owner_canary_deployment_go") is not True:
        raise CanaryContractError("Owner Canary deployment GO is absent")
    if value.get("entrypoint_execution_granted") not in {True, False}:
        raise CanaryContractError("entrypoint execution authorization is malformed")
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    required = (
        "greenfield-package",
        "greenfield-preflight",
        "greenfield-backup-restore",
        "greenfield-deploy",
        "greenfield-inspect",
        "greenfield-rollback",
        "PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW",
        "preflight_run_id",
        "deploy_run_id",
        "WP31_PRO_REVIEW_EVIDENCE_B64",
    )
    if any(item not in workflow for item in required):
        raise CanaryContractError("workflow is not connected to every reviewed phase")
    return value


def load_ops_manifest() -> dict[str, object]:
    value = _json_file(OPS_MANIFEST)
    if value.get("schema_version") != 1:
        raise CanaryContractError("ops manifest schema differs")
    if value.get("application_candidate_sha") != EXPECTED_CANDIDATE:
        raise CanaryContractError("ops manifest candidate differs")
    files = value.get("files")
    if not isinstance(files, dict) or len(files) < 10:
        raise CanaryContractError("ops manifest file set is incomplete")
    for raw_path, expected in files.items():
        if not isinstance(raw_path, str) or not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise CanaryContractError("ops manifest entry is malformed")
        path = (ROOT / raw_path).resolve()
        if not path.is_relative_to(ROOT) or path.is_symlink() or not path.is_file():
            raise CanaryContractError(f"ops path is invalid: {raw_path}")
        if sha256(path) != expected:
            raise CanaryContractError(f"ops working-tree bytes drifted: {raw_path}")
    return value


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["/usr/bin/git", *args], cwd=ROOT, capture_output=True, check=check
    )


def verify_reviewed_tree(reviewed_ops: str, manifest: dict[str, object]) -> None:
    if not FULL_SHA.fullmatch(reviewed_ops):
        raise CanaryContractError("reviewed operations SHA is invalid")
    if _git("cat-file", "-e", f"{reviewed_ops}^{{commit}}", check=False).returncode:
        raise CanaryContractError("reviewed operations commit is unavailable")
    head = _git("rev-parse", "HEAD").stdout.decode().strip()
    if _git("merge-base", "--is-ancestor", reviewed_ops, head, check=False).returncode:
        raise CanaryContractError("reviewed operations commit is not an ancestor of HEAD")
    reviewed_manifest = _git(
        "show", f"{reviewed_ops}:config/wp31_greenfield_canary_ops_manifest.json", check=False
    )
    if reviewed_manifest.returncode or hashlib.sha256(reviewed_manifest.stdout).hexdigest() != sha256(
        OPS_MANIFEST
    ):
        raise CanaryContractError("reviewed ops manifest bytes differ")
    files = manifest["files"]
    assert isinstance(files, dict)
    for raw_path, expected in files.items():
        shown = _git("show", f"{reviewed_ops}:{raw_path}", check=False)
        if shown.returncode:
            raise CanaryContractError(f"reviewed ops file is absent: {raw_path}")
        if hashlib.sha256(shown.stdout).hexdigest() != expected:
            raise CanaryContractError(f"reviewed ops commit bytes differ: {raw_path}")


def review_check(evidence_path: Path, provided_sha256: str) -> dict[str, object]:
    value = load()
    if value.get("entrypoint_execution_granted") is not True:
        raise CanaryContractError("entrypoint execution is not granted")
    manifest = load_ops_manifest()
    manifest_hash = sha256(OPS_MANIFEST)
    if not SHA256.fullmatch(provided_sha256) or sha256(evidence_path) != provided_sha256:
        raise CanaryContractError("provided Pro evidence hash differs")
    evidence = _json_file(evidence_path)
    if evidence.get("review_status") != "PASS":
        raise CanaryContractError("independent Pro review is not PASS")
    reviewed_ops = evidence.get("reviewed_ops_commit_sha")
    expected = {
        "application_candidate_sha": value["application_candidate_sha"],
        "package_manifest_sha256": value["package_manifest_sha256"],
        "ops_manifest_sha256": manifest_hash,
    }
    if any(evidence.get(key) != item for key, item in expected.items()):
        raise CanaryContractError("Pro evidence binding differs")
    if not isinstance(reviewed_ops, str):
        raise CanaryContractError("reviewed operations SHA is missing")
    reviewer = evidence.get("reviewer")
    reviewed_at = evidence.get("reviewed_at_utc")
    if reviewer != "CODEX_PRO_REVIEW_MACBOOK_PRO" or not isinstance(reviewed_at, str):
        raise CanaryContractError("Pro reviewer identity or time is missing")
    if not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", reviewed_at):
        raise CanaryContractError("Pro review time is invalid")
    if evidence.get("evidence_scope") != "PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW":
        raise CanaryContractError("Pro evidence scope differs")
    if evidence.get("reviewer_independent") is not True or evidence.get("production_mutation") is not False:
        raise CanaryContractError("Pro evidence independence or production effect differs")
    verify_reviewed_tree(reviewed_ops, manifest)
    return {
        "status": "PASS",
        **expected,
        "reviewed_ops_commit_sha": reviewed_ops,
        "pro_review_evidence_sha256": provided_sha256,
    }


def package_check(path: Path) -> dict[str, object]:
    value = load()
    manifest = _json_file(path)
    if sha256(path) != value["package_manifest_sha256"]:
        raise CanaryContractError("package manifest hash differs")
    candidate = manifest.get("candidate")
    migration = manifest.get("migration")
    images = manifest.get("images")
    if not isinstance(candidate, dict) or candidate.get("commit_sha") != value["application_candidate_sha"]:
        raise CanaryContractError("package candidate differs")
    if not isinstance(migration, dict) or migration.get("head") != value["migration_head"]:
        raise CanaryContractError("package migration differs")
    if not isinstance(images, dict):
        raise CanaryContractError("package images are missing")
    for service in ("api", "web", "worker"):
        key = service if service != "worker" else "worker_evidence_only"
        expected = str(value["images"][key]).split("@", 1)[1]
        image = images.get(service)
        if not isinstance(image, dict) or image.get("registry_digest") != expected:
            raise CanaryContractError(f"package {service} digest differs")
    return {"status": "PASS", "package_manifest_sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract-check")
    review = commands.add_parser("review-check")
    review.add_argument("--evidence", type=Path, required=True)
    review.add_argument("--evidence-sha256", required=True)
    package = commands.add_parser("package-check")
    package.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "contract-check":
            value = load()
            load_ops_manifest()
            result = {
                "status": "PASS",
                "owner_canary_deployment_go": value["owner_canary_deployment_go"],
                "entrypoint_execution_granted": value["entrypoint_execution_granted"],
            }
        elif args.command == "review-check":
            result = review_check(args.evidence, args.evidence_sha256)
        else:
            result = package_check(args.manifest)
    except (
        CanaryContractError,
        OSError,
        KeyError,
        TypeError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        print(f"WP31_GREENFIELD_CANARY=FAIL reason={error}")
        return 2
    print("WP31_GREENFIELD_CANARY=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
