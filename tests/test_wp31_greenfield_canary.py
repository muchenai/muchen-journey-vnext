import base64
import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import wp15_rds_database, wp15_rds_schema_owner
from scripts import wp31_greenfield_canary as contract
from scripts import wp31_ops_closure as closure
from scripts import wp31_phase_evidence as phase_evidence
from scripts import wp31_prepare_greenfield_canary as prepare


ROOT = Path(__file__).resolve().parents[1]


def test_contract_is_exact_and_mutable_authorization_is_external() -> None:
    value = contract.load()
    assert value["application_candidate_sha"] == prepare.CANDIDATE
    assert value["scope"]["max_allowlisted_learners"] == 8
    assert value["scope"]["worker_started"] is False
    assert value["scope"]["release_go"] is False
    assert value["authorization_model"] == (
        "ENVIRONMENT_APPROVAL_PLUS_PROTECTED_OWNER_EXECUTION_EVIDENCE"
    )
    assert "owner_canary_deployment_go" not in value
    assert "entrypoint_execution_granted" not in value


def test_review_requires_real_evidence_hash_and_all_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = contract.load()
    monkeypatch.setattr(contract, "load", lambda: value)
    monkeypatch.setattr(contract, "verify_reviewed_tree", lambda *_: None)
    manifest_hash = contract.sha256(contract.OPS_MANIFEST)
    evidence = tmp_path / "review.json"
    reviewed = "1" * 40
    reviewed_ref = f"refs/tags/muchen-journey-greenfield-ops-{reviewed}"
    evidence.write_text(
        json.dumps(
            {
                "review_status": "PASS",
                "reviewer": "CODEX_PRO_REVIEW_MACBOOK_PRO",
                "reviewed_at_utc": "2026-08-27T00:00:00Z",
                "evidence_scope": "PRO_GREENFIELD_CANARY_ENTRYPOINT_REVIEW",
                "reviewer_independent": True,
                "production_mutation": False,
                "reviewed_ops_commit_sha": reviewed,
                "reviewed_ops_ref": reviewed_ref,
                "application_candidate_sha": value["application_candidate_sha"],
                "package_manifest_sha256": value["package_manifest_sha256"],
                "ops_manifest_sha256": manifest_hash,
            },
            sort_keys=True,
        )
        + "\n"
    )
    digest = contract.sha256(evidence)
    assert contract.review_check(evidence, digest, reviewed_ref)["status"] == "PASS"
    with pytest.raises(contract.CanaryContractError, match="hash differs"):
        contract.review_check(evidence, "0" * 64, reviewed_ref)
    changed = json.loads(evidence.read_text())
    changed["reviewer"] = "SELF_SIGNED_FIXTURE"
    evidence.write_text(json.dumps(changed) + "\n")
    with pytest.raises(contract.CanaryContractError, match="reviewer identity"):
        contract.review_check(evidence, contract.sha256(evidence), reviewed_ref)
    changed["reviewer"] = "CODEX_PRO_REVIEW_MACBOOK_PRO"
    changed["ops_manifest_sha256"] = "0" * 64
    evidence.write_text(json.dumps(changed) + "\n")
    with pytest.raises(contract.CanaryContractError, match="binding differs"):
        contract.review_check(evidence, contract.sha256(evidence), reviewed_ref)
    changed["ops_manifest_sha256"] = manifest_hash
    evidence.write_text(json.dumps(changed) + "\n")
    with pytest.raises(contract.CanaryContractError, match="exact reviewed immutable tag"):
        contract.review_check(evidence, contract.sha256(evidence), "refs/heads/movable")


def test_owner_authorization_is_external_exact_phase_short_lived_and_hash_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = contract.load()
    monkeypatch.setattr(contract, "load", lambda: value)
    reviewed = "1" * 40
    reviewed_ref = f"refs/tags/muchen-journey-greenfield-ops-{reviewed}"
    monkeypatch.setattr(
        contract,
        "_git",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, (reviewed + "\n").encode(), b""),
    )
    now = datetime.now(timezone.utc)
    evidence = tmp_path / "owner-authorization.json"
    payload = {
        "authorization_id": str(uuid.uuid4()),
        "authorization_status": "GRANTED",
        "authorized_at_utc": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "not_after_utc": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        "authorized_by": "刘默文",
        "authority": "PRODUCT_OWNER_AND_RELEASE_OPS_OWNER",
        "environment": "PRODUCTION_CANARY_UAT",
        "application_candidate_sha": value["application_candidate_sha"],
        "reviewed_ops_commit_sha": reviewed,
        "reviewed_ops_ref": reviewed_ref,
        "ops_manifest_sha256": contract.sha256(contract.OPS_MANIFEST),
        "pro_review_evidence_sha256": "2" * 64,
        "phase": "greenfield-preflight",
        "max_allowlisted_learners": 8,
        "production_job_execution_authorized": True,
        "worker_start_authorized": False,
        "release_go": False,
    }
    evidence.write_text(json.dumps(payload, sort_keys=True) + "\n")
    digest = contract.sha256(evidence)
    result = contract.authorization_check(
        evidence, digest, "2" * 64, "greenfield-preflight", reviewed_ref, reviewed
    )
    assert result["status"] == "PASS"
    with pytest.raises(contract.CanaryContractError, match="binding differs"):
        contract.authorization_check(
            evidence, digest, "2" * 64, "greenfield-deploy", reviewed_ref, reviewed
        )
    payload["not_after_utc"] = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    evidence.write_text(json.dumps(payload, sort_keys=True) + "\n")
    with pytest.raises(contract.CanaryContractError, match="not currently valid"):
        contract.authorization_check(
            evidence,
            contract.sha256(evidence),
            "2" * 64,
            "greenfield-preflight",
            reviewed_ref,
            reviewed,
        )


def test_fast_canary_authorization_uses_empty_pro_review_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = contract.load()
    monkeypatch.setattr(contract, "load", lambda: value)
    reviewed = "1" * 40
    reviewed_ref = f"refs/tags/muchen-journey-greenfield-ops-{reviewed}"
    monkeypatch.setattr(
        contract,
        "_git",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, (reviewed + "\n").encode(), b""),
    )
    now = datetime.now(timezone.utc)
    payload = {
        "authorization_id": str(uuid.uuid4()),
        "authorization_status": "GRANTED",
        "authorized_at_utc": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "not_after_utc": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        "authorized_by": "刘默文",
        "authority": "PRODUCT_OWNER_AND_RELEASE_OPS_OWNER",
        "environment": "PRODUCTION_CANARY_UAT",
        "application_candidate_sha": value["application_candidate_sha"],
        "reviewed_ops_commit_sha": reviewed,
        "reviewed_ops_ref": reviewed_ref,
        "ops_manifest_sha256": contract.sha256(contract.OPS_MANIFEST),
        "pro_review_evidence_sha256": "",
        "phase": "greenfield-canary-fast",
        "max_allowlisted_learners": 8,
        "production_job_execution_authorized": True,
        "worker_start_authorized": False,
        "release_go": False,
    }
    evidence = tmp_path / "fast-owner-authorization.json"
    evidence.write_text(json.dumps(payload, sort_keys=True) + "\n")
    assert contract.authorization_check(
        evidence, contract.sha256(evidence), "", "greenfield-canary-fast", reviewed_ref, reviewed
    )["status"] == "PASS"
    payload["pro_review_evidence_sha256"] = "2" * 64
    evidence.write_text(json.dumps(payload, sort_keys=True) + "\n")
    with pytest.raises(contract.CanaryContractError, match="must not include Pro review evidence"):
        contract.authorization_check(
            evidence,
            contract.sha256(evidence),
            "2" * 64,
            "greenfield-canary-fast",
            reviewed_ref,
            reviewed,
        )


def test_reviewed_tree_rejects_descendant_head(monkeypatch: pytest.MonkeyPatch) -> None:
    reviewed = "1" * 40
    descendant = "2" * 40

    def fake_git(*args: str, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if args[:2] == ("cat-file", "-e"):
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if args[:2] == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(args, 0, (descendant + "\n").encode(), b"")
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(contract, "_git", fake_git)
    with pytest.raises(contract.CanaryContractError, match="exact reviewed operations commit"):
        contract.verify_reviewed_tree(reviewed, {"files": {}})


def test_transitive_greenfield_closure_is_fully_manifest_bound() -> None:
    result = closure.validate(ROOT, contract.OPS_MANIFEST)
    assert result["missing"] == []
    discovered = closure.discover(ROOT)
    for required in (
        "infra/staging/main.tf",
        "deploy/staging/Caddyfile",
        "scripts/wp08_security_group.py",
        "scripts/wp15_production_inventory.py",
        "scripts/wp15_rds_database.py",
        "scripts/wp15_rds_schema_owner.py",
    ):
        assert required in discovered
    assert result["candidate_bound_references"] == ["scripts/wp07_candidate.py"]


def test_transitive_greenfield_closure_rejects_unbound_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / closure.MANIFEST
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({"files": {}}) + "\n")
    monkeypatch.setattr(
        closure,
        "discover",
        lambda _root: {closure.MANIFEST, "scripts/unbound_operation.py"},
    )
    with pytest.raises(closure.ClosureError, match="scripts/unbound_operation.py"):
        closure.validate(tmp_path, manifest_path)


def test_transitive_greenfield_closure_extracts_and_rejects_real_workflow_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = closure.greenfield_workflow_text

    def workflow_with_unbound_reference(root: Path) -> str:
        return original(root) + "\n      - run: python3 scripts/muchen_candidate.py\n"

    monkeypatch.setattr(closure, "greenfield_workflow_text", workflow_with_unbound_reference)
    with pytest.raises(closure.ClosureError, match="scripts/muchen_candidate.py"):
        closure.validate(ROOT, contract.OPS_MANIFEST)


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
    no_secret_gate = workflow[
        workflow.index("  greenfield_authorize:\n") : workflow.index(
            "  greenfield_execution_authorize:\n"
        )
    ]
    owner_gate = workflow[
        workflow.index("  greenfield_execution_authorize:\n") : workflow.index(
            "  greenfield_canary:\n"
        )
    ]
    job = workflow[workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")]
    assert "environment:" not in no_secret_gate
    assert "${{ secrets." not in no_secret_gate
    assert "WP31_EXECUTION_AUTHORIZATION_B64" in owner_gate
    assert "VOLCENGINE_ACCESS_KEY" not in owner_gate
    assert "WP08_MIGRATION_DB_PASSWORD" not in owner_gate
    assert "needs.greenfield_authorize.outputs.reviewed_ops_commit_sha == github.sha" in owner_gate
    assert "needs.greenfield_authorize.outputs.reviewed_ops_ref == github.ref" in owner_gate
    assert "environment: production-canary-uat" in job
    assert "scripts/wp31_greenfield_canary.py review-check" in job
    assert job.index("review-check") < job.index("terraform init")
    assert "greenfield_execution_authorize" in job
    assert "greenfield-backup-restore" in job
    assert "greenfield-deploy" in job
    assert "greenfield-rollback" in job
    assert "WP31_CANARY_LEARNER_USER_IDS: ${{ secrets.WP31_CANARY_LEARNER_USER_IDS }}" in job


def test_fast_canary_uses_environment_approval_without_pro_review() -> None:
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text()
    assert "if [[ '${{ inputs.phase }}' == greenfield-canary-fast ]]; then" in workflow
    assert "pro_review_evidence_sha256=" in workflow
    assert "greenfield-canary-fast" in workflow


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
    assert "grep -qx 'RELEASE_MARKER=PRODUCTION_CANARY_UAT' secrets/web.env" in deploy
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
                "schema_version": 2,
                "application_candidate_sha": contract.EXPECTED_CANDIDATE,
                "closure_model": "REPOSITORY_GREENFIELD_TRANSITIVE_V2",
                "candidate_bound_references": ["scripts/wp07_candidate.py"],
                "manifest_self_binding": "PRO_EVIDENCE_SHA256_PLUS_EXACT_REVIEWED_COMMIT",
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
    expected = "journey_next_canary_20260901_c72fea5"
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
    web = (output / "secrets/web.env").read_text()
    assert "RELEASE_MARKER=PRODUCTION_CANARY_UAT\n" in api
    assert "RELEASE_MARKER=PRODUCTION_CANARY_UAT\n" in web
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
