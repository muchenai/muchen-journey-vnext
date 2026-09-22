"""Workflow suites simulate human-paced writes; limiter tests control their own clock."""
from datetime import UTC, datetime, timedelta
from threading import Lock

import pytest

_write_time = datetime.now(UTC)
_write_lock = Lock()


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
