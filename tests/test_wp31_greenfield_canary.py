import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import wp15_rds_database, wp15_rds_schema_owner
from scripts import wp31_greenfield_canary as contract
from scripts import wp31_phase_evidence as phase_evidence
from scripts import wp31_prepare_greenfield_canary as prepare


ROOT = Path(__file__).resolve().parents[1]


def test_contract_is_exact_and_execution_remains_fail_closed() -> None:
    value = contract.load()
    assert value["application_candidate_sha"] == prepare.CANDIDATE
    assert value["scope"]["max_allowlisted_learners"] == 8
    assert value["scope"]["worker_started"] is False
    assert value["scope"]["release_go"] is False
    assert value["owner_canary_deployment_go"] is True
    assert value["entrypoint_execution_granted"] is False
    with pytest.raises(contract.CanaryContractError, match="execution is not granted"):
        contract.review_check(Path("missing"), "0" * 64)


def test_review_requires_real_evidence_hash_and_all_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = contract.load()
    value["entrypoint_execution_granted"] = True
    monkeypatch.setattr(contract, "load", lambda: value)
    monkeypatch.setattr(contract, "verify_reviewed_tree", lambda *_: None)
    manifest_hash = contract.sha256(contract.OPS_MANIFEST)
    evidence = tmp_path / "review.json"
    evidence.write_text(
        json.dumps(
            {
                "review_status": "PASS",
                "reviewer": "CODEX_PRO_REVIEW_MACBOOK_PRO",
                "reviewed_at_utc": "2026-08-27T00:00:00Z",
                "evidence_scope": "PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW",
                "reviewer_independent": True,
                "production_mutation": False,
                "reviewed_ops_commit_sha": "1" * 40,
                "application_candidate_sha": value["application_candidate_sha"],
                "package_manifest_sha256": value["package_manifest_sha256"],
                "ops_manifest_sha256": manifest_hash,
            },
            sort_keys=True,
        )
        + "\n"
    )
    digest = contract.sha256(evidence)
    assert contract.review_check(evidence, digest)["status"] == "PASS"
    with pytest.raises(contract.CanaryContractError, match="hash differs"):
        contract.review_check(evidence, "0" * 64)
    changed = json.loads(evidence.read_text())
    changed["reviewer"] = "SELF_SIGNED_FIXTURE"
    evidence.write_text(json.dumps(changed) + "\n")
    with pytest.raises(contract.CanaryContractError, match="reviewer identity"):
        contract.review_check(evidence, contract.sha256(evidence))
    changed["reviewer"] = "CODEX_PRO_REVIEW_MACBOOK_PRO"
    changed["ops_manifest_sha256"] = "0" * 64
    evidence.write_text(json.dumps(changed) + "\n")
    with pytest.raises(contract.CanaryContractError, match="binding differs"):
        contract.review_check(evidence, contract.sha256(evidence))


def test_phase_evidence_closes_chain_and_detects_payload_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WP15_BACKUP_KEY", "k" * 40)
    payload = tmp_path / "facts.json"
    payload.write_text('{"safe":true}\n')
    evidence = tmp_path / "preflight.json"
    result = phase_evidence.create(
        evidence,
        "preflight",
        "123456",
        "1" * 40,
        "2" * 64,
        "3" * 40,
        None,
        [payload],
        30,
    )
    assert result["payload_sha256"]["facts.json"] == hashlib.sha256(payload.read_bytes()).hexdigest()
    verified = phase_evidence.verify(
        evidence, "preflight", "123456", "1" * 40, "2" * 64, "3" * 40, None, tmp_path
    )
    assert verified["run_id"] == "123456"
    payload.write_text('{"safe":false}\n')
    with pytest.raises(phase_evidence.PhaseEvidenceError, match="payload bytes differ"):
        phase_evidence.verify(
            evidence, "preflight", "123456", "1" * 40, "2" * 64, "3" * 40, None, tmp_path
        )


def test_phase_evidence_rejects_expiry_replay_and_wrong_previous_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WP15_BACKUP_KEY", "k" * 40)
    evidence = tmp_path / "phase.json"
    phase_evidence.create(
        evidence, "deploy", "123456", "1" * 40, "2" * 64, "3" * 40, "111111", [], 30
    )
    with pytest.raises(phase_evidence.PhaseEvidenceError, match="chain binding differs"):
        phase_evidence.verify(
            evidence, "deploy", "123456", "1" * 40, "2" * 64, "3" * 40, "222222", tmp_path
        )
    value = json.loads(evidence.read_text())
    value.pop("evidence_hmac_sha256")
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    value["created_at_utc"] = past.isoformat().replace("+00:00", "Z")
    value["expires_at_utc"] = (past + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    value["evidence_hmac_sha256"] = __import__("hmac").new(
        b"k" * 40, phase_evidence.canonical(value), hashlib.sha256
    ).hexdigest()
    evidence.write_text(json.dumps(value) + "\n")
    with pytest.raises(phase_evidence.PhaseEvidenceError, match="expired"):
        phase_evidence.verify(
            evidence, "deploy", "123456", "1" * 40, "2" * 64, "3" * 40, "111111", tmp_path
        )


def test_canary_compose_has_api_web_only_and_distinct_edge_alias() -> None:
    compose = (ROOT / "deploy/production/compose.greenfield-canary.yaml").read_text()
    assert "  api:\n" in compose
    assert "  web:\n" in compose
    assert "  worker:\n" not in compose
    assert "greenfield-canary-api" in compose
    assert "greenfield-canary-web" in compose
    assert "production-web" not in compose


def test_workflow_requires_real_review_before_infrastructure_read() -> None:
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    job = workflow[workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")]
    assert "environment: production-canary-uat" in job
    assert "scripts/wp31_greenfield_canary.py review-check" in job
    assert job.index("review-check") < job.index("terraform init")
    assert "greenfield-backup-restore" in job
    assert "greenfield-deploy" in job
    assert "greenfield-rollback" in job
    assert "WP31_CANARY_LEARNER_USER_IDS: ${{ secrets.WP31_CANARY_LEARNER_USER_IDS }}" in job


def test_workflow_closes_phase_chain_and_has_failure_rollback_cleanup() -> None:
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    job = workflow[workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")]
    assert "preflight_run_id" in workflow and "deploy_run_id" in workflow
    assert "wp31-canary-preflight-${{ inputs.preflight_run_id }}" in job
    assert "wp31-canary-backup-${{ inputs.backup_run_id }}" in job
    assert "wp31-canary-deploy-${{ inputs.deploy_run_id }}" in job
    assert "scripts/wp31_phase_evidence.py verify" in job
    assert "steps.deploy.outcome == 'failure' || steps.inspect.outcome == 'failure'" in job
    assert "steps.upload_deploy_evidence.outcome == 'failure'" in job
    assert "Automatic rollback after any deploy or public inspection failure" in job
    assert "Always remove transient credentials and remote registry session" in job
    assert "docker logout ghcr.io" in job
    assert "Close temporary SSH ingress" in job


def test_backup_and_deploy_proofs_bind_real_files_and_exact_release() -> None:
    backup = (ROOT / "deploy/production/greenfield_canary_backup_restore.sh").read_text()
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text()
    edge = (ROOT / "deploy/production/greenfield_canary_edge.sh").read_text()
    assert 'assert source == restored' in backup
    assert '"encrypted_backup_sha256": encrypted_sha' in backup
    assert '"source_facts_sha256": source_facts_sha' in backup
    assert '"restored_facts_sha256": facts_sha' in backup
    assert 'digest("canary-source.dump.enc") == value["encrypted_backup_sha256"]' in deploy
    assert 'cmp -s "$before" "$current_before"' in deploy
    assert 'rm -f -- "$root/current"' in deploy
    assert '"release":sys.argv[2]' in edge


def test_ops_manifest_fails_closed_on_working_tree_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {}
    for index in range(10):
        path = tmp_path / f"op-{index}.txt"
        path.write_text(f"stable-{index}\n")
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "application_candidate_sha": contract.EXPECTED_CANDIDATE,
                "files": files,
            }
        )
        + "\n"
    )
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(contract, "OPS_MANIFEST", manifest)
    assert contract.load_ops_manifest()["files"] == files
    (tmp_path / "op-3.txt").write_text("drifted\n")
    with pytest.raises(contract.CanaryContractError, match="bytes drifted"):
        contract.load_ops_manifest()


def test_exact_canary_database_is_the_only_new_rds_target() -> None:
    expected = "journey_next_canary_20260827_1bccbbf"
    assert wp15_rds_database.GREENFIELD_CANARY_DATABASE_NAME == expected
    assert wp15_rds_schema_owner.GREENFIELD_CANARY_DATABASE_NAME == expected
    assert expected in wp15_rds_database.ALLOWED_DATABASES
    assert expected in wp15_rds_schema_owner.ALLOWED_DATABASES


def test_prepare_accepts_zero_allowlist_and_never_writes_worker_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {
        "WP08_MIGRATION_DB_PASSWORD": "m" * 32,
        "WP08_RUNTIME_DB_PASSWORD": "r" * 32,
        "WP15_SESSION_SECRET": "s" * 40,
        "WP15_INVITE_SECRET": "i" * 40,
        "WP15_IMPORT_SIGNING_KEY": "k" * 40,
        "WP15_BACKUP_KEY": "b" * 40,
        "WP09_IDENTITY_SUBJECT_SECRET": "d" * 40,
        "WP09_FEISHU_APP_ID": "cli_fixture",
        "WP09_FEISHU_APP_SECRET": "f" * 24,
        "WP08_RDS_CA_PEM_B64": base64.b64encode(
            b"-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n"
        ).decode(),
        "WP31_CANARY_LEARNER_USER_IDS": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    output = tmp_path / "bundle"
    prepare.prepare(output, "private.example.internal", 5432)
    proof = json.loads((output / "allowlist-proof.json").read_text())
    assert proof["allowlist_count"] == 0
    assert proof["raw_identifiers_in_proof"] is False
    assert not (output / "secrets/worker.env").exists()
    api = (output / "secrets/api.env").read_text()
    assert "RELEASE_MARKER=PRODUCTION_CANARY_UAT\n" in api
    assert "ALLOW_FIXTURE_IDENTITY=false\n" in api
    assert "NOTIFICATION_RECIPIENTS_ENABLED=false\n" in api


def test_prepare_rejects_more_than_eight_or_duplicate_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [f"00000000-0000-0000-0000-{item:012d}" for item in range(1, 10)]
    monkeypatch.setenv("WP31_CANARY_LEARNER_USER_IDS", ",".join(values))
    with pytest.raises(prepare.PrepareCanaryError, match="at most 8"):
        prepare.allowlist()
    monkeypatch.setenv("WP31_CANARY_LEARNER_USER_IDS", f"{values[0]},{values[0]}")
    with pytest.raises(prepare.PrepareCanaryError, match="unique"):
        prepare.allowlist()
