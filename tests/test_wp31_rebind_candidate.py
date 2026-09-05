import hashlib
import json
from pathlib import Path

import pytest

from scripts import wp31_candidate_binding as candidate_binding
from scripts import wp31_rebind_candidate as rebind


NEW_CANDIDATE = "1" * 40
OLD_CANDIDATE = "9e2d3496f5df80da1291c77bd6f949a5078ef25d"
NEW_RUN = "33999999999"
NEW_MANIFEST = "d" * 64
NEW_DIGESTS = {service: "sha256:" + letter * 64 for service, letter in zip(("api", "web", "worker"), "abc")}
OLD_DIGESTS = {service: "sha256:" + letter * 64 for service, letter in zip(("api", "web", "worker"), "xyz")}


def _binding() -> dict[str, object]:
    return {
        "schema_version": 1,
        "application_candidate_sha": NEW_CANDIDATE,
        "package_workflow_run_id": NEW_RUN,
        "release_manifest_sha256": NEW_MANIFEST,
        "images": {
            service: {
                "registry_reference": f"ghcr.io/muchenai/muchen-journey-vnext-{service}:{NEW_CANDIDATE}",
                "registry_digest": NEW_DIGESTS[service],
                "sbom_path": f"artifacts/wp07-candidate/{service}.spdx.json",
                "sbom_sha256": "e" * 64,
            }
            for service in ("api", "web", "worker")
        },
        "build_definition_manifest_sha256": "f" * 64,
    }


def _fixture(root: Path) -> Path:
    targets = {
        "config/wp31_greenfield_canary.json": json.dumps(
            {
                "schema_version": 3,
                "application_candidate_sha": OLD_CANDIDATE,
                "package_workflow_run_id": "33838169130",
                "package_manifest_sha256": "0" * 64,
                "images": {
                    "api": f"ghcr.io/muchenai/muchen-journey-vnext-api@{OLD_DIGESTS['api']}",
                    "web": f"ghcr.io/muchenai/muchen-journey-vnext-web@{OLD_DIGESTS['web']}",
                    "worker_evidence_only": f"ghcr.io/muchenai/muchen-journey-vnext-worker@{OLD_DIGESTS['worker']}",
                },
            }
        ),
        "config/wp31_greenfield_canary_execution_authorization.schema.json": OLD_CANDIDATE,
        "config/wp31_greenfield_canary_pro_review_evidence.schema.json": OLD_CANDIDATE + " 0" * 64,
        "scripts/wp31_greenfield_canary.py": f'EXPECTED_CANDIDATE = "{OLD_CANDIDATE}"\n"package_workflow_run_id": "33838169130"\n"0" * 64',
        "scripts/wp31_prepare_greenfield_canary.py": (
            f'CANDIDATE = "{OLD_CANDIDATE}"\n'
            f'"API_IMAGE": "ghcr.io/muchenai/muchen-journey-vnext-api@{OLD_DIGESTS["api"]}",\n'
            f'"WEB_IMAGE": "ghcr.io/muchenai/muchen-journey-vnext-web@{OLD_DIGESTS["web"]}",'
        ),
        ".github/workflows/wp15-wartime-production.yml": (
            f"{OLD_CANDIDATE} 33838169130 0{'x' * 64} "
            f"ghcr.io/muchenai/muchen-journey-vnext-api@{OLD_DIGESTS['api']}"
        ),
    }
    for relative, content in targets.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for relative in (
        ".github/workflows/wp31-candidate-rebind.yml",
        "scripts/wp31_candidate_binding.py",
        "scripts/wp31_canary_database_guard.py",
        "scripts/wp31_rebind_candidate.py",
        "tests/test_wp31_candidate_binding.py",
        "tests/test_wp31_binding_consumers.py",
        "tests/test_wp31_canary_database_guard.py",
        "tests/test_wp31_rebind_candidate.py",
        "tests/test_wp31_rebind_workflow.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture for {relative}\n", encoding="utf-8")
    manifest = root / "config/wp31_greenfield_canary_ops_manifest.json"
    manifest.write_text(
        json.dumps(
            {"schema_version": 2, "files": {relative: "0" * 64 for relative in targets}},
            indent=2,
        ),
        encoding="utf-8",
    )
    binding_path = root / "candidate-binding.json"
    binding_path.write_bytes(candidate_binding.serialize(_binding()))
    return binding_path


def test_rebind_updates_consumers_and_refreshes_manifest_hashes(tmp_path: Path) -> None:
    binding_path = _fixture(tmp_path)

    changed = rebind.rebind(tmp_path, binding_path)

    assert changed
    assert NEW_CANDIDATE in (tmp_path / "scripts/wp31_greenfield_canary.py").read_text()
    assert NEW_RUN in (tmp_path / ".github/workflows/wp15-wartime-production.yml").read_text()
    assert NEW_DIGESTS["api"] in (tmp_path / "scripts/wp31_prepare_greenfield_canary.py").read_text()
    value = json.loads((tmp_path / "config/wp31_greenfield_canary.json").read_text())
    assert value["package_manifest_sha256"] == NEW_MANIFEST
    manifest = json.loads((tmp_path / "config/wp31_greenfield_canary_ops_manifest.json").read_text())
    assert manifest["application_candidate_sha"] == NEW_CANDIDATE
    assert "config/wp31_candidate_binding.json" in manifest["files"]
    persisted = json.loads((tmp_path / "config/wp31_candidate_binding.json").read_text())
    assert persisted["package_workflow_run_id"] == NEW_RUN
    for relative, expected in manifest["files"].items():
        assert expected == hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()


def test_rebind_branch_name_is_unique_to_package_run() -> None:
    assert rebind.branch_name("33999999999") == "codex/canary-rebind-33999999999"
    with pytest.raises(rebind.RebindError):
        rebind.branch_name("not-a-run")
