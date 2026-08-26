from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.construction_module_content import canonical_document_sha256
from journey_api.db import SessionLocal
from journey_api.fixtures import OPERATOR_ID, ORGANIZATION_ID, REVIEWER_ID
from journey_api.main import app
from journey_api.models import (
    Assignment,
    Evaluation,
    JourneyDefinition,
    JourneyStageVersion,
    ModuleContentPackageBinding,
    Review,
    Role,
    RoleAssignment,
    Submission,
    SubmissionVersion,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)


OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}
REVIEWER_HEADERS = {"X-Fixture-Role": "REVIEWER"}
client = TestClient(app, base_url="http://localhost")


def _data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def _command(
    actor: TestClient,
    path: str,
    payload: dict[str, object],
    *,
    role_headers: dict[str, str] | None = None,
):
    headers = {
        "Idempotency-Key": str(uuid.uuid4()),
        **(role_headers or {}),
    }
    csrf = actor.cookies.get("journey_next_csrf")
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return actor.post(path, headers=headers, json=payload)


def _finalize_module_review(
    reviewer: TestClient,
    assignment_id: str,
    *,
    decision: str,
) -> dict[str, object]:
    queue = _data(reviewer.get("/api/v1/reviews", headers=REVIEWER_HEADERS))
    review = next(
        item
        for item in queue["items"]
        if item["assignment_id"] == assignment_id
    )
    started = _data(
        _command(
            reviewer,
            f"/api/v1/reviews/{review['id']}/start",
            {"expected_revision": review["revision"]},
            role_headers=REVIEWER_HEADERS,
        )
    )
    detail = _data(
        reviewer.get(
            f"/api/v1/reviews/{review['id']}", headers=REVIEWER_HEADERS
        )
    )
    needs_revision = decision == "REQUEST_REVISION"
    rubric_evaluations = [
        {
            "dimension_key": dimension["dimension_key"],
            "rating": "NEEDS_WORK" if needs_revision else "MEETS",
            "score": None,
            "feedback": (
                "请补充可定位的合成证据。"
                if needs_revision
                else "合成证据可定位。"
            ),
        }
        for dimension in detail["rubric"]["dimensions"]
    ]
    return _data(
        _command(
            reviewer,
            f"/api/v1/reviews/{review['id']}/finalize",
            {
                "expected_revision": started["review_revision"],
                "overall_decision": decision,
                "overall_feedback": (
                    "请补充一处能够定位到输入材料的证据，再提交新版本。"
                    if needs_revision
                    else "证据与判断能够对应，本次合成练习通过。"
                ),
                "rubric_evaluations": rubric_evaluations,
            },
            role_headers=REVIEWER_HEADERS,
        )
    )


def _hash(document: dict[str, object]) -> dict[str, object]:
    document["sha256"] = canonical_document_sha256(document)
    return document


def _package(
    *,
    package_id: str,
    task_key: str,
    purpose: str,
    deliverables: list[str],
    owner_name: str,
    backup_name: str,
    effective_at: datetime,
    module_key: str = "ai-academy",
) -> dict[str, object]:
    owner_role = (
        "ai_academy_owner"
        if module_key == "ai-academy"
        else "delivery_guild_owner"
    )
    source_ref = "SRC-AIA-01" if module_key == "ai-academy" else "SRC-GOV-01"
    document: dict[str, object] = {
        "schema_version": "module-content-package.v1",
        "package_id": package_id,
        "module_key": module_key,
        "version": "1",
        "owner": {
            "role": owner_role,
            "person_name": owner_name,
            "signed_at": (effective_at - timedelta(minutes=10)).isoformat(),
            "decision": "APPROVED",
        },
        "source_refs": [source_ref, "SRC-OWNER-01"],
        "effective_at": effective_at.isoformat(),
        "expires_at": None,
        "content_items": [
            _hash(
                {
                    "content_id": "ai-unit-synthetic",
                    "title": "合成 AI 学院首单元",
                    "version": "1",
                    "source_ref": source_ref,
                    "owner": owner_name,
                    "estimated_minutes": 30,
                    "visibility": ["LEARNER", "REVIEWER"],
                    "data_classification": "INTERNAL",
                }
            )
        ],
        "task_versions": [
            _hash(
                {
                    "task_key": task_key,
                    "version": "1",
                    "purpose": purpose,
                    "non_goals": ["不执行生产作业", "不生成正式人才结论"],
                    "inputs": ["合成学习材料"],
                    "deliverables": deliverables,
                    "rubric_id": "aia-rubric-synthetic-v1",
                    "reviewer_pool_ref": "aia-reviewer-pool-synthetic-v1",
                    "help_path": "help/ai-academy-synthetic",
                    "execution_environment": "SIMULATION",
                    "retention_policy": "synthetic-test-only",
                }
            )
        ],
        "rubrics": [
            _hash(
                {
                    "rubric_id": "aia-rubric-synthetic-v1",
                    "version": "1",
                    "dimensions": ["证据可定位"],
                    "human_decision_required": True,
                    "calibration_evidence_ref": "evidence/synthetic-calibration",
                }
            )
        ],
        "reviewer_policy": {
            "pool_ref": "aia-reviewer-pool-synthetic-v1",
            "primary_reviewers": ["试点主管"],
            "backup_reviewers": [backup_name],
            "first_response_sla_minutes": 60,
            "completion_sla_minutes": 1440,
            "escalation_owner": "合成升级 Owner",
        },
        "data_policy": {
            "production_write_allowed": False,
            "raw_customer_data_allowed": False,
            "ai_high_impact_decision_allowed": False,
            "visibility": ["PERSON", "ASSIGNED_REVIEWERS"],
            "retention_policy": "synthetic-test-only",
        },
    }
    return _hash(document)


def _runtime_fixture(
    *,
    module_key: str = "ai-academy",
    review_ready_rubric: bool = True,
) -> dict[str, object]:
    nonce = uuid.uuid4().hex[:10].upper()
    prefix = "AIA" if module_key == "ai-academy" else "DLG"
    owner_label = "AI" if module_key == "ai-academy" else "公会"
    task_key = f"{prefix}-SYN-{nonce}"
    owner_name = f"合成 {owner_label} Owner {nonce}"
    backup_name = f"合成备 Reviewer {nonce}"
    purpose = "仅用于机器验证 AI 学院内容包、任务版本与 Reviewer 谱系绑定。"
    deliverables = ["一份合成练习记录"]
    with SessionLocal.begin() as session:
        owner = User(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            display_name=owner_name,
            status=UserStatus.ACTIVE,
        )
        backup = User(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            display_name=backup_name,
            status=UserStatus.ACTIVE,
        )
        outsider = User(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            display_name=f"合成非具名 Reviewer {nonce}",
            status=UserStatus.ACTIVE,
        )
        session.add_all([owner, backup, outsider])
        session.flush()
        session.add_all(
            [
                RoleAssignment(
                    id=uuid.uuid4(),
                    organization_id=ORGANIZATION_ID,
                    user_id=backup.id,
                    role=Role.REVIEWER,
                ),
                RoleAssignment(
                    id=uuid.uuid4(),
                    organization_id=ORGANIZATION_ID,
                    user_id=outsider.id,
                    role=Role.REVIEWER,
                ),
            ]
        )
        definition = TaskDefinition(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            stable_key=task_key,
            status=TaskDefinitionStatus.PUBLISHED,
            revision=1,
            created_by=OPERATOR_ID,
        )
        session.add(definition)
        session.flush()
        task = TaskVersion(
            id=uuid.uuid4(),
            organization_id=ORGANIZATION_ID,
            task_definition_id=definition.id,
            version=1,
            title="合成 AI 学院练习",
            purpose=purpose,
            learner_outcome="提交一份可由真人 Reviewer 复核的合成练习证据。",
            instructions=["阅读合成材料", "提交合成练习"],
            completion_criteria=["证据可定位"],
            required_deliverables=deliverables,
            content_source_notes=["SRC-AIA-01", "synthetic-machine-test-only"],
            change_summary="合成机器测试内容，不代表 Owner 正式内容。",
            reviewer_calibration_note="仅验证绑定，不代表真人校准通过。",
            allowed_attachment_types=[],
            max_attachment_size_bytes=0,
            reference_materials=[],
            learning_materials=[
                {
                    "key": "synthetic-material",
                    "title": "合成学习材料",
                    "kind": "TEXT",
                    "source_label": "synthetic-machine-test-only",
                    "body": "仅用于机器验证。",
                    "estimated_duration_minutes": 5,
                    "required": True,
                }
            ],
            learning_experience={},
            estimated_duration_minutes=30,
            rubric={
                "version": 1,
                "dimensions": [
                    {
                        "dimension_key": "traceability",
                        "title": "证据可定位",
                        **(
                            {
                                "purpose": "确认判断能够回到固定输入材料。",
                                "evidence_expected": "至少一处可定位材料证据。",
                                "levels": {
                                    "MEETS": "证据与判断能够对应",
                                    "NEEDS_WORK": "只有结论，缺少可定位证据",
                                },
                                "required": True,
                                "feedback_prompt": "指出缺少的证据与修改动作。",
                                "blocking_rule": "REQUIRE_FEEDBACK",
                            }
                            if review_ready_rubric
                            else {}
                        ),
                    }
                ],
            },
            rubric_version=1,
            reviewer_role="REVIEWER",
            feedback_sla_business_days=2,
            sensitivity="INTERNAL",
            audience="LEARNER",
            published_by=OPERATOR_ID,
            reviewed_by=REVIEWER_ID,
        )
        session.add(task)
        session.flush()
        return {
            "owner_id": owner.id,
            "backup_id": backup.id,
            "outsider_id": outsider.id,
            "task_id": task.id,
            "task_key": task_key,
            "owner_name": owner_name,
            "backup_name": backup_name,
            "purpose": purpose,
            "deliverables": deliverables,
        }


def _current_module_version(module_key: str = "ai-academy") -> int:
    with SessionLocal() as session:
        definition = session.scalar(
            select(JourneyDefinition).where(
                JourneyDefinition.organization_id == ORGANIZATION_ID,
                JourneyDefinition.stable_key == module_key.upper(),
            )
        )
        if definition is None:
            return 0
        from journey_api.models import JourneyVersion

        return len(
            session.scalars(
                select(JourneyVersion.id).where(
                    JourneyVersion.organization_id == ORGANIZATION_ID,
                    JourneyVersion.journey_definition_id == definition.id,
                )
            ).all()
        )


def _publish_and_join_module(
    module_key: str,
) -> tuple[TestClient, dict[str, object], dict[str, object]]:
    fixture = _runtime_fixture(module_key=module_key)
    package = _package(
        package_id=f"{module_key}.revision-cycle.{uuid.uuid4().hex}",
        task_key=str(fixture["task_key"]),
        purpose=str(fixture["purpose"]),
        deliverables=list(fixture["deliverables"]),
        owner_name=str(fixture["owner_name"]),
        backup_name=str(fixture["backup_name"]),
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
        module_key=module_key,
    )
    published = _data(
        client.post(
            "/api/v1/ops/module-content-packages/publish",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "package": package,
                "task_version_id": str(fixture["task_id"]),
                "owner_user_id": str(fixture["owner_id"]),
                "primary_reviewer_user_id": str(REVIEWER_ID),
                "backup_reviewer_user_id": str(fixture["backup_id"]),
                "reviewed_by": str(REVIEWER_ID),
                "expected_current_version": _current_module_version(module_key),
                "review_acknowledged": True,
            },
        )
    )
    invite = _data(
        client.post(
            "/api/v1/ops/invites",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "purpose": f"{module_key} 合成返工闭环机器验证",
                "expires_in_hours": 1,
                "role": "LEARNER",
                "reviewer_id": str(REVIEWER_ID),
                "journey_version_id": published["journey_version_id"],
            },
        )
    )
    learner = TestClient(
        app,
        base_url="http://localhost",
        client=(f"{module_key}-revision-{uuid.uuid4()}", 58_100),
    )
    exchanged = _data(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite["invite_token"], "return_to": "/app"},
        )
    )
    _data(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": f"{module_key} 合成学员",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    return learner, fixture, published


@pytest.mark.parametrize("module_key", ["ai-academy", "delivery-guild"])
def test_ai_and_guild_each_reuse_full_revision_and_human_pass_loop(module_key: str):
    learner, fixture, published = _publish_and_join_module(module_key)
    reviewer = TestClient(
        app,
        base_url="http://localhost",
        client=(f"{module_key}-reviewer-{uuid.uuid4()}", 58_200),
    )
    action = _data(learner.get("/api/v1/me/current-action"))
    assignment_id = action["resource_id"]
    detail = _data(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
    assert detail["journey_stage"]["completion_policy"] == "REVIEW_REQUIRED"
    assert detail["stable_task_key"] == fixture["task_key"]
    assert detail["task_version"] == 1
    assert published["task_version_id"] == str(fixture["task_id"])

    early_start = _command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/start",
        {"expected_revision": detail["revision"]},
    )
    assert early_start.status_code == 409
    assert early_start.json()["error"]["code"] == "LEARNING_MATERIALS_INCOMPLETE"
    for material in detail["learning_materials"]:
        _data(
            _command(
                learner,
                f"/api/v1/me/assignments/{assignment_id}/materials/{material['key']}/complete",
                {"task_version": detail["task_version"]},
            )
        )

    started = _data(
        _command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/start",
            {"expected_revision": detail["revision"]},
        )
    )
    first_submission = _data(
        _command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            {
                "expected_revision": started["revision"],
                "body": (
                    "这是第一版合成练习，只用于验证共享返工闭环。我先记录材料中的"
                    "可核对事实，再说明自己的判断、仍不确定的地方和下一步需要补充的证据。"
                ),
            },
        )
    )
    assert first_submission["assignment_status"] == "SUBMITTED"
    assert first_submission["version_no"] == 1

    overwrite_attempt = _command(
        learner,
        f"/api/v1/me/assignments/{assignment_id}/submissions",
        {
            "expected_revision": first_submission["assignment_revision"],
            "body": (
                "这是一次未经过真人评审就再次提交的覆盖尝试；服务端必须拒绝，并继续"
                "保留已经固定的第一版 SubmissionVersion，不得把新正文写入原版本。"
            ),
        },
    )
    assert overwrite_attempt.status_code == 409
    assert overwrite_attempt.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    revision = _finalize_module_review(
        reviewer, assignment_id, decision="REQUEST_REVISION"
    )
    assert revision["assignment_status"] == "NEEDS_REVISION"
    revision_detail = _data(
        learner.get(f"/api/v1/me/assignments/{assignment_id}")
    )
    second_submission = _data(
        _command(
            learner,
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            {
                "expected_revision": revision_detail["revision"],
                "body": (
                    "第二版根据真人返工意见补充了可定位的合成材料证据，并逐条回应缺口；"
                    "第一版仍作为不可变历史保留，本次只追加新的 SubmissionVersion。"
                ),
            },
        )
    )
    assert second_submission["assignment_status"] == "SUBMITTED"
    assert second_submission["version_no"] == 2
    assert second_submission["submission_version_id"] != first_submission[
        "submission_version_id"
    ]
    approved = _finalize_module_review(reviewer, assignment_id, decision="APPROVE")
    assert approved["assignment_status"] == "PASSED"

    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(assignment_id))
        assert assignment is not None
        submission = session.scalar(
            select(Submission).where(Submission.assignment_id == assignment.id)
        )
        assert submission is not None
        assert session.scalar(
            select(func.count(SubmissionVersion.id)).where(
                SubmissionVersion.submission_id == submission.id
            )
        ) == 2
        assert session.scalar(
            select(func.count(Review.id)).where(Review.assignment_id == assignment.id)
        ) == 2
        assert session.scalar(
            select(func.count(Evaluation.id)).where(
                Evaluation.assignment_id == assignment.id
            )
        ) == 2


def test_owner_signed_ai_package_publishes_one_immutable_shared_core_binding():
    fixture = _runtime_fixture()
    package = _package(
        package_id=f"ai-academy.synthetic.{uuid.uuid4().hex}",
        task_key=fixture["task_key"],
        purpose=fixture["purpose"],
        deliverables=fixture["deliverables"],
        owner_name=fixture["owner_name"],
        backup_name=fixture["backup_name"],
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    key = str(uuid.uuid4())
    body = {
        "package": package,
        "task_version_id": str(fixture["task_id"]),
        "owner_user_id": str(fixture["owner_id"]),
        "primary_reviewer_user_id": str(REVIEWER_ID),
        "backup_reviewer_user_id": str(fixture["backup_id"]),
        "reviewed_by": str(REVIEWER_ID),
        "expected_current_version": _current_module_version(),
        "review_acknowledged": True,
    }
    response = client.post(
        "/api/v1/ops/module-content-packages/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": key},
        json=body,
    )
    assert response.status_code == 200, response.text
    published = response.json()["data"]
    assert published["module_key"] == "ai-academy"
    assert published["package_sha256"] == package["sha256"]
    assert published["status"] == "PUBLISHED_CONTENT_BOUND"

    replay = client.post(
        "/api/v1/ops/module-content-packages/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": key},
        json=body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"]["binding_id"] == published["binding_id"]
    assert replay.json()["data"]["idempotency_replay"] is True

    invite_response = client.post(
        "/api/v1/ops/invites",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "purpose": "合成 AI 学院单元加入验证",
            "expires_in_hours": 1,
            "role": "LEARNER",
            "reviewer_id": str(REVIEWER_ID),
            "journey_version_id": published["journey_version_id"],
        },
    )
    assert invite_response.status_code == 200, invite_response.text
    invite = invite_response.json()["data"]
    learner = TestClient(
        app,
        base_url="http://localhost",
        client=(f"module-learner-{uuid.uuid4()}", 58_000),
    )
    exchange = learner.post(
        "/api/v1/join/exchange",
        json={"token": invite["invite_token"], "return_to": "/app"},
    )
    assert exchange.status_code == 200, exchange.text
    csrf = exchange.json()["data"]["csrf_token"]
    confirmed = learner.post(
        "/api/v1/identity/confirm",
        headers={"X-CSRF-Token": csrf},
        json={
            "display_name": "合成 AI 学院学员",
            "accepted_purpose": True,
            "return_to": "/app",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    action = learner.get("/api/v1/me/current-action")
    assert action.status_code == 200, action.text
    assert action.json()["data"]["journey"]["stable_key"] == "AI-ACADEMY"
    assert action.json()["data"]["journey"]["total_stages"] == 1
    enrollments = learner.get("/api/v1/me/enrollments")
    assert enrollments.status_code == 200, enrollments.text
    enrollment = next(
        item
        for item in enrollments.json()["data"]["items"]
        if item["journey_version_id"] == published["journey_version_id"]
    )
    outside_roster = client.put(
        f"/api/v1/ops/enrollments/{enrollment['id']}/reviewer",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_revision": enrollment["revision"],
            "reviewer_id": str(fixture["outsider_id"]),
            "reason": "合成负向验证：非内容包具名 Reviewer 不得接管。",
        },
    )
    assert outside_roster.status_code == 422
    assert outside_roster.json()["error"]["code"] == "CONTENT_BINDING_INVALID"
    replacement = client.put(
        f"/api/v1/ops/enrollments/{enrollment['id']}/reviewer",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_revision": enrollment["revision"],
            "reviewer_id": str(fixture["backup_id"]),
            "reason": "合成机器验证：按 Owner 内容包名单启用备 Reviewer。",
        },
    )
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["data"]["reviewer_id"] == str(fixture["backup_id"])
    workload = client.get(
        "/api/v1/ops/reviewer-workload", headers=OPERATOR_HEADERS
    )
    assert workload.status_code == 200, workload.text
    workload_item = next(
        item
        for item in workload.json()["data"]["items"]
        if item["binding_id"] == published["binding_id"]
    )
    assert workload_item["active_enrollment_count"] == 1
    assert workload_item["open_review_count"] == 0
    assert workload_item["overdue_review_count"] == 0
    assert workload_item["capacity_limit"] is None
    assert workload_item["capacity_status"] == "PENDING_OWNER_CONTENT"
    assert workload_item["replacement_scope"] == "PRIMARY_OR_NAMED_BACKUP_ONLY"

    with SessionLocal() as session:
        binding = session.get(
            ModuleContentPackageBinding, uuid.UUID(published["binding_id"])
        )
        stage = session.get(
            JourneyStageVersion, uuid.UUID(published["journey_stage_version_id"])
        )
        definition = session.scalar(
            select(JourneyDefinition).where(
                JourneyDefinition.organization_id == ORGANIZATION_ID,
                JourneyDefinition.stable_key == "AI-ACADEMY",
            )
        )
        assert binding is not None and stage is not None and definition is not None
        assert binding.package_document["sha256"] == package["sha256"]
        assert canonical_document_sha256(binding.package_document) == package["sha256"]
        assert stage.task_version_id == fixture["task_id"]
        assert stage.completion_policy.value == "REVIEW_REQUIRED"

    with pytest.raises(DBAPIError, match="immutable"):
        with SessionLocal.begin() as session:
            session.execute(
                update(ModuleContentPackageBinding)
                .where(
                    ModuleContentPackageBinding.id
                    == uuid.UUID(published["binding_id"])
                )
                .values(package_version="rewritten")
            )


def test_package_publish_fails_before_effective_time_without_creating_binding():
    fixture = _runtime_fixture()
    package = _package(
        package_id=f"ai-academy.future.{uuid.uuid4().hex}",
        task_key=fixture["task_key"],
        purpose=fixture["purpose"],
        deliverables=fixture["deliverables"],
        owner_name=fixture["owner_name"],
        backup_name=fixture["backup_name"],
        effective_at=datetime.now(UTC) + timedelta(days=1),
    )
    response = client.post(
        "/api/v1/ops/module-content-packages/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "package": package,
            "task_version_id": str(fixture["task_id"]),
            "owner_user_id": str(fixture["owner_id"]),
            "primary_reviewer_user_id": str(REVIEWER_ID),
            "backup_reviewer_user_id": str(fixture["backup_id"]),
            "reviewed_by": str(REVIEWER_ID),
            "expected_current_version": 0,
            "review_acknowledged": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTENT_PACKAGE_NOT_EFFECTIVE"
    with SessionLocal() as session:
        assert session.scalar(
            select(ModuleContentPackageBinding.id).where(
                ModuleContentPackageBinding.package_id == package["package_id"]
            )
        ) is None


def test_package_publish_rejects_rubric_that_cannot_drive_human_review():
    fixture = _runtime_fixture(review_ready_rubric=False)
    package = _package(
        package_id=f"ai-academy.incomplete-rubric.{uuid.uuid4().hex}",
        task_key=fixture["task_key"],
        purpose=fixture["purpose"],
        deliverables=fixture["deliverables"],
        owner_name=fixture["owner_name"],
        backup_name=fixture["backup_name"],
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    response = client.post(
        "/api/v1/ops/module-content-packages/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "package": package,
            "task_version_id": str(fixture["task_id"]),
            "owner_user_id": str(fixture["owner_id"]),
            "primary_reviewer_user_id": str(REVIEWER_ID),
            "backup_reviewer_user_id": str(fixture["backup_id"]),
            "reviewed_by": str(REVIEWER_ID),
            "expected_current_version": _current_module_version(),
            "review_acknowledged": True,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CONTENT_BINDING_INVALID"
    with SessionLocal() as session:
        assert session.scalar(
            select(ModuleContentPackageBinding.id).where(
                ModuleContentPackageBinding.package_id == package["package_id"]
            )
        ) is None


def test_delivery_guild_reuses_the_same_package_journey_and_task_core():
    fixture = _runtime_fixture(module_key="delivery-guild")
    package = _package(
        package_id=f"delivery-guild.synthetic.{uuid.uuid4().hex}",
        task_key=fixture["task_key"],
        purpose=fixture["purpose"],
        deliverables=fixture["deliverables"],
        owner_name=fixture["owner_name"],
        backup_name=fixture["backup_name"],
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
        module_key="delivery-guild",
    )
    response = client.post(
        "/api/v1/ops/module-content-packages/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "package": package,
            "task_version_id": str(fixture["task_id"]),
            "owner_user_id": str(fixture["owner_id"]),
            "primary_reviewer_user_id": str(REVIEWER_ID),
            "backup_reviewer_user_id": str(fixture["backup_id"]),
            "reviewed_by": str(REVIEWER_ID),
            "expected_current_version": _current_module_version("delivery-guild"),
            "review_acknowledged": True,
        },
    )
    assert response.status_code == 200, response.text
    published = response.json()["data"]
    assert published["module_key"] == "delivery-guild"
    with SessionLocal() as session:
        binding = session.get(
            ModuleContentPackageBinding, uuid.UUID(published["binding_id"])
        )
        assert binding is not None
        assert binding.task_version_id == fixture["task_id"]
        assert binding.package_document["module_key"] == "delivery-guild"


def test_module_content_publish_cannot_bypass_controlled_real_task_authorization():
    fixture = _runtime_fixture(module_key="delivery-guild")
    package = _package(
        package_id=f"delivery-guild.real-task.{uuid.uuid4().hex}",
        task_key=fixture["task_key"],
        purpose=fixture["purpose"],
        deliverables=fixture["deliverables"],
        owner_name=fixture["owner_name"],
        backup_name=fixture["backup_name"],
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
        module_key="delivery-guild",
    )
    package["task_versions"][0]["execution_environment"] = "CONTROLLED_REAL_TASK"
    package["task_versions"][0]["controlled_task_authorization_ref"] = (
        "controlled-task-authorization/pending-owner-signature"
    )
    package["task_versions"][0]["sha256"] = canonical_document_sha256(
        package["task_versions"][0]
    )
    package["sha256"] = canonical_document_sha256(package)
    response = client.post(
        "/api/v1/ops/module-content-packages/publish",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "package": package,
            "task_version_id": str(fixture["task_id"]),
            "owner_user_id": str(fixture["owner_id"]),
            "primary_reviewer_user_id": str(REVIEWER_ID),
            "backup_reviewer_user_id": str(fixture["backup_id"]),
            "reviewed_by": str(REVIEWER_ID),
            "expected_current_version": _current_module_version("delivery-guild"),
            "review_acknowledged": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == (
        "CONTROLLED_TASK_AUTHORIZATION_REQUIRED"
    )
