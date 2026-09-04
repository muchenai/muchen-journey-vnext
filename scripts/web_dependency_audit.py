#!/usr/bin/env python3
"""Fail closed on Web dependency advisories with one bounded dev-only waiver."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "apps" / "web"
LOCK_FILE = WEB_ROOT / "package-lock.json"
BRACE_EXPANSION_DOS = "https://github.com/advisories/GHSA-mh99-v99m-4gvg"
WAIVERS = {BRACE_EXPANSION_DOS: date(2026, 8, 31)}


class AuditError(RuntimeError):
    pass


def advisory_urls(
    package: str,
    vulnerabilities: dict[str, object],
    seen: set[str] | None = None,
) -> set[str]:
    visited = set() if seen is None else set(seen)
    if package in visited:
        return set()
    visited.add(package)
    item = vulnerabilities.get(package)
    if not isinstance(item, dict):
        raise AuditError(f"audit references missing vulnerability package: {package}")
    via = item.get("via")
    if not isinstance(via, list):
        raise AuditError(f"audit vulnerability has invalid via list: {package}")
    urls: set[str] = set()
    for cause in via:
        if isinstance(cause, str):
            urls.update(advisory_urls(cause, vulnerabilities, visited))
        elif isinstance(cause, dict) and isinstance(cause.get("url"), str):
            urls.add(cause["url"])
        else:
            raise AuditError(f"audit vulnerability has unknown cause: {package}")
    return urls


def validate_report(
    report: dict[str, object],
    lock: dict[str, object],
    *,
    today: date,
) -> tuple[int, set[str]]:
    if report.get("error"):
        raise AuditError("npm audit returned an error response")
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise AuditError("npm audit report is missing vulnerabilities")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise AuditError("package-lock is missing package metadata")

    waived: set[str] = set()
    for name, raw_item in vulnerabilities.items():
        if not isinstance(name, str) or not isinstance(raw_item, dict):
            raise AuditError("npm audit vulnerability entry is invalid")
        urls = advisory_urls(name, vulnerabilities)
        if not urls:
            raise AuditError(f"vulnerability has no advisory identity: {name}")
        for url in urls:
            expiry = WAIVERS.get(url)
            if expiry is None:
                raise AuditError(f"unwaived npm advisory: {url}")
            if today > expiry:
                raise AuditError(f"npm advisory waiver expired: {url}")
            waived.add(url)

        nodes = raw_item.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise AuditError(f"vulnerability has no package-lock nodes: {name}")
        for node in nodes:
            package = packages.get(node) if isinstance(node, str) else None
            if not isinstance(package, dict) or package.get("dev") is not True:
                raise AuditError(f"waived advisory reaches a non-dev package: {name}")
    return len(vulnerabilities), waived


def main() -> None:
    try:
        lock = json.loads(LOCK_FILE.read_text())
        result = subprocess.run(
            ["npm", "audit", "--audit-level=low", "--json"],
            cwd=WEB_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise AuditError(f"npm audit failed with exit code {result.returncode}")
        report = json.loads(result.stdout)
        count, waived = validate_report(report, lock, today=date.today())
    except (
        AuditError,
        json.JSONDecodeError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"WEB_DEPENDENCY_AUDIT_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    if waived:
        expiry = min(WAIVERS[url] for url in waived)
        print(
            "WEB_DEPENDENCY_AUDIT=PASS"
            f" vulnerability_packages={count} waived_advisories={len(waived)}"
            f" scope=dev-only waiver_expires={expiry.isoformat()}"
        )
    else:
        print("WEB_DEPENDENCY_AUDIT=PASS vulnerability_packages=0 waived_advisories=0")


if __name__ == "__main__":
    main()
