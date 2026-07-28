from pathlib import Path

import pytest

from scripts.wp12_candidate_hardening import (
    HardeningError,
    validate_staging_app_sandbox,
    validate_web_source_map_policy,
)


def test_staging_app_containers_drop_linux_capabilities_and_privilege_escalation(
    tmp_path: Path,
):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "x-app-security: &app-security\n"
        "  security_opt:\n"
        "    - no-new-privileges:true\n"
        "  cap_drop:\n"
        "    - ALL\n"
        "  pids_limit: 256\n"
        "services:\n"
        "  api:\n    <<: [*common, *app-security]\n"
        "  web:\n    <<: [*common, *app-security]\n"
        "  worker:\n    <<: [*common, *app-security]\n"
    )

    validate_staging_app_sandbox(compose)

    compose.write_text(compose.read_text().replace("no-new-privileges:true", ""))
    with pytest.raises(HardeningError, match="sandbox contract"):
        validate_staging_app_sandbox(compose)


def test_production_browser_source_maps_are_explicitly_disabled(tmp_path: Path):
    next_config = tmp_path / "next.config.ts"
    next_config.write_text("const nextConfig = { productionBrowserSourceMaps: false };\n")

    validate_web_source_map_policy(next_config)

    next_config.write_text("const nextConfig = {};\n")
    with pytest.raises(HardeningError, match="source maps"):
        validate_web_source_map_policy(next_config)
