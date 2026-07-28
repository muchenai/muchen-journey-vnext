import pytest
from pydantic import ValidationError

from journey_api.config import Settings


def test_fixture_identity_configuration_fails_closed_outside_local_test():
    with pytest.raises(ValidationError, match="ALLOW_FIXTURE_IDENTITY"):
        Settings(app_env="production", allow_fixture_identity=True)


def test_nonlocal_identity_requires_distinct_vnext_secrets():
    with pytest.raises(ValidationError, match="independently configured"):
        Settings(app_env="production", allow_fixture_identity=False)
    with pytest.raises(ValidationError, match="must be independent"):
        Settings(
            app_env="staging",
            allow_fixture_identity=False,
            session_secret="same-secret-value-that-is-long-enough-12345",
            invite_secret="same-secret-value-that-is-long-enough-12345",
            import_signing_key="staging-import-signing-key-example-123456",
            identity_subject_secret="staging-identity-subject-key-example-123456",
            feishu_oauth_enabled=True,
            feishu_app_id="cli_staging",
            feishu_app_secret="staging-feishu-secret-123",
            feishu_oauth_redirect_uri="https://staging.example.test/auth/feishu/callback",
        )
    configured = Settings(
        app_env="production",
        allow_fixture_identity=False,
        session_secret="production-session-secret-example-123456",
        invite_secret="production-invite-secret-example-1234567",
        import_signing_key="production-import-signing-key-example-123456",
        identity_subject_secret="production-identity-subject-key-example-123456",
        feishu_oauth_enabled=True,
        feishu_app_id="cli_production",
        feishu_app_secret="production-feishu-secret-123",
        feishu_oauth_redirect_uri="https://journey.example.test/auth/feishu/callback",
        attachments_enabled=True,
        attachment_storage_backend="TOS",
        attachment_scanner_backend="CLAMAV",
        tos_endpoint="tos-cn-beijing.volces.com",
        tos_region="cn-beijing",
        tos_bucket="journey-private-test",
        tos_ecs_role_name="journey-runtime-test",
        notification_channel="FEISHU",
        notification_recipients_enabled=True,
        notification_recipient_key="bm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm4",
    )
    assert configured.allow_fixture_identity is False


def test_nonlocal_attachment_dependencies_fail_closed():
    common = {
        "app_env": "staging",
        "allow_fixture_identity": False,
        "session_secret": "staging-session-secret-example-123456789",
        "invite_secret": "staging-invite-secret-example-1234567890",
        "import_signing_key": "staging-import-signing-key-example-123456",
        "identity_subject_secret": "staging-identity-subject-key-example-123456",
        "feishu_oauth_enabled": True,
        "feishu_app_id": "cli_staging",
        "feishu_app_secret": "staging-feishu-secret-123",
        "feishu_oauth_redirect_uri": "https://staging.example.test/auth/feishu/callback",
        "attachments_enabled": True,
        "notification_channel": "FEISHU",
    }
    with pytest.raises(ValidationError, match="must use TOS"):
        Settings(**common)
    with pytest.raises(ValidationError, match="must use CLAMAV"):
        Settings(**common, attachment_storage_backend="TOS")
    with pytest.raises(ValidationError, match="ECS role are required"):
        Settings(
            **common,
            attachment_storage_backend="TOS",
            attachment_scanner_backend="CLAMAV",
        )


def test_nonlocal_disabled_attachments_do_not_require_storage_or_scanner():
    configured = Settings(
        app_env="staging",
        allow_fixture_identity=False,
        session_secret="staging-session-secret-example-123456789",
        invite_secret="staging-invite-secret-example-1234567890",
        import_signing_key="staging-import-signing-key-example-123456",
        identity_subject_secret="staging-identity-subject-key-example-123456",
        feishu_oauth_enabled=True,
        feishu_app_id="cli_staging",
        feishu_app_secret="staging-feishu-secret-123",
        feishu_oauth_redirect_uri="https://staging.example.test/auth/feishu/callback",
        attachments_enabled=False,
        notification_channel="FEISHU",
    )
    assert configured.attachment_storage_backend == "LOCAL"
    assert configured.attachment_scanner_backend == "TEST"


def test_nonlocal_disabled_attachments_still_reject_local_identity_secrets():
    with pytest.raises(ValidationError, match="independently configured"):
        Settings(
            app_env="staging",
            allow_fixture_identity=False,
            feishu_oauth_enabled=True,
            feishu_app_id="cli_staging",
            feishu_app_secret="staging-feishu-secret-123",
            feishu_oauth_redirect_uri="https://staging.example.test/auth/feishu/callback",
            attachments_enabled=False,
            notification_channel="FEISHU",
        )


def test_config_schema_version_is_fail_closed():
    with pytest.raises(ValidationError, match="CONFIG_SCHEMA_VERSION"):
        Settings(config_schema_version=1)
