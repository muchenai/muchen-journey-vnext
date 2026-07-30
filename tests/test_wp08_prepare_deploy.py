import base64
import stat
from pathlib import Path

import pytest

import scripts.wp08_prepare_deploy as prepare


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "WP08_MIGRATION_DB_PASSWORD": "Migration-Password-123!",
        "WP08_RUNTIME_DB_PASSWORD": "Runtime-Password-456!",
        "WP08_SESSION_SECRET": "session-secret-independent-000000001",
        "WP08_INVITE_SECRET": "invite-secret-independent-0000000002",
        "WP08_IMPORT_SIGNING_KEY": "import-key-independent-00000000003",
        "WP09_IDENTITY_SUBJECT_SECRET": "identity-subject-secret-independent-004",
        "WP09_FEISHU_APP_ID": "cli_test_independent",
        "WP09_FEISHU_APP_SECRET": "feishu-app-secret-independent-05",
        "WP11_NOTIFICATION_RECIPIENT_KEY": base64.urlsafe_b64encode(
            b"notification-recipient-key-00001"
        ).decode(),
        "WP11_FEISHU_APP_ID": "cli_notification_independent",
        "WP11_FEISHU_APP_SECRET": "notification-app-secret-independent-06",
        "WP08_RDS_CA_PEM_B64": base64.b64encode(
            b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"
        ).decode(),
        "WP08_ACME_EMAIL": "ops@example.com",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_prepare_writes_private_independent_environment_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    output = tmp_path / "bundle"
    prepare.prepare(output, "postgres.internal.example", 5432)
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    ca_path = output / "secrets" / "volcengine-rds-ca.pem"
    private_paths = [
        path for path in (output / "secrets").iterdir() if path != ca_path
    ]
    for path in [*private_paths, output / ".deployment.env"]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(ca_path.stat().st_mode) == 0o444
    api_env = (output / "secrets/api.env").read_text()
    worker_env = (output / "secrets/worker.env").read_text()
    assert "NOTIFICATION_ADAPTER=FEISHU" in worker_env
    assert "OBSERVABILITY_SNAPSHOT_SECONDS=60" in worker_env
    assert "FEISHU_NOTIFICATION_APP_ID=cli_notification_independent" in worker_env
    assert (
        "NOTIFICATION_RESULT_URL=https://staging-vnext.muchenai.com/app/result"
        in worker_env
    )
    assert "NOTIFICATION_RECIPIENTS_ENABLED=true" in api_env
    assert "DB_POOL_SIZE=20" in api_env
    assert "DB_MAX_OVERFLOW=5" in api_env
    assert "DB_POOL_TIMEOUT_SECONDS=5" in api_env
    assert "DB_POOL_SIZE=2" in worker_env
    assert "DB_MAX_OVERFLOW=1" in worker_env
    assert "DB_POOL_TIMEOUT_SECONDS=5" in worker_env
    api_recipient_key = next(
        line
        for line in api_env.splitlines()
        if line.startswith("NOTIFICATION_RECIPIENT_KEY=")
    )
    worker_recipient_key = next(
        line
        for line in worker_env.splitlines()
        if line.startswith("NOTIFICATION_RECIPIENT_KEY=")
    )
    assert api_recipient_key == worker_recipient_key
    assert "ALLOW_FIXTURE_IDENTITY=false" in (output / "secrets/api.env").read_text()
    assert "FEISHU_OAUTH_ENABLED=true" in (output / "secrets/api.env").read_text()
    assert "CONFIG_SCHEMA_VERSION=3" in (output / "secrets/api.env").read_text()
    assert "ATTACHMENTS_ENABLED=false" in (output / "secrets/api.env").read_text()
    assert (
        "FEISHU_OAUTH_REDIRECT_URI=https://staging-vnext.muchenai.com/auth/feishu/callback"
        in (output / "secrets/api.env").read_text()
    )
    assert "Migration-Password" not in (output / "secrets/api.env").read_text()
    deployment = (output / ".deployment.env").read_text()
    assert f"CANDIDATE_COMMIT={prepare.CANDIDATE}" in deployment
    for image in prepare.IMAGES.values():
        assert image in deployment


def test_prepare_rejects_reused_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    configure(monkeypatch)
    monkeypatch.setenv("WP08_RUNTIME_DB_PASSWORD", "Migration-Password-123!")
    with pytest.raises(prepare.PrepareError, match="independent"):
        prepare.prepare(tmp_path / "bundle", "postgres.internal.example", 5432)


def test_prepare_rejects_reused_notification_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    monkeypatch.setenv("WP11_FEISHU_APP_ID", "cli_test_independent")
    with pytest.raises(prepare.PrepareError, match="notification app must be independent"):
        prepare.prepare(tmp_path / "bundle", "postgres.internal.example", 5432)


def test_prepare_rejects_invalid_notification_recipient_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    configure(monkeypatch)
    monkeypatch.setenv(
        "WP11_NOTIFICATION_RECIPIENT_KEY",
        base64.urlsafe_b64encode(b"too-short").decode(),
    )
    with pytest.raises(prepare.PrepareError, match="exactly 32 bytes"):
        prepare.prepare(tmp_path / "bundle", "postgres.internal.example", 5432)
