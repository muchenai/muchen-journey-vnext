"""Course and experience permissions derive only from active, local staff identities."""
from sqlalchemy import or_, select

from journey_api.errors import ApiError
from journey_api.management_access_models import CourseManagementSettings
from journey_api.models import Organization, RoleAssignment, User, UserStatus
from journey_api.review_admin_access import STAFF_ROLES
from journey_api.review_admin_models import ReviewAdminAccess


def fail(message, status=422):
    raise ApiError(status, {403: "FORBIDDEN", 409: "CONFLICT"}.get(status, "INVALID_REQUEST"), message)


def staff_directory(session, actor):
    explicit_role = select(RoleAssignment.id).where(
        RoleAssignment.user_id == User.id, RoleAssignment.organization_id == actor.organization_id,
        RoleAssignment.role.in_(STAFF_ROLES)).exists()
    query = select(User, ReviewAdminAccess).outerjoin(ReviewAdminAccess, ReviewAdminAccess.user_id == User.id).where(
        User.organization_id == actor.organization_id, User.status == UserStatus.ACTIVE,
        ReviewAdminAccess.revoked_at.is_(None), or_(explicit_role, ReviewAdminAccess.user_id.is_not(None))
    ).order_by(User.display_name, User.id)
    return session.execute(query).all()


def course_scope(session, actor, lock=False):
    from journey_api.academy_routes import TAGS

    if not actor.roles.intersection(STAFF_ROLES):
        fail("请使用已认证的管理端账号。", 403)
    if lock:
        # Serialize settings creation as well as changes, including the first assignment.
        session.scalar(select(Organization.id).where(Organization.id == actor.organization_id).with_for_update())
        session.scalar(select(User.id).where(User.id == actor.id, User.organization_id == actor.organization_id).with_for_update())
    state = session.get(CourseManagementSettings, actor.organization_id, populate_existing=True)
    staff = staff_directory(session, actor)
    candidates = {str(user.id): {"id": str(user.id), "name": user.display_name} for user, _ in staff}
    if str(actor.id) not in candidates:
        fail("当前管理账号已停用或权限已撤销。", 403)
    super_ids = [str(user.id) for user, access in staff if access and access.access_role == "super_admin"]
    protected = [str(user.id) for user, access in staff if access and access.can_grant_super_admin and access.access_role == "super_admin"]
    # When the designated owner is revoked, only an existing system super admin can take over.
    initial_owner = next(iter(sorted(protected or super_ids)), None)
    saved = state.assignments if state else {}
    owner = saved.get("ownerId")
    if owner not in candidates:
        owner = initial_owner
    members = {i for i in saved.get("memberIds", list(candidates)) if i in candidates}
    if owner:
        members.add(owner)
    # Existing certified administrators already manage the legacy academy.
    # Persist explicit membership on the first change so future grants are deliberate.
    existing_admins = [str(user.id) for user, access in staff if access and str(user.id) != owner]
    admins = [i for i in saved.get("adminIds", existing_admins) if i in members]
    reviewers = [r for r in saved.get("reviewers", []) if r["personId"] in members]
    people = [person for pid, person in candidates.items() if pid in members]
    return {"actorId": str(actor.id), "people": people, "assignments": {
        "ownerId": owner, "adminIds": admins, "reviewers": reviewers,
    }, "revision": state.revision if state else 0, "tags": list(state.tags if state else TAGS)}


def writable_settings(session, actor, scope, revision=None):
    if scope["actorId"] != scope["assignments"]["ownerId"]:
        fail("只有课程负责人可以更改此设置。", 403)
    if revision is not None and revision != scope["revision"]:
        fail("配置已被更新，请重新打开后再保存。", 409)
    row = session.get(CourseManagementSettings, actor.organization_id)
    if not row:
        row = CourseManagementSettings(organization_id=actor.organization_id, revision=0,
            issuers=[], tags=scope["tags"], assignments={**scope["assignments"], "memberIds": [p["id"] for p in scope["people"]]})
        session.add(row)
    return row


def set_course_tags(session, actor, tags):
    scope = course_scope(session, actor, lock=True)
    row = writable_settings(session, actor, scope)
    if not isinstance(tags, list) or len(tags) > 100 or any(not isinstance(tag, str) or not tag.strip() or len(tag) > 50 for tag in tags):
        fail("课程标签过长或格式有误。")
    clean = [tag.strip() for tag in tags]
    if len(set(clean)) != len(clean):
        fail("请先移除重复的课程标签。")
    if any(tag not in clean for reviewer in scope["assignments"]["reviewers"] for tag in reviewer["tagNames"]):
        fail("部分标签仍被用于审核权限，请先调整审核范围。", 409)
    row.tags = clean
    row.revision += 1
    session.flush()
