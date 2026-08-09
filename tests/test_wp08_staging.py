import json
from pathlib import Path

import pytest

import scripts.wp08_staging as staging


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
                'SECRETS="$PWD/secrets"',
                "docker compose -f compose.yaml -f compose.migrate.yaml config --quiet",
                "docker compose pull",
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
                'timeout --signal=TERM --kill-after=30s 8m docker pull "$WEB_IMAGE"',
                'timeout --signal=TERM --kill-after=30s 8m docker pull "$API_IMAGE"',
                "alembic upgrade 0014_wp12_data_lifecycle",
                "docker compose up -d --no-deps --wait --wait-timeout 180 web",
                "WP08_WEB_ONLY_ROLLBACK=START",
                "WP08_RUNTIME_REPAIR_ROLLBACK=START",
                "WP08_RUNTIME_REPAIR=PASS",
                "DEPLOYED_CANDIDATE.tmp",
                "DEPLOYED_COMPONENTS.json",
                "WP08_WEB_ONLY_DEPLOY=PASS",
                'if [[ "$DEPLOY_MODE" == "runtime-repair" ]]',
                "verify_runtime_repair_prestate",
                'docker pull "$API_IMAGE"',
                'docker pull "$WORKER_IMAGE"',
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
            "docker compose pull\n"
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api python -c \"from pathlib import Path; "
            "Path('/run/secrets/volcengine-rds-ca.pem').read_bytes()\"\n"
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api alembic upgrade head",
            "docker compose -f compose.yaml -f compose.migrate.yaml "
            "run --rm --no-deps api alembic upgrade head\n"
            "docker compose pull\n"
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
        "  web:\n"
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
        "  web:\n"
        "    healthcheck:\n"
        "      test: http://localhost:3000/ops\n"
        "  edge:\n"
        f"    image: {staging.EDGE_IMAGE}\n"
    )
    with pytest.raises(staging.StagingError, match="readiness route"):
        staging.validate_staging_compose(compose)

    compose.write_text(
        "services:\n  edge:\n    image: caddy:2.10.2-alpine@sha256:" + "a" * 64 + "\n"
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
        "  web:\n"
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
            "          - deploy",
            "          - inspect-runtime",
            "          - diagnose-publication",
            "          - repair-edge-route",
            "          - cleanup-failed-release",
            "inputs.confirmation == 'AUDIT_WP08_RDS_NETWORK'",
            "inputs.confirmation == 'CLEANUP_FAILED_RELEASE_EF0A512_30808632624'",
            "DEPLOY_WEB_222096D_ON_02863D0_STAGING",
            "REPAIR_RUNTIME_02863D0_FOR_WEB_222096D_STAGING",
            '["/ops", "/review"]',
            "isContentRoute && !isContentLogin && !hasSession",
            "INSPECT_RUNTIME_3B7D757_STAGING",
            "DIAGNOSE_FORMAL_JOURNEY_EF0A512_STAGING",
            "REPAIR_EDGE_ROUTE_EF0A512_STAGING",
            "id: terraform_init",
            'if [[ "${{ inputs.phase }}" == "deploy" ]]; then',
            'git cat-file -e "$candidate:apps/web/src/app/health/ready/route.ts"',
            'git show "$candidate:deploy/staging/compose.yaml"',
            'git show "$candidate:apps/web/src/proxy.ts"',
            'git show "$candidate:apps/web/src/proxy.ts" | grep -Fq \'["/ops", "/review"]\'',
            'git show "$candidate:apps/web/src/proxy.ts" | grep -Fq \'isContentRoute && !isContentLogin && !hasSession\'',
            'git show "$candidate:apps/web/src/app/content/login/page.tsx"',
            "使用飞书进入",
            'git show "$candidate:apps/web/src/app/ops/invite-management-panel.tsx"',
            "formatJourneyOptionLabel(journey)",
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
            "https://staging-vnext.muchenai.com/health/ready",
            "https://staging-vnext.muchenai.com/ops",
            "https://staging-vnext.muchenai.com/review",
            "https://staging-vnext.muchenai.com/content",
            "https://staging-vnext.muchenai.com/content/login",
            "'%{http_code}'",
            '= "401"',
            '= "303"',
            "^location: /content/login",
            "^cache-control: .*no-store",
            "使用飞书进入",
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
