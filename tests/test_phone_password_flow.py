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
    monkeypatch.setenv("PHONE_OTP_ENABLED", "true")
    monkeypatch.setenv("PHONE_OTP_PROVIDER", "LOCAL_TEST")
    get_settings.cache_clear()
    yield learner_provider
    get_settings.cache_clear()


def register(label):
    client = client_for(label + uuid.uuid4().hex)
    credentials = {"phone": "139" + str(secrets.randbelow(10**8)).zfill(8), "password": "test1234"}
    assert_ok(client.post("/api/v1/auth/phone/request-code", json={"phone": credentials["phone"], "purpose": "register"}))
    assert assert_ok(client.post("/api/v1/auth/password/register", json={**credentials, "code": "123456"}))["is_new_user"]
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


COMPANY_LEARNER_VIEWS = (
    "/novice/tasks", "/novice/medals", "/course-workspace/village-summary",
    "/course-workspace?camp=village", "/course-workspace?camp=academy", "/academy", "/guild",
)


def test_phone_identity_only_accesses_exploration_and_its_shared_personal_views(password_provider):
    from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID, TASK_DEFINITION_ID, TASK_VERSION_ID
    from journey_api.models import EnrollmentStatus

    client, _ = register("phone-module-views")
    me = "/api/v1/me"
    assert assert_ok(client.get(me + "/learner-profile"))["exploration_only"] is True
    asset = uuid.uuid4()
    paths = (*COMPANY_LEARNER_VIEWS, f"/academy/courses/{asset}/video", f"/academy/courses/{asset}/cover",
             f"/course-assets/{asset}", f"/novice/tasks/{asset}/materials/0")
    for path in paths:
        response = client.get(me + path)
        assert (response.status_code, response.json()["error"]["code"]) == (403, "COMPANY_ACCOUNT_REQUIRED"), path
        assert response.json()["error"]["message"] == "请用公司认证的飞书账号进行登录和使用", path
    for path in ("/novice/growth", "/novice/wallet", "/current-action"):
        assert_ok(client.get(me + path))

    # A legacy phone user could have claimed a village task before this restriction existed.
    owner = uuid.UUID(assert_ok(client.get("/api/v1/session"))["user_id"])
    assignment_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        enrollment = Enrollment(id=uuid.uuid4(), organization_id=ORGANIZATION_ID, learner_id=owner,
            reviewer_id=REVIEWER_ID, novice_task_id=TASK_DEFINITION_ID, status=EnrollmentStatus.ACTIVE)
        session.add(enrollment)
        session.flush()
        session.add(Assignment(id=assignment_id, organization_id=ORGANIZATION_ID, enrollment_id=enrollment.id,
            task_definition_id=TASK_DEFINITION_ID, task_version_id=TASK_VERSION_ID,
            position=1, status=AssignmentStatus.IN_PROGRESS))
    path = f"{me}/assignments/{assignment_id}"
    assert assert_ok(client.get(f"{me}/novice/assignments/{assignment_id}")) == {"taskId": None}
    assert client.get(path).status_code == 403
    assert client.get(path + "/ai-self-checks").status_code == 403
    headers = {"X-CSRF-Token": client.cookies["journey_next_csrf"], "Idempotency-Key": str(uuid.uuid4())}
    body = {"expected_revision": 1, "body": "existing assignment response"}
    assert client.put(path + "/draft", json=body, headers=headers).status_code == 403
    assert client.post(path + "/submissions", json=body, headers=headers).status_code == 403


@pytest.mark.parametrize("staff_role", [None, Role.REVIEWER, Role.OPERATOR])
def test_completion_code_preserves_corporate_account_and_retires_phone_login(password_provider, staff_role, monkeypatch):
    source, credentials = register("password-graduate")
    source_id = uuid.UUID(assert_ok(source.get("/api/v1/session"))["user_id"])
    assignment_id = assert_ok(source.get("/api/v1/me/current-action"))["resource_id"]
    detail_path = f"/api/v1/me/assignments/{assignment_id}"
    detail = assert_ok(source.get(detail_path))
    assert_ok(source.get("/api/v1/me/knowledge/dashboard"))
    for module in ("village", "academy", "guild"):
        assert source.get(f"/api/v1/me/knowledge/{module}").status_code == 403
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
    assert assert_ok(target.get("/api/v1/me/learner-profile"))["exploration_only"] is False
    assert_ok(target.get("/api/v1/me/course-workspace"))
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
    for module in ("village", "academy", "guild"):
        assert_ok(target.get(f"/api/v1/me/knowledge/{module}"))
    assert target.get("/api/v1/me/timeline").status_code == 200
    returning, result = login(password_provider, "graduate-return" + uuid.uuid4().hex, subject)
    assert_ok(result)
    assert assert_ok(returning.get("/api/v1/session"))["user_id"] == str(target_id)
    assert assert_ok(returning.get("/api/v1/me/learner-profile"))["exploration_only"] is False
    for path in COMPANY_LEARNER_VIEWS:
        assert_ok(returning.get("/api/v1/me" + path))
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
