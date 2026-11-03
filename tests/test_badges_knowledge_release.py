"""The combined release preserves its predecessor and rehearses the additive migration."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


with patch.dict(sys.modules):
    sys.modules['canary_schema_upgrade'] = load('canary_schema_upgrade', 'scripts/canary_schema_upgrade.py')
    sys.modules['prepare'] = load('prepare', 'deploy/exploration-release/prepare.py')
    release = load('combined_release', 'deploy/badges-knowledge/activate.py')


def manifest():
    data = json.loads((ROOT/'deploy/badges-knowledge/baseline.json').read_text())
    data['candidate'] = 'a'*40
    return data


def prior(path):
    if path.name == 'schema-upgrade-prepared.json':
        return json.dumps({'manifest':{'candidate':release.BASE,'images':{'api':'sha256:'+'b'*64,'web':'sha256:'+'c'*64}}}).encode()
    return json.dumps({'release':release.BASE,'status':'PASS','schema':release.SOURCE_SCHEMA}).encode()


def test_exact_predecessor_schema_and_production_approval_gate():
    with patch.object(release,'read_file',side_effect=prior):
        app = release.Activation(manifest(),Path('/package'))
    assert str(app.base).endswith(release.BASE+'-learner-navigation')
    assert str(app.new).endswith('-badges-knowledge')
    assert release.SOURCE_SCHEMA == '0051_community_modules'
    assert release.TARGET_SCHEMA == '0052_knowledge_publication'
    assert release.NEW_TABLES == ('knowledge_favorites',)
    workflow = (ROOT/'.github/workflows/badges-knowledge-release.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert "run['head_sha']==p['candidate']" in workflow
    grants = (ROOT/'deploy/badges-knowledge/grant_runtime.py').read_text()
    assert 'public.knowledge_favorites TO journey_next_runtime' in grants
    assert 'install_project36_medals' not in (ROOT/'deploy/badges-knowledge/activate.py').read_text()


@pytest.mark.parametrize('field', ['base_release','old_images'])
def test_unverified_baseline_is_rejected(field):
    data = manifest(); data[field] = '/wrong' if field == 'base_release' else {'web':'latest'}
    with patch.object(release,'read_file',side_effect=prior), pytest.raises(release.UpgradeError):
        release.Activation(data,Path('/package'))


def test_migration_and_only_new_runtime_table_precede_app_switch():
    with patch.object(release,'read_file',side_effect=prior):
        app = release.Activation(manifest(),Path('/package'))
    app.images.update(api='sha256:'+'d'*64,web='sha256:'+'e'*64)
    def files(path):
        if path.name == 'backup-receipt.json':
            return json.dumps({'restore':'PASS','candidate':'a'*40,'backup_sha256':'hash'}).encode()
        return json.dumps({'schema':release.TARGET_SCHEMA}).encode()
    with patch.object(app,'verify_base'), patch.object(app,'verify_prepared'), \
         patch.object(release,'read_file',side_effect=files), patch.object(release,'file_sha',return_value='hash'), \
         patch.object(app,'docker_api',side_effect=[b'0',release.SOURCE_SCHEMA.encode(),b'',release.TARGET_SCHEMA.encode(),b'',b'']) as api, \
         patch.object(release,'compose'), patch.object(app,'guard',return_value={'existing':'unchanged'}), \
         patch.object(app,'up') as up, patch.object(app,'healthy'), patch.object(app,'pointer'), \
         patch.object(release,'run'), patch.object(release,'write_new'):
        app.activate()
        assert api.call_args_list[2].args == ('secrets/migration.env','alembic','upgrade',release.TARGET_SCHEMA)
        assert api.call_args_list[4].args == ('secrets/migration.env','python','/tmp/grant_runtime.py')
        up.assert_called_once_with(app.new)
