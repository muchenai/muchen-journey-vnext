"""Disposable 0056 -> 0057 rehearsal with old formal work and new curriculum.

Never point this at an application database. CI creates and removes the exact
named isolated database; production rehearsal instead uses the verified backup.
"""
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
url = make_url(os.environ["DATABASE_URL"])
assert os.environ.get("APP_ENV") == "test"
assert url.database == "journey_exploration_drill_test", "DISPOSABLE_DATABASE_REQUIRED"


def run(*args):
    subprocess.run(args, check=True)


run("alembic", "upgrade", "0056_guild_halls")
run("python", "-m", "journey_api.seed", "--with-formal-journey")

from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID
from journey_api.journey_service import create_journey_assignments, published_formal_journey
from journey_api.models import (AISelfCheck, AssignmentStatus, Enrollment, EnrollmentStatus,
    Review, ReviewStatus, Role, RoleAssignment, Submission, SubmissionDraft, SubmissionVersion,
    User, UserStatus)
from journey_api.review_admin_models import ReviewAdminAccess
from scripts.upgrade_exploration_catalog import (NEW_TABLES, STABLE_KEYS, existing_business_rows,
    upgrade_catalog, verify_preserved)
from grant_runtime import GRANT_SQL, TABLES as RUNTIME_TABLES

engine = create_engine(url)
drill_learner_id = uuid.uuid5(ORGANIZATION_ID, "dynamic-exploration-migration-drill-learner")
with SessionLocal.begin() as session:
    session.add(ReviewAdminAccess(user_id=REVIEWER_ID, organization_id=ORGANIZATION_ID,
        access_role="super_admin", level="高级", domain="产品开发", granted_by=REVIEWER_ID))
    formal = published_formal_journey(session, ORGANIZATION_ID)
    assert formal is not None
    # The regular seed owns its own active enrollment and one legacy task.
    # Build the eight-stage history for an isolated learner without mutating
    # that seed enrollment or violating its one-active-enrollment constraint.
    session.add(User(id=drill_learner_id, organization_id=ORGANIZATION_ID,
        display_name="Isolated exploration migration rehearsal", status=UserStatus.ACTIVE))
    session.flush()
    session.add(RoleAssignment(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
        user_id=drill_learner_id, role=Role.LEARNER))
    enrollment = Enrollment(id=uuid.uuid4(), organization_id=ORGANIZATION_ID, learner_id=drill_learner_id,
        reviewer_id=REVIEWER_ID, journey_version_id=formal.id, status=EnrollmentStatus.ACTIVE, revision=3)
    session.add(enrollment)
    session.flush()
    assignments = create_journey_assignments(session, enrollment=enrollment)
    session.flush()
    assert len(assignments) == 8
    for assignment, status in zip(assignments, [AssignmentStatus.COMPLETED,
            AssignmentStatus.NEEDS_REVISION, AssignmentStatus.SUBMITTED]):
        assignment.status, assignment.revision = status, 4
        submission = Submission(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
            assignment_id=assignment.id, current_version_no=1)
        session.add(submission)
        session.flush()
        version = SubmissionVersion(id=uuid.uuid4(), submission_id=submission.id, version_no=1,
            body="Existing formal learning evidence must survive curriculum upgrade unchanged.", created_by=drill_learner_id)
        session.add(version)
        session.flush()
        if status == AssignmentStatus.SUBMITTED:
            session.add(Review(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
                assignment_id=assignment.id, submission_id=submission.id, submission_version_id=version.id,
                reviewer_id=REVIEWER_ID, status=ReviewStatus.ASSIGNED, revision=1))
    session.add(SubmissionDraft(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
        assignment_id=assignments[1].id, owner_id=drill_learner_id, body="Existing returned-work draft.",
        attachment_ids=[], revision=2))
    session.add(AISelfCheck(id=uuid.uuid4(), organization_id=ORGANIZATION_ID, learner_id=drill_learner_id,
        assignment_id=assignments[1].id, document_token="isolated-exploration-drill",
        document_url="https://example.com/isolated-drill", status="COMPLETED", attempt_id=uuid.uuid4(),
        model="isolated-drill", rule_version="drill", result="Preserved AI feedback history."))
    session.flush()
    baseline = existing_business_rows(session)

run("alembic", "upgrade", "0057_dynamic_exploration")
with SessionLocal.begin() as session:
    assert existing_business_rows(session) == baseline, "MIGRATION_CHANGED_EXISTING_FACTS"
    for table in NEW_TABLES:
        assert session.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0
    plan = upgrade_catalog(session, ORGANIZATION_ID, REVIEWER_ID, "isolated-migration-rehearsal")
    assert len(plan["missing"]) == 8 and plan["inserted"] == []
    first = upgrade_catalog(session, ORGANIZATION_ID, REVIEWER_ID, "isolated-migration-rehearsal", apply=True)
    assert len(first["inserted"]) == 8 and first["business_records_preserved"]
    verify_preserved(baseline, existing_business_rows(session))
    for table in ("exploration_work", "exploration_progress", "exploration_self_checks"):
        assert session.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0, "FAKE_LEARNER_PROGRESS"
    assert session.execute(text("SELECT count(*) FROM exploration_catalog_tasks")).scalar_one() == 8
    assert session.execute(text("SELECT count(*) FROM exploration_materials")).scalar_one() == 1
    checkout = session.execute(text("SELECT d.stable_key FROM exploration_catalog_tasks c JOIN task_definitions d ON d.id=c.task_id ORDER BY c.position DESC LIMIT 1")).scalar_one()
    assert checkout == STABLE_KEYS[-1], "CHECKOUT_NOT_LAST"
    imported = existing_business_rows(session)

with SessionLocal.begin() as session:
    repeated = upgrade_catalog(session, ORGANIZATION_ID, REVIEWER_ID, "isolated-migration-rehearsal", apply=True)
    assert repeated["inserted"] == [] and len(repeated["preserved"]) == 8
    assert existing_business_rows(session) == imported, "REPLAY_CHANGED_BUSINESS_RECORDS"

# Exercise the five new table grants against a real unprivileged database role.
# Roll back even role creation, so CI leaves no cluster-level authority behind.
with engine.connect() as connection:
    transaction = connection.begin()
    try:
        if not connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='journey_next_runtime')")).scalar_one():
            connection.execute(text("CREATE ROLE journey_next_runtime NOLOGIN"))
        assert set(RUNTIME_TABLES) == set(NEW_TABLES), "RUNTIME_GRANT_TABLES_MISMATCH"
        connection.execute(text(GRANT_SQL))
        for table in NEW_TABLES:
            for permission in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert connection.execute(text("SELECT has_table_privilege(:role,:table,:permission)"),
                    {"role": "journey_next_runtime", "table": "public." + table, "permission": permission}).scalar_one()
    finally:
        transaction.rollback()

print("0056 -> 0057: old formal assignments, submission versions, pending review, draft and AI feedback preserved; eight reference courses and QR initialized atomically; replay and five table grants verified", flush=True)
