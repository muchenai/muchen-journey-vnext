"""Course and experience permissions derive only from active, local staff identities."""
from sqlalchemy import select

from journey_api.errors import ApiError
from journey_api.management_access_models import CourseManagementSettings
from journey_api.models import Organization
from journey_api.review_admin_access import STAFF_ROLES, permissions, require_publisher


def fail(message, status=422):
    raise ApiError(status, {403: "FORBIDDEN", 409: "CONFLICT"}.get(status, "INVALID_REQUEST"), message)


def course_scope(session, actor, lock=False):
    from journey_api.academy_routes import TAGS

    if not actor.roles.intersection(STAFF_ROLES):
        fail("请使用已认证的管理端账号。", 403)
    if lock:
        require_publisher(session, actor)
        session.scalar(select(Organization.id).where(Organization.id == actor.organization_id).with_for_update())
    rights = permissions(session, actor)
    if not rights["canPublish"]:
        fail("当前管理账号已停用或权限已撤销。", 403)
    settings = session.get(CourseManagementSettings, actor.organization_id, populate_existing=True)
    return {"actorId": str(actor.id), "actorName": actor.display_name,
            "isSuperAdmin": rights["isSuperAdmin"], "canPublish": rights["canPublish"],
            "revision": settings.revision if settings else 0, "tags": list(settings.tags if settings else TAGS)}


def set_course_tags(session, actor, tags):
    if not isinstance(tags, list) or len(tags) > 100 or any(not isinstance(tag, str) or not tag.strip() or len(tag) > 50 for tag in tags):
        fail("课程标签过长或格式有误。")
    clean = [tag.strip() for tag in tags]
    if len(set(clean)) != len(clean):
        fail("请先移除重复的课程标签。")
    row = session.get(CourseManagementSettings, actor.organization_id)
    if not row:
        row = CourseManagementSettings(organization_id=actor.organization_id, revision=0, assignments={}, issuers=[])
        session.add(row)
    row.tags = clean
    row.revision += 1
    session.flush()
