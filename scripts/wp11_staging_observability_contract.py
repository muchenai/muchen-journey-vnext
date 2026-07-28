#!/usr/bin/env python3
"""Static fail-closed contract for the WP-11 read-only staging audit."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/wp11-staging-observability-audit.yml"

REQUIRED_MARKERS = {
    "workflow confirmation": "AUDIT_WP11_STAGING_OBSERVABILITY",
    "frozen infrastructure": "Read frozen staging infrastructure",
    "temporary SSH open": "wp08_security_group open",
    "bounded host audit": "wp11_host_observability_audit.py",
    "unconditional cleanup": "if: always()",
    "temporary SSH close": "wp08_security_group close",
}
FORBIDDEN_MARKERS = {
    "terraform plan": "terraform plan",
    "terraform apply": "terraform apply",
    "deployment phase": "phase=deploy",
    "notification send": "send_as_bot",
    "recipient mutation": "notification-endpoint",
}


class ContractError(RuntimeError):
    """Raised when the workflow exceeds the read-only audit boundary."""


def validate_workflow(source: str) -> None:
    for label, marker in REQUIRED_MARKERS.items():
        if marker not in source:
            raise ContractError(f"missing {label}")
    for label, marker in FORBIDDEN_MARKERS.items():
        if marker in source:
            raise ContractError(f"forbidden {label}")
    if source.count("wp08_security_group open") != 1:
        raise ContractError("temporary SSH open must occur exactly once")
    if source.count("wp08_security_group close") != 1:
        raise ContractError("temporary SSH close must occur exactly once")


def main() -> int:
    validate_workflow(WORKFLOW.read_text())
    print("WP11_STAGING_OBSERVABILITY_WORKFLOW=PASS mode=read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
