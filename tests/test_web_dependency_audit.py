import json
import subprocess
from datetime import date

import pytest

from scripts.web_dependency_audit import (
    BRACE_EXPANSION_DOS,
    AuditError,
    main,
    validate_report,
)


def report(url: str = BRACE_EXPANSION_DOS) -> dict[str, object]:
    return {
        "vulnerabilities": {
            "brace-expansion": {
                "via": [{"url": url}],
                "nodes": ["node_modules/brace-expansion"],
            },
            "minimatch": {
                "via": ["brace-expansion"],
                "nodes": ["node_modules/minimatch"],
            },
        }
    }


def lock(*, minimatch_dev: bool = True) -> dict[str, object]:
    return {
        "packages": {
            "node_modules/brace-expansion": {"dev": True},
            "node_modules/minimatch": {"dev": minimatch_dev},
        }
    }


def test_exact_dev_only_advisory_is_waived_until_expiry():
    count, waived = validate_report(
        report(), lock(), today=date(2026, 8, 31)
    )
    assert count == 2
    assert waived == {BRACE_EXPANSION_DOS}


def test_waiver_rejects_non_dev_reachability():
    with pytest.raises(AuditError, match="non-dev"):
        validate_report(report(), lock(minimatch_dev=False), today=date(2026, 7, 25))


def test_waiver_rejects_other_or_expired_advisories():
    with pytest.raises(AuditError, match="unwaived"):
        validate_report(
            report("https://github.com/advisories/GHSA-unknown"),
            lock(),
            today=date(2026, 7, 25),
        )
    with pytest.raises(AuditError, match="expired"):
        validate_report(report(), lock(), today=date(2026, 9, 1))


def test_clean_report_passes_without_waiver():
    count, waived = validate_report(
        {"vulnerabilities": {}}, {"packages": {}}, today=date(2026, 7, 25)
    )
    assert count == 0
    assert waived == set()


def test_audit_allows_registry_response_within_five_minute_bound(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def slow_registry_response(*args, timeout: int, **kwargs):
        if timeout < 300:
            raise subprocess.TimeoutExpired(args[0], timeout)
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout=json.dumps({"vulnerabilities": {}}),
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.web_dependency_audit.subprocess.run",
        slow_registry_response,
    )

    main()

    assert (
        "WEB_DEPENDENCY_AUDIT=PASS vulnerability_packages=0"
        in capsys.readouterr().out
    )
