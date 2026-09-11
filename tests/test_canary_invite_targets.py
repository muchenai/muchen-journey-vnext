"""Isolated SQLite checks; never connects to the deployment database."""
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from journey_api import auth, identity_routes
from journey_api.errors import ApiError
from journey_api.models import Organization, Role, User, UserStatus
from journey_api.schemas import CreateInviteCommand, InviteTargetsResponse


@pytest.fixture
def context(monkeypatch):
    engine = create_engine("sqlite://")
    Organization.__table__.create(engine)
    User.__table__.create(engine)
    org, other = uuid4(), uuid4()
    ids = [uuid4() for _ in range(4)]
    settings = SimpleNamespace(release_marker="PRODUCTION_CANARY_UAT", canary_learner_user_ids=ids[:3])
    monkeypatch.setattr(identity_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    with Session(engine) as s:
        s.add_all([Organization(id=org, name="Synthetic A"), Organization(id=other, name="Synthetic B")])
        for uid, name, organization, status in (
            (ids[0], "Synthetic learner without roles", org, UserStatus.ACTIVE),
            (ids[1], "Other organization", other, UserStatus.ACTIVE),
            (ids[2], "Inactive", org, UserStatus.PENDING_IDENTITY),
            (ids[3], "Not allowed", org, UserStatus.ACTIVE),
        ):
            s.add(User(id=uid, display_name=name, organization_id=organization, status=status))
        s.commit()
        operator = auth.Actor(id=uuid4(), organization_id=org, roles=frozenset({Role.OPERATOR}), display_name="Synthetic operator")
        req = Request({"type": "http", "state": {"request_id": "req_synthetic"}})
        yield s, settings, operator, req, ids
    engine.dispose()


def test_targets_only_active_same_organization_allowlisted_users(context):
    s, _, operator, req, ids = context
    before = s.scalars(select(User.id)).all()
    result = identity_routes.list_invite_targets(req, operator, s)
    validated = InviteTargetsResponse.model_validate(result)
    assert validated.data.target_required is True
    assert [x.user_id for x in validated.data.items] == [ids[0]]
    assert set(result["data"]["items"][0]) == {"user_id", "display_name"}
    assert s.scalars(select(User.id)).all() == before
    assert not s.new and not s.dirty and not s.deleted


@pytest.mark.parametrize("role", [Role.LEARNER, Role.REVIEWER, Role.CONTENT_EDITOR])
def test_non_operator_cannot_list_targets(context, role):
    _, _, operator, req, _ = context
    denied = auth.Actor(id=operator.id, organization_id=operator.organization_id, roles=frozenset({role}), display_name="Denied")
    db = Mock()
    with pytest.raises(ApiError) as error:
        identity_routes.list_invite_targets(req, denied, db)
    assert error.value.status_code == 403
    db.execute.assert_not_called()


def test_empty_allowlist_does_not_fall_back_to_all_users(context):
    s, settings, operator, req, _ = context
    settings.canary_learner_user_ids = []
    assert identity_routes.list_invite_targets(req, operator, s)["data"] == {"target_required": True, "items": []}


def test_non_canary_preserves_untargeted_invitation_mode(context):
    _, settings, operator, req, _ = context
    settings.release_marker = "CONTROLLED_ALPHA"
    db = Mock()
    assert identity_routes.list_invite_targets(req, operator, db)["data"] == {"target_required": False, "items": []}
    db.execute.assert_not_called()


@pytest.mark.parametrize("target", [None, "removed"])
def test_create_still_rechecks_allowlist_before_any_write(context, target):
    _, settings, operator, req, ids = context
    settings.canary_learner_user_ids = []
    command = CreateInviteCommand(purpose="Synthetic test", expires_in_hours=24, reviewer_id=operator.id, task_version_id=uuid4(), target_user_id=ids[0] if target else None)
    db = Mock()
    with pytest.raises(ApiError) as error:
        identity_routes.create_invite(command, req, "synthetic-key", operator, db)
    assert error.value.code == "CANARY_ACCESS_DENIED"
    db.scalar.assert_not_called()
    db.commit.assert_not_called()
