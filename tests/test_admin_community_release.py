"""Release guardrails must reject an unverified baseline and unsafe rollback."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with patch.dict(sys.modules):
    sys.modules['canary_schema_upgrade'] = load('canary_schema_upgrade', 'scripts/canary_schema_upgrade.py')
    sys.modules['prepare'] = load('prepare', 'deploy/exploration-release/prepare.py')
    release = load('learner_release', 'deploy/admin-community/activate.py')


def manifest():
    result = json.loads((ROOT / 'deploy/admin-community/baseline.json').read_text())
    result['candidate'] = 'a' * 40
    return result


def prior_files(path):
    if path.name == 'schema-upgrade-prepared.json':
        return json.dumps({'manifest': {'candidate': release.BASE,
            'images': {'api': 'sha256:'+'b'*64, 'web': 'sha256:'+'c'*64}}}).encode()
    assert path.name == 'activation-receipt.json'
    return json.dumps({'release': release.BASE, 'status': 'PASS', 'schema': release.SOURCE_SCHEMA}).encode()


def test_old_images_bound_to_verified_prior_release_without_owner_bootstrap():
    with patch.object(release, 'read_file', side_effect=prior_files):
        activation = release.Activation(manifest(), Path('/package'))
    assert activation.old_images == {'api':'sha256:'+'b'*64, 'web':'sha256:'+'c'*64}
    assert str(activation.new).endswith('-admin-community')
    assert release.TARGET_SCHEMA == '0051_community_modules'


@pytest.mark.parametrize('change', ['receipt', 'candidate', 'image', 'path', 'override'])
def test_unverified_baseline_stops_before_any_mutation(change):
    value = manifest()
    if change == 'path':
        value['base_release'] = '/other/path'
    if change == 'override':
        value['old_images'] = {'api': 'unsafe'}
    def altered(path):
        data = json.loads(prior_files(path))
        if change == 'receipt' and 'status' in data:
            data['status'] = 'FAIL'
        if 'manifest' in data:
            if change == 'candidate':
                data['manifest']['candidate'] = 'd'*40
            if change == 'image':
                data['manifest']['images']['web'] = 'latest'
        return json.dumps(data).encode()
    with patch.object(release, 'read_file', side_effect=altered):
        with pytest.raises(release.UpgradeError):
            release.Activation(value, Path('/package'))


def test_existing_model_config_and_credentials_are_preserved():
    raw = b'APP_RELEASE=old\nAI_MODEL=old-model\nAI_API_KEY_FILE=/run/secrets/ai_api_key\nIDENTITY_SUBJECT_SECRET=unchanged\n'
    changed = release.add_env(raw, {'APP_RELEASE':'new', 'AI_MODEL':'deepseek-v4.1-flash',
                                   'AI_FALLBACK_MODEL':'deepseek-v4-pro-0813'})
    assert release.env_values(changed) == {**release.env_values(raw), 'APP_RELEASE':'new',
        'AI_MODEL':'deepseek-v4.1-flash', 'AI_FALLBACK_MODEL':'deepseek-v4-pro-0813'}
    with pytest.raises(release.UpgradeError):
        release.add_env(raw, {'UNSAFE':'value\nOTHER=bad'})


def activation_for_switch():
    with patch.object(release, 'read_file', side_effect=prior_files):
        return release.Activation(manifest(), Path('/package'))


@pytest.mark.parametrize('busy', [b'1', b'0'])
def test_busy_ai_prevents_downtime_and_migration_failure_restores_prior_app(busy):
    app = activation_for_switch()
    def files(path):
        if path.name == 'backup-receipt.json':
            return json.dumps({'restore':'PASS','candidate':'a'*40,'backup_sha256':'hash'}).encode()
        if path.name == 'migration-rehearsal.json':
            return json.dumps({'schema':release.TARGET_SCHEMA}).encode()
        raise AssertionError(path)
    with patch.object(app,'verify_base'), patch.object(app,'verify_prepared'), \
         patch.object(release,'read_file',side_effect=files), patch.object(release,'file_sha',return_value='hash'), \
         patch.object(app,'docker_api',side_effect=[busy, b'wrong-schema']), \
         patch.object(release,'compose') as compose, patch.object(app,'guard',return_value={'fixed':'facts'}), \
         patch.object(app,'up') as up, patch.object(app,'healthy'), patch.object(app,'current',return_value=app.base):
        with pytest.raises(release.UpgradeError):
            app.activate()
        if busy == b'1':
            compose.assert_not_called()
            up.assert_not_called()
        else:
            compose.assert_called_once_with(app.base, 'stop', 'web', 'api', timeout=90)
            up.assert_called_once_with(app.base)


def test_activation_applies_pinned_upgrade_and_grants_before_starting_application():
    app = activation_for_switch()
    app.images.update(api='sha256:'+'d'*64, web='sha256:'+'e'*64)
    def files(path):
        if path.name == 'backup-receipt.json':
            return json.dumps({'restore':'PASS','candidate':'a'*40,'backup_sha256':'hash'}).encode()
        if path.name == 'migration-rehearsal.json':
            return json.dumps({'schema':release.TARGET_SCHEMA}).encode()
        raise AssertionError(path)
    with patch.object(app,'verify_base'), patch.object(app,'verify_prepared'), \
         patch.object(release,'read_file',side_effect=files), patch.object(release,'file_sha',return_value='hash'), \
         patch.object(app,'docker_api',side_effect=[b'0',release.SOURCE_SCHEMA.encode(),b'',release.TARGET_SCHEMA.encode(),b'',b'']) as api, \
         patch.object(release,'compose'), patch.object(app,'guard',return_value={'learner_notification_reads':[3,'unchanged']}), \
         patch.object(app,'up') as up, patch.object(app,'healthy'), patch.object(app,'pointer'), \
         patch.object(release,'run'), patch.object(release,'write_new'):
        app.activate()
        assert api.call_args_list[2].args == ('secrets/migration.env','alembic','upgrade',release.TARGET_SCHEMA)
        assert api.call_args_list[4].args == ('secrets/migration.env','python','/tmp/grant_runtime.py')
        assert '>=0' in api.call_args_list[-1].args[-1]
        up.assert_called_once_with(app.new)


def test_phone_and_notification_receipts_are_included_in_fingerprints():
    from journey_api.db import engine
    from sqlalchemy import text
    guard = load('admin_guard', 'deploy/admin-community/facts_guard.py')
    with engine.connect() as connection:
        connection.execute(text('CREATE TEMP TABLE external_identities (id integer, phone_ciphertext text) ON COMMIT DROP'))
        connection.execute(text("INSERT INTO external_identities VALUES (1, 'old')"))
        before = tuple(connection.execute(guard.fingerprint_query('external_identities')).one())
        connection.execute(text("UPDATE external_identities SET phone_ciphertext='changed'"))
        assert tuple(connection.execute(guard.fingerprint_query('external_identities')).one()) != before
        connection.execute(text('CREATE TEMP TABLE learner_notification_reads (id integer) ON COMMIT DROP'))
        empty = tuple(connection.execute(guard.fingerprint_query('learner_notification_reads')).one())
        connection.execute(text('INSERT INTO learner_notification_reads VALUES (1)'))
        assert tuple(connection.execute(guard.fingerprint_query('learner_notification_reads')).one()) != empty
        connection.rollback()

def test_release_packages_authenticated_restore_helpers_and_keeps_environment_gate():
    workflow=(ROOT/'.github/workflows/admin-community-release.yml').read_text()
    package=(ROOT/'deploy/admin-community/package.py').read_text()
    source=(ROOT/'deploy/admin-community/activate.py').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert "run['head_sha']==p['candidate']" in workflow
    assert 'timeout-minutes: 180' in workflow
    assert '"restore_backup.py":' in package and '"diagnose_backup.py":' in package
    assert 'install_safe_command_reporting(sys.modules[__name__])' in source
    assert 'return restore_verified_backup(' in source
    assert release.BASE == '356b0ad02ea6cd8bed89e5068c040a88cbe3bb1e'
