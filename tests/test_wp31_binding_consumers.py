import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_canary_contract_uses_the_unified_candidate_binding() -> None:
    binding = json.loads((ROOT / "config/wp31_candidate_binding.json").read_text())
    contract = json.loads((ROOT / "config/wp31_greenfield_canary.json").read_text())
    assert contract["application_candidate_sha"] == binding["application_candidate_sha"]
    assert contract["package_workflow_run_id"] == binding["package_workflow_run_id"]
    assert contract["package_manifest_sha256"] == binding["release_manifest_sha256"]
    for service, contract_key in (
        ("api", "api"),
        ("web", "web"),
        ("worker", "worker_evidence_only"),
    ):
        expected = (
            f"ghcr.io/muchenai/muchen-journey-vnext-{service}@"
            f"{binding['images'][service]['registry_digest']}"
        )
        assert contract["images"][contract_key] == expected


def test_canary_consumers_read_the_binding_file() -> None:
    for relative in (
        "scripts/wp31_greenfield_canary.py",
        "scripts/wp31_prepare_greenfield_canary.py",
    ):
        assert "config/wp31_candidate_binding.json" in (ROOT / relative).read_text(encoding="utf-8")
