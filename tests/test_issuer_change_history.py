from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from journey_api.db import SessionLocal
from journey_api.errors import ApiError
from journey_api.experience_permissions import ISSUER_CHANGE
from journey_api.identity import add_audit
from journey_api.management_access_models import CourseManagementSettings
from journey_api.management_access_routes import SetIssuers, read_experience, read_issuer_settings
from journey_api.models import Organization, User
from test_management_access import accounts, change, person, request


def save(actor, revision, first, second):
    return change(actor, SetIssuers(action="configure", issuers=[first, second], revision=revision))


def settings(actor):
    with SessionLocal() as session:
        return read_issuer_settings(request(), actor, session)["data"]


def test_saved_slots_change_history_and_access_together(accounts):
    operator, first, second, learner = accounts
    assert settings(operator)["history"] == []
    save(operator, 0, None, None)
    assert settings(operator)["revision"] == 0
    save(operator, 0, first.id, second.id)
    save(operator, 1, second.id, first.id)
    save(operator, 2, None, first.id)
    with SessionLocal() as session:
        assert read_experience(request(), first, session)["data"]["canGrant"]
        with pytest.raises(ApiError) as denied:
            read_experience(request(), second, session)
        assert denied.value.status_code == 403
    result = settings(operator)
    assert result["issuers"] == [None, str(first.id)]
    assert [row["id"] for row in result["selected"]] == [str(first.id)]
    assert [(c["slot"], c["beforeId"], c["afterId"]) for c in result["history"]] == [
        (1, str(second.id), None),
        (1, str(first.id), str(second.id)), (2, str(second.id), str(first.id)),
        (1, None, str(first.id)), (2, None, str(second.id))]
    with pytest.raises(ApiError):
        save(operator, 3, learner.id, first.id)
    save(operator, 3, None, first.id)
    assert settings(operator) == result
    with SessionLocal.begin() as session:
        session.get(User, first.id).display_name = "后来改名"
    assert settings(operator)["history"] == result["history"]
    assert result["history"][0]["beforeName"] == second.display_name
    assert all(row["operatorName"] == operator.display_name and row["time"] for row in result["history"])
    save(operator, 3, None, None)
    assert settings(operator)["history"][0]["slot"] == 2
    with pytest.raises(ApiError) as denied:
        settings(first)
    assert denied.value.status_code == 403


def test_legacy_issuer_events_are_reconstructed_without_synthetic_saves(accounts):
    operator, first, second, _ = accounts
    foreign_org = uuid4()
    with SessionLocal.begin() as session:
        session.add(Organization(id=foreign_org, name="独立管理组织"))
    foreign = person(foreign_org, "其他操作人", "super_admin")
    save(foreign, 0, foreign.id, None)
    with SessionLocal.begin() as session:
        session.add(CourseManagementSettings(organization_id=operator.organization_id, revision=3,
                    issuers=[str(operator.id), str(second.id)], assignments={}, tags=[]))
        for revision, ids in [(1, [first.id, second.id]), (2, [first.id, second.id]),
                              (3, [operator.id, second.id])]:
            add_audit(session, request_id=str(uuid4()), action=ISSUER_CHANGE, resource_type="review_admin",
                      result="SUCCESS", organization_id=operator.organization_id, actor_id=operator.id,
                      resource_id=operator.organization_id, details={"revision": revision, "issuers": list(map(str, ids))})
    rows = settings(operator)["history"]
    assert [(r["slot"], r["beforeName"], r["afterName"]) for r in rows] == [
        (1, first.display_name, operator.display_name), (1, None, first.display_name), (2, None, second.display_name)]
    assert all(r["operatorName"] == operator.display_name for r in rows)


def test_first_assignment_keeps_prior_settings_revision_and_empty_slot(accounts):
    operator, first, _, _ = accounts
    with SessionLocal.begin() as session:
        session.add(CourseManagementSettings(organization_id=operator.organization_id, revision=4,
                    issuers=[], assignments={}, tags=["现有标签"]))
    assert settings(operator)["history"] == []
    save(operator, 4, None, first.id)
    state = settings(operator)
    assert state["revision"] == 5 and state["issuers"] == [None, str(first.id)]
    assert [(r["slot"], r["beforeName"], r["afterName"]) for r in state["history"]] == [
        (2, None, first.display_name)]


def test_competing_issuer_changes_do_not_duplicate_or_overwrite_history(accounts):
    operator, first, second, _ = accounts

    def try_save(user_id):
        try:
            save(operator, 0, None, user_id)
            return 200
        except ApiError as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(try_save, [first.id, second.id])) == [200, 409]
    saved = settings(operator)
    assert saved["revision"] == 1 and len(saved["history"]) == 1
    assert saved["history"][0]["slot"] == 2 and saved["history"][0]["afterId"] == saved["issuers"][1]
