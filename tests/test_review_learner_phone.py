import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from journey_api.db import SessionLocal
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.learner_phone import read_verified_phone, remember_verified_phone
from journey_api.models import ExternalIdentity
from journey_api.phone_auth_routes import phone_subject
from test_phone_password_flow import password_provider, register, learner_provider, oauth_provider
from test_reviewer_workbench import create_submission, client_for, assert_ok, REVIEWER_HEADERS


def test_review_phone_is_scoped_and_feishu_takes_precedence():
    flow = create_submission('review-phone-' + uuid.uuid4().hex[:8])
    client = client_for('phone-reviewer')

    def row():
        data = assert_ok(client.get('/api/v1/review-admin/reviews', headers=REVIEWER_HEADERS))
        return next(item for item in data['items'] if item['id'] == str(flow['review_id']))

    initial = row()
    assert initial['learner_phone'] == ''
    learner_id = uuid.UUID(initial['learner_id'])
    phone = '13900000042'
    identity_id = uuid.uuid4()
    with SessionLocal.begin() as session:
        identity = ExternalIdentity(id=identity_id, organization_id=ORGANIZATION_ID,
            user_id=learner_id, provider='PHONE_PASSWORD', subject=phone_subject(phone), revision=1)
        remember_verified_phone(identity, phone)
        assert phone not in identity.phone_ciphertext
        session.add(identity)
    actual = row()
    assert actual['learner_phone'] == phone
    assert actual['learner_is_feishu'] is False
    assert flow['learner'].get('/api/v1/review-admin/reviews').status_code == 403
    with SessionLocal.begin() as session:
        session.add(ExternalIdentity(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
            user_id=learner_id, provider='FEISHU', subject='test-feishu-' + uuid.uuid4().hex, revision=1))
    assert row()['learner_phone'] == ''
    assert row()['learner_is_feishu'] is True


def test_phone_ciphertext_cannot_be_rebound_or_read_after_revocation():
    identity = ExternalIdentity(id=uuid.uuid4(), organization_id=ORGANIZATION_ID,
        user_id=uuid.uuid4(), provider='PHONE_PASSWORD', subject=phone_subject('13900000043'))
    remember_verified_phone(identity, '13900000043')
    assert read_verified_phone(identity) == '13900000043'
    original_user = identity.user_id
    identity.user_id = uuid.uuid4()
    assert read_verified_phone(identity) == ''
    identity.user_id = original_user
    identity.revoked_at = datetime.now(UTC)
    assert read_verified_phone(identity) == ''


def test_verified_registration_and_successful_login_capture_phone(password_provider):
    client, credentials = register('phone-display')
    subject = phone_subject(credentials['phone'])
    with SessionLocal.begin() as session:
        identity = session.scalar(select(ExternalIdentity).where(
            ExternalIdentity.provider == 'PHONE_PASSWORD', ExternalIdentity.subject == subject))
        assert read_verified_phone(identity) == credentials['phone']
        identity.phone_ciphertext = ''  # Existing accounts have no recoverable phone yet.
    login = client_for('phone-display-login-' + uuid.uuid4().hex)
    assert login.post('/api/v1/auth/password/login', json={**credentials, 'password':'wrong123'}).status_code == 401
    with SessionLocal() as session:
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.subject == subject))
        assert identity.phone_ciphertext == ''
    assert_ok(login.post('/api/v1/auth/password/login', json=credentials))
    with SessionLocal() as session:
        identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.subject == subject))
        assert read_verified_phone(identity) == credentials['phone']
