#!/usr/bin/env python3
"""Provision the approved 李鑫波 production identity with Operator and Reviewer roles."""

from __future__ import annotations

import argparse
import json
import uuid

from sqlalchemy import select


TARGET_USER_ID = uuid.UUID("934d4bab-2494-4ed3-ac15-9378913b9c01")
TARGET_DISPLAY_NAME = "李鑫波"
CONFIRMATION = "PROVISION_LIXINBO_OPERATOR_REVIEWER"
AUTHORIZATION_REFERENCE = "ACCESS-LIXINBO-20260924"


class ProvisionError(RuntimeError):
    pass


def _business_organizations(organizations: list[object]) -> list[object]:
    return [
        organization
        for organization in organizations
        if not str(getattr(organization, "name", "")).strip().casefold().startswith("wp12b:")
    ]


def provision(session: object) -> dict[str, object]:
    """Create or reuse the exact approved user and add only the two approved roles."""
    from journey_api.identity import add_audit
    from journey_api.models import Organization, Role, RoleAssignment, User, UserStatus

    organizations = session.scalars(select(Organization)).all()
    business_organizations = _business_organizations(organizations)
    if len(business_organizations) != 1:
        raise ProvisionError("production organization topology is ambiguous")
    organization = business_organizations[0]

    same_name = session.scalars(
        select(User).where(User.display_name == TARGET_DISPLAY_NAME)
    ).all()
    target = session.get(User, TARGET_USER_ID)
    if any(user.id != TARGET_USER_ID for user in same_name):
        raise ProvisionError("a different user already has the approved display name")

    created_user = target is None
    if target is None:
        target = User(
            id=TARGET_USER_ID,
            organization_id=organization.id,
            display_name=TARGET_DISPLAY_NAME,
            status=UserStatus.ACTIVE,
        )
        session.add(target)
        session.flush()
        add_audit(
            session,
            request_id=f"access-provision:{uuid.uuid4()}",
            organization_id=organization.id,
            actor_id=None,
            action="internal_access.user_created",
            resource_type="user",
            resource_id=target.id,
            result="SUCCESS",
            details={"authorization_reference": AUTHORIZATION_REFERENCE},
        )
    elif (
        target.organization_id != organization.id
        or target.display_name != TARGET_DISPLAY_NAME
        or target.status != UserStatus.ACTIVE
    ):
        raise ProvisionError("approved target user state differs")

    assignments = session.scalars(
        select(RoleAssignment).where(
            RoleAssignment.organization_id == organization.id,
            RoleAssignment.user_id == target.id,
        )
    ).all()
    existing_roles = {assignment.role for assignment in assignments}
    added_roles: list[str] = []
    for role in (Role.OPERATOR, Role.REVIEWER):
        if role in existing_roles:
            continue
        assignment = RoleAssignment(
            id=uuid.uuid4(),
            organization_id=organization.id,
            user_id=target.id,
            role=role,
        )
        session.add(assignment)
        added_roles.append(role.value)
        add_audit(
            session,
            request_id=f"access-provision:{uuid.uuid4()}",
            organization_id=organization.id,
            actor_id=None,
            action="internal_access.role_granted",
            resource_type="role_assignment",
            resource_id=assignment.id,
            result="SUCCESS",
            details={
                "role": role.value,
                "authorization_reference": AUTHORIZATION_REFERENCE,
            },
        )

    session.commit()
    return {
        "user_id": str(target.id),
        "display_name": TARGET_DISPLAY_NAME,
        "created_user": created_user,
        "added_roles": added_roles,
        "effective_roles": [Role.OPERATOR.value, Role.REVIEWER.value],
        "authorization_reference": AUTHORIZATION_REFERENCE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise ProvisionError(f"confirmation must be {CONFIRMATION}")

    from journey_api.config import get_settings
    from journey_api.db import SessionLocal

    settings = get_settings()
    if settings.app_env != "production" or settings.release_marker != "PRODUCTION_CANARY_UAT":
        raise ProvisionError("provisioning requires the live production Canary runtime")
    with SessionLocal() as session:
        result = provision(session)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
