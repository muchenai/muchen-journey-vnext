"""Production owner resolution against real ORM identities, without provider calls."""
from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import uuid

import pytest
from sqlalchemy import func, select
from journey_api.db import SessionLocal
from journey_api.models import AuditEntry, ExternalIdentity, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_models import ReviewAdminAccess

spec = importlib.util.spec_from_file_location('production_owner_bootstrap',
    Path(__file__).resolve().parents[1] / 'deploy/admin-directory/bootstrap_owners.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@pytest.fixture
def owners(monkeypatch):
    with SessionLocal() as session:
        org = uuid.uuid4()
        li, legacy_liu, current_liu = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        monkeypatch.setattr(bootstrap, 'OWNERS', [
            ('李鑫波','e10822a0',str(li)), ('刘默文','f20eef44',str(legacy_liu))])
        session.add(Organization(id=org,name='Owner bootstrap test'))
        session.flush()
        for uid, name in [(li,'李鑫波'),(legacy_liu,'刘默文'),(current_liu,'刘默文')]:
            session.add(User(id=uid,organization_id=org,display_name=name,status=UserStatus.ACTIVE))
        session.flush()
        for uid, role in [(li,Role.REVIEWER),(legacy_liu,Role.REVIEWER),(current_liu,Role.LEARNER)]:
            session.add(RoleAssignment(id=uuid.uuid4(),organization_id=org,user_id=uid,role=role))
        verified = []
        for expected, actual, name, suffix in [(li,li,'李鑫波','e10822a0'),(legacy_liu,current_liu,'刘默文','f20eef44')]:
            person={'name':name,'open_id':'ou_'+uuid.uuid4().hex+suffix}
            verified.append((expected,person))
            session.add(ExternalIdentity(id=uuid.uuid4(),organization_id=org,user_id=actual,
                provider='FEISHU',subject=bootstrap.directory_subject(person['open_id']),revision=1))
        session.flush()
        yield session, org, verified, li, legacy_liu, current_liu
        session.rollback()


def identity_for(session, person):
    return session.scalar(select(ExternalIdentity).where(
        ExternalIdentity.subject == bootstrap.directory_subject(person['open_id'])))


def test_existing_feishu_learner_receives_approved_grant_without_rebinding_or_merging(owners):
    session, org, verified, li, legacy, current = owners
    identity_id = identity_for(session,verified[1][1]).id
    bootstrap.configure_owners(session,org,verified,apply=False,release='test')
    assert not session.scalar(select(ReviewAdminAccess).where(ReviewAdminAccess.organization_id==org))
    bootstrap.configure_owners(session,org,verified,apply=True,release='test')
    assert identity_for(session,verified[1][1]).id == identity_id
    assert identity_for(session,verified[1][1]).user_id == current
    assert session.get(ReviewAdminAccess,legacy) is None
    assert session.get(User,legacy).display_name == '刘默文'
    assert set(session.scalars(select(User.id).where(User.organization_id==org))) == {li,legacy,current}
    assert set(session.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id==current))) == {Role.LEARNER,Role.REVIEWER}
    assert set(session.scalars(select(ReviewAdminAccess.user_id).where(ReviewAdminAccess.organization_id==org))) == {li,current}
    audits = session.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.organization_id==org))
    bootstrap.configure_owners(session,org,verified,apply=True,release='test')
    assert session.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.organization_id==org)) == audits


@pytest.mark.parametrize('problem,code',[
    ('revoked','OWNER_IDENTITY_REVOKED'),('disabled','OWNER_USER_MISMATCH'),
    ('wrong_name','OWNER_USER_MISMATCH'),('wrong_org','OWNER_IDENTITY_WRONG_ORGANIZATION')])
def test_invalid_bound_identity_still_blocks_owner_grant(owners,problem,code):
    session, org, verified, _, _, current = owners
    identity = identity_for(session,verified[1][1])
    user = session.get(User,current)
    if problem == 'revoked':
        identity.revoked_at = datetime.now(UTC)
    elif problem == 'disabled':
        user.status = UserStatus.DISABLED
    elif problem == 'wrong_name':
        user.display_name = 'Different person'
    else:
        other = uuid.uuid4(); other_user = uuid.uuid4()
        session.add(Organization(id=other,name='Other organization')); session.flush()
        session.add(User(id=other_user,organization_id=other,display_name='刘默文',status=UserStatus.ACTIVE)); session.flush()
        identity.organization_id=other; identity.user_id=other_user
    session.flush()
    with pytest.raises(AssertionError, match=code):
        bootstrap.configure_owners(session,org,verified,apply=True,release='test')
    assert not session.scalar(select(ReviewAdminAccess).where(ReviewAdminAccess.organization_id==org))


def test_first_owner_stays_pinned_to_existing_approved_user(owners):
    session, org, verified, _, _, _ = owners
    other = User(id=uuid.uuid4(),organization_id=org,display_name='李鑫波',status=UserStatus.ACTIVE)
    session.add(other); session.flush()
    identity_for(session,verified[0][1]).user_id=other.id
    session.flush()
    with pytest.raises(AssertionError,match='PINNED_OWNER_IDENTITY_MISMATCH'):
        bootstrap.configure_owners(session,org,verified,apply=True,release='test')


def test_unbound_historical_reviewer_is_used_only_when_identity_does_not_exist(owners):
    session, org, verified, _, legacy, current = owners
    session.delete(identity_for(session,verified[1][1])); session.flush()
    bootstrap.configure_owners(session,org,verified,apply=False,release='test')
    assert identity_for(session,verified[1][1]) is None
    bootstrap.configure_owners(session,org,verified,apply=True,release='test')
    assert identity_for(session,verified[1][1]).user_id == legacy
    assert session.get(ReviewAdminAccess,legacy).can_grant_super_admin
    assert session.get(ReviewAdminAccess,current) is None


def test_revoked_explicit_access_is_not_reactivated(owners):
    session, org, verified, li, _, current = owners
    session.add(ReviewAdminAccess(user_id=current,organization_id=org,access_role='admin',
        level='初级',domain='产品开发',granted_by=li,revoked_at=datetime.now(UTC)))
    session.flush()
    with pytest.raises(AssertionError,match='OWNER_ACCESS_CONFLICT'):
        bootstrap.configure_owners(session,org,verified,apply=True,release='test')
    assert session.get(ReviewAdminAccess,current).revoked_at is not None
