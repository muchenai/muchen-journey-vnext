"""Guild isolation, artifact persistence and legacy certification compatibility."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import uuid

import pytest
from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.guild_catalog import HALLS, TASKS
from journey_api.guild_models import GuildCertificationRequest, GuildTaskSubmission
from journey_api.guild_routes import owned_evidence
from journey_api.models import CompletionCode, ExternalIdentity, Organization, Role, RoleAssignment, User, UserStatus
from test_guild_certification import users, account, add_badge, ok, post, review, snapshot

ARTIFACT = "需求确认需要明确数据交付范围、有效条数、歧义样本处理、质量抽检标准、验收格式以及确认责任人。承诺交期前应与客户确认这些边界并保存可复核的书面证据。"


def join(user, guild="multilingual"):
    return ok(post(user, "me/guild/join", dict(guildId=guild)))


def save(user, *, guild="multilingual", level=1, artifact=ARTIFACT, checks=None, submit=True, revision=0):
    return post(user, "me/guild/tasks", dict(guildId=guild, level=level, artifact=artifact,
        checks=TASKS[level - 1]["checks"] if checks is None else checks, submit=submit, expectedRevision=revision))


def apply(user, guild="multilingual", level=1):
    submission = next((item for item in snapshot(user)["submissions"] if item["guildId"] == guild and item["level"] == level), None)
    return post(user, "me/guild/requests", dict(guildId=guild, level=level, expectedRevision=submission["revision"] if submission else 1))


def test_halls_catalog_join_selection_and_cross_account_persistence(users):
    learner, _ = users
    state = snapshot(learner)
    assert [hall["id"] for hall in state["halls"]] == [hall["id"] for hall in HALLS]
    assert len(state["tasks"]) == 3
    assert all(task["source"] == "project39-template" and task["mentor"] == "内置任务模板" for task in state["tasks"])
    assert post(learner, "me/guild/join", {"guildId": "unknown"}).status_code == 422
    join(learner, "functional")
    reloaded = snapshot(account(learner["org"], user_id=learner["id"]))
    assert reloaded["joinedGuild"] == "functional"
    assert {hall["id"] for hall in reloaded["halls"] if hall["joined"]} == {"functional", "multilingual"}
    other = snapshot(account(learner["org"]))
    assert other["joinedGuild"] is None and not any(hall["joined"] for hall in other["halls"])


def test_draft_submit_require_real_badges_self_checks_and_correct_revision(users):
    learner, _ = users
    assert save(learner, artifact="草稿", checks=[], submit=False).status_code == 409
    add_badge(learner)
    assert save(learner, guild="functional").status_code == 409
    draft = ok(save(learner, artifact="草稿", checks=[], submit=False))["submissions"][0]
    assert draft["artifact"] == "草稿" and draft["status"] == "draft" and draft["submittedAt"] is None
    assert apply(learner).status_code == 409
    assert save(learner, revision=0).status_code == 409
    assert save(learner, artifact="太短", revision=1).status_code == 422
    assert save(learner, artifact="字" * 6001, revision=1).status_code == 422
    for checks in ([], TASKS[0]["checks"][:2], [TASKS[0]["checks"][0]] * 3, ["伪造"]):
        assert save(learner, checks=checks, revision=1).status_code == 422
    submitted = ok(save(learner, revision=1))
    assert submitted["submissions"][0]["revision"] == 2
    assert submitted["requirements"][0]["eligible"] and submitted["requirements"][0]["taskSubmitted"]
    assert save(learner, level=2).status_code == 409
    assert post(learner, "me/guild/requests", {"level": 1, "expectedRevision": 1}).status_code == 409


def test_independent_guild_requests_levels_and_immutable_artifact_snapshots(users):
    learner, staff = users
    add_badge(learner)
    ok(save(learner))
    first = ok(apply(learner))["requests"][0]
    assert first["task"]["artifact"] == ARTIFACT and first["task"]["source"] == "project39-template"
    assert first["guildId"] == "multilingual" and first["guildTitle"] == HALLS[0]["title"]
    assert save(learner, revision=1).status_code == 409
    join(learner, "functional")
    assert snapshot(learner)["level"] == 0 and snapshot(learner)["requests"] == []
    ok(save(learner, guild="functional"))
    second = ok(apply(learner, "functional"))["requests"][0]
    ok(review(staff, first["id"]))
    current = snapshot(learner)
    assert current["level"] == 0 and current["requests"][0]["id"] == second["id"]
    assert next(h for h in current["halls"] if h["id"] == "multilingual")["level"] == 1
    ok(review(staff, second["id"]))
    assert snapshot(learner)["level"] == 1
    assert save(learner, guild="functional", revision=1).status_code == 409


def test_return_preserves_old_snapshot_and_requires_resubmission(users):
    learner, staff = users
    add_badge(learner)
    ok(save(learner))
    first = ok(apply(learner))["requests"][0]
    ok(review(staff, first["id"], "returned", "请明确验收责任人"))
    returned = snapshot(learner)
    assert returned["submissions"][0]["status"] == "draft" and returned["submissions"][0]["revision"] == 2
    assert returned["requests"][0]["task"]["artifact"] == ARTIFACT
    assert not returned["requirements"][0]["eligible"]
    assert apply(learner).status_code == 409
    revised = ARTIFACT + "由客户指定验收负责人签署最终确认。"
    ok(save(learner, artifact=revised, revision=2))
    state = ok(apply(learner))
    assert state["requests"][0]["task"]["artifact"] == revised
    assert state["requests"][1]["task"]["artifact"] == ARTIFACT
    ok(review(staff, state["requests"][0]["id"]))


def test_concurrent_drafts_reject_lost_update(users):
    learner, _ = users
    add_badge(learner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda i: save(learner, artifact=f"草稿{i}", checks=[], submit=False), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    stored = snapshot(learner)["submissions"][0]
    assert stored["revision"] == 1
    assert stored["artifact"] in {"草稿0", "草稿1"}


def test_legacy_global_history_keeps_null_scope_and_remains_reviewable(users):
    learner, staff = users
    add_badge(learner)
    request_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        evidence = owned_evidence(session, learner["org"], learner["id"])
        session.add(GuildCertificationRequest(id=request_id, organization_id=learner["org"], user_id=learner["id"],
            student_name="旧认证学员", level=1, status="pending", evidence=evidence, reviewer_name="", reason=""))
    legacy = snapshot(learner)["legacyRequests"][0]
    assert legacy["guildId"] is None and legacy["task"] is None and legacy["guildTitle"] == "旧版全局认证"
    ok(post(learner, "me/guild/requests", {"level": 1, "expectedRevision": 1}))
    ok(save(learner))
    scoped = ok(apply(learner))["requests"][0]
    ok(review(staff, request_id))
    state = snapshot(learner)
    assert state["level"] == 0 and state["legacyRequests"][0]["status"] == "approved"
    assert state["requests"][0]["id"] == scoped["id"]
    ok(review(staff, scoped["id"]))
    assert snapshot(learner)["level"] == 1


def test_review_revalidates_submitted_artifact_integrity(users):
    learner, staff = users
    add_badge(learner)
    ok(save(learner))
    request_id = ok(apply(learner))["requests"][0]["id"]
    with SessionLocal.begin() as session:
        row = session.get(GuildTaskSubmission, (learner["org"], learner["id"], "multilingual", 1))
        row.artifact = ARTIFACT + "异常修改"
    assert review(staff, request_id).status_code == 409
    ok(review(staff, request_id, "returned", "请重新提交成果"))


def test_apply_requires_confirmed_revision_and_rejects_stale_tab(users):
    learner, _ = users
    add_badge(learner)
    ok(save(learner))
    command = dict(guildId="multilingual", level=1)
    assert post(learner, "me/guild/requests", command).status_code == 422
    for invalid in (0, -1, "1", True):
        assert post(learner, "me/guild/requests", {**command, "expectedRevision": invalid}).status_code == 422
    # Another tab replaces the artifact after this tab displayed revision 1.
    ok(save(learner, artifact=ARTIFACT + "更新后的客户确认记录。", revision=1))
    stale = post(learner, "me/guild/requests", {**command, "expectedRevision": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "GUILD_REVISION_CONFLICT"
    assert snapshot(learner)["requests"] == []
    created = ok(post(learner, "me/guild/requests", {**command, "expectedRevision": 2}))["requests"][0]
    assert created["task"]["revision"] == 2
    assert post(learner, "me/guild/requests", {**command, "expectedRevision": 1}).status_code == 409
    retried = ok(post(learner, "me/guild/requests", {**command, "expectedRevision": 2}))["requests"][0]
    assert retried["id"] == created["id"]


def migrated_corporate_account(learner, *, invalid=None):
    """Mirror the consumed-code identity link; expiry no longer revokes migration."""
    now = datetime.now(UTC)
    organization_id = learner["org"]
    if invalid == "cross_organization":
        organization_id = uuid.uuid4()
        with SessionLocal.begin() as session:
            session.add(Organization(id=organization_id, name="Unrelated guild organization"))
    corporate = account(organization_id)
    with SessionLocal.begin() as session:
        session.get(User, learner["id"]).status = UserStatus.DISABLED
        if invalid == "disabled_corporate":
            session.get(User, corporate["id"]).status = UserStatus.DISABLED
        if invalid == "missing_learner_role":
            role = session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == corporate["id"],
                RoleAssignment.role == Role.LEARNER))
            session.delete(role)
        session.add(ExternalIdentity(id=uuid.uuid4(), organization_id=organization_id,
            user_id=corporate["id"], provider="PHONE" if invalid == "not_feishu" else "FEISHU",
            subject="isolated-guild-migration-" + uuid.uuid4().hex, revision=1,
            revoked_at=now if invalid == "revoked_feishu" else None))
        session.add(CompletionCode(id=uuid.uuid4(), organization_id=learner["org"], user_id=learner["id"],
            code_hash=uuid.uuid4().hex + uuid.uuid4().hex, code_ciphertext="isolated-test-unused-ciphertext",
            code_hint="test", expires_at=now - timedelta(days=1),
            used_at=None if invalid == "unused_code" else now - timedelta(days=2), migrated_to_user_id=corporate["id"]))
    return corporate


def test_migrated_feishu_learner_can_submit_and_receive_independent_approval(users):
    learner, staff = users
    add_badge(learner)
    corporate = migrated_corporate_account(learner)
    # These authenticated writes now belong to the retired temporary owner.
    ok(save(corporate))
    request_id = ok(apply(corporate))["requests"][0]["id"]
    corporate_staff = account(corporate["org"], admin=True, user_id=corporate["id"])
    assert review(corporate_staff, request_id).status_code == 403
    ok(review(staff, request_id))
    assert snapshot(corporate)["level"] == 1
    with SessionLocal() as session:
        row = session.get(GuildCertificationRequest, uuid.UUID(request_id))
        assert row.user_id == learner["id"] and row.reviewer_id == staff["id"]
        assert session.get(User, learner["id"]).status == UserStatus.DISABLED
        assert row.task_snapshot["artifact"] == ARTIFACT


@pytest.mark.parametrize("invalid", ["unused_code", "cross_organization", "disabled_corporate",
    "revoked_feishu", "not_feishu", "missing_learner_role"])
def test_invalid_migration_does_not_make_disabled_learner_eligible(users, invalid):
    learner, staff = users
    add_badge(learner)
    ok(save(learner))
    request_id = ok(apply(learner))["requests"][0]["id"]
    migrated_corporate_account(learner, invalid=invalid)
    rejected = review(staff, request_id)
    assert rejected.status_code == 409
    with SessionLocal() as session:
        row = session.get(GuildCertificationRequest, uuid.UUID(request_id))
        assert row.status == "pending" and row.reviewer_id is None
