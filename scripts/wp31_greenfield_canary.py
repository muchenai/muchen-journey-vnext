#!/usr/bin/env python3
"""Fail-closed contract, immutable ops-tree, and independent-review gate for WP-31."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

try:
    from scripts.wp31_candidate_binding import BindingError, verify_binding
except ModuleNotFoundError:  # direct invocation from the scripts directory
    from wp31_candidate_binding import BindingError, verify_binding


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/wp31_greenfield_canary.json"
OPS_MANIFEST = ROOT / "config/wp31_greenfield_canary_ops_manifest.json"
BINDING = ROOT / "config/wp31_candidate_binding.json"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
DIGEST_IMAGE = re.compile(r"ghcr\.io/muchenai/[a-z0-9-]+@sha256:[0-9a-f]{64}")


class CanaryContractError(RuntimeError):
    pass


def _runtime_binding() -> dict[str, object]:
    try:
        return verify_binding(BINDING)
    except BindingError as error:
        raise CanaryContractError("candidate binding is invalid") from error


EXPECTED_CANDIDATE = str(_runtime_binding()["application_candidate_sha"])
EXPECTED_ROLLBACK = "ff53052847a268d025bceb93c3eab37986d50219"


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
    if value.get("schema_version") != 3:
        raise CanaryContractError("schema version differs")
    binding = _runtime_binding()
    expected_scalars = {
        "environment": "PRODUCTION_CANARY_UAT",
        "application_candidate_sha": binding["application_candidate_sha"],
        "package_workflow_run_id": binding["package_workflow_run_id"],
        "package_manifest_sha256": binding["release_manifest_sha256"],
        "migration_head": "0028_canary_main_merge",
        "production_host": "journey.muchenai.com",
        "source_database": "journey_next_cutover_20260810",
        "isolated_canary_database": "journey_next_canary_20260901_c72fea5",
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
    binding_images = binding["images"]
    assert isinstance(binding_images, dict)
    expected_images = {
        "api": f"ghcr.io/muchenai/muchen-journey-vnext-api@{binding_images['api']['registry_digest']}",
        "web": f"ghcr.io/muchenai/muchen-journey-vnext-web@{binding_images['web']['registry_digest']}",
        "worker_evidence_only": f"ghcr.io/muchenai/muchen-journey-vnext-worker@{binding_images['worker']['registry_digest']}",
    }
    if images != expected_images:
        raise CanaryContractError("contract images differ from candidate binding")
    rollback = value.get("rollback")
    if not isinstance(rollback, dict) or rollback.get("candidate_sha") != EXPECTED_ROLLBACK:
        raise CanaryContractError("rollback candidate differs")
    if rollback.get("database") != value["source_database"]:
        raise CanaryContractError("rollback database differs")
    if value.get("authorization_model") != (
        "EXTERNAL_PRO_EVIDENCE_PLUS_PROTECTED_OWNER_EXECUTION_EVIDENCE"
    ):
        raise CanaryContractError("authorization model differs")
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    required = (
        "greenfield-package",
        "greenfield-preflight",
        "greenfield-backup-restore",
        "greenfield-deploy",
        "greenfield-inspect",
        "greenfield-rollback",
        "preflight_run_id",
        "deploy_run_id",
        "pro_review_evidence_b64",
        "execution_authorization_sha256",
        "greenfield_authorize",
        "greenfield_execution_authorize",
        "WP31_EXECUTION_AUTHORIZATION_B64",
    )
    if any(item not in workflow for item in required):
        raise CanaryContractError("workflow is not connected to every reviewed phase")
    return value


def load_ops_manifest() -> dict[str, object]:
    value = _json_file(OPS_MANIFEST)
    if value.get("schema_version") != 2:
        raise CanaryContractError("ops manifest schema differs")
    if value.get("application_candidate_sha") != EXPECTED_CANDIDATE:
        raise CanaryContractError("ops manifest candidate differs")
    if value.get("closure_model") != "REPOSITORY_GREENFIELD_TRANSITIVE_V2":
        raise CanaryContractError("ops manifest closure model differs")
    if value.get("candidate_bound_references") != ["scripts/wp07_candidate.py"]:
        raise CanaryContractError("application candidate boundary differs")
    if value.get("manifest_self_binding") != (
        "PRO_EVIDENCE_SHA256_PLUS_EXACT_REVIEWED_COMMIT"
    ):
        raise CanaryContractError("ops manifest self-binding differs")
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
    if head != reviewed_ops:
        raise CanaryContractError("executing HEAD is not the exact reviewed operations commit")
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


def review_check(
    evidence_path: Path, provided_sha256: str, executing_ref: str
) -> dict[str, object]:
    value = load()
    manifest = load_ops_manifest()
    manifest_hash = sha256(OPS_MANIFEST)
    if not SHA256.fullmatch(provided_sha256) or sha256(evidence_path) != provided_sha256:
        raise CanaryContractError("provided Pro evidence hash differs")
    evidence = _json_file(evidence_path)
    review_fields = {
        "application_candidate_sha",
        "evidence_scope",
        "ops_manifest_sha256",
        "package_manifest_sha256",
        "production_mutation",
        "review_status",
        "reviewed_at_utc",
        "reviewed_ops_commit_sha",
        "reviewed_ops_ref",
        "reviewer",
        "reviewer_independent",
    }
    if set(evidence) != review_fields:
        raise CanaryContractError("Pro evidence fields differ")
    if evidence.get("review_status") != "PASS":
        raise CanaryContractError("independent Pro review is not PASS")
    reviewed_ops = evidence.get("reviewed_ops_commit_sha")
    reviewed_ref = evidence.get("reviewed_ops_ref")
    expected = {
        "application_candidate_sha": value["application_candidate_sha"],
        "package_manifest_sha256": value["package_manifest_sha256"],
        "ops_manifest_sha256": manifest_hash,
    }
    if any(evidence.get(key) != item for key, item in expected.items()):
        raise CanaryContractError("Pro evidence binding differs")
    if not isinstance(reviewed_ops, str):
        raise CanaryContractError("reviewed operations SHA is missing")
    expected_ref = f"refs/tags/muchen-journey-greenfield-ops-{reviewed_ops}"
    if reviewed_ref != expected_ref or executing_ref != expected_ref:
        raise CanaryContractError("executing ref is not the exact reviewed immutable tag")
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
        "reviewed_ops_ref": reviewed_ref,
        "pro_review_evidence_sha256": provided_sha256,
    }


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CanaryContractError(f"{field} is not UTC")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise CanaryContractError(f"{field} is invalid") from error
    if result.tzinfo != timezone.utc:
        raise CanaryContractError(f"{field} is not UTC")
    return result


def authorization_check(
    evidence_path: Path,
    provided_sha256: str,
    pro_review_evidence_sha256: str,
    phase: str,
    executing_ref: str,
    reviewed_ops_commit_sha: str,
) -> dict[str, object]:
    value = load()
    manifest_hash = sha256(OPS_MANIFEST)
    if not SHA256.fullmatch(provided_sha256) or sha256(evidence_path) != provided_sha256:
        raise CanaryContractError("provided Owner authorization evidence hash differs")
    if not SHA256.fullmatch(pro_review_evidence_sha256):
        raise CanaryContractError("Pro review evidence hash is invalid")
    evidence = _json_file(evidence_path)
    authorization_fields = {
        "application_candidate_sha",
        "authorization_id",
        "authorization_status",
        "authorized_at_utc",
        "authorized_by",
        "authority",
        "environment",
        "max_allowlisted_learners",
        "not_after_utc",
        "ops_manifest_sha256",
        "phase",
        "pro_review_evidence_sha256",
        "production_job_execution_authorized",
        "release_go",
        "reviewed_ops_commit_sha",
        "reviewed_ops_ref",
        "worker_start_authorized",
    }
    if set(evidence) != authorization_fields:
        raise CanaryContractError("Owner execution authorization fields differ")
    expected = {
        "authorization_status": "GRANTED",
        "authorized_by": "刘默文",
        "authority": "PRODUCT_OWNER_AND_RELEASE_OPS_OWNER",
        "environment": "PRODUCTION_CANARY_UAT",
        "application_candidate_sha": value["application_candidate_sha"],
        "reviewed_ops_commit_sha": reviewed_ops_commit_sha,
        "reviewed_ops_ref": executing_ref,
        "ops_manifest_sha256": manifest_hash,
        "pro_review_evidence_sha256": pro_review_evidence_sha256,
        "phase": phase,
        "max_allowlisted_learners": 8,
        "production_job_execution_authorized": True,
        "worker_start_authorized": False,
        "release_go": False,
    }
    if any(evidence.get(key) != item for key, item in expected.items()):
        raise CanaryContractError("Owner execution authorization binding differs")
    if _git("rev-parse", "HEAD").stdout.decode().strip() != reviewed_ops_commit_sha:
        raise CanaryContractError("Owner authorization is not executing at the reviewed commit")
    if executing_ref != f"refs/tags/muchen-journey-greenfield-ops-{reviewed_ops_commit_sha}":
        raise CanaryContractError("Owner authorization ref differs")
    try:
        authorization_id = UUID(str(evidence.get("authorization_id")))
    except (ValueError, TypeError) as error:
        raise CanaryContractError("Owner authorization ID is invalid") from error
    if authorization_id.version != 4:
        raise CanaryContractError("Owner authorization ID is not UUIDv4")
    authorized_at = _utc(evidence.get("authorized_at_utc"), "authorized_at_utc")
    not_after = _utc(evidence.get("not_after_utc"), "not_after_utc")
    now = datetime.now(timezone.utc)
    if not authorized_at <= now < not_after:
        raise CanaryContractError("Owner execution authorization is not currently valid")
    if not_after - authorized_at > timedelta(hours=6):
        raise CanaryContractError("Owner execution authorization lifetime exceeds six hours")
    return {
        "status": "PASS",
        "authorization_id": str(authorization_id),
        "authorization_evidence_sha256": provided_sha256,
        **expected,
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
    review.add_argument("--executing-ref", required=True)
    authorization = commands.add_parser("authorization-check")
    authorization.add_argument("--evidence", type=Path, required=True)
    authorization.add_argument("--evidence-sha256", required=True)
    authorization.add_argument("--pro-review-evidence-sha256", required=True)
    authorization.add_argument("--phase", required=True)
    authorization.add_argument("--executing-ref", required=True)
    authorization.add_argument("--reviewed-ops-commit-sha", required=True)
    package = commands.add_parser("package-check")
    package.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "contract-check":
            value = load()
            load_ops_manifest()
            result = {"status": "PASS", "authorization_model": value["authorization_model"]}
        elif args.command == "review-check":
            result = review_check(args.evidence, args.evidence_sha256, args.executing_ref)
        elif args.command == "authorization-check":
            result = authorization_check(
                args.evidence,
                args.evidence_sha256,
                args.pro_review_evidence_sha256,
                args.phase,
                args.executing_ref,
                args.reviewed_ops_commit_sha,
            )
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
