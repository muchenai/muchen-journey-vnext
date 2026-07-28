#!/usr/bin/env python3
"""Static, read-only WP-12 candidate hardening contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HardeningError(RuntimeError):
    """A candidate hardening requirement is absent or ambiguous."""


def validate_staging_app_sandbox(compose_path: Path) -> None:
    compose = compose_path.read_text(encoding="utf-8")
    required = (
        "x-app-security: &app-security",
        "no-new-privileges:true",
        "cap_drop:\n    - ALL",
        "pids_limit: 256",
    )
    if any(marker not in compose for marker in required):
        raise HardeningError("staging application sandbox contract is incomplete")
    if compose.count("<<: [*common, *app-security]") != 3:
        raise HardeningError("exactly API, Web, and Worker must inherit the application sandbox")


def validate_web_source_map_policy(next_config_path: Path) -> None:
    next_config = next_config_path.read_text(encoding="utf-8")
    if "productionBrowserSourceMaps: false" not in next_config:
        raise HardeningError("production browser source maps must be explicitly disabled")


def check() -> None:
    validate_staging_app_sandbox(ROOT / "deploy" / "staging" / "compose.yaml")
    validate_web_source_map_policy(ROOT / "apps" / "web" / "next.config.ts")


if __name__ == "__main__":
    try:
        check()
    except (HardeningError, OSError) as error:
        raise SystemExit(f"WP12_HARDENING=FAIL reason={error}") from error
    print("WP12_HARDENING=PASS app_sandbox=3 source_maps=disabled")
