"""Exercise the actual Canary bundle grant entrypoint without cloud credentials."""

import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/wp15-wartime-production.yml"
TARGET = "journey_next_canary_20260901_c72fea5"


def bundled_module():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow.split("  greenfield_canary:\n", 1)[1].split("  legacy_identity_bootstrap_disabled:\n", 1)[0]
    sources = re.findall(r'cp (deploy/production/[a-z_]+\.py) "\$bundle/grant_runtime\.py"', job)
    assert len(sources) == 1, "Canary must have exactly one grant entrypoint"
    spec = importlib.util.spec_from_file_location("canary_bundle_grant", ROOT / sources[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, sources[0]


def exercise(monkeypatch, database, fail_on_grant=False):
    module, _ = bundled_module()
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    statements = []

    def execute(statement):
        sql = str(statement)
        statements.append(sql)
        if sql == "SELECT current_database()":
            result = MagicMock()
            result.scalar_one.return_value = database
            return result
        if fail_on_grant:
            raise RuntimeError("synthetic grant failure")
        return MagicMock()

    connection.execute.side_effect = execute
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://invalid/" + database)
    monkeypatch.setattr(module, "create_engine", lambda _: engine)
    return module, engine, statements


def test_actual_bundled_grant_accepts_exact_canary(monkeypatch):
    module, engine, statements = exercise(monkeypatch, TARGET)
    module.main()
    assert statements[0] == "SELECT current_database()"
    assert len(statements) == 7
    assert statements[1] == f"GRANT CONNECT ON DATABASE {TARGET} TO journey_next_runtime"
    assert not any("ALL PRIVILEGES" in sql or "SUPERUSER" in sql or "GRANT CREATE" in sql for sql in statements)
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("database", ["journey_next_cutover_20260810", "journey_next_production", "journey_next_restore_20260803", "journey_next_staging", TARGET + "_other"])
def test_wrong_database_rejected_before_any_grant(monkeypatch, database):
    module, engine, statements = exercise(monkeypatch, database)
    with pytest.raises(RuntimeError, match="canary grant runner connected to unexpected database"):
        module.main()
    assert statements == ["SELECT current_database()"]
    engine.dispose.assert_called_once()
    assert engine.begin.return_value.__exit__.call_args.args[0] is RuntimeError


def test_grant_failure_exits_transaction_and_disposes(monkeypatch):
    module, engine, _ = exercise(monkeypatch, TARGET, fail_on_grant=True)
    with pytest.raises(RuntimeError, match="synthetic grant failure"):
        module.main()
    engine.dispose.assert_called_once()
    assert engine.begin.return_value.__exit__.call_args.args[0] is RuntimeError


def test_target_matches_contract_and_migration_mount():
    module, source = bundled_module()
    config = json.loads((ROOT / "config/wp31_greenfield_canary.json").read_text())
    assert module.DATABASE == config["isolated_canary_database"] == TARGET
    assert source == "deploy/production/greenfield_canary_grant_runtime.py"
    mount = (ROOT / "deploy/production/compose.greenfield-canary.migrate.yaml").read_text()
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text()
    assert "./grant_runtime.py:/tmp/grant_runtime.py:ro" in mount
    grant = "api python /tmp/grant_runtime.py"
    assert deploy.index("api alembic upgrade head") < deploy.index(grant) < deploy.index("up -d --wait")


def test_legacy_production_grant_is_not_retargeted():
    source = (ROOT / "deploy/production/wartime_grant_runtime.py").read_text()
    assert 'DATABASE = "journey_next_cutover_20260810"' in source
    workflow = WORKFLOW.read_text()
    operate = workflow.split("  operate:\n", 1)[1]
    assert 'cp deploy/production/wartime_grant_runtime.py "$bundle/grant_runtime.py"' in operate


def test_grant_set_is_dml_only_and_exact(monkeypatch):
    module, _, statements = exercise(monkeypatch, TARGET)
    module.main()
    assert statements[2:] == [
        "GRANT USAGE ON SCHEMA public TO journey_next_runtime",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO journey_next_runtime",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO journey_next_runtime",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO journey_next_runtime",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO journey_next_runtime",
    ]


def test_downstream_boundaries_remain_after_grant():
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text()
    anchors = [
        "api python /tmp/grant_runtime.py",
        'assert after["counts"].get(table) == count',
        "up -d --wait",
        'ln -sfn "$PWD" "$root/current"',
        "WP31_EDGE_MODE=canary",
        "WP31_CANARY_DEPLOY=PASS",
    ]
    assert [deploy.index(x) for x in anchors] == sorted(deploy.index(x) for x in anchors)
    workflow = WORKFLOW.read_text()
    sequence = [
        "      - name: Deploy exact zero-worker Canary against isolated restore",
        "      - name: Bootstrap three controlled identities inside isolated Canary database",
        "      - name: Upload encrypted identity bootstrap result",
        "      - name: Inspect exact public and remote Canary state",
    ]
    assert [workflow.index(x) for x in sequence] == sorted(workflow.index(x) for x in sequence)
    assert "steps.identity_result.outcome == 'failure'" in workflow
    assert "steps.upload_identity_result.outcome == 'failure'" in workflow
