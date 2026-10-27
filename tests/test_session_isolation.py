"""Real auth endpoints with both logins in a single browser cookie jar."""
import uuid
import pytest
from sqlalchemy import select
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import SESSION_COOKIE, CSRF_COOKIE, STAFF_SESSION_COOKIE, STAFF_CSRF_COOKIE, utc_now, credential_hash
from journey_api.models import Role, RoleAssignment, IdentitySession
from test_wp09_feishu_identity import oauth_provider, create_role_user, create_link, begin_oauth, callback, assert_ok
from test_learner_feishu_login import learner_provider, login
from test_phone_password_flow import password_provider, register

LEARNER={'X-Journey-Session-Scope':'learner'}
STAFF={'X-Journey-Session-Scope':'staff'}

def staff_login(browser,provider,subject,link=None):
    code=uuid.uuid4().hex
    provider.subjects[code]=subject
    state=begin_oauth(browser,'/review',link)
    return assert_ok(callback(browser,code,state))

@pytest.mark.parametrize('logout_scope',['staff','learner'])
def test_phone_and_staff_logins_remain_independent(password_provider,monkeypatch,logout_scope):
    browser,credentials=register('isolated-phone')
    phone=assert_ok(browser.get('/api/v1/session',headers=LEARNER))
    phone_token=browser.cookies[SESSION_COOKIE]
    phone_csrf=browser.cookies[CSRF_COOKIE]
    staff_id=create_role_user(Role.REVIEWER)
    link=create_link(Role.REVIEWER,staff_id)
    monkeypatch.setenv('ALLOW_FIXTURE_IDENTITY','false');get_settings.cache_clear()
    staff_login(browser,password_provider,'ou_isolated_'+uuid.uuid4().hex,str(link['link_token']))
    assert browser.cookies[SESSION_COOKIE]==phone_token
    assert browser.cookies[CSRF_COOKIE]==phone_csrf
    assert assert_ok(browser.get('/api/v1/session',headers=LEARNER))['user_id']==phone['user_id']
    assert assert_ok(browser.get('/api/v1/session',headers=STAFF))['user_id']==str(staff_id)
    assert browser.get('/api/v1/me/current-action',headers=LEARNER).status_code==200
    assert browser.get('/api/v1/reviews',headers=STAFF).status_code==200
    # A second phone login must not overwrite or revoke the staff login.
    staff_token=browser.cookies[STAFF_SESSION_COOKIE]
    assert_ok(browser.post('/api/v1/auth/password/login',json=credentials))
    assert browser.cookies[STAFF_SESSION_COOKIE]==staff_token
    assert assert_ok(browser.get('/api/v1/session',headers=STAFF))['user_id']==str(staff_id)
    pair=(STAFF_SESSION_COOKIE,STAFF_CSRF_COOKIE) if logout_scope=='staff' else (SESSION_COOKIE,CSRF_COOKIE)
    scope=STAFF if logout_scope=='staff' else LEARNER
    other=LEARNER if logout_scope=='staff' else STAFF
    assert_ok(browser.post('/api/v1/session/logout',headers={**scope,'X-CSRF-Token':browser.cookies[pair[1]]}))
    assert pair[0] not in browser.cookies and pair[1] not in browser.cookies
    assert browser.get('/api/v1/session',headers=scope).status_code==401
    assert browser.get('/api/v1/session',headers=other).status_code==200


def test_same_feishu_user_staff_login_does_not_revoke_learner(password_provider,monkeypatch):
    subject='ou_dual_'+uuid.uuid4().hex
    browser,response=login(password_provider,'dual-'+uuid.uuid4().hex,subject)
    assert_ok(response)
    principal=assert_ok(browser.get('/api/v1/session',headers=LEARNER))
    with SessionLocal.begin() as db:
        db.add(RoleAssignment(id=uuid.uuid4(),user_id=uuid.UUID(principal['user_id']),organization_id=uuid.UUID(principal['organization_id']),role=Role.REVIEWER))
    token=browser.cookies[SESSION_COOKIE]
    monkeypatch.setenv('ALLOW_FIXTURE_IDENTITY','false');get_settings.cache_clear()
    staff_login(browser,password_provider,subject)
    assert browser.cookies[SESSION_COOKIE]==token
    assert browser.get('/api/v1/session',headers=LEARNER).status_code==200
    assert browser.get('/api/v1/session',headers=STAFF).status_code==200
    # Expiring just staff cannot fall back to the learner cookie.
    with SessionLocal.begin() as db:
        row=db.scalar(select(IdentitySession).where(IdentitySession.token_hash==credential_hash(get_settings().session_secret,'session',browser.cookies[STAFF_SESSION_COOKIE])))
        row.expires_at=utc_now()
    assert browser.get('/api/v1/session',headers=STAFF).status_code==401
    assert browser.get('/api/v1/session',headers=LEARNER).status_code==200


def test_cookie_swapping_and_cross_scope_csrf_are_rejected(password_provider,monkeypatch):
    browser,_=register('isolated-security')
    staff_id=create_role_user(Role.REVIEWER);link=create_link(Role.REVIEWER,staff_id)
    monkeypatch.setenv('ALLOW_FIXTURE_IDENTITY','false');get_settings.cache_clear()
    staff_login(browser,password_provider,'ou_scope_'+uuid.uuid4().hex,str(link['link_token']))
    assert browser.post('/api/v1/session/logout',headers={**STAFF,'X-CSRF-Token':browser.cookies[CSRF_COOKIE]}).status_code==403
    assert browser.post('/api/v1/session/logout',headers={**LEARNER,'X-CSRF-Token':browser.cookies[STAFF_CSRF_COOKIE]}).status_code==403
    assert browser.get('/api/v1/session',headers={**STAFF,'Cookie':f'{STAFF_SESSION_COOKIE}={browser.cookies[SESSION_COOKIE]}'}).status_code==401
    assert browser.get('/api/v1/session',headers={**LEARNER,'Cookie':f'{SESSION_COOKIE}={browser.cookies[STAFF_SESSION_COOKIE]}'}).status_code==401
    assert browser.get('/api/v1/me/current-action',headers=STAFF).status_code==403
    assert browser.get('/api/v1/session',headers=LEARNER).status_code==200
    assert browser.get('/api/v1/session',headers=STAFF).status_code==200
