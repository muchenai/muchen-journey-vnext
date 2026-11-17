"""Explicit production provisioning must never reset real learning records."""
from collections import Counter
import os
import uuid

import pytest
from sqlalchemy import select, text

from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.exploration_models import ExplorationCatalogTask, ExplorationMaterial, ExplorationWork
from journey_api.models import Assignment, AuditEntry, Submission, TaskDefinition, TaskVersion, User, UserStatus
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminAccess, ReviewAdminTask
from scripts.upgrade_exploration_catalog import STABLE_KEYS, existing_business_rows, upgrade_catalog, verify_preserved
from test_dynamic_exploration import command, exploration, publish, read
from test_wp09_feishu_identity import assert_ok


def ids(exploration):
    author = exploration[2]
    with SessionLocal() as session:
        return session.get(User, author).organization_id, author


def provision(session, scope, *, apply=True):
    return upgrade_catalog(session, *scope, "owner-approved-release-20261117", apply=apply)


def test_production_plan_is_read_only_and_import_is_idempotent_without_fake_review(exploration, monkeypatch):
    scope = ids(exploration)
    monkeypatch.setenv("APP_ENV", "production")
    with SessionLocal.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        planned = provision(session, scope, apply=False)
        assert len(planned["missing"]) == 8 and planned["inserted"] == []
        assert session.scalar(select(TaskDefinition.id).where(TaskDefinition.organization_id == scope[0])) is None
    with SessionLocal.begin() as session:
        first = provision(session, scope)
        assert len(first["inserted"]) == 8
        assert first["independent_review"] is False
        assert first["business_records_preserved"] and not first["legacy_progress_rewritten"]
        definitions = list(session.scalars(select(TaskDefinition).where(TaskDefinition.organization_id == scope[0])))
        assert {row.stable_key for row in definitions} == set(STABLE_KEYS)
        assert not any("测试" in row.title for row in session.scalars(select(TaskVersion).where(TaskVersion.organization_id == scope[0])))
        audits = list(session.scalars(select(AuditEntry).where(AuditEntry.organization_id == scope[0],
            AuditEntry.action == "exploration.production_course_initialized")))
        assert len(audits) == 8 and all(row.details["independent_review"] is False for row in audits)
        seventh = session.get(PublishedTaskContent, uuid.uuid5(uuid.uuid5(scope[0], STABLE_KEYS[6]), "published-v1"))
        assert len(seventh.content["materials"]) == 1 and len(seventh.content["taskFiles"]) == 1
        assert seventh.content["assessmentUrl"] == ""
        qr = session.get(ExplorationMaterial, uuid.uuid5(scope[0], "exploration-checkout-qr-20261117"))
        assert qr.content.startswith(b"\x89PNG") and qr.organization_id == scope[0]
        original = existing_business_rows(session)
    with SessionLocal.begin() as session:
        second = provision(session, scope)
        assert not second["inserted"] and len(second["preserved"]) == 8
        assert existing_business_rows(session) == original
    assert os.environ["APP_ENV"] == "production"


def test_existing_administrator_edits_and_archived_courses_are_not_overwritten(exploration):
    scope = ids(exploration)
    with SessionLocal.begin() as session:
        provision(session, scope)
        task_id = uuid.uuid5(scope[0], STABLE_KEYS[0])
        profile = session.get(ReviewAdminTask, task_id)
        profile.content = {**profile.content, "title": "管理员已更新的标题"}
        profile.status, profile.revision = "archived", profile.revision + 1
    with SessionLocal.begin() as session:
        assert provision(session, scope)["inserted"] == []
        profile = session.get(ReviewAdminTask, task_id)
        assert profile.content["title"] == "管理员已更新的标题" and profile.status == "archived"


def test_old_pending_assignment_submission_and_reviewer_ownership_survive(exploration):
    scope = ids(exploration)
    _, learner, _ = exploration
    old_id, _, _ = publish(exploration, "assessment")
    task = assert_ok(command(learner, read(learner, old_id), "claim"))
    task = assert_ok(command(learner, task, "submit", answer="原有课程的真实待审核成果，升级之后仍应由原审核人处理。"))
    with SessionLocal.begin() as session:
        assignment_id = uuid.UUID(task["assignmentId"])
        work = session.scalar(select(ExplorationWork).where(ExplorationWork.assignment_id == assignment_id))
        # Reconstruct the original formal lifecycle: canonical work predates all
        # new ExplorationWork/catalog rows and must not be inferred as new work.
        session.delete(work)
        session.delete(session.get(ExplorationCatalogTask, uuid.UUID(old_id)))
        session.get(TaskDefinition, uuid.UUID(old_id)).stable_key = "DAY-0"
        session.flush()
        original = existing_business_rows(session)
        assignment = session.get(Assignment, assignment_id)
        version_id, enrollment_id, status = assignment.task_version_id, assignment.enrollment_id, assignment.status
        submission = session.scalar(select(Submission).where(Submission.assignment_id == assignment_id))
        submission_id, version_no = submission.id, submission.current_version_no
        provision(session, scope)
        verify_preserved(original, existing_business_rows(session))
        assert (assignment.task_version_id, assignment.enrollment_id, assignment.status) == (version_id, enrollment_id, status)
        assert (submission.id, submission.current_version_no) == (submission_id, version_no)
        assert session.get(ExplorationWork, (scope[0], work.user_id, uuid.UUID(old_id))) is None


@pytest.mark.parametrize("change", ["ordinary", "revoked", "inactive", "cross_org"])
def test_only_real_active_same_organization_super_admin_can_initialize(exploration, change):
    scope = ids(exploration)
    with SessionLocal.begin() as session:
        access = session.get(ReviewAdminAccess, scope[1])
        if change == "ordinary":
            access.access_role = "admin"
        elif change == "revoked":
            from datetime import UTC, datetime
            access.revoked_at = datetime.now(UTC)
        elif change == "inactive":
            session.get(User, scope[1]).status = UserStatus.DISABLED
        else:
            scope = (uuid.uuid4(), scope[1])
        session.flush()
        with pytest.raises((ValueError, ApiError)):
            provision(session, scope)


def test_late_failure_rolls_back_all_course_and_qr_inserts(exploration, monkeypatch):
    import scripts.upgrade_exploration_catalog as upgrade
    scope = ids(exploration)
    real_audit = upgrade.add_audit
    calls = []

    def fail_after_seventh(*args, **kwargs):
        calls.append(kwargs["resource_id"])
        if len(calls) == 8:
            raise RuntimeError("injected failure after QR was inserted")
        return real_audit(*args, **kwargs)

    monkeypatch.setattr(upgrade, "add_audit", fail_after_seventh)
    with pytest.raises(RuntimeError):
        with SessionLocal.begin() as session:
            provision(session, scope)
    with SessionLocal() as session:
        assert session.scalar(select(TaskDefinition.id).where(TaskDefinition.organization_id == scope[0])) is None
        assert session.scalar(select(ExplorationMaterial.id).where(ExplorationMaterial.organization_id == scope[0])) is None
        assert session.scalar(select(AuditEntry.id).where(AuditEntry.organization_id == scope[0],
            AuditEntry.action == "exploration.production_course_initialized")) is None


def test_preservation_guard_rejects_updates_and_unexpected_learning_rows():
    before = {"assignments": Counter({"old-work": 1}), "task_definitions": Counter({"old-course": 1})}
    verify_preserved(before, {**before, "task_definitions": Counter({"old-course": 1, "new-course": 1})})
    with pytest.raises(ValueError, match="EXISTING_BUSINESS_RECORD_CHANGED:assignments"):
        verify_preserved(before, {**before, "assignments": Counter({"old-work": 1, "fake-progress": 1})})
    with pytest.raises(ValueError, match="EXISTING_BUSINESS_RECORD_CHANGED:task_definitions"):
        verify_preserved(before, {**before, "task_definitions": Counter({"rewritten-old-course": 1})})
