"""Administrator scoring configuration and sandbox integration, without AI calls."""
import json
from types import SimpleNamespace

import pytest

from journey_api.ai_rubric_materials import canonicalize_ai_rubric
from journey_api.errors import ApiError
from journey_api.review_admin_routes import SandboxCommand, sandbox, task_content_for_publish
from test_ai_rubric_materials import attachment, content


def publishable(camp="exploration"):
    return {**content([attachment()]), "camp": camp, "completionMode": "assessment",
        "title": "发布人员评分配置测试", "summary": "阅读材料后完成作答，并按照本任务的评分标准进行评测。",
        "materials": [{"id": "learning", "name": "学习材料", "type": "link", "url": "https://example.com/read"}],
        "taskFiles": [{"id": "task", "name": "任务题目", "type": "link", "url": "https://example.com/task"}]}


def test_publishing_rejects_zero_dimension_even_when_other_dimension_totals_100():
    task = publishable()
    task["rubric"][0]["points"], task["rubric"][1]["points"] = 0, 100
    with pytest.raises(ApiError, match="大于 0"):
        task_content_for_publish(task)


def test_publishing_reads_the_document_and_rejects_empty_original_bytes():
    task = publishable()
    task["rubricAttachments"] = [attachment(b"   ")]
    task["rubricAttachments"][0]["text"] = "Do not trust this fake body"
    with pytest.raises(ApiError, match="没有可读取正文"):
        task_content_for_publish(task)


def test_server_canonical_snapshot_cannot_be_supplied_by_the_browser():
    from journey_api.review_admin_routes import TaskContent
    task = publishable()
    task["aiRubricSnapshot"] = {"fake": "client-supplied answer"}
    typed = TaskContent.model_validate(task).model_dump(mode="json")
    assert "aiRubricSnapshot" not in typed
    saved = canonicalize_ai_rubric(typed)
    assert saved["aiRubricSnapshot"]["reference_documents"][0]["body"] == "Reference answer: B"


def sandbox_harness(monkeypatch, response):
    import journey_api.review_admin_routes as routes
    import journey_api.ai_self_check_clients as clients
    import journey_api.config as config
    calls = []
    class Reviewer:
        last_model = "local-fake-model"
        def review(self, system, evidence):
            calls.append((system, evidence))
            return response
    monkeypatch.setattr(routes, "require_camp_publisher", lambda *args: None)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(ai_self_check_enabled=True, ai_model="configured"))
    monkeypatch.setattr(clients, "get_reviewer", lambda: Reviewer())
    request = SimpleNamespace(state=SimpleNamespace(request_id="sandbox-test"))
    return calls, request


def test_exploration_sandbox_uses_parsed_private_policy_and_validated_scores(monkeypatch):
    response = json.dumps({"task_match": {"status": "matched", "reason": "对应当前任务"},
        "summary": "答案符合大部分要求。", "dimensions": [
            {"id": "correctness", "score": 80, "evidence": "选择了 B。", "feedback": "判断正确。"},
            {"id": "reason", "score": 10, "evidence": "只给出简短解释。", "feedback": "需要补充依据。"}],
        "next_steps": ["补充判断的具体依据。"]})
    calls, request = sandbox_harness(monkeypatch, response)
    result = sandbox(SandboxCommand(task=publishable(), answer="我选择 B，并将进一步说明这个判断的依据。"),
        request, actor=object(), session=object())["data"]
    assert result["validated"] is True and result["score"] == 90 and result["passed"] is True
    assert result["model"] == "local-fake-model"
    evidence = calls[0][1]
    assert evidence["grading_policy"]["reference_documents"][0]["body"] == "Reference answer: B"
    serialized = json.dumps(evidence)
    assert "data:" not in serialized and "base64" not in serialized and "UNTRUSTED CLIENT" not in serialized
    assert evidence["grading_policy"]["dimensions"][0]["description"].startswith("标准答案为 B")
    assert not any(key in result for key in ("completedAt", "assignmentId", "status"))


def test_novice_sandbox_keeps_advisory_result_and_does_not_send_base64(monkeypatch):
    calls, request = sandbox_harness(monkeypatch, "已按配置的评分描述完成逐项建议，不改变学员状态。")
    task = publishable("novice")
    task.update(domain="产品开发", difficulty="入门", publishingDepartment="IT部",
        badges=[{"id": "product", "weight": 100}], taskFiles=[])
    result = sandbox(SandboxCommand(task=task, answer="我选择 B，并补充对这个判断的解释与依据。"),
        request, actor=object(), session=object())["data"]
    assert result["result"].startswith("已按配置")
    assert "score" not in result and "validated" not in result
    assert "data:" not in json.dumps(calls[0][1])


def test_exploration_publishing_accepts_answer_document_without_manual_dimensions_and_keeps_raw_rows_empty():
    task = publishable()
    task["rubric"] = []
    version = task_content_for_publish(task)
    saved = canonicalize_ai_rubric(task)
    assert version["title"] == task["title"]
    # TaskVersion's human review schema remains independent of private AI rows.
    assert version["rubric"]["dimensions"][0]["dimension_key"] == "task_completion"
    assert saved["rubric"] == task["rubric"] == []
    assert saved["aiRubricSnapshot"]["dimensions"][0]["id"] == "answer-document"
    assert "Reference answer" not in json.dumps(version)


@pytest.mark.parametrize("rubric,files", [
    ([], []), ([], [attachment(b"   ")]),
    ([{"id": "unfinished", "name": "正确性", "points": 100, "description": ""}], [attachment()]),
])
def test_exploration_publishing_does_not_bypass_missing_document_or_incomplete_explicit_dimensions(rubric, files):
    task = publishable()
    task.update(rubric=rubric, rubricAttachments=files)
    with pytest.raises(ApiError):
        task_content_for_publish(task)


def test_novice_publishing_still_requires_explicit_dimensions_with_answer_document():
    task = publishable("novice")
    task.update(domain="产品开发", difficulty="入门", publishingDepartment="IT部",
        badges=[{"id": "product", "weight": 100}], taskFiles=[], rubric=[])
    with pytest.raises(ApiError, match="评分维度"):
        task_content_for_publish(task)


@pytest.mark.parametrize("score,passed", [(59, False), (60, True)])
def test_document_only_sandbox_uses_effective_policy_and_publisher_threshold(monkeypatch, score, passed):
    response = json.dumps({"task_match": {"status": "matched", "reason": "作答对应当前任务"},
        "summary": "已逐题核对当前任务作答。", "dimensions": [
            {"id": "answer-document", "score": score, "evidence": "第一题选择了 B，第二题未说明判断依据。",
                "feedback": "第一题符合标准，第二题需要补充判断依据。"}],
        "next_steps": ["补充遗漏题目的判断依据。"]})
    calls, request = sandbox_harness(monkeypatch, response)
    task = publishable()
    task.update(rubric=[], passScore=60)
    result = sandbox(SandboxCommand(task=task, answer="我在第一题选择 B，第二题尚需补充完整判断依据。"),
        request, actor=object(), session=object())["data"]
    assert result["validated"] is True and result["score"] == score and result["passed"] is passed
    evidence = calls[0][1]
    assert evidence["grading_policy"]["dimensions"][0]["id"] == "answer-document"
    assert evidence["grading_policy"]["reference_documents"][0]["body"] == "Reference answer: B"
    assert "data:" not in json.dumps(evidence) and "UNTRUSTED" not in json.dumps(evidence)
    assert not any(key in result for key in ("completedAt", "assignmentId", "status"))


@pytest.mark.parametrize("status", ["mismatched", "uncertain"])
def test_document_only_sandbox_still_refuses_unmatched_answers(monkeypatch, status):
    response = json.dumps({"task_match": {"status": status, "reason": "作答题干并非本任务要求"},
        "summary": "", "dimensions": [], "next_steps": []})
    _, request = sandbox_harness(monkeypatch, response)
    task = publishable()
    task["rubric"] = []
    with pytest.raises(ApiError, match="不匹配或无法确认") as exc:
        sandbox(SandboxCommand(task=task, answer="这段作答内容属于另外一项任务，无法核对本题。"),
            request, actor=object(), session=object())
    assert exc.value.code == "AI_TASK_DOCUMENT_MISMATCH"
