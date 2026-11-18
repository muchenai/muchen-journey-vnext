"""Recheck the authenticated learner after model/document I/O.

Learning facts keep their original owner after a temporary phone account is
retired. Authorize that owner through the current corporate session and its
consumed migration code, never through an arbitrary active linked account.
The caller owns the transaction; these SHARE locks last until its commit.
"""
from datetime import UTC, datetime

from sqlalchemy import select

from journey_api.models import (
    CompletionCode, ExternalIdentity, IdentitySession, Role, RoleAssignment,
    User, UserStatus,
)


def _learner_role(session, user_id, organization_id):
    return session.scalar(select(RoleAssignment.id).where(
        RoleAssignment.user_id == user_id,
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.role == Role.LEARNER).with_for_update(read=True)) is not None


def _user(session, user_id, organization_id):
    return session.scalar(select(User).where(
        User.id == user_id, User.organization_id == organization_id)
        .execution_options(populate_existing=True).with_for_update(read=True))


def authorize_exploration_learner(session, actor):
    """Return whether this exact actor still controls its learner record."""
    if not actor.has_role(Role.LEARNER):
        return False
    if actor.session_id is None:
        # Local/test fixture actors have no principal session. They must never
        # acquire disabled or inherited history through this compatibility path.
        if actor.inherited_learner_id is not None:
            return False
        user = _user(session, actor.id, actor.organization_id)
        return bool(user is not None and user.status == UserStatus.ACTIVE
            and _learner_role(session, actor.id, actor.organization_id))

    binding = session.execute(select(
        IdentitySession.user_id, IdentitySession.external_identity_id).where(
        IdentitySession.id == actor.session_id,
        IdentitySession.organization_id == actor.organization_id)).first()
    if binding is None:
        return False
    # Login/revocation lock external identity before user/session. Migration
    # locks the corporate user before its code and only the retired source's
    # credentials. Recheck the snapshot binding after acquiring these locks.
    identity = None
    if binding.external_identity_id is not None:
        identity = session.scalar(select(ExternalIdentity).where(
            ExternalIdentity.id == binding.external_identity_id,
            ExternalIdentity.user_id == binding.user_id,
            ExternalIdentity.organization_id == actor.organization_id,
            ExternalIdentity.revoked_at.is_(None))
            .execution_options(populate_existing=True).with_for_update(read=True))
        if identity is None:
            return False
    principal = _user(session, binding.user_id, actor.organization_id)
    if principal is None or principal.status != UserStatus.ACTIVE:
        return False
    current = session.scalar(select(IdentitySession).where(
        IdentitySession.id == actor.session_id,
        IdentitySession.organization_id == actor.organization_id)
        .execution_options(populate_existing=True).with_for_update(read=True))
    if current is None:
        return False
    expires_at = current.expires_at
    # SQLite test sessions lose timezone metadata; stored session times are UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (current.user_id != principal.id
            or current.external_identity_id != binding.external_identity_id
            or current.role != Role.LEARNER
            or current.revoked_at is not None or expires_at <= datetime.now(UTC)):
        return False
    if identity is not None and identity.revision != current.external_identity_revision:
        return False
    if not _learner_role(session, principal.id, actor.organization_id):
        return False
    if actor.id == principal.id:
        return actor.inherited_learner_id is None
    if actor.inherited_learner_id != actor.id:
        return False
    migration = session.scalar(select(CompletionCode).where(
        CompletionCode.user_id == actor.id,
        CompletionCode.organization_id == actor.organization_id,
        CompletionCode.migrated_to_user_id == principal.id,
        CompletionCode.used_at.is_not(None))
        .execution_options(populate_existing=True).with_for_update(read=True))
    if migration is None:
        return False
    # Expiration prevents redeeming unused codes; an already consumed code is
    # the durable ownership mapping and does not expire with its redemption TTL.
    owner = _user(session, actor.id, actor.organization_id)
    return bool(owner is not None and owner.status in {UserStatus.ACTIVE, UserStatus.DISABLED}
        and _learner_role(session, actor.id, actor.organization_id))
