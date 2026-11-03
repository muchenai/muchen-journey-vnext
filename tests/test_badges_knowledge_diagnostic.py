"""The stopped release diagnostic emits categories and only touches scratch resources."""
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('restore_diagnostic', ROOT/'deploy/badges-knowledge/diagnose_restore.py')
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.mark.parametrize(('message','category'), [
    (b'no space left on device private','DISK_FULL'),
    (b'Permission denied private','PERMISSION_DENIED'),
    (b'password authentication failed private','AUTHENTICATION'),
    (b'container is not running private','CONTAINER_EXITED'),
    (b'connection refused private','CONNECTION_REFUSED'),
    (b'private unknown error','UNCLASSIFIED'),
])
def test_diagnostics_emit_only_fixed_error_categories(message, category):
    assert diagnostic.classify(message) == category
    assert 'private' not in diagnostic.classify(message)


def test_diagnostic_is_bound_to_stopped_package_and_protected_production_gate():
    assert diagnostic.CANDIDATE == '2bab0cefe55447c9d64af81dd5c52f5db67db09c'
    assert str(diagnostic.SOURCE).endswith('/41592358400-1-activate')
    assert set(diagnostic.EXPECTED) == {'activate.py','prepare.py','canary_schema_upgrade.py',
        'wp31_database_snapshot.py','db_facts.py','db_facts_control.py','grant_runtime.py',
        'facts_guard.py','restore_backup.py','diagnose_backup.py'}
    workflow = (ROOT/'.github/workflows/badges-knowledge-diagnose.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    source = (ROOT/'deploy/badges-knowledge/diagnose_restore.py').read_text()
    assert 'app.activate(' not in source and 'alembic\',\'upgrade' not in source
    assert "'journey.operation=restore-probe'" in source
