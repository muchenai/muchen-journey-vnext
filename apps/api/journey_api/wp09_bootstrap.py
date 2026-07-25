"""Create the single audited staging link needed to bind the first real Operator."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import add_audit, credential_hash, random_token, utc_now
from journey_api.models import (
    ExternalIdentity,
    ExternalIdentityLink,
    IdentityLinkStatus,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)

PROVIDER = "FEISHU"
CONFIRMATION = "CREATE_STAGING_OPERATOR_LINK"
AUTHORIZATION_REFERENCE = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")


class BootstrapError(RuntimeError):
    pass


def create_operator_link(
    session: Session,
    *,
    target_user_id: uuid.UUID,
    secret: str,
    authorization_reference: str,
    expires_in_minutes: int = 15,
    now: datetime | None = None,
) -> dict[str, str | int]:
    if not AUTHORIZATION_REFERENCE.fullmatch(authorization_reference):
        raise BootstrapError("authorization reference must be a non-sensitive stable identifier")
    if not 5 <= expires_in_minutes <= 30:
        raise BootstrapError("bootstrap link lifetime must be 5-30 minutes")
    issued_at = now or utc_now()
    target = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == target_user_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == User.organization_id,
            RoleAssignment.role == Role.OPERATOR,
        )
        .with_for_update()
    )
    if target is None:
        raise BootstrapError("target must be one active internal Operator")
    active_identity = session.scalar(
        select(ExternalIdentity.id).where(
            ExternalIdentity.organization_id == target.organization_id,
            ExternalIdentity.user_id == target.id,
            ExternalIdentity.provider == PROVIDER,
            ExternalIdentity.revoked_at.is_(None),
        )
    )
    if active_identity is not None:
        raise BootstrapError("target Operator already has an active Feishu identity")
    pending = session.scalar(
        select(ExternalIdentityLink.id).where(
            ExternalIdentityLink.organization_id == target.organization_id,
            ExternalIdentityLink.user_id == target.id,
            ExternalIdentityLink.role == Role.OPERATOR,
            ExternalIdentityLink.provider == PROVIDER,
            ExternalIdentityLink.status == IdentityLinkStatus.PENDING,
            ExternalIdentityLink.expires_at > issued_at,
        )
    )
    if pending is not None:
        raise BootstrapError("target Operator already has an unexpired bootstrap link")

    token = random_token()
    expires_at = issued_at + timedelta(minutes=expires_in_minutes)
    link = ExternalIdentityLink(
        id=uuid.uuid4(),
        organization_id=target.organization_id,
        user_id=target.id,
        role=Role.OPERATOR,
        provider=PROVIDER,
        token_hash=credential_hash(secret, "identity-link", token),
        status=IdentityLinkStatus.PENDING,
        expires_at=expires_at,
        created_by=None,
        revision=1,
    )
    session.add(link)
    add_audit(
        session,
        request_id=f"wp09-bootstrap:{uuid.uuid4()}",
        organization_id=target.organization_id,
        actor_id=None,
        action="identity_link.bootstrap_created",
        resource_type="external_identity_link",
        resource_id=link.id,
        result="SUCCESS",
        details={
            "provider": PROVIDER,
            "role": Role.OPERATOR.value,
            "authorization_reference": authorization_reference,
        },
    )
    session.commit()
    return {
        "link_id": str(link.id),
        "start_path": "/auth/feishu?return_to=%2Fops&link_token=" + token,
        "expires_at": expires_at.isoformat(),
        "expires_in_minutes": expires_in_minutes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-user-id", required=True, type=uuid.UUID)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--expires-in-minutes", type=int, default=15)
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    if settings.app_env != "staging":
        raise BootstrapError("first-Operator bootstrap is permitted only in staging")
    if args.confirm != CONFIRMATION:
        raise BootstrapError(f"confirmation must be {CONFIRMATION}")
    with SessionLocal() as session:
        result = create_operator_link(
            session,
            target_user_id=args.target_user_id,
            secret=settings.identity_subject_secret,
            authorization_reference=args.authorization_reference,
            expires_in_minutes=args.expires_in_minutes,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
