import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

from journey_api.auth import Actor
from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID, TASK_VERSION_V2_ID
from journey_api.main import app
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Attachment,
    AttachmentScanStatus,
    AttachmentStatus,
    AuditEntry,
    Decision,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    Invite,
    InviteStatus,
    Organization,
    OutboxEvent,
    Review,
    ReviewStatus,
    Role,
    RoleAssignment,
    Submission,
    SubmissionVersion,
    SubmissionVersionAttachment,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)
from journey_api.review_routes import locked_scoped_context_query


REVIEWER_HEADERS = {"X-Fixture-Role": "REVIEWER"}
OPERATOR_HEADERS = {"X-Fixture-Role": "OPERATOR"}
CONTENT_EDITOR_HEADERS = {"X-Fixture-Role": "CONTENT_EDITOR"}
RUBRIC_KEYS = (
    "problem_clarity",
    "evidence_quality",
    "action_feasibility",
    "validation_design",
)


def test_reviewer_transition_locks_context_in_one_scoped_postgres_query():
    statement = locked_scoped_context_query(
        Actor(REVIEWER_ID, ORGANIZATION_ID, Role.REVIEWER, "Fixture Reviewer"),
        uuid.uuid4(),
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert sql.count("SELECT ") == 1
    assert "FOR UPDATE OF reviews, assignments" in sql
    assert "reviews.organization_id =" in sql
    assert "reviews.reviewer_id =" in sql
    assert "assignments.organization_id =" in sql
    assert "enrollments.status =" in sql
    assert "enrollments.reviewer_id = reviews.reviewer_id" in sql
    assert "task_versions.task_definition_id = assignments.task_definition_id" in sql
    assert (
        "journey_stage_versions.journey_version_id = enrollments.journey_version_id"
        in sql
    )
    assert (
        "journey_stage_versions.task_version_id = assignments.task_version_id" in sql
    )


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 52_000))


def assert_ok(response):
    assert response.status_code < 400, response.text
    assert response.headers["X-Request-ID"].startswith("req_")
    return response.json()["data"]


def submission_body(label: str) -> str:
    return (
        f"{label}：新人需要把真实问题转化为清楚行动。"
        "事实一是入口说明可核对，事实二是责任人反馈可以核对。"
        "行动不超过三步并明确第一步责任人；两周内用理解率验证，"
        "若低于百分之九十就停止扩量并调整。"
    )


def create_submission(
    label: str,
    reviewer_id: uuid.UUID = REVIEWER_ID,
    *,
    ai_use: dict[str, object] | None = None,
):
    operator = client_for(f"operator-{label}")
    invite = assert_ok(
        operator.post(
            "/api/v1/ops/invites",
            headers={
                **OPERATOR_HEADERS,
                "Idempotency-Key": f"wp04-invite-{uuid.uuid4()}",
            },
            json={
                "purpose": "验证 WP-04 Reviewer 工作台与不可变结论",
                "expires_in_hours": 24,
                "role": "LEARNER",
                "reviewer_id": str(reviewer_id),
                "task_version_id": str(TASK_VERSION_V2_ID),
                "target_user_id": None,
            },
        )
    )
    learner = client_for(f"learner-{label}")
    exchanged = assert_ok(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": invite["invite_token"], "return_to": "/app"},
        )
    )
    confirmed = assert_ok(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": f"WP04 新人 {label}",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    current = assert_ok(learner.get("/api/v1/me/current-action"))
    started = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{current['resource_id']}/start",
            headers={
                "Idempotency-Key": f"wp04-start-{uuid.uuid4()}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={"expected_revision": current["revision"]},
        )
    )
    submitted = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{current['resource_id']}/submissions",
            headers={
                "Idempotency-Key": f"wp04-submit-{uuid.uuid4()}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={
                "expected_revision": started["revision"],
                "body": submission_body(label),
                "attachment_ids": [],
                **({"ai_use": ai_use} if ai_use is not None else {}),
            },
        )
    )
    with SessionLocal() as session:
        review = session.scalar(
            select(Review).where(
                Review.submission_version_id
                == uuid.UUID(submitted["submission_version_id"])
            )
        )
        assert review is not None
        review_id = review.id
    return {
        "learner": learner,
        "csrf": confirmed["csrf_token"],
        "assignment_id": current["resource_id"],
        "submission": submitted,
        "review_id": review_id,
    }


def test_ai_provenance_is_durable_visible_and_advisory_only():
    learner_ai = {
        "used": True,
        "purpose": "check structure before learner submission",
        "model_version": "advisory-model-v1",
        "prompt_version": "learner-self-check-v1",
        "output_is_advisory_only": True,
    }
    flow = create_submission("ai-provenance", ai_use=learner_ai)
    reviewer = client_for("reviewer-ai-provenance")
    detail = assert_ok(reviewer.get(f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS))
    assert detail["submission_ai_use"] == learner_ai

    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"ai-review-start-{uuid.uuid4()}",
            },
            json={"expected_revision": detail["revision"]},
        )
    )
    reviewer_ai = {
        "used": True,
        "purpose": "organize rubric notes before human decision",
        "model_version": "advisory-model-v1",
        "prompt_version": "reviewer-note-check-v1",
        "output_is_advisory_only": True,
    }
    payload = finalize_payload(started["review_revision"], decision="APPROVE")
    payload["ai_use"] = reviewer_ai
    assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"ai-review-finalize-{uuid.uuid4()}",
            },
            json=payload,
        )
    )
    finalized = assert_ok(
        reviewer.get(f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS)
    )
    assert finalized["evaluation"]["ai_use"] == reviewer_ai
    with SessionLocal() as session:
        version = session.get(
            SubmissionVersion,
            uuid.UUID(flow["submission"]["submission_version_id"]),
        )
        evaluation = session.scalar(
            select(Evaluation).where(Evaluation.review_id == uuid.UUID(str(flow["review_id"])))
        )
        assert version is not None and version.ai_use == learner_ai
        assert evaluation is not None and evaluation.ai_use == reviewer_ai
        submission_id = version.submission_id
    try:
        with SessionLocal.begin() as session:
            session.add(
                SubmissionVersion(
                    id=uuid.uuid4(),
                    submission_id=submission_id,
                    version_no=99,
                    body=submission_body("invalid-db-ai-provenance"),
                    ai_use={
                        "used": True,
                        "purpose": "draft answer",
                        "model_version": "advisory-model-v1",
                        "prompt_version": "learner-self-check-v1",
                        "output_is_advisory_only": False,
                    },
                    created_by=uuid.UUID(assert_ok(flow["learner"].get("/api/v1/session"))["user_id"]),
                )
            )
    except DBAPIError as error:
        assert "ck_submission_versions_ai_provenance" in str(error)
    else:
        raise AssertionError("database accepted non-advisory AI provenance")


def test_incomplete_or_non_advisory_ai_provenance_fails_closed():
    flow = create_submission("ai-invalid-baseline")
    reviewer = client_for("reviewer-ai-invalid")
    detail = assert_ok(reviewer.get(f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS))
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"ai-invalid-start-{uuid.uuid4()}",
            },
            json={"expected_revision": detail["revision"]},
        )
    )
    payload = finalize_payload(started["review_revision"], decision="APPROVE")
    payload["ai_use"] = {
        "used": True,
        "purpose": "draft reviewer notes",
        "model_version": "advisory-model-v1",
        "prompt_version": "reviewer-note-check-v1",
        "output_is_advisory_only": False,
    }
    response = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/finalize",
        headers={
            **REVIEWER_HEADERS,
            "Idempotency-Key": f"ai-invalid-finalize-{uuid.uuid4()}",
        },
        json=payload,
    )
    assert response.status_code == 422


def finalize_payload(
    expected_revision: int,
    *,
    decision: str,
    needs_work_key: str | None = None,
    overall_feedback: str = "总体反馈具体说明当前证据与下一步行动。",
) -> dict[str, object]:
    return {
        "expected_revision": expected_revision,
        "overall_decision": decision,
        "overall_feedback": overall_feedback,
        "rubric_evaluations": [
            {
                "dimension_key": key,
                "rating": "NEEDS_WORK" if key == needs_work_key else "MEETS",
                "feedback": (
                    "请补充这一维度的具体证据和可执行修改。"
                    if key == needs_work_key
                    else "该维度的证据符合批准锚点。"
                ),
            }
            for key in RUBRIC_KEYS
        ],
    }


def test_learner_reentry_after_revision_required_rotates_session_without_business_fact_changes():
    flow = create_submission("reentry-after-revision")
    reviewer = client_for("reviewer-reentry-after-revision")
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"reentry-review-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    feedback = "请补充来源证据，并明确第一步责任人后提交新的修订版本。"
    assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"reentry-review-finalize-{uuid.uuid4()}",
            },
            json=finalize_payload(
                started["review_revision"],
                decision="REQUEST_REVISION",
                needs_work_key="evidence_quality",
                overall_feedback=feedback,
            ),
        )
    )
    original_session = assert_ok(flow["learner"].get("/api/v1/session"))

    tracked_models = (
        User,
        Enrollment,
        Assignment,
        Submission,
        SubmissionVersion,
        Review,
        Evaluation,
        OutboxEvent,
    )
    with SessionLocal() as session:
        assignment = session.get(Assignment, uuid.UUID(flow["assignment_id"]))
        assert assignment is not None
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        assert enrollment is not None
        enrollment_id = enrollment.id
        enrollment_revision = enrollment.revision
        before = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in tracked_models
        }

    operator = client_for("operator-create-learner-reentry")
    idempotency_key = f"learner-reentry-{uuid.uuid4()}"
    payload = {
        "expected_revision": enrollment_revision,
        "expires_in_minutes": 30,
        "reason": "Learner 会话已过期，需要继续既有修订任务",
    }
    created = assert_ok(
        operator.post(
            f"/api/v1/ops/enrollments/{enrollment_id}/learner-reentry",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": idempotency_key},
            json=payload,
        )
    )
    replay = assert_ok(
        operator.post(
            f"/api/v1/ops/enrollments/{enrollment_id}/learner-reentry",
            headers={**OPERATOR_HEADERS, "Idempotency-Key": idempotency_key},
            json=payload,
        )
    )
    assert replay["invite_token"] == created["invite_token"]
    assert replay["idempotency_replay"] is True
    duplicate = operator.post(
        f"/api/v1/ops/enrollments/{enrollment_id}/learner-reentry",
        headers={**OPERATOR_HEADERS, "Idempotency-Key": f"duplicate-{uuid.uuid4()}"},
        json=payload,
    )
    assert duplicate.status_code == 409

    reentry_client = client_for("learner-reentry-new-browser")
    exchanged = assert_ok(
        reentry_client.post(
            "/api/v1/join/exchange",
            json={"token": created["invite_token"], "return_to": "/app"},
        )
    )
    assert exchanged["status"] == "PENDING_REENTRY"
    assert exchanged["flow"] == "REENTRY"
    confirmed = assert_ok(
        reentry_client.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": None,
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    assert confirmed["user_id"] == original_session["user_id"]
    assert confirmed["enrollment_status"] == "ACTIVE"
    assert flow["learner"].get("/api/v1/session").status_code == 401
    current = assert_ok(reentry_client.get("/api/v1/me/current-action"))
    assert current["resource_id"] == flow["assignment_id"]
    assert current["action_type"] == "REVISE_SUBMISSION"
    detail = assert_ok(
        reentry_client.get(f"/api/v1/me/assignments/{flow['assignment_id']}")
    )
    assert detail["allowed_commands"] == ["submit_revision"]
    assert detail["latest_revision_feedback"] == feedback

    consumed_again = client_for("learner-reentry-replay").post(
        "/api/v1/join/exchange",
        json={"token": created["invite_token"], "return_to": "/app"},
    )
    assert consumed_again.status_code == 410
    with SessionLocal() as session:
        after = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in tracked_models
        }
        invite = session.get(Invite, uuid.UUID(created["id"]))
        assert invite is not None
        assert invite.token_hash != created["invite_token"]
        assert invite.status == InviteStatus.CONSUMED
        assert session.scalar(
            select(AuditEntry.id).where(
                AuditEntry.action == "learner_reentry.confirmed",
                AuditEntry.actor_id == uuid.UUID(original_session["user_id"]),
            )
        )
    assert after == before


def create_other_org_review() -> uuid.UUID:
    organization_id = uuid.uuid4()
    learner_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()
    definition_id = uuid.uuid4()
    task_id = uuid.uuid4()
    enrollment_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    submission_id = uuid.uuid4()
    version_id = uuid.uuid4()
    review_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        source = session.get(TaskVersion, TASK_VERSION_V2_ID)
        assert source is not None
        session.add(Organization(id=organization_id, name="WP04 隔离组织"))
        session.add_all(
            [
                User(
                    id=learner_id,
                    organization_id=organization_id,
                    display_name="隔离组织新人",
                    status=UserStatus.ACTIVE,
                ),
                User(
                    id=reviewer_id,
                    organization_id=organization_id,
                    display_name="隔离组织主管",
                    status=UserStatus.ACTIVE,
                ),
            ]
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=organization_id,
                user_id=reviewer_id,
                role=Role.REVIEWER,
            )
        )
        session.add(
            TaskDefinition(
                id=definition_id,
                organization_id=organization_id,
                stable_key=f"TSK-{uuid.uuid4().hex[:8].upper()}",
                status=TaskDefinitionStatus.PUBLISHED,
                revision=1,
                created_by=reviewer_id,
            )
        )
        session.flush()
        session.add(
            TaskVersion(
                id=task_id,
                organization_id=organization_id,
                task_definition_id=definition_id,
                version=1,
                title=source.title,
                purpose=source.purpose,
                learner_outcome=source.learner_outcome,
                instructions=source.instructions,
                completion_criteria=source.completion_criteria,
                required_deliverables=source.required_deliverables,
                content_source_notes=source.content_source_notes,
                change_summary=source.change_summary,
                reviewer_calibration_note=source.reviewer_calibration_note,
                allowed_attachment_types=source.allowed_attachment_types,
                max_attachment_size_bytes=source.max_attachment_size_bytes,
                reference_materials=source.reference_materials,
                estimated_duration_minutes=source.estimated_duration_minutes,
                rubric=source.rubric,
                rubric_version=source.rubric_version,
                reviewer_role=source.reviewer_role,
                feedback_sla_business_days=source.feedback_sla_business_days,
                sensitivity=source.sensitivity,
                audience=source.audience,
                published_by=reviewer_id,
                reviewed_by=reviewer_id,
            )
        )
        session.flush()
        session.add(
            Enrollment(
                id=enrollment_id,
                organization_id=organization_id,
                learner_id=learner_id,
                reviewer_id=reviewer_id,
                status=EnrollmentStatus.ACTIVE,
                revision=1,
            )
        )
        session.flush()
        session.add(
            Assignment(
                id=assignment_id,
                organization_id=organization_id,
                enrollment_id=enrollment_id,
                task_definition_id=definition_id,
                task_version_id=task_id,
                position=1,
                status=AssignmentStatus.SUBMITTED,
                revision=3,
            )
        )
        session.flush()
        session.add(
            Submission(
                id=submission_id,
                organization_id=organization_id,
                assignment_id=assignment_id,
                current_version_no=1,
            )
        )
        session.flush()
        session.add(
            SubmissionVersion(
                id=version_id,
                submission_id=submission_id,
                version_no=1,
                body=submission_body("跨组织固定版本"),
                created_by=learner_id,
            )
        )
        session.flush()
        session.add(
            Review(
                id=review_id,
                organization_id=organization_id,
                assignment_id=assignment_id,
                submission_id=submission_id,
                submission_version_id=version_id,
                reviewer_id=reviewer_id,
                status=ReviewStatus.ASSIGNED,
                revision=1,
            )
        )
    return review_id


def test_queue_detail_scope_priority_and_get_are_side_effect_free():
    own = create_submission("scope-own")
    other_reviewer_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=other_reviewer_id,
                organization_id=ORGANIZATION_ID,
                display_name="同组织其他主管",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=other_reviewer_id,
                role=Role.REVIEWER,
            )
        )
    other = create_submission("scope-other-reviewer", other_reviewer_id)
    cross_org_review_id = create_other_org_review()

    with SessionLocal() as session:
        review_before = session.get(Review, own["review_id"])
        assert review_before is not None
        state_before = (
            review_before.status,
            review_before.revision,
            review_before.started_at,
            review_before.finalized_at,
        )
        counts_before = (
            session.scalar(select(func.count(Evaluation.id))),
            session.scalar(select(func.count(AuditEntry.id))),
            session.scalar(select(func.count(OutboxEvent.id))),
            session.scalar(select(func.count(Review.id))),
        )

    reviewer = client_for("reviewer-scope")
    queue = assert_ok(reviewer.get("/api/v1/reviews", headers=REVIEWER_HEADERS))
    own_item = next(item for item in queue["items"] if item["id"] == str(own["review_id"]))
    assert own_item["allowed_commands"] == ["start"]
    assert own_item["material_status"] == "COMPLETE"
    assert own_item["submission_version_id"] == own["submission"]["submission_version_id"]
    assert own_item["priority_reason"] == "按等待时间排序"
    assert own_item["submitted_at"]
    assert own_item["feedback_sla_business_days"] >= 1
    assert own_item["revision_count"] == 0
    assert own_item["sensitivity"]
    assert own_item["audience"]
    assert own_item["conflict_status"] == "NOT_EVALUATED"
    queue_ids = {item["id"] for item in queue["items"]}
    assert str(other["review_id"]) not in queue_ids
    assert str(cross_org_review_id) not in queue_ids

    first = assert_ok(
        reviewer.get(f"/api/v1/reviews/{own['review_id']}", headers=REVIEWER_HEADERS)
    )
    second = assert_ok(
        reviewer.get(f"/api/v1/reviews/{own['review_id']}", headers=REVIEWER_HEADERS)
    )
    assert first == second
    assert first["submission_body"] == submission_body("scope-own")
    assert first["materials"]["status"] == "COMPLETE"
    assert len(first["required_deliverables"]) == 4
    assert (
        reviewer.get(f"/api/v1/reviews/{other['review_id']}", headers=REVIEWER_HEADERS).status_code
        == 404
    )
    assert (
        reviewer.get(
            f"/api/v1/reviews/{cross_org_review_id}", headers=REVIEWER_HEADERS
        ).status_code
        == 404
    )
    assert (
        own["learner"].get(f"/api/v1/reviews/{own['review_id']}").status_code
        == 403
    )

    with SessionLocal() as session:
        review_after = session.get(Review, own["review_id"])
        assert review_after is not None
        assert (
            review_after.status,
            review_after.revision,
            review_after.started_at,
            review_after.finalized_at,
        ) == state_before
        assert (
            session.scalar(select(func.count(Evaluation.id))),
            session.scalar(select(func.count(AuditEntry.id))),
            session.scalar(select(func.count(OutboxEvent.id))),
            session.scalar(select(func.count(Review.id))),
        ) == counts_before


def test_non_reviewer_roles_cannot_read_or_sign_the_business_review_gate():
    flow = create_submission("role-permission-matrix")
    content_editor_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        session.add(
            User(
                id=content_editor_id,
                organization_id=ORGANIZATION_ID,
                display_name="合成内容编辑",
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RoleAssignment(
                id=uuid.uuid4(),
                organization_id=ORGANIZATION_ID,
                user_id=content_editor_id,
                role=Role.CONTENT_EDITOR,
            )
        )

    with SessionLocal() as session:
        review = session.get(Review, flow["review_id"])
        assert review is not None
        state_before = (review.status, review.revision, review.started_at)
        counts_before = (
            session.scalar(select(func.count(Evaluation.id))),
            session.scalar(select(func.count(AuditEntry.id))),
            session.scalar(select(func.count(OutboxEvent.id))),
        )

    actors = (
        (client_for("operator-cannot-sign-review"), OPERATOR_HEADERS),
        (client_for("content-editor-cannot-sign-review"), CONTENT_EDITOR_HEADERS),
        (flow["learner"], {"X-CSRF-Token": flow["csrf"]}),
    )
    for actor, role_headers in actors:
        assert (
            actor.get(
                f"/api/v1/reviews/{flow['review_id']}", headers=role_headers
            ).status_code
            == 403
        )
        assert (
            actor.post(
                f"/api/v1/reviews/{flow['review_id']}/start",
                headers={
                    **role_headers,
                    "Idempotency-Key": f"forbidden-start-{uuid.uuid4()}",
                },
                json={"expected_revision": 1},
            ).status_code
            == 403
        )
        assert (
            actor.post(
                f"/api/v1/reviews/{flow['review_id']}/finalize",
                headers={
                    **role_headers,
                    "Idempotency-Key": f"forbidden-finalize-{uuid.uuid4()}",
                },
                json=finalize_payload(1, decision="APPROVE"),
            ).status_code
            == 403
        )

    with SessionLocal() as session:
        review = session.get(Review, flow["review_id"])
        assert review is not None
        assert (review.status, review.revision, review.started_at) == state_before
        assert (
            session.scalar(select(func.count(Evaluation.id))),
            session.scalar(select(func.count(AuditEntry.id))),
            session.scalar(select(func.count(OutboxEvent.id))),
        ) == counts_before


def test_inactive_enrollment_closes_review_mutation_window_without_hiding_history():
    flow = create_submission("inactive-enrollment-window")
    with SessionLocal.begin() as session:
        assignment = session.get(Assignment, uuid.UUID(flow["assignment_id"]))
        assert assignment is not None
        enrollment = session.get(Enrollment, assignment.enrollment_id)
        assert enrollment is not None
        enrollment.status = EnrollmentStatus.CANCELLED

    reviewer = client_for("reviewer-inactive-enrollment")
    historical = assert_ok(
        reviewer.get(
            f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS
        )
    )
    assert historical["allowed_commands"] == []
    denied = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/start",
        headers={
            **REVIEWER_HEADERS,
            "Idempotency-Key": f"inactive-start-{uuid.uuid4()}",
        },
        json={"expected_revision": 1},
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "NOT_FOUND"
    with SessionLocal() as session:
        review = session.get(Review, flow["review_id"])
        assert review is not None
        assert review.status == ReviewStatus.ASSIGNED
        assert review.revision == 1
        assert review.started_at is None


def test_request_revision_is_structured_replayable_and_history_is_immutable():
    flow = create_submission("revision")
    reviewer = client_for("reviewer-revision")
    start_key = f"wp04-review-start-{uuid.uuid4()}"
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={**REVIEWER_HEADERS, "Idempotency-Key": start_key},
            json={"expected_revision": 1},
        )
    )
    start_replay = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={**REVIEWER_HEADERS, "Idempotency-Key": start_key},
            json={"expected_revision": 1},
        )
    )
    assert started["review_status"] == "IN_REVIEW"
    assert start_replay["idempotency_replay"] is True
    detail = assert_ok(
        reviewer.get(f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS)
    )
    assert detail["allowed_commands"] == ["approve", "request_revision"]

    incomplete = finalize_payload(
        started["review_revision"],
        decision="REQUEST_REVISION",
        needs_work_key="evidence_quality",
    )
    incomplete["rubric_evaluations"] = incomplete["rubric_evaluations"][:-1]
    response = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/finalize",
        headers={**REVIEWER_HEADERS, "Idempotency-Key": f"invalid-{uuid.uuid4()}"},
        json=incomplete,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"

    inconsistent = finalize_payload(
        started["review_revision"],
        decision="APPROVE",
        needs_work_key="evidence_quality",
    )
    response = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/finalize",
        headers={**REVIEWER_HEADERS, "Idempotency-Key": f"invalid-{uuid.uuid4()}"},
        json=inconsistent,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"

    payload = finalize_payload(
        started["review_revision"],
        decision="REQUEST_REVISION",
        needs_work_key="evidence_quality",
        overall_feedback="请补充事实来源，再明确第一步责任人后提交修订。",
    )
    final_key = f"wp04-final-{uuid.uuid4()}"
    finalized = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={**REVIEWER_HEADERS, "Idempotency-Key": final_key},
            json=payload,
        )
    )
    replay = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={**REVIEWER_HEADERS, "Idempotency-Key": final_key},
            json=payload,
        )
    )
    assert finalized["decision"] == "REVISION_REQUIRED"
    assert finalized["assignment_status"] == "NEEDS_REVISION"
    assert replay["evaluation_id"] == finalized["evaluation_id"]
    assert replay["idempotency_replay"] is True
    changed_payload = {**payload, "overall_feedback": "这是不同的反馈内容，必须拒绝重用幂等键。"}
    changed = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/finalize",
        headers={**REVIEWER_HEADERS, "Idempotency-Key": final_key},
        json=changed_payload,
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    stale = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/finalize",
        headers={**REVIEWER_HEADERS, "Idempotency-Key": f"stale-{uuid.uuid4()}"},
        json=payload,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    final_detail = assert_ok(
        reviewer.get(f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS)
    )
    assert final_detail["allowed_commands"] == []
    assert final_detail["evaluation"]["overall_decision"] == "REQUEST_REVISION"
    assert final_detail["evaluation"]["feedback_structure_version"] == 1
    assert len(final_detail["evaluation"]["rubric_evaluations"]) == 4
    learner_detail = assert_ok(
        flow["learner"].get(f"/api/v1/me/assignments/{flow['assignment_id']}")
    )
    assert learner_detail["allowed_commands"] == ["submit_revision"]
    assert learner_detail["latest_revision_feedback"] == payload["overall_feedback"]
    reviewed_version = learner_detail["submission"]["versions"][-1]
    assert reviewed_version["decision"] == "REVISION_REQUIRED"
    assert len(reviewed_version["rubric_feedback"]) == 4
    assert all(item["feedback"] for item in reviewed_version["rubric_feedback"])
    current = assert_ok(flow["learner"].get("/api/v1/me/current-action"))
    assert current["action_type"] == "REVISE_SUBMISSION"

    evaluation_id = uuid.UUID(finalized["evaluation_id"])
    try:
        with SessionLocal.begin() as session:
            session.execute(
                update(Evaluation)
                .where(Evaluation.id == evaluation_id)
                .values(feedback="覆盖旧结论")
            )
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("final Evaluation update unexpectedly succeeded")
    try:
        with SessionLocal.begin() as session:
            session.execute(delete(Review).where(Review.id == flow["review_id"]))
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("final Review deletion unexpectedly succeeded")

    revision_detail = assert_ok(
        flow["learner"].get(f"/api/v1/me/assignments/{flow['assignment_id']}")
    )
    revised = assert_ok(
        flow["learner"].post(
            f"/api/v1/me/assignments/{flow['assignment_id']}/submissions",
            headers={
                "Idempotency-Key": f"wp04-revision-submit-{uuid.uuid4()}",
                "X-CSRF-Token": flow["csrf"],
            },
            json={
                "expected_revision": revision_detail["revision"],
                "body": submission_body("revision-v2") + " 已补充具体来源。",
                "attachment_ids": [],
            },
        )
    )
    assert revised["version_no"] == 2
    queue = assert_ok(reviewer.get("/api/v1/reviews", headers=REVIEWER_HEADERS))
    revision_item = next(
        item
        for item in queue["items"]
        if item["submission_version_id"] == revised["submission_version_id"]
    )
    assert revision_item["priority_reason"] == "修订提交，优先复评"
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(Review.id)).where(
                Review.assignment_id == uuid.UUID(flow["assignment_id"])
            )
        ) == 2
        evaluation = session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        assert evaluation.decision == Decision.REVISION_REQUIRED
        assert evaluation.submission_version_id == uuid.UUID(
            flow["submission"]["submission_version_id"]
        )


def test_incomplete_material_blocks_finalize_without_creating_evaluation():
    flow = create_submission("missing-material")
    attachment_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        submission_id = uuid.UUID(flow["submission"]["submission_id"])
        version_id = uuid.UUID(flow["submission"]["submission_version_id"])
        assignment_id = uuid.UUID(flow["assignment_id"])
        session.add(
            Attachment(
                id=attachment_id,
                organization_id=ORGANIZATION_ID,
                owner_id=session.get(SubmissionVersion, version_id).created_by,
                assignment_id=assignment_id,
                purpose="SUBMISSION_EVIDENCE",
                original_filename="尚未完成扫描.txt",
                storage_key=f"wp04/incomplete/{attachment_id}",
                content_type="text/plain",
                size_bytes=20,
                sha256="a" * 64,
                status=AttachmentStatus.UPLOADED,
                scan_status=AttachmentScanStatus.PENDING,
            )
        )
        session.flush()
        session.add(
            SubmissionVersionAttachment(
                submission_id=submission_id,
                submission_version_id=version_id,
                attachment_id=attachment_id,
                organization_id=ORGANIZATION_ID,
                assignment_id=assignment_id,
                position=1,
            )
        )
    reviewer = client_for("reviewer-material")
    detail = assert_ok(
        reviewer.get(f"/api/v1/reviews/{flow['review_id']}", headers=REVIEWER_HEADERS)
    )
    assert detail["material_status"] == "INCOMPLETE"
    assert detail["materials"]["missing_items"] == ["附件 尚未完成扫描.txt 当前不可用"]
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"material-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    blocked = reviewer.post(
        f"/api/v1/reviews/{flow['review_id']}/finalize",
        headers={
            **REVIEWER_HEADERS,
            "Idempotency-Key": f"material-final-{uuid.uuid4()}",
        },
        json=finalize_payload(started["review_revision"], decision="APPROVE"),
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "MATERIALS_INCOMPLETE"
    with SessionLocal() as session:
        review = session.get(Review, flow["review_id"])
        assert review is not None and review.status == ReviewStatus.IN_REVIEW
        assert session.scalar(
            select(func.count(Evaluation.id)).where(Evaluation.review_id == flow["review_id"])
        ) == 0


def test_approve_completes_assignment_and_keeps_minimal_result_compatibility():
    flow = create_submission("approve")
    reviewer = client_for("reviewer-approve")
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"approve-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    approved = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/finalize",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"approve-final-{uuid.uuid4()}",
            },
            json=finalize_payload(
                started["review_revision"],
                decision="APPROVE",
                overall_feedback="四个维度全部达标，可以进入既有最小交接结果。",
            ),
        )
    )
    assert approved["decision"] == "PASS"
    assert approved["assignment_status"] == "PASSED"
    result = assert_ok(flow["learner"].get("/api/v1/me/result"))
    assert result["decision"] == "PASS"
    current = assert_ok(flow["learner"].get("/api/v1/me/current-action"))
    assert current["action_type"] == "VIEW_RESULT_OR_HANDOFF"


def test_concurrent_finalize_has_one_winner_and_same_key_replays():
    def run_pair(flow, payload, keys):
        def finalize(label_and_key):
            label, key = label_and_key
            response = client_for(label).post(
                f"/api/v1/reviews/{flow['review_id']}/finalize",
                headers={**REVIEWER_HEADERS, "Idempotency-Key": key},
                json=payload,
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(finalize, zip(("final-a", "final-b"), keys)))

    flow = create_submission("concurrent-different")
    reviewer = client_for("reviewer-concurrent-different")
    started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"concurrent-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    payload = finalize_payload(
        started["review_revision"],
        decision="REQUEST_REVISION",
        needs_work_key="validation_design",
    )
    different = run_pair(
        flow,
        payload,
        (f"different-{uuid.uuid4()}", f"different-{uuid.uuid4()}"),
    )
    assert sorted(status for status, _ in different) == [200, 409]
    assert next(body for status, body in different if status == 409)["error"]["code"] == "VERSION_CONFLICT"
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(Evaluation.id)).where(Evaluation.review_id == flow["review_id"])
        ) == 1

    replay_flow = create_submission("concurrent-replay")
    replay_started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{replay_flow['review_id']}/start",
            headers={
                **REVIEWER_HEADERS,
                "Idempotency-Key": f"concurrent-start-{uuid.uuid4()}",
            },
            json={"expected_revision": 1},
        )
    )
    replay_payload = finalize_payload(
        replay_started["review_revision"],
        decision="REQUEST_REVISION",
        needs_work_key="action_feasibility",
    )
    shared_key = f"same-{uuid.uuid4()}"
    same = run_pair(replay_flow, replay_payload, (shared_key, shared_key))
    assert [status for status, _ in same] == [200, 200]
    assert sorted(body["data"]["idempotency_replay"] for _, body in same) == [False, True]
    assert len({body["data"]["evaluation_id"] for _, body in same}) == 1
