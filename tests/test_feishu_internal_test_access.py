from dataclasses import replace
from uuid import uuid4

import pytest

from journey_api import auth
from journey_api.errors import ApiError
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.models import Role
from test_production_canary_gate import production_settings


@pytest.mark.parametrize("enabled,verified,same_org,allowed", [
    (True, True, True, True),
    (False, True, True, False),
    (True, False, True, False),
    (True, True, False, False),
])
def test_company_login_does_not_admit_unverified_or_other_platform_sessions(
    monkeypatch, enabled, verified, same_org, allowed,
):
    settings = production_settings(feishu_learner_registration_enabled=enabled,
                                   feishu_learner_organization_id=ORGANIZATION_ID)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    actor = auth.Actor(id=uuid4(), organization_id=ORGANIZATION_ID if same_org else uuid4(),
                       roles=frozenset({Role.LEARNER}), display_name="Learner",
                       external_identity_verified=verified)
    if allowed:
        assert auth.enforce_canary_learner_scope(actor) == actor
        with pytest.raises(ApiError):
            auth.require_role(actor, Role.REVIEWER)
        with pytest.raises(ApiError):
            auth.require_role(actor, Role.OPERATOR)
    else:
        with pytest.raises(ApiError) as error:
            auth.enforce_canary_learner_scope(actor)
        assert error.value.code == "CANARY_ACCESS_DENIED"
    # Existing named testers retain access, without making invitations public.
    settings.canary_learner_user_ids = [actor.id]
    assert auth.enforce_canary_learner_scope(replace(actor, external_identity_verified=False)) == replace(actor, external_identity_verified=False)
    with pytest.raises(ApiError):
        auth.enforce_canary_invite_target(None)
