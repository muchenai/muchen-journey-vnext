import json
import os
import subprocess
from pathlib import Path

import pytest

import scripts.wp08_prepare_deploy as prepare
import scripts.wp08_staging as staging


def test_archive_runtime_image_builder_is_candidate_bound():
    source = (staging.ROOT / "scripts" / "wp08_prepare_deploy.py").read_text()

    assert 'f"{component.lower()}:{CANDIDATE}"' in source


def pull_helper_source() -> str:
    script = staging.DEPLOY_SCRIPT.read_text()
    start = script.index("pull_with_bounded_retry() {")
    end = script.index('\n\n[[ "${EUID}"', start)
    return script[start:end]


def test_image_pull_retries_only_transient_failures_and_redacts_raw_error(tmp_path: Path):
    attempt_file = tmp_path / "attempts"
    fake_pull = tmp_path / "fake-pull"
    fake_pull.write_text(
        "#!/usr/bin/env bash\n"
        "count=0\n"
        '[[ ! -f "$ATTEMPT_FILE" ]] || count=$(cat "$ATTEMPT_FILE")\n'
        "count=$((count + 1))\n"
        'printf \'%s\' "$count" > "$ATTEMPT_FILE"\n'
        'if [[ "$count" -lt 3 ]]; then\n'
        "  printf 'TLS handshake timeout https://signed.example.invalid/?secret=must-not-leak\\n' >&2\n"
        "  exit 1\n"
        "fi\n"
    )
    fake_pull.chmod(0o755)
    command = f"""
set -euo pipefail
{pull_helper_source()}
pull_with_bounded_retry api {fake_pull!s}
"""
    env = os.environ.copy()
    env["ATTEMPT_FILE"] = str(attempt_file)
    result = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, check=False, env=env
    )
    assert result.returncode == 0
    assert attempt_file.read_text() == "3"
    assert result.stdout.count("result=RETRY") == 2
    assert "attempt=3 max_attempts=3 result=PASS" in result.stdout
    assert "signed.example.invalid" not in result.stdout + result.stderr


def test_image_pull_does_not_retry_non_transient_failure_or_leak_log(tmp_path: Path):
    attempt_file = tmp_path / "attempts"
    fake_pull = tmp_path / "fake-pull"
    fake_pull.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'1\' > "$ATTEMPT_FILE"\n'
        "printf 'manifest unknown https://signed.example.invalid/?secret=must-not-leak\\n' >&2\n"
        "exit 7\n"
    )
    fake_pull.chmod(0o755)
    command = f"""
set -euo pipefail
{pull_helper_source()}
pull_with_bounded_retry api {fake_pull!s}
"""
    env = os.environ.copy()
    env["ATTEMPT_FILE"] = str(attempt_file)
    result = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, check=False, env=env
    )
    assert result.returncode == 7
    assert attempt_file.read_text() == "1"
    assert "category=NON_RETRYABLE result=FAIL" in result.stderr
    assert "result=RETRY" not in result.stdout + result.stderr
    assert "signed.example.invalid" not in result.stdout + result.stderr


def contract(tmp_path: Path, *, estimate=None) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "provider": "volcengine",
                "region_id": "cn-beijing",
                "billing_mode": "PostPaid",
                "monthly_budget_cny": 800,
                "approved_monthly_estimate_cny": estimate,
                "candidate_commit": "f" * 40,
                "candidate_artifact_run_id": 123456,
                "candidate_image_digests": {
                    "api": "sha256:" + "a" * 64,
                    "web": "sha256:" + "b" * 64,
                    "worker": "sha256:" + "c" * 64,
                },
                "staging_origin": "https://staging-vnext.muchenai.com",
                "resource_prefix": "journey-next-staging",
            }
        )
    )
    return path


def infrastructure_files(tmp_path: Path) -> tuple[Path, Path]:
    versions = tmp_path / "versions.tf"
    versions.write_text('source  = "hashicorp/random"\nversion = "3.7.2"\n')
    main = tmp_path / "main.tf"
    main.write_text(
        "\n".join(
            (
                'resource "random_password" "ecs_bootstrap" {',
                'length           = 30',
                'override_special = "!@#%^&*_-+=?"',
                '}',
                'resource "volcenginecc_rdspostgresql_allow_list" "app" {',
                'security_group_bind_infos = [{',
                'bind_mode = "AssociateEcsIp"',
                'security_group_id = "sg-reviewed"',
                'security_group_name = "journey-next-staging-app"',
                '}]',
                'depends_on = [volcenginecc_ecs_instance.app]',
                'lifecycle {',
                'ignore_changes = [security_group_bind_infos]',
                '}',
                '}',
                'resource "volcenginecc_rdspostgresql_instance_ssl" "staging" {',
                '}',
                'resource "volcenginecc_rdspostgresql_db_account" "migration" {',
                'depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]',
                '}',
                'resource "volcenginecc_rdspostgresql_db_account" "runtime" {',
                'depends_on = [volcenginecc_rdspostgresql_db_account.migration]',
                '}',
                'resource "volcenginecc_ecs_instance" "app" {',
                'password                  = random_password.ecs_bootstrap.result',
                'PasswordAuthentication no',
                'KbdInteractiveAuthentication no',
                'PermitRootLogin prohibit-password',
                'stopped_mode              = "KeepCharging"',
                'prevent_destroy = true',
                'ignore_changes = [',
                'eip_address.bandwidth_mbps',
                'eip_address.charge_type',
                'eip_address.isp',
                'eip_address.release_with_instance',
                'image.security_enhancement_strategy',
                'install_run_command_agent',
                'password',
                'system_volume.delete_with_instance',
                'system_volume.size',
                'system_volume.volume_type',
                'user_data',
                ']',
                '}',
            )
        )
    )
    return versions, main


def test_contract_locks_provider_region_budget_and_origin(tmp_path: Path):
    data = staging.load_contract(contract(tmp_path))
    assert data["region_id"] == "cn-beijing"
    assert data["monthly_budget_cny"] == 800
    assert data["candidate_artifact_run_id"] == 123456


def test_contract_requires_three_valid_candidate_digests(tmp_path: Path):
    path = contract(tmp_path)
    payload = json.loads(path.read_text())
    del payload["candidate_image_digests"]["worker"]
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="api, web, and worker"):
        staging.load_contract(path)

    payload["candidate_image_digests"]["worker"] = "latest"
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="invalid digest"):
        staging.load_contract(path)


def test_active_candidate_binding_matches_deploy_preflight():
    data = staging.load_contract()
    script = staging.DEPLOY_SCRIPT.read_text()
    candidate = str(data["candidate_commit"])
    digests = data["candidate_image_digests"]

    assert f'[[ "${{CANDIDATE_COMMIT:-}}" == "{candidate}" ]]' in script
    assert isinstance(digests, dict)
    for component in ("api", "web", "worker"):
        key = f"{component.upper()}_IMAGE"
        local_key = f"{component.upper()}_LOCAL_IMAGE_DIGEST"
        assert prepare.IMAGES[key].endswith(f"@{digests[component]}")
        assert str(digests[component]) in script
        assert prepare.LOCAL_IMAGE_DIGESTS[local_key] in script


def test_active_candidate_local_digests_match_verified_archive():
    expected = {
        "API_LOCAL_IMAGE_DIGEST": "sha256:11ce12d31a93ab5953b89f7d911cc7b92aa9fe20178d552503aec26732bfec7b",
        "WEB_LOCAL_IMAGE_DIGEST": "sha256:2f5090a28037ce13af6808e6a1fc67f0fb903a3544f3406e330f3527de57e0c7",
        "WORKER_LOCAL_IMAGE_DIGEST": "sha256:c89d1aefb21e74df597dc08d329b144aea28eee3184eefde917395c28a5cc848",
    }

    assert prepare.LOCAL_IMAGE_DIGESTS == expected


def test_apply_requires_quote_and_rejects_over_budget(tmp_path: Path):
    data = staging.load_contract(contract(tmp_path))
    staging.validate_cost(data, require_quote=False)
    with pytest.raises(staging.StagingError, match="estimate is not recorded"):
        staging.validate_cost(data, require_quote=True)

    over = staging.load_contract(contract(tmp_path, estimate=800.01))
    with pytest.raises(staging.StagingError, match="exceeds"):
        staging.validate_cost(over, require_quote=True)


def test_apply_accepts_positive_quote_within_budget(tmp_path: Path):
    data = staging.load_contract(contract(tmp_path, estimate=799.99))
    staging.validate_cost(data, require_quote=True)


def test_over_budget_evidence_preserves_null_approval(tmp_path: Path):
    path = contract(tmp_path)
    payload = json.loads(path.read_text())
    payload["latest_cost_evidence"] = {
        "status": "OVER_BUDGET_NO_DEPLOY",
        "subtotal_before_tos_backup_and_traffic_cny": 800.01,
    }
    path.write_text(json.dumps(payload))
    data = staging.load_contract(path)
    assert data["approved_monthly_estimate_cny"] is None
    with pytest.raises(staging.StagingError, match="quote exceeds"):
        staging.validate_cost(data, require_quote=True)

    payload["approved_monthly_estimate_cny"] = 799
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="cannot be approved"):
        staging.load_contract(path)


def test_reauthorized_baseline_requires_refreshed_total_quote(tmp_path: Path):
    path = contract(tmp_path)
    payload = json.loads(path.read_text())
    payload["latest_cost_evidence"] = {
        "status": "BASELINE_WITHIN_BUDGET_QUOTE_REFRESH_REQUIRED",
        "subtotal_before_tos_backup_and_traffic_cny": 717.26,
    }
    path.write_text(json.dumps(payload))
    data = staging.load_contract(path)
    with pytest.raises(staging.StagingError, match="quote must be refreshed"):
        staging.validate_cost(data, require_quote=True)

    payload["approved_monthly_estimate_cny"] = 717.26
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="cannot be approved"):
        staging.load_contract(path)


def test_approved_quote_matches_forecast_and_budget(tmp_path: Path):
    path = contract(tmp_path, estimate=656.26)
    payload = json.loads(path.read_text())
    payload["latest_cost_evidence"] = {
        "status": "WITHIN_BUDGET_APPROVED",
        "subtotal_before_tos_and_traffic_cny": 573.26,
        "approved_monthly_forecast_cny": 656.26,
    }
    path.write_text(json.dumps(payload))
    data = staging.load_contract(path)
    staging.validate_cost(data, require_quote=True)

    payload["approved_monthly_estimate_cny"] = 656.25
    path.write_text(json.dumps(payload))
    with pytest.raises(staging.StagingError, match="forecast differ"):
        staging.load_contract(path)


def test_infrastructure_uses_state_only_bootstrap_password(tmp_path: Path, monkeypatch):
    versions, main = infrastructure_files(tmp_path)
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    staging.validate_infrastructure()

    main.write_text(main.read_text().replace("PasswordAuthentication no", ""))
    with pytest.raises(staging.StagingError, match="bootstrap marker"):
        staging.validate_infrastructure()


def test_infrastructure_rejects_unreviewed_ignore_set_and_mutable_allowlist_binding(
    tmp_path: Path, monkeypatch
):
    versions, main = infrastructure_files(tmp_path)
    source = main.read_text()
    main.write_text(source.replace("user_data\n", ""))
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    with pytest.raises(staging.StagingError, match="ignore list differs"):
        staging.validate_infrastructure()

    main.write_text(source.replace("security_group_name", "ip_list = []\nsecurity_group_name", 1))
    with pytest.raises(staging.StagingError, match="must not configure ip_list"):
        staging.validate_infrastructure()

    main.write_text(source.replace("ignore_changes = [security_group_bind_infos]", ""))
    with pytest.raises(staging.StagingError, match="must be immutable after creation"):
        staging.validate_infrastructure()

    main.write_text(source.replace("depends_on = [volcenginecc_ecs_instance.app]", ""))
    with pytest.raises(staging.StagingError, match="security-group attachment"):
        staging.validate_infrastructure()


def test_deploy_requires_release_local_secrets_and_safe_preflight(tmp_path: Path):
    script = tmp_path / "deploy.sh"
    valid = (
        "\n".join(
            (
                "pull_with_bounded_retry()",
                "for attempt in 1 2 3",
                "timeout --signal=TERM --kill-after=30s 8m",
                "TRANSIENT_NETWORK",
                "COMMAND_TIMEOUT",
                "NON_RETRYABLE",
                "WP08_IMAGE_PULL",
                'SECRETS="$PWD/secrets"',
                "docker compose -f compose.yaml -f compose.migrate.yaml config --quiet",
                "python3 ./wp07_image_archive.py verify-files",
                'load_verified_archive api "$API_RUNTIME_IMAGE" "$API_LOCAL_IMAGE_DIGEST"',
                'load_verified_archive web "$WEB_RUNTIME_IMAGE" "$WEB_LOCAL_IMAGE_DIGEST"',
                'load_verified_archive worker "$WORKER_RUNTIME_IMAGE" "$WORKER_LOCAL_IMAGE_DIGEST"',
                "docker compose -f compose.yaml -f compose.migrate.yaml "
                "run --rm --no-deps api python -c \"from pathlib import Path; "
                "Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()\"",
                "docker compose -f compose.yaml -f compose.migrate.yaml "
                "run --rm --no-deps api alembic upgrade head",
                "WP08_ROLLBACK=STOP_FAILED_FIRST_RELEASE",
                "docker compose down --remove-orphans",
                '[[ "${DEPLOY_MODE:-}" == "full" || "${DEPLOY_MODE:-}" == "web-only" || "${DEPLOY_MODE:-}" == "runtime-repair" ]]',
                "verify_web_only_runtime",
                "verify_runtime_repair_prestate",
                'pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"',
                'pull_with_bounded_retry runtime-api docker pull "$API_IMAGE"',
                'pull_with_bounded_retry runtime-worker docker pull "$WORKER_IMAGE"',
                "alembic upgrade 0014_wp12_data_lifecycle",
                "docker compose up -d --no-deps --wait --wait-timeout 180 web",
                "WP08_WEB_ONLY_ROLLBACK=START",
                "WP08_RUNTIME_REPAIR_ROLLBACK=START",
                "WP08_RUNTIME_REPAIR=PASS",
                "DEPLOYED_CANDIDATE.tmp",
                "DEPLOYED_COMPONENTS.json",
                "validate_component_marker_shape",
                "full_sha.fullmatch(value)",
                "WP08_WEB_ONLY_DEPLOY=PASS",
                'if [[ "$DEPLOY_MODE" == "web-only" ]]',
                'validate_component_marker_shape "$ROOT/DEPLOYED_COMPONENTS.json"',
                'verify_web_only_runtime "$previous"',
                'pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"',
                'if [[ "$DEPLOY_MODE" == "runtime-repair" ]]',
                "verify_runtime_repair_prestate",
                'pull_with_bounded_retry runtime-api docker pull "$API_IMAGE"',
                'pull_with_bounded_retry runtime-worker docker pull "$WORKER_IMAGE"',
                "alembic upgrade 0014_wp12_data_lifecycle",
                "python /tmp/grant_runtime.py",
                "docker compose up -d --no-deps --wait --wait-timeout 180 api",
                "docker compose up -d --no-deps --wait --wait-timeout 180 worker",
                "verify_web_only_runtime",
                "write_component_markers",
                "fi",
            )
        )
    )
    script.write_text(valid)
    staging.validate_deploy_script(script)

    script.write_text(valid.replace("full_sha.fullmatch(value)", "value == candidate"))
    with pytest.raises(staging.StagingError, match="Web-only deployment contract is incomplete"):
        staging.validate_deploy_script(script)

    script.write_text(valid + '\ncomponents["api"] == baseline\n')
    with pytest.raises(staging.StagingError, match="live runtime instead of trusting stale markers"):
        staging.validate_deploy_script(script)

    script.write_text(
        valid.replace(
            'validate_component_marker_shape "$ROOT/DEPLOYED_COMPONENTS.json"\n'
            'verify_web_only_runtime "$previous"',
            'verify_web_only_runtime "$previous"\n'
            'validate_component_marker_shape "$ROOT/DEPLOYED_COMPONENTS.json"',
        )
    )
    with pytest.raises(staging.StagingError, match="marker shape and live runtime"):
        staging.validate_deploy_script(script)

    script.write_text(valid + "\npython -m journey_api.seed\n")
    with pytest.raises(staging.StagingError, match="must not seed fixture business facts"):
        staging.validate_deploy_script(script)

    script.write_text(valid.replace("for attempt in 1 2 3", "for attempt in 1 2 3 4"))
    with pytest.raises(staging.StagingError, match="three-attempt bounded retry"):
        staging.validate_deploy_script(script)

    script.write_text(
        valid.replace(
            'pull_with_bounded_retry web-only docker pull "$WEB_IMAGE"',
            'timeout --signal=TERM --kill-after=30s 8m docker pull "$WEB_IMAGE"',
        )
    )
    with pytest.raises(staging.StagingError, match="bounded retry"):
        staging.validate_deploy_script(script)

    script.write_text('SECRETS="$ROOT/secrets"\n')
    with pytest.raises(staging.StagingError, match="release-local"):
        staging.validate_deploy_script(script)

    script.write_text(
        valid.replace(
            "write_component_markers\nfi",
            "docker compose up -d --no-deps --wait --wait-timeout 180 web\n"
            "write_component_markers\nfi",
        )
    )
    with pytest.raises(staging.StagingError, match="mutation boundary"):
        staging.validate_deploy_script(script)

    script.write_text(
        valid.replace(
            "python3 ./wp07_image_archive.py verify-files\n"
            'load_verified_archive api "$API_RUNTIME_IMAGE" "$API_LOCAL_IMAGE_DIGEST"\n'
            'load_verified_archive web "$WEB_RUNTIME_IMAGE" "$WEB_LOCAL_IMAGE_DIGEST"\n'
            'load_verified_archive worker "$WORKER_RUNTIME_IMAGE" "$WORKER_LOCAL_IMAGE_DIGEST"\n'
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api python -c \"from pathlib import Path; "
            "Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()\"\n"
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api alembic upgrade head",
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api alembic upgrade head\n"
            "python3 ./wp07_image_archive.py verify-files\n"
            'load_verified_archive api "$API_RUNTIME_IMAGE" "$API_LOCAL_IMAGE_DIGEST"\n'
            'load_verified_archive web "$WEB_RUNTIME_IMAGE" "$WEB_LOCAL_IMAGE_DIGEST"\n'
            'load_verified_archive worker "$WORKER_RUNTIME_IMAGE" "$WORKER_LOCAL_IMAGE_DIGEST"\n'
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api python -c \"from pathlib import Path; "
            "Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()\"",
        )
    )
    with pytest.raises(staging.StagingError, match="before database migration"):
        staging.validate_deploy_script(script)

    script.write_text(
        valid.replace(
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api python -c \"from pathlib import Path; "
            "Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()\"\n",
            "",
        )
    )
    with pytest.raises(staging.StagingError, match="preflight commands"):
        staging.validate_deploy_script(script)

    script.write_text(valid.replace("docker compose down --remove-orphans", ""))
    with pytest.raises(staging.StagingError, match="stop partial application containers"):
        staging.validate_deploy_script(script)


def test_edge_mirror_workflow_is_manual_and_digest_pinned(tmp_path: Path):
    workflow = tmp_path / "edge-mirror.yml"
    source = "\n".join(
        (
            "workflow_dispatch:",
            "packages: write",
            "inputs.confirmation == 'MIRROR_CADDY_2_10_2_TO_GHCR'",
            "docker/login-action@4907a6ddec9925e35a0a9e82d7399ccc52663121",
            "docker.io/library/caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d",
            "ghcr.io/muchenai2024-creator/muchen-journey-vnext-edge:caddy-2.10.2-alpine-4c6e91c6ed0e",
            'docker buildx imagetools inspect "$target@$digest"',
        )
    )
    workflow.write_text(source)
    staging.validate_edge_mirror_workflow(workflow)

    workflow.write_text(source.replace("workflow_dispatch:", "push:"))
    with pytest.raises(staging.StagingError, match="incomplete"):
        staging.validate_edge_mirror_workflow(workflow)


def test_staging_edge_uses_verified_project_ghcr_digest(tmp_path: Path, monkeypatch):
    readiness = tmp_path / "route.ts"
    readiness.write_text('status: "ready"\n"Cache-Control": "no-store"\n')
    proxy = tmp_path / "proxy.ts"
    proxy.write_text(
        'code: "AUTH_REQUIRED"\n{ status: 401 }\n'
        'requestHeaders.set("Content-Security-Policy", policy)\n'
    )
    layout = tmp_path / "layout.tsx"
    layout.write_text(
        'import { connection } from "next/server"\nawait connection()\n'
    )
    monkeypatch.setattr(staging, "WEB_READINESS_ROUTE", readiness)
    monkeypatch.setattr(staging, "WEB_PROXY", proxy)
    monkeypatch.setattr(staging, "WEB_LAYOUT", layout)
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text(
        "log_skip /auth/feishu*\n"
        "reverse_proxy journey-next-staging-web-1:3000\n"
        "reverse_proxy production-web:3000\n"
    )
    monkeypatch.setattr(staging, "STAGING_CADDYFILE", caddyfile)
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  api:\n    image: ${API_RUNTIME_IMAGE:?required}\n"
        "  worker:\n    image: ${WORKER_RUNTIME_IMAGE:?required}\n"
        "  web:\n"
        "    image: ${WEB_RUNTIME_IMAGE:?required}\n"
        "    healthcheck:\n"
        "      test: http://localhost:3000/health/ready\n"
        "  edge:\n"
        f"    image: {staging.EDGE_IMAGE}\n"
    )
    staging.validate_staging_compose(compose)

    caddyfile.write_text(
        "log_skip /auth/feishu*\n"
        "reverse_proxy web:3000\n"
        "reverse_proxy production-web:3000\n"
    )
    with pytest.raises(staging.StagingError, match="unique Web network alias"):
        staging.validate_staging_compose(compose)
    caddyfile.write_text(
        "log_skip /auth/feishu*\n"
        "reverse_proxy journey-next-staging-web-1:3000\n"
        "reverse_proxy production-web:3000\n"
    )

    compose.write_text(
        "services:\n"
        "  api:\n    image: ${API_RUNTIME_IMAGE:?required}\n"
        "  worker:\n    image: ${WORKER_RUNTIME_IMAGE:?required}\n"
        "  web:\n"
        "    image: ${WEB_RUNTIME_IMAGE:?required}\n"
        "    healthcheck:\n"
        "      test: http://localhost:3000/ops\n"
        "  edge:\n"
        f"    image: {staging.EDGE_IMAGE}\n"
    )
    with pytest.raises(staging.StagingError, match="readiness route"):
        staging.validate_staging_compose(compose)

    compose.write_text(
        "services:\n"
        "  api:\n    image: ${API_RUNTIME_IMAGE:?required}\n"
        "  worker:\n    image: ${WORKER_RUNTIME_IMAGE:?required}\n"
        "  web:\n    image: ${WEB_RUNTIME_IMAGE:?required}\n"
        "  edge:\n    image: caddy:2.10.2-alpine@sha256:" + "a" * 64 + "\n"
    )
    with pytest.raises(staging.StagingError, match="project GHCR digest"):
        staging.validate_staging_compose(compose)


def test_staging_web_requires_dynamic_per_request_csp_nonce(tmp_path: Path, monkeypatch):
    readiness = tmp_path / "route.ts"
    readiness.write_text('status: "ready"\n"Cache-Control": "no-store"\n')
    proxy = tmp_path / "proxy.ts"
    proxy.write_text('code: "AUTH_REQUIRED"\n{ status: 401 }\n')
    layout = tmp_path / "layout.tsx"
    layout.write_text('export default function Layout() {}\n')
    monkeypatch.setattr(staging, "WEB_READINESS_ROUTE", readiness)
    monkeypatch.setattr(staging, "WEB_PROXY", proxy)
    monkeypatch.setattr(staging, "WEB_LAYOUT", layout)
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text(
        "log_skip /auth/feishu*\n"
        "reverse_proxy journey-next-staging-web-1:3000\n"
        "reverse_proxy production-web:3000\n"
    )
    monkeypatch.setattr(staging, "STAGING_CADDYFILE", caddyfile)
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  api:\n    image: ${API_RUNTIME_IMAGE:?required}\n"
        "  worker:\n    image: ${WORKER_RUNTIME_IMAGE:?required}\n"
        "  web:\n"
        "    image: ${WEB_RUNTIME_IMAGE:?required}\n"
        "    healthcheck:\n"
        "      test: http://localhost:3000/health/ready\n"
        "  edge:\n"
        f"    image: {staging.EDGE_IMAGE}\n"
    )

    with pytest.raises(staging.StagingError, match="receive the per-request CSP nonce"):
        staging.validate_staging_compose(compose)

    proxy.write_text(
        'code: "AUTH_REQUIRED"\n{ status: 401 }\n'
        'requestHeaders.set("Content-Security-Policy", policy)\n'
    )
    with pytest.raises(staging.StagingError, match="dynamically rendered"):
        staging.validate_staging_compose(compose)


def test_workflow_requires_guard_before_each_saved_plan_apply(tmp_path: Path, monkeypatch):
    versions, main = infrastructure_files(tmp_path)
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    workflow = tmp_path / "staging.yml"
    source = "\n".join(
        (
                "- audit",
                "          - deploy-web",
                "          - inspect-runtime",
            "          - diagnose-publication",
            "          - repair-edge-route",
            "          - cleanup-failed-release",
                "inputs.confirmation == 'AUDIT_WP08_RDS_NETWORK'",
                "inputs.confirmation == 'DEPLOY_WEB_C2E665A_ON_9E8A806_STAGING'",
            "inputs.confirmation == 'CLEANUP_FAILED_RELEASE_EF0A512_30808632624'",
            "DEPLOY_WEB_222096D_ON_02863D0_STAGING",
            "REPAIR_RUNTIME_02863D0_FOR_WEB_222096D_STAGING",
            'pathname === "/ops" || pathname.startsWith("/ops/")',
            "isReviewRoute && !isReviewLogin && !hasSession",
            "isContentRoute && !isContentLogin && !hasSession",
            "INSPECT_RUNTIME_EB7C40B_STAGING",
            "DIAGNOSE_FORMAL_JOURNEY_EF0A512_STAGING",
            "REPAIR_EDGE_ROUTE_EF0A512_STAGING",
            "id: terraform_init",
            "max_attempts=3",
            "WP08_TERRAFORM_INIT attempt=%s/%s result=START",
            "WP08_TERRAFORM_INIT attempt=%s/%s result=PASS",
            "WP08_TERRAFORM_INIT attempt=%s/%s result=RETRY next_in_seconds=%s",
            "WP08_TERRAFORM_INIT attempt=%s/%s result=FAIL retries_exhausted=true",
            "WP08_TERRAFORM_VALIDATE result=PASS",
            'if [[ "${{ inputs.phase }}" == "deploy" ]]; then',
            'git cat-file -e "$candidate:apps/web/src/app/health/ready/route.ts"',
            'git show "$candidate:deploy/staging/compose.yaml"',
            'git show "$candidate:apps/web/src/proxy.ts"',
            'git show "$candidate:apps/web/src/proxy.ts" | grep -Fq \'pathname === "/ops" || pathname.startsWith("/ops/")\'',
            'git show "$candidate:apps/web/src/proxy.ts" | grep -Fq \'isReviewRoute && !isReviewLogin && !hasSession\'',
            'git show "$candidate:apps/web/src/app/review/login/page.tsx"',
            "进入主管评审",
            'git show "$candidate:apps/web/src/proxy.ts" | grep -Fq \'isContentRoute && !isContentLogin && !hasSession\'',
            'git show "$candidate:apps/web/src/app/content/login/page.tsx"',
            "使用飞书进入",
            'git show "$candidate:apps/web/src/app/ops/invite-management-panel.tsx"',
            "formatJourneyOptionLabel(journey)",
            'git show "$candidate:.github/workflows/staging.yml"',
            "WP08_SURFACE_CHECK",
            'git show "$candidate:.github/workflows/staging.yml"',
            "attempts=12",
            'git show "$candidate:apps/web/src/lib/server/oauth-proxy.ts"',
            'git show "$candidate:scripts/wp08_web_runtime_check.py"',
            'git show "$candidate:scripts/wp08_web_runtime_check.py"',
            'git show "$candidate:scripts/wp08_web_runtime_check.py"',
            "anonymous_content=login-page",
            "oauth_redirect=root-relative-content",
            "expired_reviewer=explicit-relogin",
            'git show "$candidate:apps/worker/journey_worker/main.py"',
            '"runtime.snapshot"',
            'git show "$candidate:apps/worker/journey_worker/main.py"',
            "active_recipient_exists",
            'git show "$candidate:scripts/wp08_prepare_deploy.py"',
            "scripts/wp07_image_archive.py verify-files",
            "artifacts/wp07-candidate/image-archives.json",
            "artifacts/wp07-candidate/images/api.tar",
            "WP08_BUNDLE_TRANSFER=START transport=ssh-compressed",
            "WP08_BUNDLE_TRANSFER=PASS transport=ssh-compressed",
            "timeout --signal=TERM --kill-after=30s 20m ssh",
            "WP08_BUNDLE_TRANSFER=FAIL cleanup=exact-release",
            "timeout --signal=TERM --kill-after=30s 2m ssh",
            'rm -rf -- \'$release\'',
            'NOTIFICATION_RESULT_URL": f"https://{STAGING_HOST}/app/result"',
            'git show "$candidate:scripts/wp08_prepare_deploy.py" | grep -Fq \'"DB_POOL_SIZE": "20"\'',
            'git show "$candidate:scripts/wp08_prepare_deploy.py" | grep -Fq \'"DB_MAX_OVERFLOW": "5"\'',
            'git show "$candidate:scripts/wp08_prepare_deploy.py" | grep -Fq \'"DB_POOL_SIZE": "2"\'',
            'git show "$candidate:scripts/wp08_prepare_deploy.py" | grep -Fq \'"DB_MAX_OVERFLOW": "1"\'',
            'git cat-file -e "$candidate:docs/runbooks/WP11_STAGING_INTEGRATIONS.md"',
            'git cat-file -e "$candidate:scripts/wp12b_load.py"',
            'git cat-file -e "$candidate:apps/api/journey_api/wp12b_synthetic.py"',
            'git cat-file -e "$candidate:config/wp12b_multitenant_load.json"',
            'if [[ "${{ inputs.phase }}" == "deploy-web" || "${{ inputs.phase }}" == "repair-runtime" ]]; then',
            "python3 scripts/wp08_web_only.py check",
            '--mode "$mode"',
            "mode=runtime-repair",
            "      - name: Audit frozen ECS to RDS allowlist binding",
            "        if: inputs.phase == 'audit'",
            "terraform -chdir=infra/staging state pull >\"$state_file\"",
            "python3 -m scripts.wp08_rds_network_audit",
            "      - name: Reconcile the exact existing staging DNS record",
            "        if: inputs.phase == 'provision'",
            "scripts/wp08_dns_record.py",
            'terraform state pull | jq -er',
            'terraform import "$address" "$expected_id"',
            "      - name: Apply reviewed infrastructure",
            "        if: inputs.phase == 'provision'",
            'terraform show -json "$plan_file" | python3 ../../scripts/wp08_plan_guard.py',
            'terraform apply -auto-approve "$plan_file"',
            '-var="deploy_cidr=127.0.0.1/32"',
            "      - name: Read frozen Alpha pilot infrastructure",
            "        if: inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime' || inputs.phase == 'inspect-runtime' || inputs.phase == 'diagnose-publication' || inputs.phase == 'repair-edge-route' || inputs.phase == 'cleanup-failed-release'",
            "        id: frozen_infrastructure",
            "terraform output -raw staging_public_ip",
            "      - name: Open exact runner SSH ingress",
            "if: inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime' || inputs.phase == 'inspect-runtime' || inputs.phase == 'diagnose-publication' || inputs.phase == 'repair-edge-route' || inputs.phase == 'cleanup-failed-release'",
            "python3 -m scripts.wp08_security_group open",
            "      - name: Execute PII-free runtime inventory",
            "if: inputs.phase == 'inspect-runtime'",
            "scripts/wp08_runtime_inventory.py",
            "      - name: Diagnose failed formal Journey publication",
            "if: inputs.phase == 'diagnose-publication'",
            "scripts/wp19_publication_diagnostic.py",
            "      - name: Apply reviewed Edge route repair",
            "id: edge_repair_apply",
            "if: inputs.phase == 'repair-edge-route'",
            "scripts/wp08_edge_route_repair.py",
            "      - name: Verify deterministic staging and preserved production routes",
            "if: inputs.phase == 'repair-edge-route'",
            "https://journey.muchenai.com/health/ready",
            "8e56e759152efcbf17f4373f2132e02a8762af81",
            "      - name: Roll back Edge route after failed verification",
            "if: failure() && inputs.phase == 'repair-edge-route'",
            "steps.edge_repair_apply.outcome == 'success'",
            "steps.edge_repair_apply.outcome == 'failure'",
            "      - name: Remove successful Edge repair state",
            "if: success() && inputs.phase == 'repair-edge-route'",
            "      - name: Remove exact failed pre-start release",
            "if: inputs.phase == 'cleanup-failed-release'",
            "scripts/wp08_failed_release_cleanup.py",
            "'30808632624'",
            "      - name: Prepare private deploy bundle",
            "if: inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime'",
            "      - name: Deploy exact registry digests",
            "if: inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime'",
            "      - name: Verify external TLS and release surface",
            "if: inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime'",
            "origin=https://staging-vnext.muchenai.com",
            '"$origin/health/ready"',
            '"$origin/ops"',
            '"$origin/review"',
            '"$origin/content"',
            '"$origin/content/login"',
            "'%{http_code}'",
            '= "401"',
            '= "303"',
            'test "$content_location" = "/content/login"',
            "^cache-control: .*no-store",
            "使用飞书进入",
            "WP08_SURFACE_CHECK",
            "WP08_SURFACE_ATTEMPT",
            "attempts=12",
            'for attempt in $(seq 1 "$attempts")',
            "next_in_seconds=5",
            "--connect-timeout 2",
            "--max-time 3",
            "-o ServerAliveInterval=15",
            "-o ServerAliveCountMax=4",
            "-o TCPKeepAlive=yes",
            "      - name: Close SSH ingress",
            "if: always() && (inputs.phase == 'deploy' || inputs.phase == 'deploy-web' || inputs.phase == 'repair-runtime' || inputs.phase == 'inspect-runtime' || inputs.phase == 'diagnose-publication' || inputs.phase == 'repair-edge-route' || inputs.phase == 'cleanup-failed-release') && steps.frozen_infrastructure.outputs.security_group_id != ''",
            "python3 -m scripts.wp08_security_group close",
        )
    )
    workflow.write_text(source)
    staging.validate_workflow(workflow)

    workflow.write_text(source.replace("expired_reviewer=explicit-relogin", "missing-expiry-contract"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("formatJourneyOptionLabel(journey)", "missing-journey-label-contract"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("WP08_SURFACE_ATTEMPT", "missing-surface-attempt-contract"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("max_attempts=3", "max_attempts=4"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("retries_exhausted=true", "retries_exhausted=false"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("-o ServerAliveInterval=15", ""))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("-o ServerAliveCountMax=4", ""))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("-o TCPKeepAlive=yes", ""))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("scripts/wp08_plan_guard.py", "scripts/missing.py", 1))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(source.replace("scripts.wp08_security_group close", "missing"))
    with pytest.raises(staging.StagingError, match="missing bootstrap marker"):
        staging.validate_workflow(workflow)

    workflow.write_text(
        source.replace(
            "terraform output -raw staging_public_ip",
            "terraform output -raw staging_public_ip\nterraform plan",
        )
    )
    with pytest.raises(staging.StagingError, match="must not reconcile"):
        staging.validate_workflow(workflow)


def test_wp09_operator_bootstrap_workflow_encrypts_the_only_link(tmp_path: Path, monkeypatch):
    bootstrap = tmp_path / "wp09-operator-bootstrap.yml"
    source = "\n".join(
        (
            "workflow_dispatch:",
            "26d56010125024ca2dbc6e85f7dfeb59857f93dd",
            "CREATE_15M_OPERATOR_LINK_26D5601",
            "recipient_public_key_b64",
            "group: wp08-volcengine-staging",
            "environment: staging",
            "terraform output -raw staging_public_ip",
            "terraform output -raw staging_security_group_id",
            "python3 -m scripts.wp08_security_group open",
            "cat /srv/journey-next-staging/DEPLOYED_CANDIDATE",
            ". ./.deployment.env",
            "- name: Generate and encrypt the 15-minute Operator link",
            "operator_id=$(docker compose exec < /dev/null",
            "python -m journey_api.wp09_bootstrap < /dev/null",
            "--expires-in-minutes 15",
            "--confirm CREATE_STAGING_OPERATOR_LINK",
            "openssl pkeyutl -encrypt",
            "rsa_padding_mode:oaep",
            "rsa_oaep_md:sha256",
            "rsa_mgf1_md:sha256",
            "wp09-operator-link.json.enc",
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
            "retention-days: 1",
            "if: always() && steps.frozen_infrastructure.outputs.security_group_id != ''",
            "python3 -m scripts.wp08_security_group close",
        )
    )
    bootstrap.write_text(source)
    monkeypatch.setattr(staging, "WP09_BOOTSTRAP_WORKFLOW", bootstrap)

    staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source.replace("rsa_oaep_md:sha256", "rsa_oaep_md:sha1"))
    with pytest.raises(staging.StagingError, match="missing marker"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source.replace("retention-days: 1", "retention-days: 14"))
    with pytest.raises(staging.StagingError, match="exactly one day"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source + '\nrun: echo "$bootstrap_json"\n')
    with pytest.raises(staging.StagingError, match="forbidden marker"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source.replace("python -m journey_api.wp09_bootstrap", "python -m journey_api.wp09_bootstrap\npython -m journey_api.wp09_bootstrap"))
    with pytest.raises(staging.StagingError, match="exactly once"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source.replace(". ./.deployment.env", ":"))
    with pytest.raises(staging.StagingError, match="deployed image environment"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source.replace("python -m journey_api.wp09_bootstrap < /dev/null", "python -m journey_api.wp09_bootstrap"))
    with pytest.raises(staging.StagingError, match="remote script stdin"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)

    bootstrap.write_text(source)
    monkeypatch.setattr(
        staging,
        "load_contract",
        lambda: {
            "candidate_commit": "26d56010125024ca2dbc6e85f7dfeb59857f93dd"
        },
    )
    with pytest.raises(staging.StagingError, match="must remain retired"):
        staging.validate_wp09_bootstrap_workflow(bootstrap)


def test_infrastructure_requires_serial_rds_exclusive_operations(
    tmp_path: Path, monkeypatch
):
    versions, main = infrastructure_files(tmp_path)
    monkeypatch.setattr(staging, "INFRA_VERSIONS", versions)
    monkeypatch.setattr(staging, "INFRA_MAIN", main)
    source = main.read_text()

    main.write_text(
        source.replace(
            "depends_on = [volcenginecc_rdspostgresql_instance_ssl.staging]", ""
        )
    )
    with pytest.raises(staging.StagingError, match="bootstrap marker"):
        staging.validate_infrastructure()

    main.write_text(
        source.replace(
            "depends_on = [volcenginecc_rdspostgresql_db_account.migration]", ""
        )
    )
    with pytest.raises(staging.StagingError, match="bootstrap marker"):
        staging.validate_infrastructure()
