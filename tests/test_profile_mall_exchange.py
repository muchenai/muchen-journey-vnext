"""Verify real XP redemption, account migration and concurrent browser retries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from journey_api.db import SessionLocal
from journey_api import novice_economy
from journey_api.management_access_models import MallPointExchange, OfflineExperienceGrant
from journey_api.models import CompletionCode, ExternalIdentity, IdentitySession, Organization, User, UserStatus
from test_guild_certification import account

PATH = "/api/v1/me/profile/exchange"
WALLET = "/api/v1/me/novice/wallet"
HISTORY = "/api/v1/me/novice/growth"


def identity(org, provider):
    person = account(org)
    with SessionLocal.begin() as s:
        external = ExternalIdentity(id=uuid4(), organization_id=org, user_id=person["id"],
                                    provider=provider, subject=uuid4().hex)
        s.add(external)
        s.flush()
        login = s.scalar(select(IdentitySession).where(IdentitySession.user_id == person["id"]))
        login.external_identity_id = external.id
        login.external_identity_revision = external.revision
    return person


def credit(person, xp):
    with SessionLocal.begin() as s:
        s.add(OfflineExperienceGrant(organization_id=person["org"], user_id=person["id"], issuer_id=person["id"],
                                     batch=uuid4().hex, reason="测试积分", xp=xp, content={"by":"测试"}))


@pytest.fixture
def company(monkeypatch):
    monkeypatch.setattr(novice_economy, "get_settings", lambda: SimpleNamespace(app_env="local"))
    org = uuid4()
    with SessionLocal.begin() as s:
        s.add(Organization(id=org, name="商城积分验收"))
    person = identity(org, "FEISHU")
    credit(person, 105)
    return person


def exchange(person, points, key=None):
    return person["client"].post(PATH, json={"points":points}, headers={
        "X-CSRF-Token":person["csrf"], "Idempotency-Key":key or uuid4().hex})


def data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_exchange_rate_history_and_isolation(company):
    client = company["client"]
    before = data(client.get(WALLET))
    assert before["mallExchangeAvailable"] is True
    key = uuid4().hex
    first = data(exchange(company, 3, key))
    assert (first["points"], first["spentXp"], first["xpPerPoint"]) == (3, 30, 10)
    after = data(client.get(WALLET))
    assert after == first["wallet"] == {**before, "availableXp":75, "redeemedXp":30, "mallPoints":3}
    assert data(exchange(company, 3, key)) == first
    assert exchange(company, 2, key).status_code == 409
    assert exchange(company, 8).status_code == 409
    assert data(client.get(WALLET)) == after
    latest = data(exchange(company, 1))
    history = data(client.get(HISTORY, params={"kind":"mall_exchange", "limit":1}))
    assert history["total"] == 2 and history["hasMore"]
    entry = history["items"][0]
    assert entry["id"] == "mall_exchange:"+latest["id"]
    assert (entry["xp"], entry["mallPoints"], entry["xpPerPoint"], entry["badgePoints"]) == (-10, 1, 10, [])
    assert data(client.get(HISTORY, params={"kind":"mall_exchange","offset":1}))["items"][0]["id"] == "mall_exchange:"+first["id"]
    assert data(client.get(HISTORY))["total"] == 3
    other = identity(company["org"], "FEISHU")
    assert data(other["client"].get(WALLET))["mallPoints"] == 0 and exchange(other, 1, key).status_code == 409
    assert data(other["client"].get(HISTORY, params={"kind":"mall_exchange"}))["items"] == []


@pytest.mark.parametrize("environment", ["production", "staging", "test"])
def test_nonlocal_exchange_is_closed_even_for_a_preexisting_request(company, monkeypatch, environment):
    key = uuid4().hex
    data(exchange(company, 1, key))
    monkeypatch.setattr(novice_economy, "get_settings", lambda: SimpleNamespace(app_env=environment))
    before = data(company["client"].get(WALLET))
    history = data(company["client"].get(HISTORY))
    assert before["mallExchangeAvailable"] is False
    for request_key in (key, uuid4().hex):
        result = exchange(company, 1, request_key)
        assert result.status_code == 403
        assert result.json()["error"]["message"] == "暂未开放"
    assert data(company["client"].get(WALLET)) == before
    assert data(company["client"].get(HISTORY)) == history


def test_exchange_requires_company_learner_and_whole_points(company):
    phone = identity(company["org"], "PHONE_PASSWORD")
    assert exchange(phone, 1).status_code == 403
    assert exchange(account(company["org"]), 1).status_code == 403
    assert exchange(account(company["org"], admin=True), 1).status_code in {401,403}
    for value in (0, -1, 1.5, True, "2", 2**53):
        assert exchange(company, value).status_code == 422
    assert company["client"].post(PATH, json={"points":1}, headers={"X-CSRF-Token":company["csrf"]}).status_code == 422
    assert company["client"].post(PATH, json={"points":1}, headers={"Idempotency-Key":uuid4().hex}).status_code == 403
    assert data(company["client"].get(WALLET))["availableXp"] == 105


@pytest.mark.parametrize("same_key", [True, False])
def test_simultaneous_exchanges_cannot_double_spend(company, same_key):
    start = Barrier(2)
    common_key = uuid4().hex
    def spend(i):
        start.wait(timeout=10)
        return exchange(company, 10, common_key if i == 0 or same_key else uuid4().hex)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(spend, [0,1]))
    if same_key:
        assert data(responses[0])["id"] == data(responses[1])["id"]
    else:
        assert sorted(r.status_code for r in responses) == [200,409]
    updated = data(company["client"].get(WALLET))
    assert (updated["xp"],updated["availableXp"],updated["redeemedXp"],updated["mallPoints"]) == (105,5,100,10)
    with SessionLocal() as s:
        assert s.scalar(select(func.count(MallPointExchange.id)).where(MallPointExchange.user_id==company["id"])) == 1


def test_conversion_keeps_prior_corporate_credit_and_receipt_after_migration(company):
    key = uuid4().hex
    first = data(exchange(company, 3, key))
    source = identity(company["org"], "PHONE_PASSWORD")
    credit(source, 50)
    with SessionLocal.begin() as s:
        now = datetime.now(UTC)
        s.get(User,source["id"]).status = UserStatus.DISABLED
        s.add(CompletionCode(id=uuid4(), organization_id=company["org"], user_id=source["id"],
                             migrated_to_user_id=company["id"], used_at=now, expires_at=now+timedelta(days=1),
                             code_hash=uuid4().hex+uuid4().hex, code_ciphertext="test", code_hint="test"))
    replay = data(exchange(company, 3, key))
    assert replay["id"] == first["id"]
    assert replay["wallet"]["mallPoints"] == 3 and replay["wallet"]["availableXp"] == 125
    redeemed = data(exchange(company, 12))["wallet"]
    assert (redeemed["xp"],redeemed["availableXp"],redeemed["redeemedXp"],redeemed["mallPoints"]) == (155,5,150,15)
    assert data(company["client"].get(HISTORY, params={"kind":"mall_exchange"}))["total"] == 2
    assert exchange(source, 1).status_code == 401
