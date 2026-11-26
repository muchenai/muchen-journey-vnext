import pytest
from pydantic import ValidationError

from journey_api.novice_economy import rewards
from journey_api.review_admin_routes import TaskContent, task_content_for_publish


@pytest.mark.parametrize("xp,difficulty", [(0, "入门"), (50, "入门"), (73, "进阶"), (101, "挑战")])
def test_ordinary_task_uses_published_xp_and_can_omit_materials(xp, difficulty):
    task = TaskContent(title="自主实践任务", summary="按照说明独立操作并提交任务成果。", xp=xp,
                       rewardRulesVersion=4, difficulty="入门", publishingDepartment="公司通用常识",
                       badges=[{"id": "product", "weight": 100}])
    content = task.model_dump(mode="json")
    assert task.difficulty == difficulty
    assert task_content_for_publish(content)["learning_materials"] == []
    assert rewards(content)["xp"] == xp
    assert rewards(content)["totalPoints"] == xp // 10


def test_legacy_task_rewards_and_invalid_custom_values():
    assert rewards({"difficulty": "挑战"})["xp"] == 200
    assert rewards({"difficulty": "挑战", "rewardRulesVersion": 3})["xp"] == 150
    for invalid in [None, True, -1, 1.5, 1000001]:
        with pytest.raises(ValidationError):
            TaskContent(rewardRulesVersion=4, xp=invalid)
