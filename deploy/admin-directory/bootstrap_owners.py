"""Bind only the two owner-approved production administrators to verified Feishu identities."""
import json
import sys
import uuid
from sqlalchemy import select
from journey_api.config import get_settings
from journey_api.db import SessionLocal, engine
from journey_api.feishu_directory import FeishuDirectory
from journey_api.identity import add_audit
from journey_api.models import ExternalIdentity, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.review_admin_routes import directory_subject

OWNERS = [
    ('李鑫波', 'e10822a0', '934d4bab-2494-4ed3-ac15-9378913b9c01'),
    ('刘默文', 'f20eef44', 'fc74182c-048c-41de-bae6-c7ccd95f0a93'),
]
CHECKPOINT = 'IMPORTS'


def resolve_owner(session, org, person, expected_id, *, apply):
    approved = next((item for item in OWNERS if item[0] == person['name'] and uuid.UUID(item[2]) == expected_id), None)
    assert approved and person['open_id'].endswith(approved[1]), 'OWNER_NOT_APPROVED'
    subject = directory_subject(person['open_id'])
    query = select(ExternalIdentity).where(ExternalIdentity.provider == 'FEISHU', ExternalIdentity.subject == subject)
    identity = session.scalar(query.with_for_update() if apply else query)
    if identity:
        assert identity.organization_id == org, 'OWNER_IDENTITY_WRONG_ORGANIZATION'
        assert identity.revoked_at is None, 'OWNER_IDENTITY_REVOKED'
        user_id = identity.user_id
        if person['name'] == '李鑫波':
            assert user_id == expected_id, 'PINNED_OWNER_IDENTITY_MISMATCH'
    else:
        assert person['name'] == '刘默文', 'EXISTING_OWNER_IDENTITY_MISSING'
        user_id = expected_id
        assert not session.scalar(select(ExternalIdentity.id).where(ExternalIdentity.user_id == user_id)), 'OWNER_ALREADY_LINKED'
    query = select(User).where(User.id == user_id, User.organization_id == org)
    user = session.scalar(query.with_for_update() if apply else query)
    assert user and user.status == UserStatus.ACTIVE and user.display_name == person['name'], 'OWNER_USER_MISMATCH'
    roles = set(session.scalars(select(RoleAssignment.role).where(
        RoleAssignment.user_id == user_id, RoleAssignment.organization_id == org)))
    needs_reviewer = Role.REVIEWER not in roles
    if needs_reviewer:
        # A verified employee may already have signed in as a learner, while
        # the historical reviewer record remains unbound. Grant the explicitly
        # approved authority to that existing account without rebinding/merging.
        assert identity and person['name'] == '刘默文' and user_id != expected_id, 'OWNER_REVIEWER_ROLE_MISSING'
    return user, subject, identity is None, needs_reviewer


def configure_owners(session, org, verified, *, apply, release):
    global CHECKPOINT
    resolved = []
    for position, (expected_id, person) in enumerate(verified, 1):
        CHECKPOINT = 'DATABASE_OWNER_' + str(position)
        resolved.append(resolve_owner(session, org, person, expected_id, apply=apply))
    ids = {user.id for user, _, _, _ in resolved}
    assert len(ids) == 2, 'OWNER_ACCOUNTS_NOT_DISTINCT'
    if not apply:
        return
    actor_id = resolved[0][0].id
    for user, subject, needs_link, needs_reviewer in resolved:
        CHECKPOINT = 'GRANT_OWNER'
        row = session.get(ReviewAdminAccess, user.id)
        assert row is None or (row.access_role == 'super_admin' and row.can_grant_super_admin and row.revoked_at is None), 'OWNER_ACCESS_CONFLICT'
        if needs_link:
            session.add(ExternalIdentity(id=uuid.uuid4(), organization_id=org, user_id=user.id,
                provider='FEISHU', subject=subject, revision=1))
        if needs_reviewer:
            session.add(RoleAssignment(id=uuid.uuid4(), organization_id=org, user_id=user.id, role=Role.REVIEWER))
        if row is None:
            session.add(ReviewAdminAccess(user_id=user.id, organization_id=org,
                access_role='super_admin', level='高级', domain='产品开发', can_grant_super_admin=True,
                granted_by=actor_id, revision=1))
        if row is None or needs_link or needs_reviewer:
            add_audit(session, request_id='admin-directory-release-'+uuid.uuid4().hex,
                organization_id=org, actor_id=actor_id, action='review_admin.approved_owner_bootstrap',
                resource_type='review_admin', resource_id=user.id, result='SUCCESS',
                details={'release':release, 'can_grant_super_admin':True,
                         'reviewer_role_added':needs_reviewer, 'identity_link_added':needs_link})
    session.flush()
    actual = set(session.scalars(select(ReviewAdminAccess.user_id).where(
        ReviewAdminAccess.organization_id == org, ReviewAdminAccess.can_grant_super_admin.is_(True))))
    assert actual == ids, 'UNEXPECTED_GRANT_OWNER'


def main():
    global CHECKPOINT
    CHECKPOINT = 'CONFIGURATION'
    assert sys.argv[1:] in [['--check'], ['--apply']]
    apply = sys.argv[1] == '--apply'
    settings = get_settings()
    assert settings.app_env == 'production' and not settings.allow_fixture_identity
    assert settings.feishu_app_id == 'cli_aaef896604b85bb4'
    assert engine.url.database == 'journey_next_canary_20260901_c72fea5'
    org = settings.feishu_learner_organization_id
    assert str(org) == '10000000-0000-4000-8000-000000000001'
    directory = FeishuDirectory(settings)
    CHECKPOINT = 'DIRECTORY_READ'
    profiles = directory.read_profiles()
    verified = []
    for name, suffix, user_id in OWNERS:
        CHECKPOINT = 'DIRECTORY_OWNER_' + str(len(verified) + 1)
        matches = [p for p in profiles if p['name'] == name]
        assert len(matches) == 1 and matches[0]['open_id'].endswith(suffix), 'OWNER_DIRECTORY_MISMATCH'
        person = directory.get_user(matches[0]['open_id'])
        assert person['name'] == name and person['open_id'].endswith(suffix)
        verified.append((uuid.UUID(user_id), person))
    with SessionLocal() as session:
        configure_owners(session, org, verified, apply=apply, release=settings.app_release)
        if apply:
            CHECKPOINT = 'COMMIT_OWNERS'
            session.commit()
        print(json.dumps({'approved_owners':2,'mode':'applied' if apply else 'verified',
                          'local_test_data_imported':False,'existing_users_preserved':True}))


if __name__ == '__main__':
    main()
