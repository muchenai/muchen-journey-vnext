import json
from pathlib import Path

import pytest

from scripts import wp31_candidate_binding as binding


CANDIDATE = "9e2d3496f5df80da1291c77bd6f949a5078ef25d"
DIGESTS = {
    "api": "sha256:" + "a" * 64,
    "web": "sha256:" + "b" * 64,
    "worker": "sha256:" + "c" * 64,
}


def _write_package(root: Path) -> Path:
    root.mkdir()
    for service in ("api", "web", "worker"):
        (root / f"{service}.spdx.json").write_text(
            json.dumps({"SPDXID": f"SPDXRef-{service}"}), encoding="utf-8"
        )
    (root / "amd64-build-definition-manifest.json").write_text("{}\n", encoding="utf-8")
    manifest = {
        "candidate": {
            "commit_sha": CANDIDATE,
            "source_tree_clean": True,
        },
        "external_status": {"registry_push": "VERIFIED"},
        "images": {
            service: {
                "registry_reference": (
                    f"ghcr.io/muchenai/muchen-journey-vnext-{service}:{CANDIDATE}"
                ),
                "registry_digest": DIGESTS[service],
                "sbom": {
                    "path": f"artifacts/wp07-candidate/{service}.spdx.json",
                    "sha256": binding.sha256(root / f"{service}.spdx.json"),
                },
            }
            for service in ("api", "web", "worker")
        },
    }
    path = root / "release-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def test_build_binding_extracts_candidate_digests_and_sboms(tmp_path: Path) -> None:
    manifest = _write_package(tmp_path / "package")

    result = binding.build_binding(manifest, package_run_id="33950428823")

    assert result["application_candidate_sha"] == CANDIDATE
    assert result["package_workflow_run_id"] == "33950428823"
    assert result["images"]["api"]["registry_digest"] == DIGESTS["api"]
    assert result["images"]["worker"]["sbom_sha256"] == binding.sha256(
        manifest.parent / "worker.spdx.json"
    )
    assert result["release_manifest_sha256"] == binding.sha256(manifest)


def test_build_binding_rejects_unverified_or_unpinned_package(tmp_path: Path) -> None:
    manifest = _write_package(tmp_path / "package")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["external_status"]["registry_push"] = "NOT_RUN"
    value["images"]["api"]["registry_digest"] = None
    manifest.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(binding.BindingError, match="registry"):
        binding.build_binding(manifest, package_run_id="33950428823")


def test_binding_serialization_is_deterministic(tmp_path: Path) -> None:
    manifest = _write_package(tmp_path / "package")
    first = binding.build_binding(manifest, package_run_id="33950428823")
    second = binding.build_binding(manifest, package_run_id="33950428823")

    assert binding.serialize(first) == binding.serialize(second)
