"""Real isolated-DB orchestration, with no paid model or external Feishu writes."""
import base64
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import select

from journey_api.ai_self_check_clients import Document, document_ref
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.exploration_models import ExplorationSelfCheck
from journey_api.models import AISelfCheck, Assignment, AssignmentStatus, RoleAssignment, Role
from test_dynamic_exploration import command, exploration, publish, read, post
from test_wp09_feishu_identity import assert_ok

ANSWER = "https://answers.feishu.cn/docx/LearnerAnswerDocument1234"
REFERENCE = "https://materials.feishu.cn/docx/CourseReferenceDocument1234"


@pytest.mark.parametrize("answer", ["链接：" + ANSWER + "，补充说明我的实践案例。", "答题文档（" + ANSWER + "）。",
    "[我的答题文档](" + ANSWER + ")，这是补充说明。"])
def test_mixed_input_extracts_answer_link_from_chinese_and_markdown_text(answer):
    from journey_api.exploration_ai_self_check import input_document
    assert input_document(answer) == ANSWER


class Documents:
    def __init__(self):
        self.body, self.revision = "这是实际飞书正文，针对当前任务写出了公司学习内容和具体分析。" * 10, "1"
        self.reads, self.comments, self.updates, self.mentions = [], [], [], []
        self.owner = {"id": "verified-current-human-owner", "name": "文档所有者"}
        self.read_error = self.owner_error = self.comment_error = None
        self.before_comment = None
        self.owner_checks = self.revision_checks = 0

    def resolve(self, url):
        kind, token = document_ref(url)
        return "CourseReferenceDocument1234" if token == "ReferenceAlias1234" else token

    def resolve_reference(self, url):
        return "docx", self.resolve(url)

    def read(self, token):
        self.reads.append(token)
        if self.read_error:
            raise self.read_error
        return Document(token, "actual-title-block", "真实答题文档标题", self.body, self.revision)

    def read_reference(self, kind, token):
        self.reads.append(token)
        return Document(token, "reference-title", "任务参考材料", "当前课程需要核对的真实参考资料。", "4")

    def human_owner(self, document):
        if self.owner_error:
            raise self.owner_error
        return self.owner

    def ensure_owner(self, document, owner):
        assert owner is self.owner
        self.owner_checks += 1

    def ensure_revision(self, document):
        assert document.revision == self.revision
        self.revision_checks += 1

    def comment_on_title(self, document, feedback, recipients):
        assert recipients == (self.owner,)
        self.comments.append((document.title_block_id, feedback))
        self.mentions.append(recipients)
        if self.before_comment:
            self.before_comment()
        if self.comment_error:
            raise self.comment_error
        return "one-title-comment"

    def original_reply(self, document, comment_id, previous_text):
        assert comment_id == "one-title-comment" and "探索营 AI 任务评测" in previous_text
        return "original-root-reply"

    def update_title_comment(self, document, comment_id, reply_id, feedback, recipients):
        assert comment_id == "one-title-comment" and reply_id == "original-root-reply"
        assert recipients == (self.owner,)
        self.updates.append((comment_id, reply_id, feedback))
        if self.comment_error:
            raise self.comment_error
        return comment_id


class Reviewer:
    def __init__(self):
        self.calls = []
        self.error = None
        self.score_factor = .4
        self.on_review = None
        self.started, self.resume = Event(), Event()
        self.pause = False

    def review(self, system, evidence):
        self.calls.append(evidence)
        self.started.set()
        if self.pause:
            assert self.resume.wait(timeout=15)
        if self.on_review:
            self.on_review()
        if self.error:
            raise self.error
        return json.dumps({"task_match": {"status": "matched", "reason": "正文与本课程任务对应。"},
            "summary": f"第{len(self.calls)}次：已结合材料完成任务分析。", "dimensions": [
                {"id": item["id"], "score": round(item["points"] * self.score_factor, 2),
                 "evidence": "结合公司学习内容进行了分析。", "feedback": "补充具体实践例子。"}
                for item in evidence["grading_policy"]["dimensions"]],
            "next_steps": ["结合案例完善学习收获。"]}, ensure_ascii=False)


@pytest.fixture
def ai(monkeypatch):
    documents, reviewer = Documents(), Reviewer()
    settings = get_settings().model_copy(update={"ai_self_check_enabled": True})
    monkeypatch.setattr("journey_api.exploration_ai_self_check.get_settings", lambda: settings)
    monkeypatch.setattr("journey_api.ai_self_check_clients.get_documents", lambda: documents)
    monkeypatch.setattr("journey_api.ai_self_check_clients.get_reviewer", lambda: reviewer)
    return documents, reviewer


def claimed(exploration, **content):
    _, learner, _ = exploration
    content = {"reviewMode": "ai", "rubric": [dict(id="analysis", name="材料关联",
        points=100, description="根据任务题目，核对学员是否结合材料进行分析并补充实践例子。")], **content}
    task_id, _, _ = publish(exploration, "assessment", **content)
    return learner, assert_ok(command(learner, read(learner, task_id), "claim"))


def check(learner, task, answer, key=None):
    return post(learner, "me/exploration", dict(command="selfCheck", taskId=task["id"],
        versionId=task["versionId"], revision=task["revision"], answer=answer), key)


def history(learner, task):
    return assert_ok(learner[0].get("/api/v1/me/exploration", params={"command": "selfCheckHistory", "taskId": task["id"]}))["items"]


def test_text_uses_model_and_replay_never_generates_twice(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    answer, key = "我已阅读材料，并记录了具体学习收获和改进方向。", str(uuid.uuid4())
    first = assert_ok(check(learner, task, answer, key))["record"]
    again = assert_ok(check(learner, task, answer, key))["record"]
    assert again == first and len(reviewer.calls) == 1
    assert first["inputKind"] == "text" and first["commentStatus"] == "NOT_REQUIRED"
    assert first["status"] == "COMPLETED" and "任务评测" in first["result"]
    assert reviewer.calls[0]["answer"] == answer and documents.comments == []
    changed = check(learner, task, answer + "其他内容", key)
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(history(learner, task)) == 1


def test_publisher_standards_are_private_and_real_scoring_document_bytes_reach_model(exploration, ai):
    _, reviewer = ai
    standard = "发布人私有标准答案：应列举两项指定福利并说明申请条件。"
    file_bytes = standard.encode()
    learner, task = claimed(exploration, rubric=[dict(id="benefits", name="福利理解", points=100,
        description=standard)], rubricAttachments=[dict(id="standard", name="评分答案.txt",
        type="file", mime="text/plain", size=len(file_bytes),
        url="data:text/plain;base64," + base64.b64encode(file_bytes).decode(),
        text="客户端伪造内容不可作依据")])
    visible = json.dumps(task, ensure_ascii=False)
    assert standard not in visible and "客户端伪造" not in visible and "data:text" not in visible
    result = assert_ok(check(learner, task, "已按任务材料列出福利、申请条件和实践中的使用步骤。"))["record"]
    policy = reviewer.calls[0]["grading_policy"]
    assert policy["dimensions"][0]["description"] == standard
    assert policy["reference_documents"][0]["body"] == standard
    assert "data:text" not in json.dumps(reviewer.calls[0])
    assert result["score"] == 40 and result["passed"] is False and result["taskCompleted"] is False
    assert any("自动完成" in item for item in task["requirements"])


def test_custom_publisher_instructions_remain_unchanged(exploration, ai):
    learner, task = claimed(exploration, requirements=["回答发布人员指定的两个业务问题，并说明证据。"])
    assert read(learner, task["id"])["requirements"] == ["回答发布人员指定的两个业务问题，并说明证据。"]


def test_manual_task_never_calls_ai(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration, reviewMode="manual", rubric=[])
    response = check(learner, task, "当前任务应由人工审核，不允许走 AI 完成。")
    assert response.status_code == 409 and response.json()["error"]["code"] == "AI_NOT_CONFIGURED"
    assert not reviewer.calls and not documents.comments and not history(learner, task)


def test_incomplete_historic_standards_fail_before_model_or_comment(exploration, ai, monkeypatch):
    from journey_api import exploration_ai_self_check
    documents, reviewer = ai
    learner, task = claimed(exploration)
    evaluate = exploration_ai_self_check.evaluate
    def historic_content(session, actor, body, assignment, version, content, key):
        # Old snapshots predate strict publishing validation. Simulate that
        # boundary without weakening the database's immutable-content trigger.
        return evaluate(session, actor, body, assignment, version, {**content, "rubric": []}, key)
    monkeypatch.setattr(exploration_ai_self_check, "evaluate", historic_content)
    response = check(learner, task, ANSWER)
    assert response.status_code == 422 and response.json()["error"]["code"] == "AI_RUBRIC_INVALID"
    assert not reviewer.calls and not documents.comments and not history(learner, task)


def test_passing_text_completes_unlocks_and_replays_through_http(exploration, ai):
    from sqlalchemy import func
    from journey_api.models import Review, Submission, SubmissionVersion
    _, reviewer = ai
    learner, task = claimed(exploration, order=1)
    next_id, _, _ = publish(exploration, "learning", order=2)
    assert learner[0].get("/api/v1/me/exploration", params={"command": "learnerTask", "taskId": next_id}).status_code == 409
    reviewer.score_factor = .8
    answer, key = "我按本课程要求阅读材料，分析公司事实，给出了具体实践步骤和验证方法。", str(uuid.uuid4())
    first = assert_ok(check(learner, task, answer, key))
    assert first["record"]["score"] == 80 and first["record"]["passed"] is True
    assert first["record"]["taskCompleted"] is True and first["task"]["status"] == "completed"
    assert first["task"]["feedback"]["source"] == "AI"
    assert read(learner, next_id)["status"] == "active"
    replayed = assert_ok(check(learner, task, answer, key))
    assert replayed["record"] == first["record"] and len(reviewer.calls) == 1
    with SessionLocal() as session:
        assignment_id = uuid.UUID(task["assignmentId"])
        submission = session.scalar(select(Submission).where(Submission.assignment_id == assignment_id))
        assert session.scalar(select(func.count()).select_from(SubmissionVersion).where(
            SubmissionVersion.submission_id == submission.id)) == 1
        assert session.scalar(select(func.count()).select_from(Review).where(Review.assignment_id == assignment_id)) == 0


@pytest.mark.parametrize("uncertain", [False, True])
def test_passing_document_completes_without_misreporting_comment_delivery(exploration, ai, uncertain):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    reviewer.score_factor = .8
    if uncertain:
        documents.comment_error = ApiError(502, "FEISHU_REQUEST_FAILED", "评论请求超时，结果未知。")
    key = str(uuid.uuid4())
    result = assert_ok(check(learner, task, ANSWER, key))
    assert result["record"]["taskCompleted"] is True and result["task"]["status"] == "completed"
    assert result["record"]["commentStatus"] == ("UNCERTAIN" if uncertain else "SENT")
    assert result["task"]["answer"] == ANSWER
    assert assert_ok(check(learner, task, ANSWER, key))["record"] == result["record"]
    assert len(reviewer.calls) == len(documents.comments) == 1


def test_mixed_document_reads_real_answer_references_and_mentions_verified_owner(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration, materials=[dict(id="reference", name="参考资料", type="link", url=REFERENCE)])
    answer, key = "补充说明：请关注我的实践案例。\n" + ANSWER, str(uuid.uuid4())
    first = assert_ok(check(learner, task, answer, key))["record"]
    assert first["inputKind"] == "document" and first["documentUrl"] == ANSWER
    assert first["status"] == "COMPLETED" and first["commentStatus"] == "SENT"
    assert first["commentId"] == "one-title-comment" and first["body"] == answer
    evidence = reviewer.calls[0]
    assert evidence["answer"] == documents.body and evidence["learner_document"]["body"] == documents.body
    assert evidence["supplemental_text"] == answer
    assert evidence["reference_documents"][0]["body"] == "当前课程需要核对的真实参考资料。"
    assert documents.comments[0][0] == "actual-title-block" and documents.mentions == [(documents.owner,)]
    assert documents.owner_checks == documents.revision_checks == 1
    assert assert_ok(check(learner, task, answer, key))["record"] == first
    assert len(reviewer.calls) == len(documents.comments) == 1


def test_text_also_reads_configured_feishu_task_questions(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration, assessmentUrl=REFERENCE)
    result = assert_ok(check(learner, task, "我已结合题干，说明当前公司的课程要求和我的具体答案。"))["record"]
    assert result["status"] == "COMPLETED" and result["commentStatus"] == "NOT_REQUIRED"
    assert reviewer.calls[0]["reference_documents"][0]["body"] == "当前课程需要核对的真实参考资料。"
    assert documents.reads == ["CourseReferenceDocument1234"] and not documents.comments


def test_changed_document_recheck_updates_original_and_keeps_each_input_result(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    first = assert_ok(check(learner, task, ANSWER))["record"]
    documents.body, documents.revision = "这是改进后的新正文和新增的实践例子。" * 20, "2"
    mixed = "已按上次评价修改。\n" + ANSWER
    second = assert_ok(check(learner, task, mixed))["record"]
    assert second["id"] != first["id"] and second["commentId"] == first["commentId"]
    assert len(documents.comments) == len(documents.updates) == 1 and len(reviewer.calls) == 2
    entries = history(learner, task)
    assert [(entry["body"], entry["result"]) for entry in entries] == [(mixed, second["result"]), (ANSWER, first["result"])]
    with SessionLocal() as session:
        source = session.scalar(select(AISelfCheck).where(AISelfCheck.assignment_id == uuid.UUID(task["assignmentId"])))
        assert source.document_revision == "2" and len(source.archived_results) == 1
        assert source.archived_results[0]["result"] == first["result"]


@pytest.mark.parametrize("failure", ["read", "owner", "model"])
def test_permission_or_model_failure_is_explicit_and_does_not_comment(exploration, ai, failure):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    error = ApiError(502, "FEISHU_DOCUMENT_ACCESS" if failure != "model" else "AI_REQUEST_FAILED",
        "没有读取文档或核验所有者的权限。" if failure != "model" else "模型服务暂时不可用。")
    if failure == "read":
        documents.read_error = error
    elif failure == "owner":
        documents.owner_error = error
    else:
        reviewer.error = error
    result = assert_ok(check(learner, task, ANSWER))["record"]
    assert result["status"] == "FAILED" and result["commentStatus"] == "FAILED"
    assert error.message in result["errorMessage"] and error.message in result["result"]
    assert not documents.comments and not documents.updates
    assert len(reviewer.calls) == (1 if failure == "model" else 0)
    assert read(learner, task["id"])["status"] == "active"


@pytest.mark.parametrize("outcome", ["recovers", "exhausted", "owner_changed"])
def test_owner_query_timeout_after_scoring_preserves_comment_and_completion_contract(
        exploration, ai, monkeypatch, outcome):
    import io
    from journey_api import ai_self_check_clients as clients

    documents, reviewer = ai
    learner, task = claimed(exploration)
    reviewer.score_factor = .8
    documents.owner = clients.HumanRecipient("ou_VerifiedCurrentDocumentOwner1234")
    feishu = clients.FeishuDocuments(get_settings())
    feishu._token = "isolated-test-token"
    monkeypatch.setattr(documents, "ensure_owner", feishu.ensure_owner)
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append((request.get_method(), timeout))
            assert request.full_url == (
                "https://open.feishu.cn/open-apis/drive/v1/metas/batch_query?user_id_type=open_id")
            assert json.loads(request.data) == {"request_docs": [
                {"doc_token": "LearnerAnswerDocument1234", "doc_type": "docx"}]}
            if len(requests) == 1 or outcome == "exhausted":
                raise TimeoutError("isolated owner metadata timeout")
            owner_id = ("ou_ChangedDocumentOwner1234" if outcome == "owner_changed"
                else documents.owner.open_id)
            return io.BytesIO(json.dumps({"code": 0, "data": {"metas": [
                {"doc_token": "LearnerAnswerDocument1234", "doc_type": "docx",
                 "owner_id": owner_id}]}}).encode())

    monkeypatch.setattr(clients, "build_opener", lambda *args: Opener())
    result = assert_ok(check(learner, task, ANSWER))
    record = result["record"]
    assert requests == [("POST", 60), ("POST", 60)]
    assert len(reviewer.calls) == 1
    assert record["status"] == "COMPLETED" and record["score"] == 80 and record["passed"] is True
    assert len(history(learner, task)) == 1
    if outcome == "recovers":
        assert record["commentStatus"] == "SENT" and record["taskCompleted"] is True
        assert len(documents.comments) == 1 and not documents.updates
        assert documents.mentions == [(documents.owner,)]
        assert read(learner, task["id"])["status"] == "completed"
    else:
        assert record["commentStatus"] == "FAILED" and record["taskCompleted"] is False
        assert not documents.comments and not documents.updates
        assert read(learner, task["id"])["status"] == "active"
        assert ("变更" if outcome == "owner_changed" else "飞书接口") in record["errorMessage"]


@pytest.mark.parametrize("uncertain", [False, True])
def test_comment_failure_keeps_feedback_and_ambiguous_dispatch_is_never_repeated(exploration, ai, uncertain):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    documents.comment_error = ApiError(502, "FEISHU_REQUEST_FAILED" if uncertain else "FEISHU_DOCUMENT_ACCESS",
        "飞书请求超时，结果未知。" if uncertain else "飞书明确拒绝评论权限。")
    key = str(uuid.uuid4())
    first = assert_ok(check(learner, task, ANSWER, key))["record"]
    assert first["status"] == "COMPLETED" and "任务评测" in first["result"]
    assert first["commentStatus"] == ("UNCERTAIN" if uncertain else "FAILED")
    assert assert_ok(check(learner, task, ANSWER, key))["record"] == first
    assert len(documents.comments) == len(reviewer.calls) == 1
    documents.comment_error = None
    again = assert_ok(check(learner, task, "再次自测\n" + ANSWER))["record"]
    if uncertain:
        assert again["id"] == first["id"] and again["commentStatus"] == "UNCERTAIN"
        assert len(reviewer.calls) == len(documents.comments) == 1
        assert len(history(learner, task)) == 1
    else:
        assert again["id"] != first["id"] and again["commentStatus"] == "SENT"
        assert len(reviewer.calls) == len(documents.comments) == 2
        assert len(history(learner, task)) == 2


def test_comment_dispatch_has_durable_feedback_and_no_assignment_lock(exploration, ai):
    documents, _ = ai
    learner, task = claimed(exploration)
    def inspect():
        with SessionLocal.begin() as session:
            assignment_id = uuid.UUID(task["assignmentId"])
            assert session.scalar(select(Assignment.id).where(Assignment.id == assignment_id).with_for_update(nowait=True))
            source = session.scalar(select(AISelfCheck).where(AISelfCheck.assignment_id == assignment_id))
            check_row = session.get(ExplorationSelfCheck, source.attempt_id)
            assert source.status == "SENDING" and "任务评测" in source.result
            assert check_row.status == "COMPLETED" and check_row.result == source.result
    documents.before_comment = inspect
    assert assert_ok(check(learner, task, ANSWER))["record"]["commentStatus"] == "SENT"


@pytest.mark.parametrize("change", ["cancel", "version", "role"])
def test_permission_state_or_version_change_during_model_blocks_comment(exploration, ai, change):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    def modify():
        with SessionLocal.begin() as session:
            assignment = session.get(Assignment, uuid.UUID(task["assignmentId"]))
            if change == "cancel":
                assignment.status = AssignmentStatus.CANCELLED
            elif change == "version":
                from journey_api.models import TaskVersion
                from journey_api.review_admin_models import PublishedTaskContent
                previous = session.get(TaskVersion, assignment.task_version_id)
                values = {column.name: getattr(previous, column.name) for column in TaskVersion.__table__.columns}
                values.update(id=uuid.uuid4(), version=previous.version + 1)
                another = TaskVersion(**values)
                session.add(another)
                session.flush()
                session.add(PublishedTaskContent(task_version_id=another.id, organization_id=assignment.organization_id,
                    content=session.get(PublishedTaskContent, previous.id).content))
                assignment.task_version_id = another.id
            else:
                check_row = session.scalar(select(ExplorationSelfCheck).where(ExplorationSelfCheck.assignment_id == assignment.id))
                row = session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == check_row.user_id,
                    RoleAssignment.organization_id == check_row.organization_id, RoleAssignment.role == Role.LEARNER))
                assert row
                session.delete(row)
    reviewer.on_review = modify
    response = check(learner, task, ANSWER)
    if change == "role":
        # The in-flight authenticated request retains its actor, but delivery
        # rechecks the role rather than trusting that old request identity.
        assert response.status_code == 200, response.text
    result = assert_ok(response)["record"]
    assert result["status"] == "COMPLETED" and "任务评测" in result["result"]
    assert result["commentStatus"] == "FAILED" and "变化" in result["errorMessage"]
    assert documents.comments == []


@pytest.mark.parametrize("document", [False, True])
def test_concurrent_same_request_calls_model_once_and_returns_saved_attempt(exploration, ai, document):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    reviewer.pause = True
    answer, key = (ANSWER if document else "这里是我的学习总结和任务分析。"), str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(check, learner, task, answer, key)
        assert reviewer.started.wait(timeout=10)
        try:
            duplicate = assert_ok(pool.submit(check, learner, task, answer, key).result(timeout=10))["record"]
            assert duplicate["status"] == "RUNNING"
        finally:
            reviewer.resume.set()
        result = assert_ok(running.result(timeout=20))["record"]
    assert result["id"] == duplicate["id"] and result["status"] == "COMPLETED"
    assert len(reviewer.calls) == 1 and len(documents.comments) == int(document)
    assert assert_ok(check(learner, task, answer, key))["record"] == result


def test_reference_or_resolved_wiki_alias_cannot_receive_answer_comments(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration, taskFiles=[dict(id="ref", name="题目文件", type="link", url=REFERENCE)])
    for answer in [REFERENCE, "https://answers.feishu.cn/wiki/ReferenceAlias1234"]:
        result = assert_ok(check(learner, task, answer))["record"]
        assert result["status"] == "FAILED" and "参考材料" in result["errorMessage"]
    assert not reviewer.calls and not documents.comments


def test_distinct_keys_while_document_running_join_original_attempt(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    reviewer.pause = True
    reviewer.score_factor = .8
    second_key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(check, learner, task, ANSWER)
        assert reviewer.started.wait(timeout=10)
        try:
            joined = assert_ok(check(learner, task, "另一条补充说明\n" + ANSWER, second_key))["record"]
            assert joined["status"] == "RUNNING"
        finally:
            reviewer.resume.set()
        completed = assert_ok(running.result(timeout=20))
        result = completed["record"]
    assert result["id"] == joined["id"]
    assert result["score"] == 80 and result["passed"] is True and result["taskCompleted"] is True
    assert completed["task"]["status"] == "completed"
    assert assert_ok(check(learner, task, "另一条补充说明\n" + ANSWER, second_key))["record"] == result
    assert len(reviewer.calls) == len(documents.comments) == len(history(learner, task)) == 1


def test_failed_previous_comment_anchor_is_not_current_generated_feedback(exploration, ai):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    first = assert_ok(check(learner, task, ANSWER))["record"]
    with SessionLocal.begin() as session:
        source = session.scalar(select(AISelfCheck).where(AISelfCheck.assignment_id == uuid.UUID(task["assignmentId"])))
        # Legacy failed records can retain the previous reply text solely to
        # identify the root comment; it is not feedback for a new attempt.
        source.status, source.comment_reply_id = "FAILED", None
    documents.read_error = ApiError(502, "FEISHU_DOCUMENT_ACCESS", "本次无法读取文档。")
    again = assert_ok(check(learner, task, ANSWER))["record"]
    assert again["status"] == "FAILED" and "本次无法读取文档" in again["result"]
    assert first["result"] != again["result"] and len(reviewer.calls) == 1


@pytest.mark.parametrize("method,stage,label", [
    ("read", "read_document", "答题文档"),
    ("read_reference", "read_references", "参考材料"),
    ("human_owner", "verify_owner", "所有者"),
    ("original_reply", "resolve_original_comment", "原有标题评论"),
])
@pytest.mark.parametrize("unexpected", [False, True])
def test_read_failures_identify_phase_without_exposing_private_exception(
        exploration, ai, monkeypatch, caplog, method, stage, label, unexpected):
    documents, reviewer = ai
    learner, task = claimed(exploration,
        taskFiles=[dict(id="reference", name="课程题目", type="link", url=REFERENCE)])
    if method == "original_reply":
        assert assert_ok(check(learner, task, ANSWER))["record"]["status"] == "COMPLETED"
        with SessionLocal.begin() as session:
            source = session.scalar(select(AISelfCheck).where(
                AISelfCheck.assignment_id == uuid.UUID(task["assignmentId"])))
            source.status, source.comment_reply_id = "FAILED", None
    calls_before = len(reviewer.calls), len(documents.comments), len(documents.updates)
    caplog.clear()
    secret = "private-provider-body-credential-not-for-logs"

    def fail_read(*args):
        error = (RuntimeError(secret) if unexpected else
            ApiError(502, "FEISHU_REQUEST_FAILED", secret, retryable=True))
        raise error from TimeoutError(secret)

    monkeypatch.setattr(documents, method, fail_read)
    record = assert_ok(check(learner, task, ANSWER))["record"]
    assert record["status"] == "FAILED" and record["commentStatus"] == "FAILED"
    if not unexpected:
        assert label in record["errorMessage"] and "尚未进行 AI 评分" in record["errorMessage"]
    assert calls_before == (len(reviewer.calls), len(documents.comments), len(documents.updates))
    assert read(learner, task["id"])["status"] == "active"
    events = [json.loads(item.message) for item in caplog.records
        if item.name == "journey_api.exploration_ai_self_check"]
    assert len(events) == 1 and events[0]["event"] == "exploration.self_check_failed"
    assert events[0]["record_id"] == record["id"] and events[0]["stage"] == stage
    assert events[0]["error_type"] == ("RuntimeError" if unexpected else "ApiError")
    assert events[0]["cause_type"] == "TimeoutError" and events[0]["frames"]
    assert secret not in caplog.text and secret not in json.dumps(record)
    assert ANSWER not in json.dumps(events)


@pytest.mark.parametrize("document", [False, True])
def test_abandoned_running_attempt_expires_without_resending_same_key(exploration, ai, document):
    documents, reviewer = ai
    learner, task = claimed(exploration)
    answer, key = (ANSWER if document else "这里是学习记录。"), str(uuid.uuid4())
    result = assert_ok(check(learner, task, answer, key))["record"]
    with SessionLocal.begin() as session:
        row = session.get(ExplorationSelfCheck, uuid.UUID(result["id"]))
        row.status, row.result, row.created_at = "RUNNING", "", datetime.now(UTC) - timedelta(minutes=11)
        row.details = {**row.details, "analysisCompleted": False,
            "commentStatus": "PENDING" if document else "NOT_REQUIRED"}
        if document:
            source = session.get(AISelfCheck, uuid.UUID(row.details["aiSelfCheckId"]))
            source.status, source.result, source.comment_id = "RUNNING", "", None
            source.updated_at = datetime.now(UTC) - timedelta(minutes=11)
    expired = assert_ok(check(learner, task, answer, key))["record"]
    assert expired["status"] == "FAILED" and "超时" in expired["errorMessage"]
    assert len(reviewer.calls) == 1 and len(documents.comments) == int(document)
    retried = assert_ok(check(learner, task, answer))["record"]
    assert retried["status"] == "COMPLETED" and retried["id"] != expired["id"]
    assert len(reviewer.calls) == 2
