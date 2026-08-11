#!/usr/bin/env python3
"""Create a disposable privileged session inside an isolated local browser fixture."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import timedelta

from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import credential_hash, random_token, utc_now
from journey_api.models import IdentitySession, Role, RoleAssignment, User, UserStatus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role",
        choices=(Role.REVIEWER.value, Role.OPERATOR.value),
        default=Role.REVIEWER.value,
    )
    args = parser.parse_args()
    requested_role = Role(args.role)

    settings = get_settings()
    if settings.app_env not in {"local", "test"} or not settings.allow_fixture_identity:
        raise SystemExit("privileged browser fixture is disabled outside local/test")

    with SessionLocal() as session:
        reviewer = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.status == UserStatus.ACTIVE,
                RoleAssignment.role == requested_role,
            )
        )
        if reviewer is None:
            raise SystemExit(f"{requested_role.value.lower()} browser fixture identity is unavailable")

        session_token = random_token()
        csrf_token = random_token()
        session.add(
            IdentitySession(
                id=uuid.uuid4(),
                organization_id=reviewer.organization_id,
                user_id=reviewer.id,
                role=requested_role,
                token_hash=credential_hash(
                    settings.session_secret, "session", session_token
                ),
                csrf_token_hash=credential_hash(settings.session_secret, "csrf", csrf_token),
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
        session.commit()

    json.dump(
        {"session": session_token, "csrf": csrf_token, "role": requested_role.value},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
