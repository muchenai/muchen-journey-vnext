import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_RUNTIME_CANDIDATE = "9e2d3496f5df80da1291c77bd6f949a5078ef25d"
CURRENT_DBTOOL_NAMESPACE = "ghcr.io/muchenai/muchen-journey-vnext-dbtool"


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


def test_runtime_scripts_bind_the_candidate_at_execution_time() -> None:
    backup = (ROOT / "deploy/production/greenfield_canary_backup_restore.sh").read_text(
        encoding="utf-8"
    )
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text(encoding="utf-8")
    edge = (ROOT / "deploy/production/greenfield_canary_edge.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "deploy/production/greenfield_canary_rollback.sh").read_text(
        encoding="utf-8"
    )

    assert 'candidate="${CANDIDATE_COMMIT:-}"' in backup
    assert 'candidate="${CANDIDATE_COMMIT:-}"' in deploy
    assert LEGACY_RUNTIME_CANDIDATE not in backup
    assert LEGACY_RUNTIME_CANDIDATE not in deploy
    assert LEGACY_RUNTIME_CANDIDATE not in edge
    assert LEGACY_RUNTIME_CANDIDATE not in rollback
    assert "([0-9a-f]{40})" in edge
    assert "([0-9a-f]{40})" in rollback


def test_runtime_images_and_dbtool_use_the_current_registry_namespace() -> None:
    prepare = (ROOT / "scripts/wp31_prepare_greenfield_canary.py").read_text(encoding="utf-8")
    backup = (ROOT / "deploy/production/greenfield_canary_backup_restore.sh").read_text(
        encoding="utf-8"
    )
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text(encoding="utf-8")
    mirror = (ROOT / ".github/workflows/wp15-dbtool-mirror.yml").read_text(encoding="utf-8")

    assert CURRENT_DBTOOL_NAMESPACE in prepare
    assert CURRENT_DBTOOL_NAMESPACE in backup
    assert "muchenai2024-creator/muchen-journey-vnext-dbtool" not in prepare
    assert "muchenai2024-creator/muchen-journey-vnext-dbtool" not in backup
    assert "candidate-binding-proof.json" in backup
    assert "candidate-binding-proof.json" in deploy
    assert "runtime-verify" in backup
    assert "runtime-verify" in deploy
    assert "=~ ^ghcr\\.io/muchenai/muchen-journey-vnext-api@sha256:[0-9a-f]{64}$" not in deploy
    assert "muchenai2024-creator/muchen-journey-vnext" not in mirror.split("target=", 1)[1]
    assert 'target="ghcr.io/muchenai/muchen-journey-vnext-dbtool:' in mirror


def test_prepare_passes_bound_candidate_to_backup_runtime() -> None:
    prepare = (ROOT / "scripts/wp31_prepare_greenfield_canary.py").read_text(encoding="utf-8")
    backup_block = prepare.split('secrets / "backup.env"', 1)[1].split("    )", 1)[0]
    assert '"CANDIDATE_COMMIT": candidate' in backup_block


def test_workflow_proof_checks_use_the_dispatch_candidate() -> None:
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text(encoding="utf-8")
    assert 'assert value["candidate_sha"] == \'${{ inputs.candidate }}\'' in workflow
    assert '"public_release":"${{ inputs.candidate }}"' in workflow
    assert '"release": \'${{ inputs.candidate }}\'' in workflow
    assert 'cp scripts/wp31_candidate_binding.py "$bundle/wp31_candidate_binding.py"' in workflow


def test_ops_manifest_declared_hashes_match_the_working_tree() -> None:
    manifest = json.loads(
        (ROOT / "config/wp31_greenfield_canary_ops_manifest.json").read_text(encoding="utf-8")
    )
    for relative, expected in manifest["files"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected, relative


def test_identity_and_amd64_defaults_match_the_live_candidate_binding() -> None:
    binding = json.loads((ROOT / "config/wp31_candidate_binding.json").read_text(encoding="utf-8"))
    from scripts import wp31_identity_bootstrap as identity
    from scripts import wp31_prepare_amd64_dockerfiles as amd64

    assert identity.CANDIDATE == binding["application_candidate_sha"]
    assert identity.CONFIRMATION == (
        f"BOOTSTRAP_IDENTITIES_{binding['application_candidate_sha'][:7].upper()}_PRODUCTION_CANARY"
    )
    assert amd64.CANDIDATE == binding["application_candidate_sha"]
