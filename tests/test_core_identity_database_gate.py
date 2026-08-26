import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from journey_api.db import SessionLocal
from journey_api.fixtures import (
    ENROLLMENT_ID,
    OPERATOR_ID,
    ORGANIZATION_ID,
    REVIEWER_ID,
    TASK_VERSION_ID,
)
from journey_api.identity import utc_now
from journey_api.models import (
    ExternalIdentity,
    IdentitySession,
    Invite,
    InviteStatus,
    JoinContext,
    JoinContextStatus,
    Organization,
    Role,
    RoleAssignment,
    User,
    UserStatus,
)


def _foreign_user() -> tuple[uuid.UUID, uuid.UUID]:
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=organization_id, name="CORE-001 synthetic foreign org"))
        session.flush()
        session.add(
            User(
                id=user_id,
                organization_id=organization_id,
                display_name="CORE-001 synthetic foreign person",
                status=UserStatus.ACTIVE,
            )
        )
    return organization_id, user_id


def _flush_must_fail(instance: object) -> None:
    with SessionLocal() as session:
        session.add(instance)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_database_rejects_cross_organization_role_and_identity_facts() -> None:
    _foreign_organization_id, foreign_user_id = _foreign_user()

    _flush_must_fail(
        RoleAssignment(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            user_id=foreign_user_id,
            role=Role.LEARNER,
        )
    )
    _flush_must_fail(
        ExternalIdentity(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            user_id=foreign_user_id,
            provider="CORE001_TEST",
            subject=f"subject-{uuid.uuid4()}",
            revision=1,
        )
    )
    _flush_must_fail(
        IdentitySession(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            user_id=foreign_user_id,
            external_identity_id=None,
            role=Role.LEARNER,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            expires_at=utc_now() + timedelta(minutes=30),
        )
    )


def test_database_rejects_cross_organization_invite_target() -> None:
    _foreign_organization_id, foreign_user_id = _foreign_user()
    _flush_must_fail(
        Invite(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            purpose="CORE-001 synthetic cross-organization invite must fail",
            role=Role.LEARNER,
            reviewer_id=REVIEWER_ID,
            task_version_id=TASK_VERSION_ID,
            journey_version_id=None,
            target_user_id=foreign_user_id,
            status=InviteStatus.ACTIVE,
            expires_at=utc_now() + timedelta(hours=1),
            created_by=OPERATOR_ID,
            revision=1,
        )
    )


def test_database_rejects_cross_organization_join_context_lineage() -> None:
    _foreign_organization_id, foreign_user_id = _foreign_user()
    invite_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            Invite(
                id=invite_id,
                organization_id=ORGANIZATION_ID,
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                purpose="CORE-001 synthetic join lineage",
                role=Role.LEARNER,
                reviewer_id=REVIEWER_ID,
                task_version_id=TASK_VERSION_ID,
                journey_version_id=None,
                target_user_id=None,
                status=InviteStatus.ACTIVE,
                expires_at=utc_now() + timedelta(hours=1),
                created_by=OPERATOR_ID,
                revision=1,
            )
        )
    _flush_must_fail(
        JoinContext(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            invite_id=invite_id,
            user_id=foreign_user_id,
            enrollment_id=ENROLLMENT_ID,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            status=JoinContextStatus.PENDING,
            created_user=False,
            expires_at=utc_now() + timedelta(minutes=15),
        )
    )
