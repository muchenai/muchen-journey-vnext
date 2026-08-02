import base64
import stat
from pathlib import Path

import pytest

import scripts.wp15_prepare_production as prepare


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "WP08_MIGRATION_DB_PASSWORD": "Migration-Password-123!",
        "WP08_RUNTIME_DB_PASSWORD": "Runtime-Password-456!",
        "WP15_SESSION_SECRET": "production-session-secret-independent-001",
        "WP15_INVITE_SECRET": "production-invite-secret-independent-0002",
        "WP15_IMPORT_SIGNING_KEY": "production-import-secret-independent-03",
        "WP15_BACKUP_KEY": "production-backup-secret-independent-004",
        "WP09_IDENTITY_SUBJECT_SECRET": "identity-subject-secret-independent-005",
        "WP09_FEISHU_APP_ID": "cli_identity_independent",
        "WP09_FEISHU_APP_SECRET": "identity-app-secret-independent-006",
        "WP11_NOTIFICATION_RECIPIENT_KEY": base64.urlsafe_b64encode(
            b"notification-recipient-key-00001"
        ).decode(),
        "WP11_FEISHU_APP_ID": "cli_notification_independent",
        "WP11_FEISHU_APP_SECRET": "notification-app-secret-independent-07",
        "WP08_RDS_CA_PEM_B64": base64.b64encode(
            b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"
        ).decode(),
        "WP08_ACME_EMAIL": "ops@example.com",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_prepare_locks_production_hosts_database_and_remote_relative_backup_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    output = tmp_path / "bundle"
    prepare.prepare(output, "postgres.internal.example", 5432)
    api = (output / "secrets/api.env").read_text()
    worker = (output / "secrets/worker.env").read_text()
    backup = (output / "secrets/backup.env").read_text()
    edge = (output / "edge.env").read_text()
    assert "APP_ENV=production" in api
    assert "journey_next_restore_20260803" in api
    assert "journey_next_production" not in api
    assert "journey_next_staging" not in api
    assert "ALLOWED_HOSTS=journey.muchenai.com,production-api,localhost,127.0.0.1" in api
    assert "FEISHU_OAUTH_REDIRECT_URI=https://journey.muchenai.com/auth/feishu/callback" in api
    assert "NOTIFICATION_RESULT_URL=https://journey.muchenai.com/app/result" in worker
    assert "SOURCE_DATABASE=journey_next_staging" in backup
    assert "TARGET_DATABASE=journey_next_restore_20260803" in backup
    assert "CA_PATH=" not in backup
    assert str(tmp_path) not in backup
    assert "STAGING_HOST=staging-vnext.muchenai.com" in edge
    assert "PRODUCTION_HOST=journey.muchenai.com" in edge
    assert stat.S_IMODE((output / "secrets/backup.env").stat().st_mode) == 0o600


def test_prepare_rejects_reused_production_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    monkeypatch.setenv(
        "WP15_BACKUP_KEY", "production-session-secret-independent-001"
    )
    with pytest.raises(prepare.PrepareError, match="must be independent"):
        prepare.prepare(tmp_path / "bundle", "postgres.internal.example", 5432)


def test_prepare_can_target_exact_temporary_restore_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    output = tmp_path / "bundle"
    prepare.prepare(
        output,
        "postgres.internal.example",
        5432,
        prepare.FAILED_RESTORE_DATABASE,
    )
    backup = (output / "secrets/backup.env").read_text()
    target_facts = (output / "secrets/target-facts.env").read_text()
    assert f"TARGET_DATABASE={prepare.FAILED_RESTORE_DATABASE}" in backup
    assert f"/{prepare.FAILED_RESTORE_DATABASE}?sslmode=verify-full" in target_facts
    assert "TARGET_DATABASE=journey_next_restore_20260803" not in backup
