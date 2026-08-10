import base64
import stat
from pathlib import Path

import pytest

from scripts import wp15_prepare_wartime as prepare


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
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_prepare_locks_new_database_candidate_and_production_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    output = tmp_path / "bundle"
    prepare.prepare(output, "postgres.internal.example", 5432)
    api = (output / "secrets/api.env").read_text()
    worker = (output / "secrets/worker.env").read_text()
    backup = (output / "secrets/backup.env").read_text()
    source = (output / "secrets/source-facts.env").read_text()
    deployment = (output / ".deployment.env").read_text()
    assert f"APP_RELEASE={prepare.CANDIDATE}" in api
    assert f"/{prepare.PRODUCTION_DATABASE}?sslmode=verify-full" in api
    assert prepare.ROLLBACK_DATABASE not in api
    assert prepare.PRESERVED_FAILED_DATABASE not in api
    assert prepare.STAGING_DATABASE not in api
    assert "FEISHU_OAUTH_REDIRECT_URI=https://journey.muchenai.com/auth/feishu/callback" in api
    assert "NOTIFICATION_RESULT_URL=https://journey.muchenai.com/app/result" in worker
    assert f"SOURCE_DATABASE={prepare.STAGING_DATABASE}" in backup
    assert f"TARGET_DATABASE={prepare.PRODUCTION_DATABASE}" in backup
    assert f"/{prepare.STAGING_DATABASE}?sslmode=verify-full" in source
    assert f"PRODUCTION_DATABASE={prepare.PRODUCTION_DATABASE}" in deployment
    assert stat.S_IMODE((output / "secrets/backup.env").stat().st_mode) == 0o600


def test_prepare_rejects_reused_wartime_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setenv("WP15_BACKUP_KEY", "production-session-secret-independent-001")
    with pytest.raises(prepare.PrepareWartimeError, match="must be independent"):
        prepare.prepare(tmp_path / "bundle", "postgres.internal.example", 5432)
