"""Access to experience issuance is independent of course authorship."""
from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.management_access import fail
from journey_api.management_access_models import CourseManagementSettings
from journey_api.models import ExternalIdentity, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_access import permissions
from journey_api.review_admin_models import ReviewAdminAccess


NO_ACCESS = "当前账号没有经验发放权限。"


def settings_for(session, actor, *, lock=False):
    if lock:
        # All configuration writes and grants use this lock, including first-time setup.
        # The auth dependency already holds the current staff user's row lock.
        session.scalar(select(Organization.id).where(Organization.id == actor.organization_id).with_for_update())
    return session.get(CourseManagementSettings, actor.organization_id, populate_existing=True)


def eligible_issuer_ids(session, organization_id, ids):
    if not ids:
        return set()
    # /review signs into the REVIEWER entry. An active certification by itself is
    # insufficient if the account, login identity, or underlying role was disabled.
    has_role = select(RoleAssignment.id).where(RoleAssignment.user_id == User.id,
        RoleAssignment.organization_id == organization_id, RoleAssignment.role == Role.REVIEWER).exists()
    has_identity = select(ExternalIdentity.id).where(ExternalIdentity.user_id == User.id,
        ExternalIdentity.organization_id == organization_id, ExternalIdentity.provider == "FEISHU",
        ExternalIdentity.revoked_at.is_(None)).exists()
    revoked = select(ReviewAdminAccess.user_id).where(ReviewAdminAccess.user_id == User.id,
        ReviewAdminAccess.organization_id == organization_id, ReviewAdminAccess.revoked_at.is_not(None)).exists()
    allowed = session.scalars(select(User.id).where(User.id.in_(ids), User.organization_id == organization_id,
        User.status == UserStatus.ACTIVE, has_role, has_identity, ~revoked))
    return set(allowed).difference(get_settings().reviewer_excluded_user_ids)


def can_issue(session, actor, state):
    return bool(state and str(actor.id) in state.issuers and Role.REVIEWER in actor.roles
                and eligible_issuer_ids(session, actor.organization_id, [actor.id]))


def require_issuer(session, actor, *, lock=False):
    state = settings_for(session, actor, lock=lock)
    if not can_issue(session, actor, state):
        fail(NO_ACCESS, 403)
    return state


def require_issuer_configurator(session, actor):
    if Role.REVIEWER not in actor.roles or not permissions(session, actor)["canGrantSuperAdmins"]:
        fail("仅最高权限的超级管理员可以设置经验发放权限。", 403)
