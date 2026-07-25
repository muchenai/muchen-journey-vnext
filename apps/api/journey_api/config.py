from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "local"
    app_release: str = "dev"
    config_schema_version: int = 1
    database_url: str = "postgresql+psycopg://journey_next:journey_next_dev@localhost:5432/journey_next_dev"
    allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1"]
    allow_fixture_identity: bool = False
    session_secret: str = "journey-next-local-session-secret-change-me"
    invite_secret: str = "journey-next-local-invite-secret-change-me"
    import_signing_key: str = "journey-next-local-import-signing-key-change-me"
    session_ttl_hours: int = 8
    join_context_ttl_minutes: int = 15
    invite_exchange_limit: int = 10
    oauth_attempt_limit: int = 20
    oauth_state_ttl_minutes: int = 10
    identity_subject_secret: str = "journey-next-local-identity-subject-secret"
    feishu_oauth_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_oauth_redirect_uri: str = "http://localhost:3000/auth/feishu/callback"
    attachment_storage_root: str = "/tmp/journey-next-attachments"

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

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
        if not 5 <= self.join_context_ttl_minutes <= 30:
            raise ValueError("JOIN_CONTEXT_TTL_MINUTES must be between 5 and 30")
        if not 3 <= self.invite_exchange_limit <= 100:
            raise ValueError("INVITE_EXCHANGE_LIMIT must be between 3 and 100")
        if not 5 <= self.oauth_attempt_limit <= 100:
            raise ValueError("OAUTH_ATTEMPT_LIMIT must be between 5 and 100")
        if not 5 <= self.oauth_state_ttl_minutes <= 15:
            raise ValueError("OAUTH_STATE_TTL_MINUTES must be between 5 and 15")
        if self.app_env in {"staging", "production"} and not self.feishu_oauth_enabled:
            raise ValueError("FEISHU_OAUTH_ENABLED must be true outside local/test")
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
        if self.config_schema_version != 1:
            raise ValueError("CONFIG_SCHEMA_VERSION must be the approved version 1")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
