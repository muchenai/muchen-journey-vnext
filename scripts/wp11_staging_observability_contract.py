#!/usr/bin/env python3
"""Static fail-closed contract for the WP-11 read-only staging audit."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/wp11-staging-observability-audit.yml"

REQUIRED_MARKERS = {
    "workflow confirmation": "AUDIT_WP11_STAGING_OBSERVABILITY",
    "exact deployed candidate": "674e51d8ed67f9c29c3d04693376c9ba6f1114e5",
    "candidate machine contract": "config/wp08_staging.json",
    "frozen infrastructure": "Read frozen staging infrastructure",
    "temporary SSH open": "wp08_security_group open",
    "runner address masking": 'echo "::add-mask::$runner_ip"',
    "runner environment export": (
        'echo "WP11_RUNNER_CIDR=$runner_ip/32" >>"$GITHUB_ENV"'
    ),
    "bounded host audit": "wp11_host_observability_audit.py",
    "unconditional cleanup": "if: always()",
    "temporary SSH close": "wp08_security_group close",
}
FORBIDDEN_MARKERS = {
    "candidate artifact apply gate": "wp08-staging-apply-check",
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
    mask_position = source.find('echo "::add-mask::$runner_ip"')
    environment_position = source.find(
        'echo "WP11_RUNNER_CIDR=$runner_ip/32" >>"$GITHUB_ENV"'
    )
    if environment_position < 0 or mask_position > environment_position:
        raise ContractError("runner address must be masked before environment export")


def main() -> int:
    validate_workflow(WORKFLOW.read_text())
    print("WP11_STAGING_OBSERVABILITY_WORKFLOW=PASS mode=read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
