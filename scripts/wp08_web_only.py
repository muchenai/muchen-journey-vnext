#!/usr/bin/env python3
"""Fail-closed contract for a bounded WP-08 Web-only staging release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "wp08_web_only.json"
WP08_CONTRACT = ROOT / "config" / "wp08_staging.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class WebOnlyError(RuntimeError):
    pass


def _git(*args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode().strip()
        raise WebOnlyError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout


def _require_full_sha(value: object, label: str) -> str:
    candidate = str(value)
    if not FULL_SHA.fullmatch(candidate):
        raise WebOnlyError(f"{label} must be one full lowercase SHA")
    return candidate


def _require_digest(value: object, label: str) -> str:
    digest = str(value)
    if not DIGEST.fullmatch(digest):
        raise WebOnlyError(f"{label} must be one sha256 digest")
    return digest


def load_contract(path: Path = CONTRACT) -> dict[str, object]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise WebOnlyError(f"cannot read Web-only contract: {error}") from error
    required = {
        "schema_version",
        "target_environment",
        "region_id",
        "candidate_commit",
        "candidate_parent",
        "candidate_artifact_run_id",
        "web_image_digest",
        "runtime_baseline",
        "candidate_commit_allowed_paths",
        "baseline_compatibility_paths",
        "runtime_acceptance",
        "runtime_repair",
    }
    if set(data) != required:
        raise WebOnlyError("Web-only contract keys differ from the reviewed schema")
    if data["schema_version"] != 1:
        raise WebOnlyError("Web-only contract schema must be 1")
    if data["target_environment"] != "staging" or data["region_id"] != "cn-beijing":
        raise WebOnlyError("Web-only target must be cn-beijing staging")
    _require_full_sha(data["candidate_commit"], "candidate_commit")
    _require_full_sha(data["candidate_parent"], "candidate_parent")
    run_id = data["candidate_artifact_run_id"]
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise WebOnlyError("candidate_artifact_run_id must be a positive integer")
    _require_digest(data["web_image_digest"], "web_image_digest")

    baseline = data["runtime_baseline"]
    if not isinstance(baseline, dict) or set(baseline) != {
        "candidate_commit",
        "api_image_digest",
        "worker_image_digest",
        "migration_revision",
        "config_schema_version",
        "openapi_sha256",
    }:
        raise WebOnlyError("runtime_baseline keys differ from the reviewed schema")
    _require_full_sha(baseline["candidate_commit"], "runtime baseline candidate")
    _require_digest(baseline["api_image_digest"], "runtime baseline API digest")
    _require_digest(baseline["worker_image_digest"], "runtime baseline Worker digest")
    if baseline["migration_revision"] != "0014_wp12_data_lifecycle":
        raise WebOnlyError("runtime baseline migration must remain 0014")
    if baseline["config_schema_version"] != 3:
        raise WebOnlyError("runtime baseline config schema must remain 3")
    if not re.fullmatch(r"[0-9a-f]{64}", str(baseline["openapi_sha256"])):
        raise WebOnlyError("runtime baseline OpenAPI hash is invalid")

    allowed = data["candidate_commit_allowed_paths"]
    compatibility = data["baseline_compatibility_paths"]
    if not isinstance(allowed, list) or set(allowed) != {
        "Makefile",
        "apps/web/",
        "docs/13_REQUIREMENTS_TRACEABILITY_MATRIX.md",
        "docs/31_WP13_WP15_EXECUTION_GATE_KIT.md",
    }:
        raise WebOnlyError("candidate allowed paths differ from the reviewed set")
    if not isinstance(compatibility, list) or set(compatibility) != {
        "apps/api/",
        "apps/worker/",
        "contracts/openapi.json",
        "migrations/",
    }:
        raise WebOnlyError("baseline compatibility paths differ from the reviewed set")
    acceptance = data["runtime_acceptance"]
    if not isinstance(acceptance, dict) or acceptance != {
        "web_release": "candidate_commit",
        "api_release": "runtime_baseline.candidate_commit",
        "worker_release": "runtime_baseline.candidate_commit",
        "api_status": "READY",
        "database_status": "READY",
        "worker_stale": False,
        "root_http_status": 200,
        "anonymous_ops_http_status": 401,
        "anonymous_review_http_status": 401,
    }:
        raise WebOnlyError("runtime acceptance differs from the reviewed fail-closed set")
    repair = data["runtime_repair"]
    if not isinstance(repair, dict) or set(repair) != {
        "allowed_prestate",
        "allowed_mutations",
        "forbidden_mutations",
    }:
        raise WebOnlyError("runtime repair keys differ from the reviewed schema")
    if repair["allowed_prestate"] != {
        "web_release": "candidate_commit",
        "api_releases": [
            "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
            "runtime_baseline.candidate_commit",
        ],
        "worker_releases": [
            "172c9f62ffdcd4fce31fb4900fdca46b3405ab89",
            "runtime_baseline.candidate_commit",
        ],
        "migration_revisions": [
            "0013_wp11_notify_observability",
            "runtime_baseline.migration_revision",
        ],
        "config_schema_version": 3,
        "api_status": "READY",
    }:
        raise WebOnlyError("runtime repair prestate differs from the reviewed set")
    if repair["allowed_mutations"] != [
        "migration_0013_to_0014",
        "runtime_role_dml_grants",
        "api_to_baseline_digest",
        "worker_to_baseline_digest",
        "release_component_markers",
    ]:
        raise WebOnlyError("runtime repair mutations differ from the reviewed set")
    if repair["forbidden_mutations"] != [
        "web_container",
        "seed",
        "business_facts",
        "dns",
        "terraform",
        "cloud_resources",
        "wp12b",
    ]:
        raise WebOnlyError("runtime repair forbidden set differs from the reviewed set")
    return data


def _path_allowed(path: str, allowed: list[str]) -> bool:
    return any(path == rule or (rule.endswith("/") and path.startswith(rule)) for rule in allowed)


def check_repository(data: dict[str, object]) -> None:
    candidate = str(data["candidate_commit"])
    parent = str(data["candidate_parent"])
    baseline = data["runtime_baseline"]
    assert isinstance(baseline, dict)
    baseline_candidate = str(baseline["candidate_commit"])

    actual_parent = str(_git("rev-parse", f"{candidate}^")).strip()
    if actual_parent != parent:
        raise WebOnlyError("candidate_parent is not the candidate's direct parent")
    _git("merge-base", "--is-ancestor", baseline_candidate, candidate)

    changed = [
        item
        for item in str(_git("diff", "--name-only", parent, candidate)).splitlines()
        if item
    ]
    allowed = data["candidate_commit_allowed_paths"]
    assert isinstance(allowed, list)
    forbidden = sorted(path for path in changed if not _path_allowed(path, allowed))
    if forbidden:
        raise WebOnlyError(
            "candidate commit is not Web-only: " + ", ".join(forbidden)
        )
    if not any(path.startswith("apps/web/") for path in changed):
        raise WebOnlyError("candidate commit contains no Web change")

    compatibility = data["baseline_compatibility_paths"]
    assert isinstance(compatibility, list)
    runtime_changes = [
        item
        for item in str(
            _git("diff", "--name-only", baseline_candidate, candidate, "--", *compatibility)
        ).splitlines()
        if item
    ]
    if runtime_changes:
        raise WebOnlyError(
            "candidate is incompatible with the runtime baseline: "
            + ", ".join(sorted(runtime_changes))
        )

    openapi = _git("show", f"{candidate}:contracts/openapi.json", text=False)
    assert isinstance(openapi, bytes)
    if hashlib.sha256(openapi).hexdigest() != baseline["openapi_sha256"]:
        raise WebOnlyError("candidate OpenAPI differs from the reviewed baseline")

    wp08 = json.loads(WP08_CONTRACT.read_text())
    if wp08.get("candidate_commit") != candidate:
        raise WebOnlyError("WP-08 candidate and Web-only candidate differ")
    if wp08.get("candidate_artifact_run_id") != data["candidate_artifact_run_id"]:
        raise WebOnlyError("WP-08 artifact run and Web-only artifact run differ")
    digests = wp08.get("candidate_image_digests", {})
    if not isinstance(digests, dict) or digests.get("web") != data["web_image_digest"]:
        raise WebOnlyError("WP-08 Web digest and Web-only digest differ")


def verify_runtime(data: dict[str, object], evidence: dict[str, object]) -> None:
    expected_keys = {
        "web_release",
        "api_release",
        "worker_release",
        "migration_revision",
        "config_schema_version",
        "api_status",
        "database_status",
        "worker_stale",
        "root_http_status",
        "anonymous_ops_http_status",
        "anonymous_review_http_status",
    }
    if set(evidence) != expected_keys:
        raise WebOnlyError("runtime evidence keys differ from the reviewed schema")
    baseline = data["runtime_baseline"]
    assert isinstance(baseline, dict)
    expected = {
        "web_release": data["candidate_commit"],
        "api_release": baseline["candidate_commit"],
        "worker_release": baseline["candidate_commit"],
        "migration_revision": baseline["migration_revision"],
        "config_schema_version": baseline["config_schema_version"],
        "api_status": "READY",
        "database_status": "READY",
        "worker_stale": False,
        "root_http_status": 200,
        "anonymous_ops_http_status": 401,
        "anonymous_review_http_status": 401,
    }
    mismatches = [
        f"{key}={evidence.get(key)!r} expected={value!r}"
        for key, value in expected.items()
        if evidence.get(key) != value
    ]
    if mismatches:
        raise WebOnlyError("runtime is not UAT-compatible: " + "; ".join(mismatches))


def verify_repair_prestate(
    data: dict[str, object], evidence: dict[str, object]
) -> None:
    expected_keys = {
        "web_release",
        "api_release",
        "worker_release",
        "worker_heartbeat_release",
        "migration_revision",
        "config_schema_version",
        "api_status",
        "worker_stale",
    }
    if set(evidence) != expected_keys:
        raise WebOnlyError("runtime repair evidence keys differ from the reviewed schema")
    baseline = data["runtime_baseline"]
    assert isinstance(baseline, dict)
    old = "172c9f62ffdcd4fce31fb4900fdca46b3405ab89"
    allowed_releases = {old, baseline["candidate_commit"]}
    mismatches: list[str] = []
    if evidence["web_release"] != data["candidate_commit"]:
        mismatches.append("Web is not the reviewed candidate")
    if evidence["api_release"] not in allowed_releases:
        mismatches.append("API release is outside the reviewed repair set")
    if evidence["worker_release"] not in allowed_releases:
        mismatches.append("Worker release is outside the reviewed repair set")
    if evidence["worker_heartbeat_release"] not in allowed_releases:
        mismatches.append("Worker heartbeat release is outside the reviewed repair set")
    if evidence["migration_revision"] not in {
        "0013_wp11_notify_observability",
        baseline["migration_revision"],
    }:
        mismatches.append("migration is outside the reviewed forward-only range")
    if evidence["config_schema_version"] != baseline["config_schema_version"]:
        mismatches.append("config schema differs from the reviewed baseline")
    if evidence["api_status"] != "READY":
        mismatches.append("API is not ready")
    if not isinstance(evidence["worker_stale"], bool):
        mismatches.append("Worker stale evidence is not boolean")
    if mismatches:
        raise WebOnlyError("runtime repair prestate is not allowed: " + "; ".join(mismatches))


def _read_evidence(path: str) -> dict[str, object]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise WebOnlyError("runtime evidence must be a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    verify = subparsers.add_parser("verify-runtime")
    verify.add_argument("--evidence", required=True)
    repair = subparsers.add_parser("verify-repair-prestate")
    repair.add_argument("--evidence", required=True)
    args = parser.parse_args()
    try:
        data = load_contract()
        check_repository(data)
        if args.command == "check":
            baseline = data["runtime_baseline"]
            assert isinstance(baseline, dict)
            print(
                "WP08_WEB_ONLY_CONTRACT=PASS"
                f" candidate={data['candidate_commit']}"
                f" baseline={baseline['candidate_commit']}"
                " modes=web-container-only,runtime-repair"
            )
        elif args.command == "verify-runtime":
            verify_runtime(data, _read_evidence(args.evidence))
            print(
                "WP08_WEB_ONLY_RUNTIME=PASS"
                f" web={data['candidate_commit']}"
                f" api_worker={data['runtime_baseline']['candidate_commit']}"
            )
        else:
            verify_repair_prestate(data, _read_evidence(args.evidence))
            print(
                "WP08_RUNTIME_REPAIR_PRESTATE=PASS"
                f" web={data['candidate_commit']}"
                " mutation=api-worker-migration-only"
            )
    except (OSError, json.JSONDecodeError, WebOnlyError) as error:
        print(f"WP08_WEB_ONLY_STOPPED: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
