import pytest

from scripts.wp12_local_readiness import (
    ReadinessError,
    nearest_rank,
    summarize,
    validate_loopback_base_url,
)


def test_loopback_target_is_mandatory():
    assert validate_loopback_base_url("http://127.0.0.1:38000") == (
        "http://127.0.0.1:38000"
    )
    assert validate_loopback_base_url("http://localhost:38000/") == (
        "http://localhost:38000"
    )
    for unsafe in (
        "https://staging-vnext.muchenai.com",
        "http://10.0.0.1:8000",
        "http://127.0.0.1",
        "http://user:pass@127.0.0.1:8000",
    ):
        with pytest.raises(ReadinessError):
            validate_loopback_base_url(unsafe)


def test_nearest_rank_uses_bounded_observed_samples():
    assert nearest_rank([0.1, 0.4, 0.2, 0.3, 0.5], 0.50) == 0.3
    assert nearest_rank([0.1, 0.4, 0.2, 0.3, 0.5], 0.95) == 0.5
    with pytest.raises(ReadinessError):
        nearest_rank([], 0.95)


def test_summary_fails_closed_for_latency_or_http_error():
    status, report = summarize(
        {
            "fast": [(200, 0.1)] * 20,
            "slow": [(200, 1.1)] * 20,
            "denied": [(200, 0.1)] * 19 + [(503, 0.1)],
        },
        p95_budget_seconds=1.0,
    )
    assert status == "FAIL"
    assert report["fast"]["status"] == "PASS"
    assert report["slow"]["status"] == "FAIL"
    assert report["denied"]["status"] == "FAIL"
