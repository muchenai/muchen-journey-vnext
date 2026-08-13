#!/usr/bin/env python3
"""Create one disposable multi-role staff session in an isolated local fixture."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import timedelta

from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import credential_hash, random_token, utc_now
from journey_api.models import (
    IdentitySession,
    Organization,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)


def main() -> int:
    settings = get_settings()
    if settings.app_env not in {"local", "test"} or not settings.allow_fixture_identity:
        raise SystemExit("multi-role browser fixture is disabled outside local/test")

    with SessionLocal() as session:
        user = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.status == UserStatus.ACTIVE,
                RoleAssignment.role == Role.CONTENT_EDITOR,
            )
        )
        if user is None:
            organization = session.scalar(select(Organization).limit(1))
            if organization is None:
                raise SystemExit("browser fixture organization is unavailable")
            user = User(
                id=uuid.uuid4(),
                organization_id=organization.id,
                display_name="P0 Multi-role Browser Fixture",
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            session.flush()
            session.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    organization_id=organization.id,
                    user_id=user.id,
                    role=Role.CONTENT_EDITOR,
                )
            )
        if session.scalar(
            select(RoleAssignment.id).where(
                RoleAssignment.user_id == user.id,
                RoleAssignment.role == Role.REVIEWER,
            )
        ) is None:
            session.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    organization_id=user.organization_id,
                    user_id=user.id,
                    role=Role.REVIEWER,
                )
            )

        session_token = random_token()
        csrf_token = random_token()
        session.add(
            IdentitySession(
                id=uuid.uuid4(),
                organization_id=user.organization_id,
                user_id=user.id,
                role=Role.CONTENT_EDITOR,
                token_hash=credential_hash(
                    settings.session_secret, "session", session_token
                ),
                csrf_token_hash=credential_hash(
                    settings.session_secret, "csrf", csrf_token
                ),
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
        session.commit()

    json.dump({"session": session_token, "csrf": csrf_token}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
