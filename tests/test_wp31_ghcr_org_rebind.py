from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import wp31_ghcr_org_rebind as rebind


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def source_manifest(contract: dict) -> dict:
    return {
        "candidate": {"commit_sha": rebind.EXPECTED_CANDIDATE},
        "images": {
            component: {
                "registry_reference": (
                    f"{contract['images'][component]['source_repository']}:"
                    f"{rebind.EXPECTED_CANDIDATE}"
                ),
                "registry_digest": contract["images"][component]["source_digest"],
                "revision_label": rebind.EXPECTED_CANDIDATE,
            }
            for component in rebind.COMPONENTS
        },
    }


def prepared(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    contract = copy.deepcopy(rebind.load_contract())
    source_path = tmp_path / "source-release-manifest.json"
    write_json(source_path, source_manifest(contract))
    contract["source_manifest_sha256"] = rebind.sha256(source_path)
    facts_path = tmp_path / "target-facts.json"
    facts = {
        "candidate_sha": rebind.EXPECTED_CANDIDATE,
        "images": {
            component: {
                "prior_immutable_reference": (
                    f"{contract['images'][component]['source_repository']}@"
                    f"{contract['images'][component]['source_digest']}"
                ),
                "prior_digest": contract["images"][component]["source_digest"],
                "target_reference": rebind.target_reference(contract, component),
                "target_digest": contract["images"][component]["source_digest"],
                "digest_equal_to_prior": True,
                "revision_label": rebind.EXPECTED_CANDIDATE,
                "local_image_id": "sha256:" + component.encode().hex().ljust(64, "0")[:64],
            }
            for component in rebind.COMPONENTS
        },
    }
    write_json(facts_path, facts)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for component in rebind.COMPONENTS:
        write_json(evidence / f"{component}.spdx.json", {"spdxVersion": "SPDX-2.3"})
        write_json(evidence / f"{component}.trivy.json", {"Results": []})
    write_json(evidence / "trivy-db-metadata.json", {"UpdatedAt": "2026-08-31T00:00:00Z"})
    return contract, source_path, facts_path, evidence


def test_frozen_contract_is_valid() -> None:
    contract = rebind.load_contract()
    assert contract["application_candidate_sha"] == rebind.EXPECTED_CANDIDATE
    assert set(contract["images"]) == set(rebind.COMPONENTS)
    assert all(
        item["target_repository"].startswith("ghcr.io/muchenai/")
        for item in contract["images"].values()
    )


def test_source_manifest_rejects_namespace_drift(tmp_path: Path) -> None:
    contract = copy.deepcopy(rebind.load_contract())
    value = source_manifest(contract)
    value["images"]["api"]["registry_reference"] = "ghcr.io/other/api:bad"
    path = tmp_path / "source.json"
    write_json(path, value)
    contract["source_manifest_sha256"] = rebind.sha256(path)
    with pytest.raises(rebind.RebindError, match="source registry reference differs"):
        rebind.check_source_manifest(contract, path)


def test_existing_target_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rebind,
        "run_bytes",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, b"", b""),
    )
    with pytest.raises(rebind.RebindError, match="already exists"):
        rebind.targets_absent(rebind.load_contract())


def test_registry_auth_failure_is_not_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rebind,
        "run_bytes",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, b"", b"denied: requested access to the resource is denied"
        ),
    )
    with pytest.raises(rebind.RebindError, match="cannot prove"):
        rebind.targets_absent(rebind.load_contract())


def test_manifest_unknown_proves_target_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rebind,
        "run_bytes",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, b"", b"manifest unknown"
        ),
    )
    assert rebind.targets_absent(rebind.load_contract())["target_tags"] == "ABSENT"


def test_manifest_binds_three_zero_cve_images(tmp_path: Path) -> None:
    contract, source_path, facts_path, evidence = prepared(tmp_path)
    output = evidence / "ghcr-org-rebind-manifest.json"
    result = rebind.build_manifest(contract, source_path, facts_path, evidence, output)
    assert result["status"] == "EVIDENCE_COMPLETE"
    assert set(result["images"]) == set(rebind.COMPONENTS)
    assert all(item["digest_equal_to_prior"] for item in result["images"].values())
    assert all(item["cve"]["high"] == 0 for item in result["images"].values())
    assert result["production_effects"]["deployment"] is False


def test_high_cve_is_recorded_as_release_gate_failure(tmp_path: Path) -> None:
    contract, source_path, facts_path, evidence = prepared(tmp_path)
    write_json(
        evidence / "api.trivy.json",
        {"Results": [{"Vulnerabilities": [{"Severity": "HIGH"}]}]},
    )
    result = rebind.build_manifest(
        contract,
        source_path,
        facts_path,
        evidence,
        evidence / "manifest.json",
    )
    assert result["cve_gate"]["status"] == "FAIL"
    assert result["images"]["api"]["cve"]["status"] == "FAIL"


def test_target_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    contract, source_path, facts_path, evidence = prepared(tmp_path)
    facts = json.loads(facts_path.read_text())
    facts["images"]["worker"]["target_digest"] = "not-a-digest"
    write_json(facts_path, facts)
    with pytest.raises(rebind.RebindError, match="target fact binding differs"):
        rebind.build_manifest(
            contract,
            source_path,
            facts_path,
            evidence,
            evidence / "manifest.json",
        )


def test_evidence_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    rebind.write_json_exclusive(path, {"first": True})
    with pytest.raises(rebind.RebindError, match="refusing to replace"):
        rebind.write_json_exclusive(path, {"second": True})


def test_sha256_is_real_file_digest(tmp_path: Path) -> None:
    path = tmp_path / "value"
    path.write_bytes(b"muchen-journey")
    assert rebind.sha256(path) == hashlib.sha256(b"muchen-journey").hexdigest()


def test_workflow_is_immutable_package_only() -> None:
    workflow = (rebind.ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    job = workflow.split("  greenfield_org_rebind:", 1)[1].split(
        "\n  greenfield_authorize:", 1
    )[0]
    assert "GITHUB_REF_TYPE\" = tag" in job
    assert "muchen-journey-ghcr-org-rebind-$GITHUB_SHA" in job
    assert ".target_repository" in job
    assert "packages: write" in job
    assert "environment:" not in job
    assert "terraform" not in job
    assert "ssh " not in job
    assert "alembic" not in job
    assert "docker compose" not in job
    assert "Check out exact frozen application candidate for rebuild" in job
    assert "docker build --pull --platform linux/amd64" in job
