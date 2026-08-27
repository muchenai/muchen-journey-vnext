from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from journey_api import auth
from journey_api.auth import (
    Actor,
    enforce_canary_invite_target,
    enforce_canary_learner_scope,
)
from journey_api.config import Settings
from journey_api.errors import ApiError
from journey_api.models import Role


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "allow_fixture_identity": False,
        "release_marker": "PRODUCTION_CANARY_UAT",
        "session_secret": "production-session-secret-example-123456",
        "invite_secret": "production-invite-secret-example-1234567",
        "import_signing_key": "production-import-signing-key-example-123456",
        "identity_subject_secret": "production-identity-subject-key-example-123456",
        "feishu_oauth_enabled": True,
        "feishu_app_id": "cli_production",
        "feishu_app_secret": "production-feishu-secret-123",
        "feishu_oauth_redirect_uri": (
            "https://journey.example.test/auth/feishu/callback"
        ),
        "attachments_enabled": False,
        "notification_channel": "FEISHU",
        "notification_recipients_enabled": True,
        "notification_recipient_key": (
            "bm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm4"
        ),
    }
    values.update(overrides)
    return Settings(**values)


def actor(role: Role, user_id: UUID | None = None) -> Actor:
    return Actor(
        id=user_id or uuid4(),
        organization_id=uuid4(),
        role=role,
        display_name="Canary test actor",
    )


def test_canary_defaults_to_zero_learner_access_and_preserves_staff_access(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = production_settings(canary_learner_user_ids=[])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    with pytest.raises(ApiError) as denied:
        enforce_canary_learner_scope(actor(Role.LEARNER))
    assert denied.value.status_code == 403
    assert denied.value.code == "CANARY_ACCESS_DENIED"

    reviewer = actor(Role.REVIEWER)
    operator = actor(Role.OPERATOR)
    assert enforce_canary_learner_scope(reviewer) is reviewer
    assert enforce_canary_learner_scope(operator) is operator


def test_canary_allows_only_configured_learner(
    monkeypatch: pytest.MonkeyPatch,
):
    allowed_id = uuid4()
    settings = production_settings(canary_learner_user_ids=[allowed_id])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    allowed = actor(Role.LEARNER, allowed_id)
    assert enforce_canary_learner_scope(allowed) is allowed
    with pytest.raises(ApiError, match="受控内测"):
        enforce_canary_learner_scope(actor(Role.LEARNER))


def test_canary_blocks_untargeted_and_non_allowlisted_invites(
    monkeypatch: pytest.MonkeyPatch,
):
    allowed_id = uuid4()
    settings = production_settings(canary_learner_user_ids=[allowed_id])
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    enforce_canary_invite_target(allowed_id)
    for denied_target in (None, uuid4()):
        with pytest.raises(ApiError) as denied:
            enforce_canary_invite_target(denied_target)
        assert denied.value.status_code == 403
        assert denied.value.code == "CANARY_ACCESS_DENIED"


def test_non_canary_release_does_not_apply_invite_allowlist(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = Settings(release_marker="CONTROLLED_ALPHA")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    enforce_canary_invite_target(None)
    enforce_canary_invite_target(uuid4())


def test_canary_configuration_is_bounded_unique_and_marker_scoped():
    learner_ids = [uuid4() for _ in range(8)]
    configured = production_settings(
        canary_learner_user_ids=",".join(str(item) for item in learner_ids)
    )
    assert configured.canary_learner_user_ids == learner_ids

    with pytest.raises(ValidationError, match="at most 8 learners"):
        production_settings(canary_learner_user_ids=[*learner_ids, uuid4()])
    with pytest.raises(ValidationError, match="must be unique"):
        production_settings(canary_learner_user_ids=[learner_ids[0], learner_ids[0]])
    with pytest.raises(ValidationError, match="require RELEASE_MARKER"):
        production_settings(
            release_marker="CONTROLLED_ALPHA",
            canary_learner_user_ids=[learner_ids[0]],
        )


def test_canary_marker_requires_production_and_never_allows_fixture_identity():
    with pytest.raises(ValidationError, match="requires APP_ENV=production"):
        Settings(release_marker="PRODUCTION_CANARY_UAT")
    with pytest.raises(ValidationError, match="ALLOW_FIXTURE_IDENTITY"):
        production_settings(allow_fixture_identity=True)
