from journey_api.review_routes import effective_review_rubric


def test_learning_stage_restores_one_detailed_feedback_dimension():
    rubric = effective_review_rubric(
        "TRE-002-AI-DATA-BASICS",
        {"version": 1, "dimensions": []},
        ["指出具体错误来源", "连接人工反馈与数据质量"],
    )

    assert len(rubric["dimensions"]) == 1
    dimension = rubric["dimensions"][0]
    assert dimension["dimension_key"] == "task_completion"
    assert dimension["title"] == "本任务具体反馈"
    assert "指出具体错误来源" in dimension["evidence_expected"]
    assert dimension["required"] is True


def test_assessment_rubric_is_projected_to_one_detailed_feedback_dimension():
    original = {
        "version": 1,
        "dimensions": [{"dimension_key": "evidence", "required": True}],
    }
    rubric = effective_review_rubric(
        "ASM-001-RULE-BREAKDOWN",
        original,
        ["目标准确", "维度可执行"],
    )
    assert [item["dimension_key"] for item in rubric["dimensions"]] == [
        "task_completion"
    ]


def test_non_journey_rubric_is_preserved():
    original = {
        "version": 1,
        "dimensions": [{"dimension_key": "evidence", "required": True}],
    }
    assert effective_review_rubric("TSK-001", original, []) is original
