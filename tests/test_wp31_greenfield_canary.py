import base64
import json
import os
from pathlib import Path

import pytest

from scripts import wp15_rds_database, wp15_rds_schema_owner
from scripts import wp31_greenfield_canary as contract
from scripts import wp31_prepare_greenfield_canary as prepare


ROOT = Path(__file__).resolve().parents[1]


def test_contract_is_exact_and_independent_review_remains_pending() -> None:
    value = contract.load()
    assert value["application_candidate_sha"] == prepare.CANDIDATE
    assert value["scope"]["max_allowlisted_learners"] == 8
    assert value["scope"]["worker_started"] is False
    assert value["scope"]["release_go"] is False
    assert value["pro_review"]["status"] == "PENDING"
    with pytest.raises(contract.CanaryContractError, match="not PASS"):
        contract.review_check("0" * 64)


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
    assert "scripts/wp31_greenfield_canary.py review-check" in job
    assert job.index("review-check") < job.index("terraform init")
    assert "greenfield-backup-restore" in job
    assert "greenfield-deploy" in job
    assert "greenfield-rollback" in job
    assert "WP31_CANARY_LEARNER_USER_IDS: ${{ secrets.WP31_CANARY_LEARNER_USER_IDS }}" in job


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
