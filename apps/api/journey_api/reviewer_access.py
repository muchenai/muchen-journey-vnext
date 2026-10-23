"""Organization-scoped review access by camp, task author and admin authority."""
from uuid import UUID

from sqlalchemy import and_, or_, select

from journey_api.config import get_settings
from journey_api.models import Role, TaskDefinition
from journey_api.review_camps import exploration_task_scope
from journey_api.review_admin_models import ReviewAdminAccess


def effective_roles(user_id: UUID, roles: frozenset[Role]) -> frozenset[Role]:
    if user_id in get_settings().reviewer_excluded_user_ids:
        return roles - {Role.REVIEWER}
    return roles


def review_visibility(actor):
    # All callers additionally enforce organization and immutable task/submission
    # lineage. Assignment, delegation and historical shared pools never grant
    # access to another author's novice task submissions.
    super_admin = select(ReviewAdminAccess.user_id).where(
        ReviewAdminAccess.user_id == actor.id,
        ReviewAdminAccess.organization_id == actor.organization_id,
        ReviewAdminAccess.revoked_at.is_(None),
        ReviewAdminAccess.access_role == "super_admin",
    ).exists()
    return and_(
        actor.has_role(Role.REVIEWER),
        or_(super_admin, exploration_task_scope(), TaskDefinition.created_by == actor.id),
    )
