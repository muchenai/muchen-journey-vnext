from journey_api.formal_journey_catalog import (
    FORMAL_STAGE_CATALOG,
    formal_stage_materials,
    task_version_values,
)
from journey_api.learning_materials import task_learning_materials


def test_every_formal_stage_publishes_two_real_learning_materials():
    for stage in FORMAL_STAGE_CATALOG:
        materials = formal_stage_materials(stage.stable_key)
        assert len(materials) == 2
        assert len({item["key"] for item in materials}) == 2
        assert all(item["url"].startswith("https://") for item in materials)
        assert all("example.feishu.cn" not in item["url"] for item in materials)
        assert task_version_values(stage)["learning_materials"] == materials


def test_empty_legacy_catalog_version_resolves_current_formal_materials():
    class EmptyTask:
        learning_materials = []

    materials = task_learning_materials(EmptyTask(), "DAY-0")
    assert [item["title"] for item in materials] == [
        "给 Muchener 的一封信",
        "公司基础介绍材料",
    ]
