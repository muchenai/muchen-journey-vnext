"""All eight stages unlock on durable submission and complete on human review."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from journey_api.db import SessionLocal
from journey_api.models import JourneyCompletionPolicy, JourneyStageKind, Outcome
from sqlalchemy import select, func
from journey_api.fixtures import REVIEWER_ID
from journey_api.formal_journey_catalog import FORMAL_JOURNEY_KEY
from scripts.p0_journey_v3_browser_fixture import STAGES, task_payload
from test_wp26_learning_materials import (
    OPERATOR_HEADERS, client_for, command, data, finalize_review,
)


@pytest.mark.parametrize("legacy_policy", [False, True])
def test_all_eight_stages_persist_materials_and_allow_completed_stage_review(legacy_policy):
    operator = client_for("material-progress-operator")
    learner = client_for("material-progress-learner")
    reviewer = client_for("material-progress-reviewer")
    journeys = data(operator.get("/api/v1/ops/formal-journeys", headers=OPERATOR_HEADERS))["items"]
    journeys = [item for item in journeys if item["stable_key"] == FORMAL_JOURNEY_KEY]
    current = max(journeys, key=lambda item: item["version"]) if journeys else data(command(operator,
        "/api/v1/ops/formal-journeys/publish", {
            "reviewed_by": str(REVIEWER_ID), "catalog_version": 2,
            "expected_current_version": 0, "expected_absent": True,
            "review_acknowledged": True,
        }, headers=OPERATOR_HEADERS))
    definitions = {item["stable_key"]: item for item in data(operator.get(
        "/api/v1/ops/task-definitions", headers=OPERATOR_HEADERS))["items"]}
    versions = []
    for stable_key, title in STAGES:
        definition = definitions[stable_key]
        payload = task_payload(stable_key, title, definition["revision"], str(REVIEWER_ID))
        # Two distinct links on each synthetic stage; leave the optional second
        # material unread until the task has been submitted/completed.
        first = payload["learning_materials"][0]
        second = {**first, "key": first["key"] + "-review",
                  "url": first["url"] + "#review", "required": False}
        payload["learning_materials"] = [first, second]
        payload["verified_material_urls"] = [first["url"], second["url"]]
        versions.append(data(command(operator,
            f"/api/v1/ops/task-definitions/{definition['id']}/publish",
            payload, headers=OPERATOR_HEADERS))["id"])
    from sqlalchemy import event
    from journey_api.models import JourneyStageVersion
    def legacy_init(target, args, kwargs):
        if kwargs.get("stage_kind") != JourneyStageKind.ASSESSMENT:
            kwargs["completion_policy"] = JourneyCompletionPolicy.LEARNER_EVIDENCE
    if legacy_policy:
        event.listen(JourneyStageVersion, "init", legacy_init)
    try:
        journey = data(command(operator, "/api/v1/ops/formal-journeys/assemble-v3", {
            "reviewed_by": str(REVIEWER_ID), "expected_current_version": current["version"],
            "task_version_ids": versions,
            "content_review_note": "隔离测试：核对八关材料独立持久化和完成后回看。",
            "review_acknowledged": True,
        }, headers=OPERATOR_HEADERS))
    finally:
        if legacy_policy:
            event.remove(JourneyStageVersion, "init", legacy_init)
    invite = data(command(operator, "/api/v1/ops/invites", {
        "purpose": "材料完成状态回归测试", "expires_in_hours": 24,
        "role": "LEARNER", "reviewer_id": str(REVIEWER_ID),
        "journey_version_id": journey["id"], "target_user_id": None,
    }, headers=OPERATOR_HEADERS))
    exchanged = data(learner.post("/api/v1/join/exchange", json={
        "token": invite["invite_token"], "return_to": "/app"}))
    data(learner.post("/api/v1/identity/confirm",
        headers={"X-CSRF-Token": exchanged["csrf_token"]}, json={
            "display_name": "Materials Regression", "accepted_purpose": True, "return_to": "/app"}))
    nodes = data(learner.get("/api/v1/me/current-action"))["journey"]["nodes"]
    rejected = False
    for index, node in enumerate(nodes):
        path = f"/api/v1/me/assignments/{node['assignment_id']}"
        before = data(learner.get(path))
        assert all(m["completed_at"] is None for m in before["learning_materials"])
        if index + 1 < len(nodes):
            future_path = f"/api/v1/me/assignments/{nodes[index + 1]['assignment_id']}"
            future = data(learner.get(future_path))
            denied = command(learner,
                f"{future_path}/materials/{future['learning_materials'][0]['key']}/complete",
                {"task_version": future["task_version"]})
            assert denied.status_code == 409
            assert denied.json()["error"]["code"] == "JOURNEY_STAGE_LOCKED"
        first, second = before["learning_materials"]
        completed = data(command(learner, f"{path}/materials/{first['key']}/complete",
            {"task_version": before["task_version"]}))
        fresh = data(learner.get(path))
        assert fresh["learning_materials"][0]["completed_at"] == completed["completed_at"]
        assert fresh["learning_materials"][1]["completed_at"] is None
        started = data(command(learner, f"{path}/start", {"expected_revision": fresh["revision"]}))
        body = ("这是隔离测试的学习记录，引用材料依据并记录当前判断和下一步行动。" * 3
                + "\n飞书文档：https://zx6w57w0j34.feishu.cn/docx/MaterialRegressionEvidence")
        submitted = data(command(learner, f"{path}/submissions", {
            "expected_revision": started["revision"], "body": body,
        }))
        second_done = data(command(learner, f"{path}/materials/{second['key']}/complete",
            {"task_version": before["task_version"]}))
        after = data(learner.get(path))
        assert after["status"] == submitted["assignment_status"]
        assert after["revision"] == submitted["assignment_revision"]
        assert after["learning_materials"][0]["completed_at"] == completed["completed_at"]
        assert after["learning_materials"][1]["completed_at"] == second_done["completed_at"]
        assert submitted["assignment_status"] == "SUBMITTED"
        # A duplicate HTTP request cannot submit a second pending version.
        duplicate = command(learner, f"{path}/submissions", {
            "expected_revision": after["revision"], "body": body,
        })
        assert duplicate.status_code == 409
        progress = data(learner.get("/api/v1/me/current-action"))
        assert progress["journey"]["completed_stages"] == 0
        assert progress["journey"]["nodes"][index]["assignment_status"] == "SUBMITTED"
        assert after["submission"]["versions"][-1]["review_kind"] == "FORMAL_EVALUATION"
        if index + 1 < len(nodes):
            assert progress["resource_id"] == nodes[index + 1]["assignment_id"]
            assert progress["journey"]["nodes"][index + 1]["status"] == "CURRENT"
        if index + 2 < len(nodes):
            assert progress["journey"]["nodes"][index + 2]["status"] == "LOCKED"
        # Every stage requires an explicit edit action after rejection. Cancel
        # restores that rejection and never marks the stage as completed.
        finalize_review(reviewer, node["assignment_id"], "REQUEST_REVISION")
        rejected_detail = data(learner.get(path))
        assert rejected_detail["allowed_commands"] == ["start_evidence_revision"]
        assert command(learner, f"{path}/submissions", {
            "expected_revision": rejected_detail["revision"], "body": body,
        }).status_code == 409
        assert learner.put(f"{path}/draft", headers={
            "Idempotency-Key": str(uuid.uuid4()),
            "X-CSRF-Token": learner.cookies.get("journey_next_csrf"),
        }, json={"expected_revision": rejected_detail["revision"], "body": body}).status_code == 409
        edit = data(command(learner, f"{path}/evidence-revision/start", {
            "expected_revision": rejected_detail["revision"],
        }))
        editing = data(learner.get(path))
        assert editing["draft"]["body"] == body
        assert "submit_evidence_revision" in editing["allowed_commands"]
        cancelled = data(command(learner, f"{path}/evidence-revision/cancel", {
            "expected_revision": edit["revision"],
        }))
        assert cancelled["status"] == "NEEDS_REVISION"
        edit = data(command(learner, f"{path}/evidence-revision/start", {
            "expected_revision": cancelled["revision"],
        }))
        data(command(learner, f"{path}/submissions", {
            "expected_revision": edit["revision"], "body": body,
        }))
        pending = data(learner.get(path))
        assert pending["allowed_commands"] == []
        assert command(learner, f"{path}/evidence-revision/start", {
            "expected_revision": pending["revision"],
        }).status_code == 409
        if index + 1 < len(nodes):
            assert data(learner.get("/api/v1/me/current-action"))["journey"]["nodes"][index + 1]["status"] == "CURRENT"
        if index == 0:
            finalize_review(reviewer, node["assignment_id"], "REQUEST_REVISION")
            rejected = True
            # Even after Day 1 is returned, the next stage remains actionable.
            action = data(learner.get("/api/v1/me/current-action"))
            assert action["resource_id"] == nodes[1]["assignment_id"]
            assert action["journey"]["nodes"][0]["assignment_status"] == "NEEDS_REVISION"
        replay = data(command(learner, f"{path}/materials/{second['key']}/complete",
            {"task_version": before["task_version"]}))
        assert replay["completed_at"] == second_done["completed_at"]
    assert rejected
    # All eight have been submitted, but none may be counted as completed.
    state = data(learner.get("/api/v1/me/current-action"))
    assert state["action_type"] == "REVISE_SUBMISSION"
    assert state["journey"]["completed_stages"] == 0
    assert all(n["status"] == "CURRENT" for n in state["journey"]["nodes"])
    path = f"/api/v1/me/assignments/{nodes[0]['assignment_id']}"
    detail = data(learner.get(path))
    assert "start_evidence_revision" in detail["allowed_commands"]
    detail = data(command(learner, f"{path}/evidence-revision/start", {"expected_revision": detail["revision"]}))
    resubmitted = data(command(learner, f"{path}/submissions", {
        "expected_revision": detail["revision"], "body": body + "已补充材料依据。",
    }))
    assert resubmitted["assignment_status"] == "SUBMITTED"
    assert resubmitted["version_no"] == 3
    assert data(learner.get("/api/v1/me/current-action"))["action_type"] == "WAIT_FOR_REVIEW"
    # Approve assessments first: later approval never graduates an incomplete journey.
    for count, index in enumerate([7, 5, 6, 4, 3, 2], 1):
        finalize_review(reviewer, nodes[index]["assignment_id"], "APPROVE")
        state = data(learner.get("/api/v1/me/current-action"))
        assert state["journey"]["completed_stages"] == count
        assert state["journey"]["nodes"][index]["status"] == "COMPLETED"
        assert state["action_type"] == "WAIT_FOR_REVIEW"
        assert data(learner.get(f"/api/v1/me/assignments/{nodes[index]['assignment_id']}"))["status"] == "PASSED"
    # The final two independent reviews can arrive concurrently, in either order.
    with ThreadPoolExecutor(max_workers=2) as pool:
        approvals = [pool.submit(finalize_review, client_for(f"final-review-{i}"),
                                 nodes[i]["assignment_id"], "APPROVE") for i in (0, 1)]
        for future in approvals:
            assert future.result()["assignment_status"] == "PASSED"
    state = data(learner.get("/api/v1/me/current-action"))
    assert state["journey"]["completed_stages"] == 8
    assert state["action_type"] == "VIEW_RESULT_OR_HANDOFF"
    with SessionLocal() as session:
        from journey_api.models import Assignment
        enrollment_id = session.scalar(select(Assignment.enrollment_id).where(Assignment.id == uuid.UUID(nodes[0]["assignment_id"])))
        assert session.scalar(select(func.count(Outcome.id)).where(Outcome.enrollment_id == enrollment_id)) == 1
    # All eight passed stages expose the same edit action after graduation;
    # cancelling preserves the pass, and starting another edit is blocked.
    for node in nodes:
        passed_path = f"/api/v1/me/assignments/{node['assignment_id']}"
        passed = data(learner.get(passed_path))
        assert passed["allowed_commands"] == ["start_evidence_revision"]
        opened = data(command(learner, f"{passed_path}/evidence-revision/start", {"expected_revision": passed["revision"]}))
        other = next(n for n in nodes if n["assignment_id"] != node["assignment_id"])
        other_detail = data(learner.get(f"/api/v1/me/assignments/{other['assignment_id']}"))
        assert "start_evidence_revision" not in other_detail["allowed_commands"]
        restored = data(command(learner, f"{passed_path}/evidence-revision/cancel", {"expected_revision": opened["revision"]}))
        assert restored["status"] == "COMPLETED"
        assert data(learner.get("/api/v1/me/current-action"))["journey"]["completed_stages"] == 8
    # Explicitly modifying a passed assessment also requires another review.
    path = f"/api/v1/me/assignments/{nodes[7]['assignment_id']}"
    detail = data(learner.get(path))
    restarted = data(command(learner, f"{path}/evidence-revision/start", {"expected_revision": detail["revision"]}))
    changed = data(command(learner, f"{path}/submissions", {"expected_revision": restarted["revision"], "body": body + "重新修改后需要审核。"}))
    assert changed["assignment_status"] == "SUBMITTED"
    assert data(learner.get("/api/v1/me/current-action"))["journey"]["completed_stages"] == 7
    # While awaiting the new review, all other post-graduation edits stay locked.
    assert data(learner.get(f"/api/v1/me/assignments/{nodes[0]['assignment_id']}"))["allowed_commands"] == []
    finalize_review(reviewer, nodes[7]["assignment_id"], "REQUEST_REVISION")
    rejected = data(learner.get(path))
    opened = data(command(learner, f"{path}/evidence-revision/start", {"expected_revision": rejected["revision"]}))
    cancelled = data(command(learner, f"{path}/evidence-revision/cancel", {"expected_revision": opened["revision"]}))
    assert cancelled["status"] == "NEEDS_REVISION"
    opened = data(command(learner, f"{path}/evidence-revision/start", {"expected_revision": cancelled["revision"]}))
    data(command(learner, f"{path}/submissions", {"expected_revision": opened["revision"], "body": body}))
    finalize_review(reviewer, nodes[7]["assignment_id"], "APPROVE")
    assert data(learner.get("/api/v1/me/current-action"))["journey"]["completed_stages"] == 8
    with SessionLocal() as session:
        assert session.scalar(select(func.count(Outcome.id)).where(Outcome.enrollment_id == enrollment_id)) == 1
