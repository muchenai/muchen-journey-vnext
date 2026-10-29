"""Provision only learner access after a successful Feishu identity exchange."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.config import get_settings
from journey_api.errors import ApiError
from journey_api.identity import add_audit
from journey_api.journey_service import create_journey_assignments, published_formal_journey
from journey_api.models import (
    Enrollment, EnrollmentStatus, ExternalIdentity, Organization, Role,
    RoleAssignment, User, UserStatus,
)


def lock_learner_organization(session: Session) -> uuid.UUID:
    settings = get_settings()
    if not settings.feishu_learner_registration_enabled:
        raise ApiError(503, "LEARNER_LOGIN_NOT_CONFIGURED", "学员飞书登录尚未配置。")
    organization_id = settings.feishu_learner_organization_id
    if organization_id is None or session.scalar(
        select(Organization.id).where(Organization.id == organization_id).with_for_update()
    ) is None:
        raise ApiError(503, "LEARNER_LOGIN_NOT_CONFIGURED", "学员所属平台尚未配置。")
    # Serialize first logins so two callbacks for one subject cannot create
    # duplicate users, enrollments or roles. No tenant/company membership filter.
    return organization_id


def provision_learner(session: Session, identity: ExternalIdentity | None, *,
                      subject: str, name: str, organization_id: uuid.UUID,
                      request_id: str, provider: str = "FEISHU") -> ExternalIdentity:
    if identity is not None and identity.organization_id != organization_id:
        raise ApiError(403, "FORBIDDEN", "该身份不属于当前学习平台。")
    if identity is None:
        user = User(id=uuid.uuid4(), organization_id=organization_id,
                    display_name=name, status=UserStatus.ACTIVE)
        session.add(user)
        session.flush()
        identity = ExternalIdentity(id=uuid.uuid4(), organization_id=organization_id,
                                    user_id=user.id, provider=provider, subject=subject, revision=1)
        session.add(identity)
    else:
        user = session.scalar(select(User).where(User.id == identity.user_id,
            User.organization_id == organization_id).with_for_update())
        if user is None or user.status != UserStatus.ACTIVE or identity.revoked_at is not None:
            raise ApiError(403, "FORBIDDEN", "当前身份不可用。")
    role = session.scalar(select(RoleAssignment.id).where(
        RoleAssignment.user_id == user.id, RoleAssignment.organization_id == organization_id,
        RoleAssignment.role == Role.LEARNER))
    if role is None:
        session.add(RoleAssignment(id=uuid.uuid4(), organization_id=organization_id,
                                   user_id=user.id, role=Role.LEARNER))
    # Any existing journey, including a completed/cancelled one, is preserved.
    # Login is never an instruction to reset or replace learning history.
    enrollment = session.scalar(select(Enrollment).where(
        Enrollment.organization_id == organization_id, Enrollment.learner_id == user.id,
        Enrollment.novice_task_id.is_(None)))
    if enrollment is None:
        settings = get_settings()
        reviewer_id = settings.feishu_learner_reviewer_id
        pool = settings.feishu_learner_shared_reviewer_ids
        if reviewer_id in settings.reviewer_excluded_user_ids:
            raise ApiError(503, "LEARNER_LOGIN_NOT_CONFIGURED", "默认审核人已停用。")
        if pool:
            active_pool = set(session.scalars(select(User.id).join(RoleAssignment, RoleAssignment.user_id == User.id)
                .where(User.id.in_(pool), User.organization_id == organization_id,
                       User.status == UserStatus.ACTIVE, RoleAssignment.organization_id == organization_id,
                       RoleAssignment.role == Role.REVIEWER)).all())
            if active_pool != set(pool):
                raise ApiError(503, "LEARNER_LOGIN_NOT_CONFIGURED", "公共审核人员尚未配置完整。")
        reviewer = session.scalar(select(User.id).join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(User.id == reviewer_id, User.organization_id == organization_id,
                   User.status == UserStatus.ACTIVE, RoleAssignment.organization_id == organization_id,
                   RoleAssignment.role == Role.REVIEWER))
        journey = published_formal_journey(session, organization_id)
        if reviewer is None or journey is None:
            raise ApiError(503, "LEARNER_LOGIN_NOT_CONFIGURED", "默认学习旅程或审核人尚未配置。")
        enrollment = Enrollment(id=uuid.uuid4(), organization_id=organization_id,
            learner_id=user.id, reviewer_id=reviewer, journey_version_id=journey.id,
            review_assignment_mode="SHARED" if pool else "ASSIGNED",
            status=EnrollmentStatus.ACTIVE, revision=1)
        session.add(enrollment)
        session.flush()
        create_journey_assignments(session, enrollment=enrollment)
        add_audit(session, request_id=request_id, organization_id=organization_id,
            actor_id=user.id, action="learner.identity_registered", resource_type="enrollment",
            resource_id=enrollment.id, result="SUCCESS", details={"provider": provider,
                "review_mode": "SHARED" if pool else "ASSIGNED"})
    session.flush()
    return identity
