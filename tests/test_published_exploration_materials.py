from copy import deepcopy
from types import SimpleNamespace

import pytest

from journey_api.learning_materials import LEGACY_STAGE_LINKS, task_learning_materials


@pytest.mark.parametrize("prefix,stage", list(zip(
    ("tre002", "tre003", "tre004", "asm001", "asm002", "asm003"), LEGACY_STAGE_LINKS,
)))
def test_verified_production_pair_opens_document_then_video_without_rewriting_source(prefix, stage):
    _, _, _, document, video = LEGACY_STAGE_LINKS[stage]
    source = [
        {"key": prefix + ("-video-note" if prefix == "tre002" else "-video"), "kind": "TEXT", "title": "视频", "body": "旧视频说明", "required": True},
        {"key": prefix + "-document", "kind": "HTTPS_LINK", "title": "文档", "url": document + "?from=from_copylink", "required": True},
    ]
    before = deepcopy(source)
    resolved = task_learning_materials(SimpleNamespace(learning_materials=source))
    assert [item["url"] for item in resolved] == [document, video]
    assert all(item["kind"] == "HTTPS_LINK" for item in resolved)
    assert resolved[0]["key"] == source[1]["key"]
    assert resolved[1]["key"] not in {item["key"] for item in source}
    assert source == before
    source[1]["url"] = "https://example.com/independently-published-material"
    assert task_learning_materials(SimpleNamespace(learning_materials=source)) == source


def test_changed_company_document_and_video_have_new_completion_keys():
    source = [
        {"key": "tre001-video", "title": "旧视频", "kind": "TEXT", "body": "说明", "required": True},
        {"key": "tre001-document", "title": "旧文档", "kind": "HTTPS_LINK", "url": "https://zx6w57w0j34.feishu.cn/docx/Av3pdq3lhoQlfbxcep1cG8gtn4e?from=from_copylink", "required": True},
    ]
    resolved = task_learning_materials(SimpleNamespace(learning_materials=source))
    assert resolved[0]["url"].endswith("/wiki/TUV1wbptdiXmapkfDsOcRrvknme")
    assert resolved[1]["url"].endswith("/file/PewIbRCP3oDKAIx7MS9cSqUMnod")
    assert not {item["key"] for item in source} & {item["key"] for item in resolved}


def test_day_one_keeps_letter_completion_and_links_company_document():
    source = [
        {"key": "day0-company-intro", "title": "公司介绍", "kind": "TEXT", "body": "公司介绍", "required": True},
        {"key": "day0-letter", "title": "一封信", "kind": "HTTPS_LINK", "url": "https://zx6w57w0j34.feishu.cn/wiki/MpxDwemUwiOY0fk9jM5cqRYRn3b?from=from_parent_docx", "required": True},
    ]
    resolved = task_learning_materials(SimpleNamespace(learning_materials=source))
    assert resolved[0] == source[1]
    assert resolved[1]["url"].endswith("/docx/B9f2d0P0ior6UBxTeFRc2ELmnlg")
    assert resolved[1]["key"] != source[0]["key"]


def test_owner_supplied_video_replaces_legacy_no_video_sentinel_before_filtering():
    source = [
        {"key": "tre002-video-note", "title": "视频材料说明", "kind": "TEXT", "body": "无，自行观看", "required": True},
        {"key": "tre002-document", "title": "AI 与数据基础", "kind": "HTTPS_LINK", "url": "https://zx6w57w0j34.feishu.cn/docx/EDm2dFzmco58SJx10Xeceo0WnIc", "required": True},
    ]
    resolved = task_learning_materials(SimpleNamespace(learning_materials=source))
    assert len(resolved) == 2
    assert resolved[1]["url"] == "https://zx6w57w0j34.feishu.cn/docx/B9uhdkLwUoqqIYxeh9TcWErbnHd?from=from_parent_sheet"


def test_newly_published_video_url_is_authoritative():
    source = [
        {"key": "tre001-video", "title": "新视频", "kind": "HTTPS_LINK", "url": "https://example.com/video", "required": True},
        {"key": "tre001-document", "title": "文档", "kind": "HTTPS_LINK", "url": "https://zx6w57w0j34.feishu.cn/docx/Av3pdq3lhoQlfbxcep1cG8gtn4e", "required": True},
    ]
    assert task_learning_materials(SimpleNamespace(learning_materials=source)) == source
