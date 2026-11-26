"""Large-file limits, scope, range addressing and normal upload flows."""
import base64

import pytest

from journey_api.content_assets import CHUNK_SIZE
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.video_limits import MAX_VIDEO_SIZE
from test_academy import write
from test_exploration_review_access import administrator
from test_reviewer_workbench import create_linked_reviewer
from test_wp09_feishu_identity import assert_ok

ASSETS = "/api/v1/review-admin/content-assets"
ACADEMY = "/api/v1/ops/academy/uploads"
KNOWLEDGE = "/api/v1/review-admin/community/knowledge"
VIDEO = b"\x00\x00\x00\x18ftypisom" + bytes(180)


@pytest.fixture
def staff():
    return administrator(create_linked_reviewer("分片视频管理员"), ORGANIZATION_ID, "super_admin")


def chunk(staff, path, position, data):
    return staff[0].put(f"{path}/chunks/{position}", content=data,
        headers={"X-CSRF-Token": staff[1], "Content-Type": "application/octet-stream"})


@pytest.mark.parametrize("purpose", ["course", "exploration", "novice"])
def test_task_course_video_limits_and_final_chunk(staff, purpose):
    command = {"name": "video.mp4", "size": MAX_VIDEO_SIZE, "purpose": purpose}
    upload = assert_ok(write(staff, "post", ASSETS, command))
    path = ASSETS + "/" + upload["id"]
    assert_ok(chunk(staff, path, 1023, bytes(CHUNK_SIZE)))
    assert chunk(staff, path, 1024, bytes(1)).status_code == 409
    assert write(staff, "post", path + "/complete", {}).status_code == 422
    assert write(staff, "post", ASSETS, {**command, "size": MAX_VIDEO_SIZE + 1}).status_code == 422
    assert write(staff, "post", ASSETS, {**command, "name": "file.pdf"}).status_code in (413, 422)
    assert_ok(write(staff, "delete", path, {}))


def test_course_asset_retry_range_and_private_preview(staff):
    content = VIDEO + bytes(CHUNK_SIZE - len(VIDEO)) + b"last"
    upload = assert_ok(write(staff, "post", ASSETS, {"name":"自测.mp4","size":len(content),"purpose":"course"}))
    path = ASSETS + "/" + upload["id"]
    assert staff[0].get(path).status_code == 404
    assert_ok(chunk(staff, path, 1, b"last"))
    assert_ok(chunk(staff, path, 1, b"last"))
    assert chunk(staff, path, 1, b"FAKE").status_code == 409
    assert_ok(chunk(staff, path, 0, content[:CHUNK_SIZE]))
    result = assert_ok(write(staff, "post", path + "/complete", {}))
    assert result["size"] == len(content) and result["mime"] == "video/mp4"
    assert result == assert_ok(write(staff, "post", path + "/complete", {}))
    preview = staff[0].get(path, headers={"Range":f"bytes={CHUNK_SIZE-2}-"})
    assert preview.status_code == 206 and preview.content == b"\0\0last"
    assert preview.headers["content-type"] == "video/mp4"
    assert staff[0].head(path).headers["content-length"] == str(len(content))
    assert staff[0].get(path, headers={"Range":"bytes=9999999999-"}).status_code == 416
    other = administrator(create_linked_reviewer("其他管理员"), ORGANIZATION_ID, "admin")
    assert other[0].get(path).status_code == 404
    assert staff[0].get("/api/v1/review-admin/exploration/materials/" + result["id"]).status_code == 404


def test_legacy_academy_and_knowledge_2gib_boundary(staff):
    video = {"fileName":"video.mp4","size":MAX_VIDEO_SIZE}
    upload = assert_ok(write(staff, "post", ACADEMY, video))
    path = ACADEMY + "/" + upload["id"]
    assert_ok(chunk(staff, path, 4095, bytes(upload["chunkSize"])))
    assert write(staff, "post", ACADEMY, {**video,"size":MAX_VIDEO_SIZE+1}).status_code == 422
    assert_ok(write(staff,"delete",path,{}))
    def knowledge(action, payload):
        return write(staff,"post",KNOWLEDGE,{"action":action,"payload":payload})
    started = assert_ok(knowledge("beginUpload", video))["result"]
    part = base64.b64encode(bytes(started["chunkSize"])).decode()
    assert_ok(knowledge("uploadChunk", {"id":started["id"], "position":4095, "data":part}))
    assert knowledge("beginUpload", {**video,"size":MAX_VIDEO_SIZE+1}).status_code == 422
    assert knowledge("beginUpload", {**video,"fileName":"large.pdf"}).status_code == 422
    assert_ok(knowledge("cancelUpload", {"id":started["id"]}))


def test_task_ref_checks_complete_and_correct_purpose(staff):
    from journey_api.db import SessionLocal
    from journey_api.errors import ApiError
    from journey_api.exploration_service import validate_material_references
    def validate(asset, camp):
        with SessionLocal() as session:
            validate_material_references(session, ORGANIZATION_ID, {"camp": camp, "materials":[asset]})
    started = assert_ok(write(staff,"post",ASSETS,{"name":"task.mp4","size":len(VIDEO),"purpose":"novice"}))
    path = ASSETS + "/" + started["id"]
    metadata = {"url":"exploration-material:"+started["id"],"name":"学习视频"}
    with pytest.raises(ApiError):
        validate(metadata, "novice")
    assert_ok(chunk(staff, path, 0, VIDEO))
    assert_ok(write(staff, "post", path + "/complete", {}))
    validate(metadata, "novice")
    assert metadata["size"] == len(VIDEO)
    with pytest.raises(ApiError):
        validate(metadata,"exploration")

def test_published_novice_video_gets_scoped_learner_player_and_ranges():
    import uuid
    from journey_api.models import Role
    from test_course_workspace import identity
    from test_novice_tasks import post
    from test_review_admin import content

    author = create_linked_reviewer("视频任务发布人")
    publisher = administrator(author, ORGANIZATION_ID, "super_admin")
    upload = assert_ok(write(publisher, "post", ASSETS, {"name":"练习.mp4", "size":len(VIDEO), "purpose":"novice"}))
    upload_path = ASSETS + "/" + upload["id"]
    assert_ok(chunk(publisher, upload_path, 0, VIDEO))
    asset = assert_ok(write(publisher, "post", upload_path + "/complete", {}))
    task_id = str(uuid.uuid4())
    task = content()
    task.update(domain="项目管理", badges=[{"id":"project","weight":100}])
    task["materials"].append({k:asset[k] for k in ("id","name","mime","type","size","url")})
    staff_path = "/api/v1/review-admin/tasks/" + task_id
    draft = assert_ok(write(publisher, "put", staff_path, {"id":task_id, "expected_revision":0, "content":task}))
    assert_ok(post(publisher, f"review-admin/tasks/{task_id}/publish",
        {"expected_revision":draft["revision"], "reviewed_by":str(author), "verified_material_urls":["https://example.com/material"]}))
    learner, _ = identity(ORGANIZATION_ID, Role.LEARNER, "Video playback learner")
    view = assert_ok(learner.get(f"/api/v1/me/novice/tasks/{task_id}"))
    index = len(task["materials"])-1
    assert view["materials"][index]["url"] == f"/api/learner/village?task={task_id}&material={index}&stream=1"
    player = learner.get(f"/api/v1/me/novice/tasks/{task_id}/materials/{index}?inline=1", headers={"Range":"bytes=3-13"})
    assert player.status_code == 206 and player.content == VIDEO[3:14]
    assert player.headers["content-type"] == "video/mp4"
    assert learner.get("/api/v1/me/exploration/materials/"+asset["id"]).status_code == 404
