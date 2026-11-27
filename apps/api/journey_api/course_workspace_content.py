"""Validate publisher input and resolve private asset URLs according to the viewer."""

import hashlib
import json
import math
import re
import uuid
from copy import deepcopy
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from journey_api.academy_routes import fail, now
from journey_api.ai_rubric_materials import MAX_RUBRIC_FILE_BYTES, _plain_text, _docx_text


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        fail("编号无效。")


def text(value, limit, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        fail("请补全课程字段，并检查文字长度。")
    return value.strip()


def integer(value, low=0, high=1_000_000):
    if type(value) is not int or not low <= value <= high:
        fail("数量、经验或时长超出可用范围。")
    return value


def obj(value):
    if not isinstance(value, dict):
        fail("课程字段格式无效。")
    return value


def items(value, limit):
    if not isinstance(value, list) or len(value) > limit:
        fail("列表数量无效。")
    return value


def key(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value)
        or value in ("__proto__", "constructor", "prototype", "toString", "hasOwnProperty")
    ):
        fail("章节或材料编号无效。")
    return value


def safe_url(value):
    value = text(value, 4000, True)
    try:
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or re.search(r"[\s\\\x00-\x1f\x7f]", value)
        ):
            raise ValueError()
        url.port
    except ValueError:
        fail("请填写不含账号或密码的 HTTP 或 HTTPS 链接。")
    return value


def asset_ids(course):
    if not course:
        return set()
    return {m["assetId"] for m in [*course["materials"], course.get("cover") or {}] if m.get("assetId")}


def canonical_material(raw, asset_for):
    raw = obj(raw)
    result = {
        "id": key(raw.get("id")),
        "title": text(raw.get("title") or raw.get("name"), 240, True),
        "taskTitle": text(raw.get("taskTitle"), 150),
    }
    if raw.get("assetId"):
        row = asset_for(raw["assetId"])
        kind = (
            "video"
            if row.mime.startswith("video/")
            else "image" if row.mime.startswith("image/") else "document"
        )
        result.update(assetId=str(row.id), name=row.name, size=row.size, mime=row.mime)
    else:
        kind = raw.get("kind")
        if kind not in ("link", "document", "image", "video"):
            fail("材料类型无效。")
        result["url"] = safe_url(raw.get("url"))
        if kind == "link" and re.search(r"\.(?:mp4|m4v|webm|mov|ogv|ogg)(?:$|[?#])", result["url"], re.I):
            fail("请将视频直链添加为视频材料。")
    result["kind"] = kind
    if kind == "video":
        duration = raw.get("durationSeconds")
        if type(duration) not in (float, int) or not math.isfinite(duration) or not 0 < duration <= 864000:
            fail("视频时长无效，请选择可读取时长的视频。")
        result["durationSeconds"] = duration
    return result


def chapter_list(value, materials, publish):
    chapters = []
    valid = {m["id"] for m in materials}
    used, assigned = set(), set()

    def chapter_key(value):
        code = key(value)
        if code in used:
            fail("章节或小节编号重复。")
        used.add(code)
        return code

    for raw in items(value, 100):
        ch = obj(raw)
        ch_id = chapter_key(ch.get("id"))
        sections = []
        for raw_sec in items(ch.get("sections"), 1001):
            sec = obj(raw_sec)
            ids = [key(v) for v in items(sec.get("materialIds"), 1000)]
            if len(ids) != len(set(ids)) or not set(ids) <= valid or assigned.intersection(ids):
                fail("请将每份材料归入唯一的小节。")
            assigned.update(ids)
            level = sec.get("chapterLevel") is True
            if publish and not level and not ids:
                fail("请为每个小节添加学习材料。")
            sections.append(
                dict(
                    id=chapter_key(sec.get("id")),
                    title=text(sec.get("title"), 150, True),
                    chapterLevel=level,
                    materialIds=ids,
                )
            )
        if not sections or sum(s["chapterLevel"] for s in sections) > 1:
            fail("章节的小节设置无效。")
        if publish and not any(s["materialIds"] for s in sections):
            fail("请为每章添加学习材料。")
        homework = text(ch.get("homework"), 4000)
        chapters.append(
            dict(
                id=ch_id,
                title=text(ch.get("title"), 150, True),
                sections=sections,
                exam=text(ch.get("exam"), 4000),
                homework=homework,
                homeworkXp=integer(ch.get("homeworkXp", 0)) if homework else 0,
            )
        )
    if not chapters or valid != assigned:
        fail("请设置章节，并为每份材料选择所属章节。")
    return chapters


def edition(session, actor, row, input_course, rights, publish):
    from journey_api.content_assets import read_material_prefix, require_course_asset

    v = obj(input_course)
    previous, live = row.draft or {}, row.live or {}
    permitted_assets = asset_ids(previous) | asset_ids(live)
    assets = {}

    def asset_for(value):
        asset_id = identifier(value)
        if asset_id not in assets:
            asset = require_course_asset(session, actor, asset_id)
            if asset.uploaded_by != actor.id and str(asset_id) not in permitted_assets:
                fail("只能附加本人上传或本课程已使用的文件。", 403)
            assets[asset_id] = asset
        return assets[asset_id]

    tags = [text(t, 50, True) for t in items(v.get("tags", []), 60)]
    if len(set(tags)) != len(tags) or not set(tags) <= set(rights["tags"]):
        fail("课程标签已变更，请刷新后重试。", 409)
    mats = [canonical_material(m, asset_for) for m in items(v.get("materials", []), 1000)]
    if len(set(m["id"] for m in mats)) != len(mats):
        fail("材料编号重复。")
    village = row.scope == "village"
    rubric = text(v.get("rubric"), 6000, publish and not village) if not village else previous.get("rubric", "")
    lecture = text(v.get("contentText"), 48000) if not village else previous.get("contentText", "")
    if publish and not village and not lecture:
        for m in mats:
            extension = PurePosixPath(m.get("name", "")).suffix.lower()
            if (
                not m.get("assetId")
                or extension not in (".md", ".txt", ".docx")
                or m["size"] > MAX_RUBRIC_FILE_BYTES
            ):
                continue
            data = read_material_prefix(session, asset_for(m["assetId"]), m["size"])
            parse = _docx_text if extension == ".docx" else _plain_text
            lecture += ("\n" + m["title"] + "\n" + parse(data, m["name"]))[: 48000 - len(lecture)]
            if len(lecture) >= 48000:
                break
        if not lecture.strip():
            fail("请填写课程正文、讲义或可读取文字的学习材料。")
    cover = v.get("cover")
    if cover is not None:
        cover = obj(cover)
        if set(cover) == {"assetId"} and asset_for(cover["assetId"]).mime.startswith("image/"):
            cover = {"assetId": str(identifier(cover["assetId"]))}
        elif set(cover) == {"materialId"} and any(
            m["id"] == cover["materialId"] and m["kind"] == "image" for m in mats
        ):
            cover = {"materialId": cover["materialId"]}
        else:
            fail("请选择有效的课程封面。")
    if village and type(v.get("required", True)) is not bool:
        fail("请选择必修课程或普通任务。")
    time = now().isoformat()
    result = dict(
        id=str(row.id),
        scope=row.scope,
        required=village and v.get("required", True),
        title=text(v.get("title"), 150, True),
        summary=text(v.get("summary"), 2000),
        tags=tags,
        minutes=integer(v.get("minutes"), 1, 100000),
        rewardXp=integer(v.get("rewardXp", 20)),
        cover=cover,
        chapters=chapter_list(v.get("chapters"), mats, publish),
        materials=mats,
        contentText=lecture.strip(),
        rubric=rubric,
        author=previous.get("author", {"id": str(actor.id), "name": actor.display_name}),
        revision=previous.get("revision", 0) + 1,
        createdAt=previous.get("createdAt", time),
        updatedAt=time,
        returnReason="",
        status="draft",
    )
    if not live and previous.get("_retiredLearning"):
        result["_retiredLearning"] = previous["_retiredLearning"]
    if village:
        topic = v.get("requiredTopic", "公司通用常识")
        if topic not in ("公司文化", "公司制度", "全员通识", "公司通用常识"):
            fail("请选择有效的课程内容范围。")
        result["requiredTopic"] = topic
    if publish:
        result["status"] = "published" if rights["isSuperAdmin"] else "pending"
    return result


def study_signature(course):
    materials = {
        m["id"]: {k: v for k, v in m.items() if k not in ("taskTitle", "title")} for m in course["materials"]
    }
    chapters = {
        c["id"]: (c["exam"], c["homework"], sorted(i for s in c["sections"] for i in s["materialIds"]))
        for c in course["chapters"]
    }
    return materials, chapters, course["rubric"], course["contentText"]


def retired_learning(course):
    signature = study_signature(course)
    for material in signature[0].values():
        if "durationSeconds" in material:
            material["durationSeconds"] = float(material["durationSeconds"])
    encoded = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()
    return {"signature": hashlib.sha256(encoded).hexdigest(), "revision": course["learningRevision"]}


def publish_edition(row, draft):
    prior = row.live or row.draft or {}
    retired = draft.pop("_retiredLearning", None)
    draft["learningRevision"] = draft["revision"]
    if prior.get("learningRevision") and study_signature(draft) == study_signature(prior):
        draft["learningRevision"] = prior["learningRevision"]
    elif retired and retired_learning(draft)["signature"] == retired["signature"]:
        draft["learningRevision"] = retired["revision"]
    if draft.get("required"):
        draft["requiredSince"] = prior.get("requiredSince") or now().isoformat()
    row.live = deepcopy(draft)


def presented(course, *, staff):
    result = deepcopy(course)
    result.pop("_retiredLearning", None)
    base = "/api/review-native/content-assets/" if staff else "/api/learner/course-assets/"
    for m in result["materials"]:
        if m.get("assetId"):
            m["url"] = base + m["assetId"]
    cover = result.get("cover") or {}
    image = next(
        (m for m in result["materials"] if m["kind"] == "image" and m["id"] == cover.get("materialId")), None
    )
    image = image or next((m for m in result["materials"] if m["kind"] == "image"), None)
    video = next((m for m in result["materials"] if m["kind"] == "video"), None)
    if cover.get("assetId"):
        result["coverUrl"] = base + cover["assetId"]
    elif image:
        result["coverUrl"] = image["url"]
    elif video:
        result["coverVideoUrl"] = video["url"]
    if not staff:
        result.pop("rubric", None)
        result.pop("returnReason", None)
    return result
