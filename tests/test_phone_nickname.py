import uuid

import pytest
from journey_api.db import SessionLocal
from journey_api.models import User
from test_phone_password_flow import password_provider, register, learner_provider, oauth_provider
from test_learner_feishu_login import login
from test_wp09_feishu_identity import assert_ok, client_for

PATH = "/api/v1/me/learner-profile"


def save(client, name):
    return client.put(PATH, json={"display_name": name}, headers={
        "X-CSRF-Token": client.cookies["journey_next_csrf"]})


@pytest.mark.parametrize("name", ["小晨", "探索者", "同学😀"])
def test_nickname_survives_relogin_without_changing_identity_or_progress(password_provider, name):
    client, credentials = register("nickname")
    principal = assert_ok(client.get("/api/v1/session"))
    action = assert_ok(client.get("/api/v1/me/current-action"))
    assert assert_ok(client.get(PATH))["needs_nickname"]
    assert assert_ok(save(client, "  " + name + "  ")) == {"display_name": name, "needs_nickname": False}
    assert assert_ok(save(client, name))["display_name"] == name
    assert save(client, "另一个昵称").status_code == 409
    other = client_for("nickname-return" + uuid.uuid4().hex)
    assert_ok(other.post("/api/v1/auth/password/login", json=credentials))
    assert assert_ok(other.get(PATH)) == {"display_name": name, "needs_nickname": False}
    after = assert_ok(other.get("/api/v1/session"))
    assert after["user_id"] == principal["user_id"]
    assert after["display_name"] == name
    assert assert_ok(other.get("/api/v1/me/current-action"))["resource_id"] == action["resource_id"]


def test_nickname_validation_and_csrf(password_provider):
    client, _ = register("nickname-validation")
    for invalid in ["", "   ", "名" * 121, "a\nb"]:
        assert save(client, invalid).status_code == 422
    assert client.put(PATH, json={"display_name": "新昵称"}).status_code == 403
    assert assert_ok(client.get(PATH))["needs_nickname"]


def test_existing_phone_nickname_is_preserved(password_provider):
    client, _ = register("nickname-existing")
    user_id = uuid.UUID(assert_ok(client.get("/api/v1/session"))["user_id"])
    with SessionLocal.begin() as session:
        session.get(User, user_id).display_name = "原来的昵称"
    assert assert_ok(client.get(PATH)) == {"display_name": "原来的昵称", "needs_nickname": False}
    assert save(client, "覆盖原昵称").status_code == 409


def test_feishu_name_cannot_be_changed_by_nickname_endpoint(password_provider):
    client, response = login(password_provider, "nickname-feishu" + uuid.uuid4().hex, "ou_nickname_" + uuid.uuid4().hex)
    assert_ok(response)
    before = assert_ok(client.get("/api/v1/session"))["display_name"]
    assert not assert_ok(client.get(PATH))["needs_nickname"]
    assert save(client, "覆盖飞书姓名").status_code == 403
    assert assert_ok(client.get("/api/v1/session"))["display_name"] == before
