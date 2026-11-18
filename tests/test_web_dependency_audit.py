import json
import subprocess
from datetime import date
from io import BytesIO
from urllib.error import URLError

import pytest

from scripts.web_dependency_audit import (
    BRACE_EXPANSION_DOS,
    BRACES_PARSE_DOS,
    PICOMATCH_WITHDRAWAL_API,
    PICOMATCH_WITHDRAWN_AT,
    PICOMATCH_WITHDRAWN_ID,
    PICOMATCH_WITHDRAWN_URL,
    AuditError,
    main,
    read_official_withdrawal,
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


@pytest.mark.parametrize("day", [date(2026, 10, 20), date(2026, 10, 27)])
def test_owner_approved_braces_exception_is_dev_only_and_time_bounded(day):
    count, waived = validate_report(report(BRACES_PARSE_DOS), lock(), today=day)
    assert count == 2
    assert waived == {BRACES_PARSE_DOS}
    with pytest.raises(AuditError, match="non-dev"):
        validate_report(report(BRACES_PARSE_DOS), lock(minimatch_dev=False), today=day)


def test_braces_exception_stops_after_october_27():
    with pytest.raises(AuditError, match="expired"):
        validate_report(report(BRACES_PARSE_DOS), lock(), today=date(2026, 10, 28))


def withdrawal_proof() -> dict[str, object]:
    return {
        "ghsa_id": PICOMATCH_WITHDRAWN_ID,
        "cve_id": "CVE-2026-112366",
        "url": PICOMATCH_WITHDRAWAL_API,
        "html_url": PICOMATCH_WITHDRAWN_URL,
        "withdrawn_at": PICOMATCH_WITHDRAWN_AT,
        "updated_at": "2026-11-18T15:38:58Z",
        "vulnerabilities": [{
            "package": {"ecosystem": "npm", "name": "picomatch"},
            "vulnerable_version_range": "<= 4.0.7",
        }],
    }


def withdrawn_report() -> dict[str, object]:
    return {
        "vulnerabilities": {
            "picomatch": {
                "via": [{"url": PICOMATCH_WITHDRAWN_URL}],
                "nodes": ["node_modules/picomatch"],
            },
            "tinyglobby": {
                "via": ["picomatch"],
                "nodes": ["node_modules/tinyglobby"],
            },
        }
    }


def withdrawn_lock(*, dev=True) -> dict[str, object]:
    return {"packages": {
        "node_modules/picomatch": {"dev": dev},
        "node_modules/tinyglobby": {"dev": True},
    }}


def test_official_withdrawal_preserves_raw_count_and_is_not_a_waiver():
    count, waived = validate_report(
        withdrawn_report(), withdrawn_lock(), today=date(2026, 11, 19),
        withdrawal_proof=withdrawal_proof(),
    )
    assert count == 2
    assert waived == set()


@pytest.mark.parametrize("key,value", [
    ("withdrawn_at", None),
    ("withdrawn_at", "2026-11-18T15:39:00Z"),
    ("ghsa_id", "GHSA-unknown"),
    ("cve_id", "CVE-unknown"),
    ("url", "https://example.invalid/advisories/GHSA-fc5q-39xc-vjpf"),
    ("html_url", PICOMATCH_WITHDRAWN_URL + "/different"),
    ("updated_at", "2026-11-17T15:38:58Z"),
    ("updated_at", "2026-11-18T15:38:58"),
    ("updated_at", None),
    ("vulnerabilities", []),
    ("vulnerabilities", [{"package": {"ecosystem": "npm", "name": "other"}}]),
])
def test_withdrawal_rejects_active_unmatched_or_invalid_official_response(key, value):
    proof = withdrawal_proof()
    proof[key] = value
    with pytest.raises(AuditError, match="withdrawal"):
        validate_report(
            withdrawn_report(), withdrawn_lock(), today=date(2026, 11, 19),
            withdrawal_proof=proof,
        )


def test_no_withdrawal_evidence_keeps_exact_advisory_blocked():
    with pytest.raises(AuditError, match="unwaived"):
        validate_report(withdrawn_report(), withdrawn_lock(), today=date(2026, 11, 19))


def test_withdrawal_does_not_admit_unknown_advisories_or_runtime_packages():
    with pytest.raises(AuditError, match="unwaived"):
        validate_report(
            report("https://github.com/advisories/GHSA-unknown"), lock(),
            today=date(2026, 11, 19), withdrawal_proof=withdrawal_proof(),
        )
    with pytest.raises(AuditError, match="non-dev"):
        validate_report(
            withdrawn_report(), withdrawn_lock(dev=False), today=date(2026, 11, 19),
            withdrawal_proof=withdrawal_proof(),
        )


class AdvisoryResponse(BytesIO):
    status = 200

    def geturl(self):
        return PICOMATCH_WITHDRAWAL_API


def test_withdrawal_fetches_only_fixed_https_endpoint_with_a_timeout(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == PICOMATCH_WITHDRAWAL_API
            assert request.get_header("Accept") == "application/vnd.github+json"
            assert timeout == 20
            return AdvisoryResponse(json.dumps(withdrawal_proof()).encode())

    def opener(handler):
        assert handler.redirect_request(None, None, None, None, None, "https://example.invalid") is None
        return Opener()

    monkeypatch.setattr("scripts.web_dependency_audit.urllib.request.build_opener", opener)
    assert read_official_withdrawal() == withdrawal_proof()


@pytest.mark.parametrize("failure", [URLError("offline"), TimeoutError("timeout")])
def test_official_lookup_failure_has_no_cached_or_offline_success(monkeypatch, failure):
    class Opener:
        def open(self, *args, **kwargs):
            raise failure

    monkeypatch.setattr("scripts.web_dependency_audit.urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(AuditError, match="could not be verified"):
        read_official_withdrawal()


def test_main_reports_feed_findings_and_verified_withdrawal_separately(monkeypatch, capsys, tmp_path):
    lock_file = tmp_path / "package-lock.json"
    lock_file.write_text(json.dumps(withdrawn_lock()))
    monkeypatch.setattr("scripts.web_dependency_audit.LOCK_FILE", lock_file)
    monkeypatch.setattr("scripts.web_dependency_audit.subprocess.run", lambda *args, **kwargs:
        subprocess.CompletedProcess(args[0], 1, stdout=json.dumps(withdrawn_report()), stderr=""))
    monkeypatch.setattr("scripts.web_dependency_audit.read_official_withdrawal", withdrawal_proof)

    main()

    output = capsys.readouterr().out
    assert "NPM_ADVISORY_WITHDRAWAL_CONFIRMED ghsa=" + PICOMATCH_WITHDRAWN_ID in output
    assert "withdrawn_at=" + PICOMATCH_WITHDRAWN_AT in output
    assert "npm_report_vulnerability_packages=2" in output
    assert "WEB_DEPENDENCY_AUDIT=PASS vulnerability_packages=2 waived_advisories=0 withdrawn_advisories=1" in output


def test_main_blocks_if_official_source_is_unavailable(monkeypatch, capsys, tmp_path):
    lock_file = tmp_path / "package-lock.json"
    lock_file.write_text(json.dumps(withdrawn_lock()))
    monkeypatch.setattr("scripts.web_dependency_audit.LOCK_FILE", lock_file)
    monkeypatch.setattr("scripts.web_dependency_audit.subprocess.run", lambda *args, **kwargs:
        subprocess.CompletedProcess(args[0], 1, stdout=json.dumps(withdrawn_report()), stderr=""))

    def offline():
        raise AuditError("official picomatch withdrawal could not be verified")

    monkeypatch.setattr("scripts.web_dependency_audit.read_official_withdrawal", offline)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "could not be verified" in output.err
    assert "WEB_DEPENDENCY_AUDIT=PASS" not in output.out
