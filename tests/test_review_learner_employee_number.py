import uuid
from datetime import UTC, datetime

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.directory_cache_models import DirectoryMember
from journey_api.fixtures import ORGANIZATION_ID
from journey_api.models import ExternalIdentity, Organization, User
from journey_api.review_admin_routes import directory_subject
from test_reviewer_workbench import create_submission, client_for, assert_ok, REVIEWER_HEADERS


def test_review_queue_uses_scoped_cached_feishu_identity_not_name(monkeypatch):
    monkeypatch.setenv('FEISHU_LEARNER_ORGANIZATION_ID', str(ORGANIZATION_ID))
    get_settings.cache_clear()
    try:
        flow = create_submission('employee-number-' + uuid.uuid4().hex[:8])
        client = client_for('employee-number-reviewer')

        def row():
            data = assert_ok(client.get('/api/v1/review-admin/reviews', headers=REVIEWER_HEADERS))
            return next(item for item in data['items'] if item['id'] == str(flow['review_id']))

        initial = row()
        learner_id = uuid.UUID(initial['learner_id'])
        assert initial['learner_is_feishu'] is False
        assert initial['learner_employee_no'] == ''
        open_id, identity_id = 'ou_' + uuid.uuid4().hex, uuid.uuid4()
        app_id = get_settings().feishu_app_id
        with SessionLocal.begin() as session:
            session.add(ExternalIdentity(id=identity_id, organization_id=ORGANIZATION_ID,
                user_id=learner_id, provider='FEISHU', subject=directory_subject(open_id), revision=1))
            other_org = uuid.uuid4()
            session.add(Organization(id=other_org, name='Unrelated organization'))
            session.flush()
            for org, app, subject, number in [
                (ORGANIZATION_ID, app_id + '-other', open_id, 'WRONG-APP'),
                (other_org, app_id, open_id, 'WRONG-ORG'),
                (ORGANIZATION_ID, app_id, 'ou_' + uuid.uuid4().hex, 'WRONG-SAME-NAME'),
            ]:
                session.add(DirectoryMember(organization_id=org, app_id=app, open_id=subject,
                    search_name=initial['learner_name'], profile={'name': initial['learner_name'], 'employee_no': number}))
        missing = row()
        assert missing['learner_is_feishu'] is True
        assert missing['learner_employee_no'] == ''
        with SessionLocal.begin() as session:
            session.add(DirectoryMember(organization_id=ORGANIZATION_ID, app_id=app_id, open_id=open_id,
                search_name=initial['learner_name'], profile={'name': initial['learner_name'], 'employee_no': 'MCE0000042'}))

        from journey_api import feishu_directory
        def forbid_remote():
            raise AssertionError('Review queue must not call the remote directory')
        monkeypatch.setattr(feishu_directory, 'get_directory', forbid_remote)
        actual = row()
        assert actual['learner_name'] == initial['learner_name']
        assert actual['learner_employee_no'] == 'MCE0000042'
        with SessionLocal.begin() as session:
            session.get(ExternalIdentity, identity_id).revoked_at = datetime.now(UTC)
        revoked = row()
        assert revoked['learner_is_feishu'] is False
        assert revoked['learner_employee_no'] == ''
        assert flow['learner'].get('/api/v1/review-admin/reviews').status_code == 403
    finally:
        get_settings.cache_clear()
