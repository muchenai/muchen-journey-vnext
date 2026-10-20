from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Configuration shared by API and worker database clients only.

    Keeping this narrow prevents the worker from needing API identity and import
    secrets merely to construct its SQLAlchemy engine.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = (
        "postgresql+psycopg://journey_next:journey_next_dev@"
        "localhost:5432/journey_next_dev"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 5

    @model_validator(mode="after")
    def database_pool_is_bounded(self) -> "DatabaseSettings":
        if not 1 <= self.db_pool_size <= 25:
            raise ValueError("DB_POOL_SIZE must be between 1 and 25")
        if not 0 <= self.db_max_overflow <= 25:
            raise ValueError("DB_MAX_OVERFLOW must be between 0 and 25")
        if self.db_pool_size + self.db_max_overflow > 30:
            raise ValueError("database pool may open at most 30 connections per process")
        if not 1 <= self.db_pool_timeout_seconds <= 30:
            raise ValueError("DB_POOL_TIMEOUT_SECONDS must be between 1 and 30")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "local"
    app_release: str = "dev"
    config_schema_version: int = 3
    database_url: str = "postgresql+psycopg://journey_next:journey_next_dev@localhost:5432/journey_next_dev"
    allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1"]
    allow_fixture_identity: bool = False
    release_marker: str = "DEVELOPMENT"
    canary_learner_user_ids: Annotated[list[UUID], NoDecode] = Field(
        default_factory=list
    )
    session_secret: str = "journey-next-local-session-secret-change-me"
    invite_secret: str = "journey-next-local-invite-secret-change-me"
    import_signing_key: str = "journey-next-local-import-signing-key-change-me"
    session_ttl_hours: int = 8
    learner_session_ttl_hours: int = 24
    join_context_ttl_minutes: int = 15
    invite_exchange_limit: int = 10
    oauth_attempt_limit: int = 20
    oauth_state_ttl_minutes: int = 10
    phone_otp_enabled: bool = False
    phone_otp_provider: str = "DISABLED"
    phone_otp_ttl_minutes: int = 5
    phone_otp_resend_cooldown_seconds: int = 60
    password_login_enabled: bool = False
    ai_self_check_enabled: bool = False
    # Verify the current human owner before the one-shot title comment.
    ai_comment_mention_owner: bool = False
    ai_base_url: str = ""
    ai_api_key: str = Field(default="", repr=False)
    ai_api_key_file: str = ""
    ai_model: str = "deepseek-v4-pro"
    ai_feishu_app_id: str = ""
    ai_feishu_app_secret: str = Field(default="", repr=False)
    ai_feishu_app_secret_file: str = ""

    @model_validator(mode="after")
    def validate_ai(self) -> "Settings":
        for value_field in ("ai_api_key", "ai_feishu_app_secret"):
            filename = getattr(self, value_field + "_file")
            if not filename:
                continue
            if getattr(self, value_field):
                raise ValueError("Configure an AI secret value or file, not both")
            path = Path(filename)
            try:
                if not path.is_absolute() or not path.is_file() or path.is_symlink():
                    raise ValueError("AI secret file must be an absolute regular file")
                if path.stat().st_size > 4096:
                    raise ValueError("AI secret file is too large")
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                raise ValueError("AI secret file is unavailable") from None
            if not value or any(char.isspace() for char in value):
                raise ValueError("AI secret file must contain one nonempty credential")
            setattr(self, value_field, value)
        if bool(self.ai_feishu_app_id) != bool(self.ai_feishu_app_secret):
            raise ValueError("AI Feishu app ID and secret must be configured together")
        if self.ai_self_check_enabled:
            if self.app_env in {"production", "staging"}:
                if (not self.ai_api_key_file or not self.ai_feishu_app_secret_file
                        or not self.ai_feishu_app_id or not self.ai_comment_mention_owner):
                    raise ValueError("Production AI requires mounted secrets, a dedicated document app and owner mentions")
            endpoint = urlsplit(self.ai_base_url)
            if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username
                    or endpoint.password or endpoint.query or endpoint.fragment
                    or not self.ai_api_key or not self.ai_model):
                raise ValueError("AI configuration requires an HTTPS endpoint, key and model")
        return self

    volcengine_sms_access_key_id: str = ""
    volcengine_sms_secret_access_key: str = ""
    volcengine_sms_account: str = ""
    volcengine_sms_sign: str = ""
    volcengine_sms_template_id: str = ""
    volcengine_sms_template_code_param: str = "code"
    identity_subject_secret: str = "journey-next-local-identity-subject-secret"
    feishu_oauth_enabled: bool = False
    feishu_learner_registration_enabled: bool = False
    feishu_learner_organization_id: UUID | None = None
    feishu_learner_reviewer_id: UUID | None = None
    feishu_learner_shared_reviewer_ids: Annotated[list[UUID], NoDecode] = Field(default_factory=list)
    reviewer_excluded_user_ids: Annotated[list[UUID], NoDecode] = Field(default_factory=list)
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_oauth_redirect_uri: str = "http://localhost:3000/auth/feishu/callback"
    attachment_storage_root: str = "/tmp/journey-next-attachments"
    attachments_enabled: bool = False
    attachment_storage_backend: str = "LOCAL"
    attachment_upload_ttl_seconds: int = 300
    attachment_download_ttl_seconds: int = 60
    attachment_scanner_backend: str = "TEST"
    tos_endpoint: str = ""
    tos_region: str = ""
    tos_bucket: str = ""
    tos_ecs_role_name: str = ""
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 15
    notification_channel: str = "LOCAL_TEST"
    notification_recipients_enabled: bool = False
    notification_recipient_key: str = ""

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("canary_learner_user_ids", mode="before")
    @classmethod
    def split_canary_learner_user_ids(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("feishu_learner_shared_reviewer_ids", "reviewer_excluded_user_ids", mode="before")
    @classmethod
    def split_reviewer_ids(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def reviewer_pool_is_explicit(self) -> "Settings":
        pool = self.feishu_learner_shared_reviewer_ids
        excluded = self.reviewer_excluded_user_ids
        if len(pool) != len(set(pool)) or len(excluded) != len(set(excluded)):
            raise ValueError("Reviewer IDs must be unique")
        if set(pool) & set(excluded):
            raise ValueError("Excluded reviewers cannot be in the shared pool")
        if pool and (not self.feishu_learner_organization_id or self.feishu_learner_reviewer_id not in pool):
            raise ValueError("Shared review requires an organization and a default reviewer in the pool")
        return self

    @field_validator("app_env")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        if value not in {"local", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be local, test, staging, or production")
        return value

    @model_validator(mode="after")
    def fixture_identity_is_never_nonlocal(self) -> "Settings":
        if self.allow_fixture_identity and self.app_env not in {"local", "test"}:
            raise ValueError("ALLOW_FIXTURE_IDENTITY may only be enabled in local/test")
        if self.release_marker not in {
            "DEVELOPMENT",
            "CONTROLLED_ALPHA",
            "PRODUCTION_CANARY_UAT",
        }:
            raise ValueError("RELEASE_MARKER is unsupported")
        canary_ids = set(self.canary_learner_user_ids)
        if len(canary_ids) != len(self.canary_learner_user_ids):
            raise ValueError("CANARY_LEARNER_USER_IDS must be unique")
        if len(canary_ids) > 8:
            raise ValueError("CANARY_LEARNER_USER_IDS may contain at most 8 learners")
        if canary_ids and self.release_marker != "PRODUCTION_CANARY_UAT":
            raise ValueError(
                "CANARY_LEARNER_USER_IDS require RELEASE_MARKER=PRODUCTION_CANARY_UAT"
            )
        if self.release_marker == "PRODUCTION_CANARY_UAT":
            if self.app_env != "production":
                raise ValueError("PRODUCTION_CANARY_UAT requires APP_ENV=production")
            if self.allow_fixture_identity:
                raise ValueError("PRODUCTION_CANARY_UAT forbids fixture identity")
        if self.app_env in {"staging", "production"}:
            insecure_defaults = {
                "journey-next-local-session-secret-change-me",
                "journey-next-local-invite-secret-change-me",
                "journey-next-local-import-signing-key-change-me",
                "journey-next-local-identity-subject-secret",
            }
            if (
                self.session_secret in insecure_defaults
                or self.invite_secret in insecure_defaults
                or self.import_signing_key in insecure_defaults
                or self.identity_subject_secret in insecure_defaults
            ):
                raise ValueError("vNext secrets must be independently configured outside local/test")
        if len(self.session_secret) < 32 or len(self.invite_secret) < 32:
            raise ValueError("vNext identity secrets must contain at least 32 characters")
        if len(self.import_signing_key) < 32:
            raise ValueError("IMPORT_SIGNING_KEY must contain at least 32 characters")
        if len(self.identity_subject_secret) < 32:
            raise ValueError("IDENTITY_SUBJECT_SECRET must contain at least 32 characters")
        if self.session_secret == self.invite_secret:
            raise ValueError("SESSION_SECRET and INVITE_SECRET must be independent")
        identity_secrets = {
            self.session_secret,
            self.invite_secret,
            self.identity_subject_secret,
        }
        if len(identity_secrets) != 3 or self.import_signing_key in identity_secrets:
            raise ValueError("vNext identity and import secrets must be independent")
        if not 1 <= self.session_ttl_hours <= 24:
            raise ValueError("SESSION_TTL_HOURS must be between 1 and 24")
        if not 8 <= self.learner_session_ttl_hours <= 24:
            raise ValueError("LEARNER_SESSION_TTL_HOURS must be between 8 and 24")
        if not 5 <= self.join_context_ttl_minutes <= 30:
            raise ValueError("JOIN_CONTEXT_TTL_MINUTES must be between 5 and 30")
        if not 3 <= self.invite_exchange_limit <= 100:
            raise ValueError("INVITE_EXCHANGE_LIMIT must be between 3 and 100")
        if not 5 <= self.oauth_attempt_limit <= 100:
            raise ValueError("OAUTH_ATTEMPT_LIMIT must be between 5 and 100")
        if not 5 <= self.oauth_state_ttl_minutes <= 15:
            raise ValueError("OAUTH_STATE_TTL_MINUTES must be between 5 and 15")
        if self.phone_otp_provider not in {"DISABLED", "LOCAL_TEST", "VOLCENGINE"}:
            raise ValueError("PHONE_OTP_PROVIDER must be DISABLED, LOCAL_TEST, or VOLCENGINE")
        if self.phone_otp_provider == "LOCAL_TEST" and self.app_env not in {"local", "test"}:
            raise ValueError("LOCAL_TEST phone OTP may only be used locally")
        if self.phone_otp_enabled and self.phone_otp_provider == "DISABLED":
            raise ValueError("enabled phone OTP requires a provider")
        if not 2 <= self.phone_otp_ttl_minutes <= 10:
            raise ValueError("PHONE_OTP_TTL_MINUTES must be between 2 and 10")
        if not 30 <= self.phone_otp_resend_cooldown_seconds <= 300:
            raise ValueError("PHONE_OTP_RESEND_COOLDOWN_SECONDS must be between 30 and 300")
        if self.phone_otp_enabled and self.phone_otp_provider == "VOLCENGINE":
            required_sms_settings = {
                "VOLCENGINE_SMS_ACCESS_KEY_ID": self.volcengine_sms_access_key_id,
                "VOLCENGINE_SMS_SECRET_ACCESS_KEY": self.volcengine_sms_secret_access_key,
                "VOLCENGINE_SMS_ACCOUNT": self.volcengine_sms_account,
                "VOLCENGINE_SMS_SIGN": self.volcengine_sms_sign,
                "VOLCENGINE_SMS_TEMPLATE_ID": self.volcengine_sms_template_id,
                "VOLCENGINE_SMS_TEMPLATE_CODE_PARAM": self.volcengine_sms_template_code_param,
            }
            missing = [name for name, value in required_sms_settings.items() if not value.strip()]
            if missing:
                raise ValueError(
                    "VOLCENGINE phone OTP requires: " + ", ".join(missing)
                )
            if not self.volcengine_sms_template_code_param.isidentifier():
                raise ValueError("VOLCENGINE_SMS_TEMPLATE_CODE_PARAM must be an identifier")
        if self.app_env in {"staging", "production"} and not self.feishu_oauth_enabled:
            raise ValueError("FEISHU_OAUTH_ENABLED must be true outside local/test")
        if self.attachment_storage_backend not in {"LOCAL", "TOS"}:
            raise ValueError("ATTACHMENT_STORAGE_BACKEND must be LOCAL or TOS")
        if self.attachment_scanner_backend not in {"TEST", "CLAMAV"}:
            raise ValueError("ATTACHMENT_SCANNER_BACKEND must be TEST or CLAMAV")
        if self.notification_channel not in {"LOCAL_TEST", "FEISHU"}:
            raise ValueError("NOTIFICATION_CHANNEL must be LOCAL_TEST or FEISHU")
        if self.app_env in {"local", "test"} and self.notification_channel != "LOCAL_TEST":
            raise ValueError("local/test notification channel must use LOCAL_TEST")
        if self.app_env in {"staging", "production"} and self.notification_channel != "FEISHU":
            raise ValueError("nonlocal notification channel must use FEISHU")
        if self.notification_recipients_enabled:
            from journey_api.notification_recipients import decode_recipient_key

            decode_recipient_key(self.notification_recipient_key)
        if self.release_marker == "PRODUCTION_CANARY_UAT":
            if self.notification_recipients_enabled:
                raise ValueError("Canary notification recipients must be disabled")
        elif self.app_env == "production" and not self.notification_recipients_enabled:
            raise ValueError("production notification recipients must be enabled")
        if not 60 <= self.attachment_upload_ttl_seconds <= 900:
            raise ValueError("ATTACHMENT_UPLOAD_TTL_SECONDS must be between 60 and 900")
        if not 30 <= self.attachment_download_ttl_seconds <= 300:
            raise ValueError("ATTACHMENT_DOWNLOAD_TTL_SECONDS must be between 30 and 300")
        if not 1 <= self.clamav_timeout_seconds <= 30:
            raise ValueError("CLAMAV_TIMEOUT_SECONDS must be between 1 and 30")
        if self.attachments_enabled and self.app_env in {"staging", "production"}:
            if self.attachment_storage_backend != "TOS":
                raise ValueError("nonlocal attachment storage must use TOS")
            if self.attachment_scanner_backend != "CLAMAV":
                raise ValueError("nonlocal attachment scanning must use CLAMAV")
            if not all(
                (self.tos_endpoint, self.tos_region, self.tos_bucket, self.tos_ecs_role_name)
            ):
                raise ValueError("TOS endpoint, region, bucket, and ECS role are required")
        elif self.attachments_enabled and (
            self.attachment_storage_backend != "LOCAL"
            or self.attachment_scanner_backend != "TEST"
        ):
            raise ValueError("local/test attachments must use isolated local test adapters")
        if self.feishu_oauth_enabled:
            if not self.feishu_app_id or len(self.feishu_app_secret) < 16:
                raise ValueError("independent Feishu app credentials must be configured")
            redirect = urlsplit(self.feishu_oauth_redirect_uri)
            if (
                redirect.path != "/auth/feishu/callback"
                or redirect.query
                or redirect.fragment
                or redirect.username
                or redirect.password
                or not redirect.hostname
            ):
                raise ValueError("FEISHU_OAUTH_REDIRECT_URI must be the exact callback URL")
            if self.app_env in {"staging", "production"} and redirect.scheme != "https":
                raise ValueError("Feishu callback must use HTTPS outside local/test")
            if self.app_env in {"local", "test"} and redirect.scheme not in {"http", "https"}:
                raise ValueError("Feishu callback must use HTTP or HTTPS")
        if self.config_schema_version != 3:
            raise ValueError("CONFIG_SCHEMA_VERSION must be the approved version 3")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
