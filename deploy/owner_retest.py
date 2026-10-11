"""One-time owner-requested UAT restart; retain every historical evidence row.

Run only through the protected Owner Exploration Retest workflow. No HTTP route,
identity bypass, deletion, role change, or reusable production reset endpoint.
"""
import json
import os
import uuid

from sqlalchemy import select, text

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import add_audit
from journey_api.journey_service import create_journey_assignments, published_formal_journey
from journey_api.models import (
    Assignment, AuditEntry, Enrollment, EnrollmentStatus, ExternalIdentity,
    Organization, Review, Role, RoleAssignment, User, UserStatus,
)

ORG = uuid.UUID("10000000-0000-4000-8000-000000000001")
OWNER = uuid.UUID("934d4bab-2494-4ed3-ac15-9378913b9c01")
NAME = "李鑫波"
JOURNEY = uuid.UUID("889b6c4c-09b9-4415-948b-a028f73087db")
RELEASE = "9e24e64a6b35509da1f28a0dd0e4f8f2131c7399"
OPERATION = "owner-exploration-retest-20261011-v1"
ACTION = "enrollment.owner_uat_restarted"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def restart(session):
    """Caller owns transaction; any failed guard rolls back all changes."""
    session.execute(text("SET LOCAL lock_timeout = '5s'"))
    session.execute(text("SET LOCAL statement_timeout = '30s'"))
    # Same organization/user lock order as OAuth registration.
    require(session.scalar(select(Organization.id).where(
        Organization.id == ORG).with_for_update()) == ORG, "ORGANIZATION_MISMATCH")
    owner = session.scalar(select(User).where(User.id == OWNER,
        User.organization_id == ORG).with_for_update())
    require(owner is not None and owner.display_name == NAME and
            owner.status == UserStatus.ACTIVE, "OWNER_IDENTITY_MISMATCH")
    require(session.scalar(select(ExternalIdentity.id).where(
        ExternalIdentity.user_id == OWNER, ExternalIdentity.organization_id == ORG,
        ExternalIdentity.provider == "FEISHU", ExternalIdentity.revoked_at.is_(None)))
        is not None, "ACTIVE_FEISHU_BINDING_REQUIRED")
    roles = set(session.scalars(select(RoleAssignment.role).where(
        RoleAssignment.user_id == OWNER, RoleAssignment.organization_id == ORG)))
    require(Role.LEARNER in roles, "LEARNER_ROLE_REQUIRED")
    prior = session.scalar(select(AuditEntry).where(
        AuditEntry.action == ACTION, AuditEntry.request_id == OPERATION,
        AuditEntry.organization_id == ORG))
    if prior is not None:
        return {"result": "ALREADY_APPLIED", **prior.details}

    settings = get_settings()
    pool = set(settings.feishu_learner_shared_reviewer_ids)
    require(settings.feishu_learner_organization_id == ORG and pool and
            settings.feishu_learner_reviewer_id in pool and
            not pool.intersection(settings.reviewer_excluded_user_ids), "REVIEW_POOL_MISMATCH")
    active_pool = set(session.scalars(select(User.id).join(
        RoleAssignment, RoleAssignment.user_id == User.id).where(
        User.id.in_(pool), User.organization_id == ORG, User.status == UserStatus.ACTIVE,
        RoleAssignment.organization_id == ORG, RoleAssignment.role == Role.REVIEWER)))
    require(active_pool == pool, "REVIEW_POOL_NOT_ACTIVE")
    journey = published_formal_journey(session, ORG)
    require(journey is not None and journey.id == JOURNEY, "JOURNEY_VERSION_MISMATCH")
    rounds = list(session.scalars(select(Enrollment).where(
        Enrollment.learner_id == OWNER, Enrollment.organization_id == ORG,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PENDING_IDENTITY])
    ).with_for_update()))
    require(len(rounds) == 1 and rounds[0].status == EnrollmentStatus.ACTIVE,
            "EXPECTED_ONE_ACTIVE_LEARNING_ROUND")
    old = rounds[0]
    require(old.journey_version_id == JOURNEY, "OLD_ROUND_VERSION_MISMATCH")
    assignments = list(session.scalars(select(Assignment).where(
        Assignment.enrollment_id == old.id).order_by(Assignment.position).with_for_update()))
    require(len(assignments) == 8, "EXPECTED_EIGHT_OLD_ASSIGNMENTS")
    # Serialize with submission/review finalization, retaining their exact rows.
    list(session.scalars(select(Review).where(
        Review.assignment_id.in_([a.id for a in assignments])).with_for_update()))
    original_revision = old.revision
    old.status = EnrollmentStatus.CANCELLED
    old.revision += 1
    fresh = Enrollment(id=uuid.uuid4(), organization_id=ORG, learner_id=OWNER,
        reviewer_id=settings.feishu_learner_reviewer_id, journey_version_id=journey.id,
        review_assignment_mode="SHARED", status=EnrollmentStatus.ACTIVE, revision=1)
    session.add(fresh)
    session.flush()
    created = create_journey_assignments(session, enrollment=fresh)
    require(len(created) == 8, "EXPECTED_EIGHT_FRESH_ASSIGNMENTS")
    details = {"old_enrollment_id": str(old.id), "new_enrollment_id": str(fresh.id),
        "previous_status": "ACTIVE", "previous_revision": original_revision,
        "new_assignment_count": len(created), "review_mode": "SHARED",
        "reason": "Account owner requested a fresh exploration UAT round; historical evidence retained",
        "requested_by_user_id": str(OWNER)}
    # Service operation, not an impersonated interactive operator action.
    add_audit(session, request_id=OPERATION, action=ACTION, resource_type="enrollment",
        resource_id=fresh.id, organization_id=ORG, result="SUCCESS", details=details)
    session.flush()
    return {"result": "APPLIED", **details}


if __name__ == "__main__":
    require(os.environ.get("APP_ENV") == "production" and
            os.environ.get("APP_RELEASE") == RELEASE, "PRODUCTION_RELEASE_MISMATCH")
    with SessionLocal.begin() as session:
        require(session.scalar(text("select current_database()")) ==
                "journey_next_canary_20260901_c72fea5", "DATABASE_MISMATCH")
        require(session.scalar(text("select version_num from alembic_version")) ==
                "0032_shared_learner_review", "SCHEMA_MISMATCH")
        result = restart(session)
    # Output only after commit; never emit identity subjects or evidence content.
    print(json.dumps(result))
