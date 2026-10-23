"""Workflow suites simulate human-paced writes; limiter tests control their own clock."""
from datetime import UTC, datetime, timedelta
from threading import Lock

import pytest

_write_time = datetime.now(UTC)
_write_lock = Lock()


@pytest.fixture
def system_task_reviewer():
    """Legacy system-authored workflow tests explicitly use a super administrator.

    Ordinary author-only boundaries are covered separately; assignment alone no
    longer gives this fixture reviewer authority over system-authored tasks.
    """
    from journey_api.db import SessionLocal
    from journey_api.fixtures import ORGANIZATION_ID, REVIEWER_ID
    from journey_api.review_admin_models import ReviewAdminAccess

    with SessionLocal.begin() as session:
        assert session.get(ReviewAdminAccess, REVIEWER_ID) is None
        session.add(ReviewAdminAccess(user_id=REVIEWER_ID, organization_id=ORGANIZATION_ID,
            access_role='super_admin', level='高级', domain='产品开发', granted_by=REVIEWER_ID))
    try:
        yield
    finally:
        with SessionLocal.begin() as session:
            session.delete(session.get(ReviewAdminAccess, REVIEWER_ID))


def pytest_configure(config):
    config.addinivalue_line("markers", "write_rate_limits: exercise real or explicitly controlled write rate windows")


@pytest.fixture(autouse=True)
def human_paced_write_clock(request, monkeypatch):
    if request.node.get_closest_marker("write_rate_limits"):
        return
    from journey_api import learner_write_limits

    def next_write(_session):
        global _write_time
        with _write_lock:
            _write_time += timedelta(seconds=12)
            return _write_time

    monkeypatch.setattr(learner_write_limits, "database_now", next_write)
