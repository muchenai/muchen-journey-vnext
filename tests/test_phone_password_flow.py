import secrets
import uuid

import pytest
from sqlalchemy import select

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.models import Assignment, AssignmentStatus, Enrollment, Role, RoleAssignment, User, UserStatus, ExternalIdentity, CompletionCode, LearningMaterialCompletion
from test_learner_feishu_login import learner_provider, login
from test_wp09_feishu_identity import oauth_provider, client_for, assert_ok


@pytest.fixture
def password_provider(learner_provider, monkeypatch):
    monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "true")
    get_settings.cache_clear()
    yield learner_provider
    get_settings.cache_clear()


def register(label):
    client = client_for(label + uuid.uuid4().hex)
    credentials = {"phone": "139" + str(secrets.randbelow(10**8)).zfill(8), "password": "test1234"}
    assert assert_ok(client.post("/api/v1/auth/password/login", json=credentials))["is_new_user"]
    return client, credentials


def migrate(client, code):
    return client.post("/api/v1/me/completion-code/migrate", json={"code": code}, headers={
        "X-CSRF-Token": client.cookies["journey_next_csrf"],
        "Idempotency-Key": str(uuid.uuid4()),
    })


def test_returning_password_user_keeps_identity_and_journey(password_provider):
    first, credentials = register("password-first")
    principal = assert_ok(first.get("/api/v1/session"))
    action = assert_ok(first.get("/api/v1/me/current-action"))
    assert assert_ok(first.get("/api/v1/me/completion-code"))["status"] == "LOCKED"
    second = client_for("password-return" + uuid.uuid4().hex)
    wrong = second.post("/api/v1/auth/password/login", json={**credentials, "password": "wrong123"})
    assert wrong.status_code == 401
    assert not assert_ok(second.post("/api/v1/auth/password/login", json=credentials))["is_new_user"]
    assert assert_ok(second.get("/api/v1/session"))["user_id"] == principal["user_id"]
    assert assert_ok(second.get("/api/v1/me/current-action"))["resource_id"] == action["resource_id"]
    assert second.get("/api/v1/reviews").status_code == 403


@pytest.mark.parametrize("staff_role", [None, Role.REVIEWER, Role.OPERATOR])
def test_completion_code_preserves_corporate_account_and_retires_phone_login(password_provider, staff_role, monkeypatch):
    source, credentials = register("password-graduate")
    source_id = uuid.UUID(assert_ok(source.get("/api/v1/session"))["user_id"])
    assignment_id = assert_ok(source.get("/api/v1/me/current-action"))["resource_id"]
    detail_path = f"/api/v1/me/assignments/{assignment_id}"
    detail = assert_ok(source.get(detail_path))
    material = detail["learning_materials"][0]
    completed = assert_ok(source.post(f"{detail_path}/materials/{material['key']}/complete",
        json={"task_version": detail["task_version"]}, headers={
            "X-CSRF-Token": source.cookies["journey_next_csrf"], "Idempotency-Key": str(uuid.uuid4())}))
    # Fixture-only completed journey; the full review suite proves task transitions.
    with SessionLocal.begin() as session:
        enrollment = session.scalar(select(Enrollment).where(Enrollment.learner_id == source_id))
        assignments = session.scalars(select(Assignment).where(Assignment.enrollment_id == enrollment.id)).all()
        assignment_ids = {str(row.id) for row in assignments}
        for row in assignments:
            row.status = AssignmentStatus.COMPLETED
    code = assert_ok(source.get("/api/v1/me/completion-code"))["code"]
    assert assert_ok(source.get("/api/v1/me/completion-code"))["code"] == code
    assert migrate(source, code).status_code == 403
    subject = "ou_graduate_" + uuid.uuid4().hex
    target, response = login(password_provider, "graduate-feishu" + uuid.uuid4().hex, subject)
    assert_ok(response)
    target_id = uuid.UUID(assert_ok(target.get("/api/v1/session"))["user_id"])
    with SessionLocal.begin() as session:
        from journey_api.fixtures import ORGANIZATION_ID
        if staff_role:
            session.add(RoleAssignment(id=uuid.uuid4(), user_id=target_id,
                                      organization_id=ORGANIZATION_ID, role=staff_role))
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == target_id))
        identity_id, identity_revision = identity.id, identity.revision
    roles_before = assert_ok(target.get("/api/v1/session"))["roles"]
    if staff_role == Role.REVIEWER:
        from test_shared_learner_reviews import new_submission, review_command, approval
        monkeypatch.setenv("FEISHU_LEARNER_REVIEWER_ID", str(target_id))
        get_settings.cache_clear()
        existing_review_id = new_submission(password_provider)
        assert target.get(f"/api/v1/reviews/{existing_review_id}").status_code == 200
    # An existing corporate learning record must never be silently overwritten.
    with SessionLocal.begin() as session:
        target_enrollment = session.scalar(select(Enrollment).where(Enrollment.learner_id == target_id))
        target_assignment = session.scalar(select(Assignment).where(Assignment.enrollment_id == target_enrollment.id))
        target_assignment_id = target_assignment.id
        target_assignment.status = AssignmentStatus.IN_PROGRESS
    conflict = migrate(target, code)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "TARGET_ACCOUNT_HAS_PROGRESS"
    assert source.get("/api/v1/session").status_code == 200
    with SessionLocal.begin() as session:
        assert session.scalar(select(CompletionCode).where(CompletionCode.user_id == source_id)).used_at is None
        session.get(Assignment, target_assignment_id).status = AssignmentStatus.AVAILABLE
    result = assert_ok(migrate(target, code))
    assert result["migrated_tasks"] == len(assignment_ids)
    assert assert_ok(target.get("/api/v1/session"))["user_id"] == str(target_id)
    assert assert_ok(target.get("/api/v1/session"))["roles"] == roles_before
    if staff_role == Role.REVIEWER:
        from journey_api.models import Evaluation
        detail = assert_ok(target.get(f"/api/v1/reviews/{existing_review_id}"))
        csrf = target.cookies["journey_next_csrf"]
        started = assert_ok(review_command(target, csrf, existing_review_id, "start", {"expected_revision": detail["revision"]}))
        assert_ok(review_command(target, csrf, existing_review_id, "finalize", approval(detail, started["review_revision"])))
        with SessionLocal() as session:
            evaluation = session.scalar(select(Evaluation).where(Evaluation.review_id == existing_review_id))
            assert evaluation.reviewer_id == target_id
            assert evaluation.executor_id == target_id
    if staff_role == Role.OPERATOR:
        assert target.get("/api/v1/ops/invite-targets").status_code == 200
    inherited = assert_ok(target.get("/api/v1/me/current-action"))
    assert {n["assignment_id"] for n in inherited["journey"]["nodes"]} == assignment_ids
    assert assert_ok(target.get(detail_path))["learning_materials"][0]["completed_at"] == completed["completed_at"]
    assert target.get("/api/v1/me/timeline").status_code == 200
    returning, result = login(password_provider, "graduate-return" + uuid.uuid4().hex, subject)
    assert_ok(result)
    assert assert_ok(returning.get("/api/v1/session"))["user_id"] == str(target_id)
    assert {n["assignment_id"] for n in assert_ok(returning.get("/api/v1/me/current-action"))["journey"]["nodes"]} == assignment_ids
    outsider, _ = register("unrelated-phone")
    assert outsider.get(detail_path).status_code == 404
    assert source.get("/api/v1/session").status_code == 401
    denied = client_for("retired-phone").post("/api/v1/auth/password/login", json=credentials)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "ACCOUNT_MIGRATED"
    assert migrate(target, code).json()["error"]["code"] == "COMPLETION_CODE_USED"
    with SessionLocal() as session:
        enrollment = session.scalar(select(Enrollment).where(Enrollment.learner_id == source_id))
        assert {str(value) for value in session.scalars(select(Assignment.id).where(Assignment.enrollment_id == enrollment.id))} == assignment_ids

        assert session.get(User, target_id).status == UserStatus.ACTIVE
        assert session.get(User, source_id).status == UserStatus.DISABLED
        identity = session.get(ExternalIdentity, identity_id)
        assert (identity.user_id, identity.revision, identity.revoked_at) == (target_id, identity_revision, None)
        claim = session.scalar(select(CompletionCode).where(CompletionCode.user_id == source_id))
        assert claim.migrated_to_user_id == target_id
        assert session.scalar(select(LearningMaterialCompletion.id).where(LearningMaterialCompletion.learner_id == source_id)) is not None


def test_one_code_cannot_be_claimed_by_two_corporate_accounts(password_provider):
    from concurrent.futures import ThreadPoolExecutor
    source, _ = register("claim-race")
    source_id = uuid.UUID(assert_ok(source.get("/api/v1/session"))["user_id"])
    with SessionLocal.begin() as session:
        enrollment = session.scalar(select(Enrollment).where(Enrollment.learner_id == source_id))
        for assignment in session.scalars(select(Assignment).where(Assignment.enrollment_id == enrollment.id)):
            assignment.status = AssignmentStatus.COMPLETED
    code = assert_ok(source.get("/api/v1/me/completion-code"))["code"]
    targets = []
    for _ in range(2):
        client, response = login(password_provider, "claim-target" + uuid.uuid4().hex, "ou_claim_" + uuid.uuid4().hex)
        assert_ok(response)
        targets.append(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda target: migrate(target, code), targets))
    assert sorted(response.status_code for response in results) == [200, 409]
    for target, response in zip(targets, results):
        assert target.get("/api/v1/session").status_code == 200
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "COMPLETION_CODE_USED"
    with SessionLocal() as session:
        assert session.get(User, source_id).status == UserStatus.DISABLED
