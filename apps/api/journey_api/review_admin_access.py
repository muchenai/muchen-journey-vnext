"""Server authority for Review access and publication levels."""
from sqlalchemy import select
from journey_api.errors import ApiError
from journey_api.models import Role, User
from journey_api.review_admin_models import ReviewAdminAccess, ReviewAdminTask

STAFF_ROLES = {Role.OPERATOR, Role.REVIEWER, Role.CONTENT_EDITOR}
DIFFICULTIES = ["入门", "进阶", "挑战"]
LEVELS = ["初级", "中级", "高级"]


def access_for(session, user_id, organization_id, *, lock=False):
    if lock:
        # Same lock is taken by grants/revocation and publication.
        session.scalar(select(User.id).where(User.id == user_id, User.organization_id == organization_id).with_for_update())
    return session.scalar(select(ReviewAdminAccess).where(
        ReviewAdminAccess.user_id == user_id, ReviewAdminAccess.organization_id == organization_id)
        .execution_options(populate_existing=True))


def filter_staff_roles(session, user_id, organization_id, roles):
    row = access_for(session, user_id, organization_id)
    if row and row.revoked_at:
        return roles - STAFF_ROLES
    if row and row.access_role == "admin":
        return roles - {Role.OPERATOR, Role.CONTENT_EDITOR}
    return roles


def permissions(session, actor):
    row = access_for(session, actor.id, actor.organization_id)
    staff = actor.entry_role in STAFF_ROLES and actor.entry_role in actor.roles
    active = staff and row is not None and row.revoked_at is None
    super_admin = active and row.access_role == "super_admin"
    # Existing Review staff become ordinary administrators, defaulting to entry level.
    can_publish = active or (staff and row is None and bool({Role.OPERATOR, Role.REVIEWER} & actor.roles))
    level = row.level if active else "初级"
    return {"isSuperAdmin": super_admin, "canPublish": can_publish,
            "canGrantSuperAdmins": bool(super_admin and row.can_grant_super_admin),
            "level": level, "allowedDifficulties": DIFFICULTIES if super_admin else DIFFICULTIES[:LEVELS.index(level)+1] if can_publish else []}


def require_super(session, actor):
    access_for(session, actor.id, actor.organization_id, lock=True)
    if not permissions(session, actor)["isSuperAdmin"]:
        raise ApiError(403, "FORBIDDEN", "仅超级管理员可以执行此操作。")


def require_publisher(session, actor, difficulty=None):
    difficulty = difficulty or None
    access_for(session, actor.id, actor.organization_id, lock=True)
    rights = permissions(session, actor)
    if not rights["canPublish"]:
        raise ApiError(403, "FORBIDDEN", "当前账号没有任务发布权限。")
    if difficulty is not None and difficulty not in rights["allowedDifficulties"]:
        raise ApiError(403, "PUBLISH_LEVEL_REQUIRED", "该任务难度超出当前认证等级，请联系超级管理员调整认证等级。")


def can_manage_task(session, actor, definition):
    return definition.organization_id == actor.organization_id and (
        definition.created_by == actor.id or permissions(session, actor)["isSuperAdmin"]
    )


def require_version_publisher(session, actor, task_id):
    from journey_api.models import TaskDefinition
    from journey_api.review_camps import task_camp
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    definition = session.scalar(select(TaskDefinition).where(TaskDefinition.id == task_id).with_for_update())
    profile = session.get(ReviewAdminTask, task_id)
    # Generic endpoints must not bypass the Review difficulty check.
    if profile and profile.organization_id == actor.organization_id:
        require_super(session, actor)
        require_publisher(session, actor, profile.content.get("difficulty", "入门"))
    elif definition and definition.organization_id == actor.organization_id and task_camp(definition, profile) == "exploration":
        require_super(session, actor)
    else:
        from journey_api.auth import require_role
        require_role(actor, Role.OPERATOR)
