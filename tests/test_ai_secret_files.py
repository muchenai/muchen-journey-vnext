import pytest

from journey_api.config import Settings


def configuration(tmp_path):
    key = tmp_path / "key"
    secret = tmp_path / "secret"
    key.write_text("fake-ai-test-key-value")
    secret.write_text("fake-document-test-secret")
    return {
        "app_env": "production", "allow_fixture_identity": False,
        "session_secret": "session-" * 8, "invite_secret": "invite-" * 8,
        "import_signing_key": "import-" * 8, "identity_subject_secret": "identity-" * 8,
        "release_marker": "PRODUCTION_CANARY_UAT",
        "notification_channel": "FEISHU", "notification_recipients_enabled": False,
        "attachments_enabled": False,
        "phone_otp_enabled": False, "phone_otp_provider": "DISABLED",
        "feishu_oauth_enabled": True, "feishu_app_id": "test-login-app",
        "feishu_app_secret": "fake-login-secret-value",
        "feishu_oauth_redirect_uri": "https://journey.example.test/auth/feishu/callback",
        "ai_self_check_enabled": True, "ai_comment_mention_owner": True,
        "ai_base_url": "https://ai.example.test/v1", "ai_model": "test-model",
        "ai_feishu_app_id": "test-document-app",
        "ai_api_key": "", "ai_feishu_app_secret": "",
        "ai_api_key_file": str(key), "ai_feishu_app_secret_file": str(secret),
    }


def test_production_uses_mounted_credentials_without_printing_values(tmp_path):
    settings = Settings(**configuration(tmp_path))
    assert settings.ai_api_key == "fake-ai-test-key-value"
    assert settings.ai_feishu_app_secret == "fake-document-test-secret"
    assert settings.ai_api_key not in repr(settings)
    assert settings.ai_feishu_app_secret not in repr(settings)


@pytest.mark.parametrize("field", ["ai_api_key_file", "ai_feishu_app_secret_file", "ai_feishu_app_id", "ai_comment_mention_owner"])
def test_production_rejects_incomplete_secure_configuration(tmp_path, field):
    values = configuration(tmp_path)
    values[field] = False if field.endswith("owner") else ""
    with pytest.raises(ValueError):
        Settings(**values)


@pytest.mark.parametrize("content", ["", "two secrets", "x" * 4097])
def test_secret_files_reject_empty_multivalue_or_oversized_content(tmp_path, content):
    values = configuration(tmp_path)
    (tmp_path / "key").write_text(content)
    with pytest.raises(ValueError):
        Settings(**values)


def test_secret_sources_cannot_be_ambiguous(tmp_path):
    values = configuration(tmp_path)
    values["ai_api_key"] = "another-secret-value"
    with pytest.raises(ValueError, match="not both"):
        Settings(**values)


def test_missing_secret_file_is_configuration_failure(tmp_path):
    values = configuration(tmp_path)
    values["ai_api_key_file"] = str(tmp_path / "missing")
    with pytest.raises(ValueError):
        Settings(**values)
