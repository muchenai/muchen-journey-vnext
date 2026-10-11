"""Explicit staff exclusions and opt-in shared reviews for new OAuth learners."""
from uuid import UUID

from sqlalchemy import and_, or_

from journey_api.config import get_settings
from journey_api.models import Enrollment, JourneyStageVersion, Review, ReviewDelegation, ReviewKind, Role


def effective_roles(user_id: UUID, roles: frozenset[Role]) -> frozenset[Role]:
    if user_id in get_settings().reviewer_excluded_user_ids:
        return roles - {Role.REVIEWER}
    return roles


def review_visibility(actor):
    assigned = or_(Review.reviewer_id == actor.id, ReviewDelegation.reviewer_id == actor.id)
    settings = get_settings()
    pool = settings.feishu_learner_shared_reviewer_ids
    if actor.id not in pool or actor.organization_id != settings.feishu_learner_organization_id:
        return assigned
    # A durable enrollment setting opts in only new learner registrations.
    # Existing enrollment/reviewer lineage and immutable review ownership stay intact.
    shared = and_(
        Review.review_kind == ReviewKind.FORMAL_EVALUATION,
        Review.reviewer_id.in_(pool),
        JourneyStageVersion.id.is_not(None),
        Enrollment.review_assignment_mode == "SHARED",
    )
    return or_(assigned, shared)
