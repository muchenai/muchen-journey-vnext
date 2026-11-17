import pytest
from pydantic import ValidationError

from journey_api.review_admin_routes import Material, TaskContent


@pytest.fixture(params=[
    {"type": "link", "url": "https://example.com/material"},
    {"type": "file", "url": "data:text/plain;base64,YQ==", "mime": "text/plain", "size": 1},
    {"type": "image", "url": "data:image/png;base64,YQ==", "mime": "image/png", "size": 1},
    {"type": "text", "text": "保留材料正文与原有内容。"},
])
def material_data(request):
    return {"id": "existing-material", "name": "学习 材料", **request.param}


@pytest.mark.parametrize("name", ["", "   ", " \t\r\n ", "\u3000\u00a0"])
def test_material_rejects_empty_and_whitespace_names(material_data, name):
    with pytest.raises(ValidationError) as error:
        Material.model_validate({**material_data, "name": name})
    assert error.value.errors()[0]["loc"] == ("name",)


def test_material_trims_name_without_changing_internal_spaces_or_content(material_data):
    name = "学习  材料 第 1 版"
    value = Material.model_validate({**material_data, "name": " \t" + name + "\u3000\n"})
    assert value.name == name
    for key, original in material_data.items():
        if key != "name":
            assert getattr(value, key) == original


@pytest.mark.parametrize("field", ["materials", "rubricAttachments"])
def test_task_content_rejects_whitespace_material_names(field):
    with pytest.raises(ValidationError) as error:
        TaskContent.model_validate({field: [{
            "id": "old-material", "name": " \t ", "type": "link",
            "url": "https://example.com/material",
        }]})
    assert error.value.errors()[0]["loc"] == (field, 0, "name")
