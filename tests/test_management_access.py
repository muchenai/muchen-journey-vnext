"""Authenticated staff capability, roster matching and growth-account invariants."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from starlette.requests import Request

from journey_api.auth import Actor
from journey_api.course_workspace_models import CourseStudyAward, WorkspaceCourse
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.management_access import course_scope
from journey_api.management_access_routes import (
    Grant, MatchNames, SetIssuers, change_experience,
    configure_issuers, match_directory, read_experience, read_issuer_settings,
)
from journey_api.management_access_models import CourseManagementSettings, ExperienceRosterSnapshot
from journey_api.models import CompletionCode, ExternalIdentity, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.novice_economy import growth_history, wallet
from journey_api.review_admin_models import ReviewAdminAccess


def request():
    req = Request({"type": "http", "headers": []})
    req.state.request_id = str(uuid4())
    return req


def person(org, name, staff=None):
    role = Role.REVIEWER if staff else Role.LEARNER
    user_id = uuid4()
    with SessionLocal.begin() as session:
        session.add(User(id=user_id, organization_id=org, display_name=name))
        session.flush()
        session.add(RoleAssignment(id=uuid4(), organization_id=org, user_id=user_id, role=role))
        if staff:
            session.add(ExternalIdentity(id=uuid4(), organization_id=org, user_id=user_id,
                                         provider="FEISHU", subject=uuid4().hex))
            session.add(ReviewAdminAccess(user_id=user_id, organization_id=org, access_role=staff,
                                          granted_by=user_id, can_grant_super_admin=(staff == "super_admin")))
    return Actor(user_id, org, frozenset({role}), name, entry_role=role)


@pytest.fixture
def accounts():
    org = uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=org, name="管理权限隔离组织"))
    return (person(org, "课程负责人", "super_admin"), person(org, "发放人一", "admin"),
            person(org, "发放人二", "admin"), person(org, "测试学员"))


def change(actor, command):
    with SessionLocal() as session:
        handler = configure_issuers if isinstance(command, SetIssuers) else change_experience
        return handler(command, request(), actor, session)["data"]


def configure(owner, a, b):
    return change(owner, SetIssuers(action="configure", issuers=[a.id, b.id], revision=0))


def lookup(actor, names):
    with SessionLocal() as session:
        return match_directory(MatchNames(names=names), request(), actor, session)["data"]


def test_course_and_issuer_rights_are_independent_of_retired_assignments(accounts):
    owner, issuer, other, learner = accounts
    with pytest.raises(ApiError) as denied:
        configure(issuer, issuer, other)
    assert denied.value.status_code == 403
    with pytest.raises(ApiError):
        configure(owner, issuer, issuer)
    configure(owner, issuer, other)
    with pytest.raises(ApiError) as stale:
        configure(owner, issuer, other)
    assert stale.value.status_code == 409
    with SessionLocal.begin() as session:
        state = session.get(CourseManagementSettings, owner.organization_id)
        state.assignments = {"ownerId": str(issuer.id), "adminIds": [str(learner.id)], "reviewers": []}
    with SessionLocal() as session:
        assert course_scope(session, owner)["isSuperAdmin"]
        assert not course_scope(session, issuer)["isSuperAdmin"]
        assert read_experience(request(), issuer, session)["data"]["canGrant"]
        with pytest.raises(ApiError):
            course_scope(session, learner)
        with pytest.raises(ApiError):
            read_issuer_settings(request(), issuer, session)


def test_racing_same_batch_posts_credit_once_and_visible_in_history(accounts):
    owner, issuer, other, learner = accounts
    configure(owner, issuer, other)
    command = Grant(action="grant", mode="single", batch="入职培训", reason="现场课程通过",
                    rows=[{"learnerId": learner.id, "points": 6}])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda actor: change(actor, command), (issuer, other)))
    assert sorted(row["added"] for row in results) == [0, 1]
    conflict = command.model_copy(update={"reason": "不同的事由"})
    with pytest.raises(ApiError) as stale:
        change(issuer, conflict)
    assert stale.value.status_code == 409
    with SessionLocal.begin() as session:
        course = WorkspaceCourse(scope="academy", author_id=owner.id, organization_id=owner.organization_id, draft={})
        session.add(course)
        session.flush()
        session.add(CourseStudyAward(scope="academy", course_id=course.id, user_id=learner.id, title="完成第 1 章",
                                    organization_id=owner.organization_id, award_key="chapter:1", xp=10))
    with SessionLocal() as session:
        assert wallet(session, learner)["availableXp"] == 70
        history = growth_history(session, learner)
        assert {(row["kind"], row["xp"]) for row in history["items"]} == {("offline_grant", 60), ("course_reward", 10)}
        assert history["total"] == 2 and growth_history(session, owner)["total"] == 0
        assert len(read_experience(request(), issuer, session)["data"]["grants"]) == 1
        with pytest.raises(ApiError) as denied:
            read_experience(request(), owner, session)
        assert denied.value.status_code == 403


def test_roster_requires_matching_snapshot_and_active_authorized_issuer(accounts):
    owner, issuer, other, learner = accounts
    configure(owner, issuer, other)
    name = learner.display_name
    snapshot = lookup(issuer, [name])
    assert snapshot["matches"][0]["candidates"][0]["id"] == str(learner.id)
    command = Grant(action="grant", mode="list", batch="名单导入", reason="核对后发放",
                    snapshotId=snapshot["snapshotId"], rows=[{"learnerId": learner.id, "name": name, "points": 2}])
    with pytest.raises(ApiError) as foreign:
        change(other, command)
    assert foreign.value.status_code == 409
    assert change(issuer, command) == {"added": 1, "skipped": 0}
    with SessionLocal.begin() as session:
        session.get(ExperienceRosterSnapshot, command.snapshotId).expires_at = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(ApiError):
        change(issuer, command)
    person(owner.organization_id, name)
    same_name = lookup(issuer, [name])["matches"][0]["candidates"]
    assert len(same_name) == 2 and all(row["indistinguishable"] for row in same_name)
    with SessionLocal.begin() as session:
        session.get(ReviewAdminAccess, issuer.id).revoked_at = datetime.now(UTC)
    with pytest.raises(ApiError) as revoked:
        lookup(issuer, [name])
    assert revoked.value.status_code == 403


def test_grants_follow_graduation_code_account_and_replay_consistently(accounts):
    owner, issuer, other, corporate = accounts
    configure(owner, issuer, other)
    retired = person(owner.organization_id, "已迁移的临时学员")
    command = Grant(action="grant", mode="single", batch="迁移前", reason="线下学习",
                    rows=[{"learnerId": corporate.id, "xp": 11}])
    assert change(issuer, command)["added"] == 1
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        session.get(User, retired.id).status = UserStatus.DISABLED
        session.add(CompletionCode(id=uuid4(), organization_id=retired.organization_id, user_id=retired.id,
                                   code_hash=uuid4().hex, code_ciphertext="test", code_hint="test",
                                   expires_at=now + timedelta(days=1), used_at=now, migrated_to_user_id=corporate.id))
    assert change(issuer, command)["skipped"] == 1
    assert change(issuer, command.model_copy(update={"batch":"迁移后"}))["added"] == 1
    with SessionLocal() as session:
        assert wallet(session, retired)["xp"] == 22
        assert growth_history(session, retired)["total"] == 2

def test_only_protected_admin_configures_and_invalid_selection_does_not_replace_existing(accounts):
    owner, issuer, other, learner = accounts
    configure(owner, issuer, other)
    with SessionLocal.begin() as session:
        ordinary_super = session.get(ReviewAdminAccess, issuer.id)
        ordinary_super.access_role = "super_admin"
        state = session.get(CourseManagementSettings, owner.organization_id)
        state.assignments = {"ownerId": str(issuer.id), "adminIds": [], "reviewers": []}
    # A previous course owner who is also a standard super admin cannot configure issuers.
    with SessionLocal() as session:
        with pytest.raises(ApiError) as denied:
            read_issuer_settings(request(), issuer, session)
        assert denied.value.status_code == 403
    invalid = SetIssuers(action="configure", issuers=[learner.id, other.id], revision=1)
    with pytest.raises(ApiError) as blocked:
        change(owner, invalid)
    assert blocked.value.message == f"「{learner.display_name}」尚未开通管理系统访问权限。请先在「成员认证」中为其开通权限"
    with SessionLocal() as session:
        saved = read_issuer_settings(request(), owner, session)["data"]
        assert saved["issuers"] == [str(issuer.id),str(other.id)] and saved["revision"] == 1
        assert all(person["hasManagementAccess"] for person in saved["selected"])
        granted = change(owner, SetIssuers(action="configure", issuers=[owner.id,other.id], revision=1))
        assert granted["configured"]
        with pytest.raises(ApiError) as replaced:
            read_experience(request(), issuer, session)
        assert replaced.value.status_code == 403
    with pytest.raises(ApiError) as replaced:
        change(issuer, Grant(action="grant",mode="single",batch="旧页面",reason="旧请求",
            rows=[{"learnerId":learner.id,"xp":10}]))
    assert replaced.value.status_code == 403
    with pytest.raises(ApiError) as replaced:
        lookup(issuer, [learner.display_name])
    assert replaced.value.status_code == 403


@pytest.mark.parametrize("reason", ["role", "excluded", "revoked", "identity", "disabled", "foreign"])
def test_cannot_assign_someone_without_review_login(accounts, reason, monkeypatch):
    from sqlalchemy import select
    from journey_api.config import get_settings
    owner, issuer, other, _ = accounts
    with SessionLocal.begin() as session:
        if reason == "role":
            role = session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == issuer.id))
            role.role = Role.OPERATOR
        if reason == "excluded":
            monkeypatch.setattr(get_settings(), "reviewer_excluded_user_ids", [issuer.id])
        if reason == "revoked":
            session.get(ReviewAdminAccess,issuer.id).revoked_at = datetime.now(UTC)
        if reason == "identity":
            session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == issuer.id)).revoked_at = datetime.now(UTC)
        if reason == "disabled":
            session.get(User, issuer.id).status = UserStatus.DISABLED
        if reason == "foreign":
            foreign = uuid4()
            session.add(Organization(id=foreign,name="其他组织"))
    if reason == "foreign":
        issuer = person(foreign, "其他管理员", "admin")
    with pytest.raises(ApiError) as blocked:
        configure(owner, issuer, other)
    assert blocked.value.status_code == 422
