"""Publisher policy is authoritative; model totals and completion flags are not."""
from copy import deepcopy
import json

import pytest

from journey_api.errors import ApiError
from journey_api.exploration_ai_grading import grade_feedback, rubric_fingerprint


def content():
    return dict(reviewMode="ai", passScore=60, rubric=[
        dict(id="facts", name="事实理解", points=60, description="依据发布人提供的公司事实核对；内部答案甲。"),
        dict(id="application", name="场景应用", points=40, description="要求结合指定业务场景并说明行动。")],
        rubricAttachments=[])


def reply(first=40, second=20):
    return dict(task_match=dict(status="matched", reason="题干和作答对象对应。"),
        summary="已按发布人的任务标准逐项核对。",
        dimensions=[dict(id="facts", score=first, evidence="学员列出了公司事实。", feedback="部分事实尚需补充。"),
            dict(id="application", score=second, evidence="学员提出了业务行动。", feedback="请说明行动的验证方式。")],
        next_steps=["结合任务要求补充具体事实与行动依据。"])


def grade(value, policy=None):
    return grade_feedback(json.dumps(value, ensure_ascii=False), policy or content())


def test_server_sums_publisher_dimensions_and_uses_exact_threshold():
    result = grade(reply())
    assert result["score"] == 60 and result["maxScore"] == 100 and result["passed"] is True
    assert [item["maxScore"] for item in result["dimensions"]] == [60, 40]
    assert result["validated"] is True and "通过分数：60" in result["feedback"]
    assert result["rubricHash"] == rubric_fingerprint(content())
    assert "内部答案甲" not in result["feedback"]
    assert grade(reply(39.99, 20))["passed"] is False
    assert grade(reply(60, 40))["score"] == 100


def test_model_dimension_order_is_canonicalized_to_publisher_order():
    value = reply()
    value["dimensions"].reverse()
    assert [row["id"] for row in grade(value)["dimensions"]] == ["facts", "application"]


@pytest.mark.parametrize("score", [-1, 61, True, None, "60", float("nan"), float("inf"), .001])
def test_invalid_dimension_score_is_never_accepted(score):
    with pytest.raises(ApiError) as exc:
        grade(reply(score, 20))
    assert exc.value.code == "AI_INVALID_GRADING"


@pytest.mark.parametrize("edit", [
    lambda value: value.update(score=100),
    lambda value: value.update(passed=True),
    lambda value: value.update(status="completed"),
    lambda value: value["dimensions"].pop(),
    lambda value: value["dimensions"].append(deepcopy(value["dimensions"][0])),
    lambda value: value["dimensions"][1].update(id="facts"),
    lambda value: value["dimensions"][0].update(id="invented"),
    lambda value: value["dimensions"][0].update(maxScore=100),
    lambda value: value["dimensions"][0].update(feedback=" "),
    lambda value: value["dimensions"][0].update(evidence=" "),
    lambda value: value.update(summary=" "),
    lambda value: value.update(next_steps=[]),
    lambda value: value.update(next_steps=[" "]),
    lambda value: value.update(task_match=dict(status="matched", reason=" ")),
    lambda value: value.update(task_match=dict(status="matched", reason="匹配", passed=True)),
])
def test_invented_or_incomplete_model_schema_is_rejected(edit):
    value = reply()
    edit(value)
    with pytest.raises(ApiError) as exc:
        grade(value)
    assert exc.value.code == "AI_INVALID_GRADING"


@pytest.mark.parametrize("status", ["mismatched", "uncertain"])
def test_task_mismatch_is_not_a_passing_grade(status):
    value = reply(60, 40)
    value["task_match"]["status"] = status
    with pytest.raises(ApiError) as exc:
        grade(value)
    assert exc.value.code == "AI_TASK_DOCUMENT_MISMATCH"


@pytest.mark.parametrize("raw", ["", "[]", "null", '{"broken":', "```json\n{}\n```"])
def test_non_json_object_or_invalid_json_is_rejected(raw):
    with pytest.raises(ApiError) as exc:
        grade_feedback(raw, content())
    assert exc.value.code == "AI_INVALID_GRADING"


def test_policy_fingerprint_is_sensitive_to_standards_and_passing_score():
    original = content()
    changed = deepcopy(original)
    changed["rubric"][0]["description"] += "新的标准答案。"
    assert rubric_fingerprint(original) != rubric_fingerprint(changed)
    changed = deepcopy(original)
    changed["passScore"] = 70
    assert rubric_fingerprint(original) != rubric_fingerprint(changed)
    assert rubric_fingerprint(original) == rubric_fingerprint(deepcopy(original))


def test_missing_publisher_standards_cannot_receive_normal_grade():
    policy = content()
    policy["rubric"] = []
    with pytest.raises(ApiError) as exc:
        grade(reply(), policy)
    assert exc.value.code == "AI_RUBRIC_INVALID"


def test_generated_instructions_follow_mode_without_overwriting_custom_requirements():
    from journey_api.exploration_service import AI_ASSESSMENT_REQUIREMENTS, requirements_for_save
    ai = dict(camp="exploration", completionMode="assessment", reviewMode="ai")
    saved = requirements_for_save(ai, {})
    assert saved == AI_ASSESSMENT_REQUIREMENTS
    manual = {**ai, "reviewMode": "manual"}
    restored = requirements_for_save(manual, {**ai, "requirements": saved})
    assert all("自动完成" not in item for item in restored)
    custom = ["发布人员自定义的业务要求。"]
    assert requirements_for_save({**ai, "requirements": custom}, {}) == custom
