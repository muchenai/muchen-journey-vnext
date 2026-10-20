import pytest

from journey_api.ai_task_alignment import QUESTION, ensure_task_questions
from journey_api.errors import ApiError


MODEL_STAGE = "ASM-002-MODEL-JUDGEMENT"
DATA_STAGE = "ASM-003-DATA-CONSTRUCTION"
MODEL_TEMPLATE = "测试说明：每题判断候选结论，并说明理由。\n" + "\n".join(
    f"第 {i} 题：模型判断案例{i}\n请比较案例{i}中两个模型对不同业务问题的回答是否满足全部要求。\n回答A\n示例\n回答B\n示例\n说明："
    for i in range(1, 11))
DATA_TEMPLATE = "测试说明：每题判断数据是否合格，并说明理由。\n" + "\n".join(
    f"题目 {i}：数据构造案例{i}\n材料描述\n案例{i}的原始图片描述了不同的店铺及编号，请核对图片信息和数据答案。\n解析："
    for i in range(1, 11))


def refs(body):
    return [{"label": "题目", "body": body}]


@pytest.mark.parametrize("stage,expected,wrong", [
    (MODEL_STAGE, MODEL_TEMPLATE, DATA_TEMPLATE),
    (DATA_STAGE, DATA_TEMPLATE, MODEL_TEMPLATE),
])
def test_swapped_assessment_bodies_are_rejected_even_with_correct_title(stage, expected, wrong):
    for body in [wrong, "测评三／数据构造\n" + wrong,
                 expected.splitlines()[0] + "\n" + wrong]:
        with pytest.raises(ApiError, match="题干") as exc:
            ensure_task_questions(stage, body, refs(expected))
        assert exc.value.code == "AI_TASK_DOCUMENT_MISMATCH"


@pytest.mark.parametrize("stage,template", [(MODEL_STAGE, MODEL_TEMPLATE), (DATA_STAGE, DATA_TEMPLATE)])
def test_matching_questions_allow_blank_incorrect_and_partial_answers(stage, template):
    ensure_task_questions(stage, template, refs(template))
    ensure_task_questions(stage, template.replace("说明：", "说明：完全错误的答案"), refs(template))
    ensure_task_questions(stage, template.replace(" ", "\t"), refs(template))
    # One actual question is enough for a partial answer; completeness is AI feedback.
    question_headers = list(QUESTION.finditer(template))
    ensure_task_questions(stage, template[:question_headers[1].start()], refs(template))


def test_mixed_task_cannot_pass_by_appending_one_matching_question():
    first_data_question = DATA_TEMPLATE.split("题目 2：")[0]
    with pytest.raises(ApiError):
        ensure_task_questions(DATA_STAGE, MODEL_TEMPLATE + first_data_question, refs(DATA_TEMPLATE))


def test_title_only_or_answer_only_is_unverifiable_not_an_automatic_match():
    for body in ["测评三", "是，否，是，否", "第一题：可以。第二题：可以。"]:
        with pytest.raises(ApiError):
            ensure_task_questions(DATA_STAGE, body, refs(DATA_TEMPLATE))


def test_unreadable_authoritative_template_does_not_silently_skip_check():
    with pytest.raises(ApiError) as exc:
        ensure_task_questions(DATA_STAGE, DATA_TEMPLATE, refs("题目加载不完整"))
    assert exc.value.code == "AI_TASK_REFERENCE_UNVERIFIABLE"
