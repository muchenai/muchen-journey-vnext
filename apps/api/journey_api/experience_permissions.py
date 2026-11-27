"""Access to experience issuance is independent of course authorship."""
from uuid import UUID

from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.management_access import fail
from journey_api.management_access_models import CourseManagementSettings
from journey_api.models import AuditEntry, ExternalIdentity, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_access import permissions
from journey_api.review_admin_models import ReviewAdminAccess


NO_ACCESS = "当前账号没有经验发放权限。"
ISSUER_CHANGE = "experience.issuers_changed"


def issuer_names(session, organization_id, ids):
    if not ids:
        return {}
    rows = session.execute(select(User.id, User.display_name).where(
        User.organization_id == organization_id, User.id.in_([UUID(value) for value in ids])))
    return {str(uid): name for uid, name in rows}


def issuer_history(session, organization_id, revision):
    event_revision = AuditEntry.details["revision"].as_integer()
    events = session.scalars(select(AuditEntry).where(
        AuditEntry.organization_id == organization_id, AuditEntry.action == ISSUER_CHANGE,
        AuditEntry.resource_id == organization_id, AuditEntry.resource_type == "review_admin",
        AuditEntry.result == "SUCCESS", event_revision <= revision,
    ).order_by(event_revision, AuditEntry.id)).all()
    # Older events recorded the resulting two IDs. Compare consecutive saved editions
    # and resolve names once for the older entries that have no name snapshot.
    legacy_ids = set()
    for event in events:
        if "names" not in event.details:
            legacy_ids.update(event.details["issuers"])
            legacy_ids.add(str(event.actor_id))
    legacy_names = issuer_names(session, organization_id, legacy_ids)
    previous = [None, None]
    editions = []
    for event in events:
        saved = event.details
        before = saved.get("beforeIssuers", previous)
        after = saved["issuers"]
        names = saved.get("names", legacy_names)
        changes = []
        for slot, (old, new) in enumerate(zip(before, after, strict=True), 1):
            if old != new:
                changes.append({
                    "id": f"{event.id}:{slot}", "time": event.occurred_at.isoformat(),
                    "operatorId": str(event.actor_id), "operatorName": names.get(str(event.actor_id), "已失效成员"),
                    "slot": slot, "beforeId": old, "afterId": new,
                    "beforeName": names.get(old, "已失效成员") if old else None,
                    "afterName": names.get(new, "已失效成员") if new else None,
                })
        editions.append(changes)
        previous = after
    return [change for edition in reversed(editions) for change in edition]


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
