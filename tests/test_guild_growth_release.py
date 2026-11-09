"""Guard the split production baseline, additive schema, and rollback boundary."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
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
    sys.modules['disk_space'] = load('disk_space', 'deploy/academy-release/disk_space.py')
    sys.modules['image_transport'] = load('image_transport', 'deploy/academy-release/image_transport.py')
    release = load('guild_growth_release', 'deploy/guild-growth-release/activate.py')
guard = load('guild_growth_facts_guard', 'deploy/guild-growth-release/facts_guard.py')

API_IMAGE = 'sha256:' + 'b' * 64
WEB_IMAGE = 'sha256:' + 'c' * 64


def manifest():
    result = json.loads((ROOT / 'deploy/guild-growth-release/baseline.json').read_text())
    result['candidate'] = 'a' * 40
    return result


def baseline_files():
    files = {name: b'original-config' for name in release.COPY_FILES + release.ENV_FILES + tuple(release.SECRET_FILES.values())}
    files['.deployment.env'] = f'API_IMAGE={API_IMAGE}\nWEB_IMAGE={WEB_IMAGE}\n'.encode()
    files['secrets/api.env'] = f'APP_RELEASE={release.BASE}\n'.encode()
    files['secrets/web.env'] = f'APP_RELEASE={release.WEB_BASE}\n'.encode()
    return files


def prior(path):
    files = baseline_files()
    if path.name == 'schema-upgrade-prepared.json':
        return json.dumps({'manifest': {'candidate': release.BASE, 'images': {'api': API_IMAGE, 'web': 'sha256:' + 'd' * 64}}}).encode()
    if path.name == 'activation-receipt.json':
        return json.dumps({'release': release.BASE, 'status': 'PASS', 'schema': release.SOURCE_SCHEMA}).encode()
    if path.name == 'web-release-receipt.json':
        return json.dumps({'result': 'PASS', 'web_candidate': release.WEB_BASE, 'api_candidate': release.BASE,
            'schema': release.SOURCE_SCHEMA, 'previous_release': str(release.ROOT / 'releases' / release.API_BASE_DIRECTORY),
            'web_image_id': WEB_IMAGE, 'configuration_hashes': {name: release.digest(raw) for name, raw in files.items()}}).encode()
    return files[path.relative_to(release.ROOT / 'releases' / release.BASE_DIRECTORY).as_posix()]


def application():
    with patch.object(release, 'read_file', side_effect=prior):
        result = release.Activation(manifest(), Path('/package'))
    result.images.update(api='sha256:' + 'e' * 64, web='sha256:' + 'f' * 64)
    result.protected_runtime = {}
    return result


def test_two_successful_release_receipts_bind_current_web_and_older_api():
    app = application()
    assert app.old_images == {'api': API_IMAGE, 'web': WEB_IMAGE}
    assert app.base.name == release.WEB_BASE + '-login-layout-recovery-42173791325-1'
    assert app.new.name == 'a' * 40 + '-guild-growth'
    assert (release.SOURCE_SCHEMA, release.TARGET_SCHEMA) == ('0054_academy_covers', '0056_guild_halls')
    assert release.NEW_TABLES == ('guild_certification_requests', 'guild_memberships', 'guild_selections', 'guild_task_submissions')


@pytest.mark.parametrize('field,value', [
    ('base_release', '/wrong'), ('base_candidate', 'b' * 40),
    ('base_web_candidate', 'b' * 40), ('candidate', release.WEB_BASE),
    ('old_images', {'web': 'latest'}),
])
def test_manifest_cannot_repin_the_existing_baseline(field, value):
    data = manifest()
    data[field] = value
    with patch.object(release, 'read_file', side_effect=prior), pytest.raises(release.UpgradeError):
        release.Activation(data, Path('/package'))


@pytest.mark.parametrize('field,value', [('result', 'FAIL'), ('web_candidate', 'b' * 40), ('api_candidate', 'b' * 40),
                                        ('schema', '0052_knowledge_publication'), ('previous_release', '/other')])
def test_web_receipt_requires_the_exact_successful_split_baseline(field, value):
    def changed(path):
        data = prior(path)
        if path.name == 'web-release-receipt.json':
            receipt = json.loads(data)
            receipt[field] = value
            return json.dumps(receipt).encode()
        return data
    with patch.object(release, 'read_file', side_effect=changed), pytest.raises(release.UpgradeError, match='WEB_BASE_RECEIPT'):
        release.Activation(manifest(), Path('/package'))


def test_changed_live_configuration_stops_before_any_operation():
    def changed(path):
        return prior(path) + b'\n' if path.name == 'api.env' else prior(path)
    with patch.object(release, 'read_file', side_effect=changed), pytest.raises(release.UpgradeError, match='BASE_CONFIGURATION_CHANGED'):
        release.Activation(manifest(), Path('/package'))


def test_configuration_proof_cannot_address_an_unrelated_path():
    def changed(path):
        data = prior(path)
        if path.name == 'web-release-receipt.json':
            receipt = json.loads(data)
            receipt['configuration_hashes']['../other'] = 'd' * 64
            return json.dumps(receipt).encode()
        return data
    with patch.object(release, 'read_file', side_effect=changed), pytest.raises(release.UpgradeError, match='BASE_CONFIGURATION_PATH'):
        release.Activation(manifest(), Path('/package'))


def container(name, service, mounts):
    return {'Id': name, 'Name': '/' + name, 'Image': 'immutable',
        'Config': {'Labels': {'com.docker.compose.project': release.PROJECT, 'com.docker.compose.service': service}},
        'HostConfig': {'ReadonlyRootfs': True}, 'Mounts': mounts}


def test_non_application_mount_order_is_ignored_but_mount_values_are_preserved():
    rows = [container('api', 'api', []), container('web', 'web', []),
            container('worker', 'worker', [{'Source': '/b'}, {'Source': '/a'}])]
    with patch.object(release, 'run', side_effect=[b'api web worker', json.dumps(rows).encode()]):
        first = release.protected_containers()
    rows[2]['Mounts'].reverse()
    with patch.object(release, 'run', side_effect=[b'api web worker', json.dumps(rows).encode()]):
        second = release.protected_containers()
    assert first == second and set(first) == {'/worker'}
    rows[2]['Mounts'][0]['Source'] = '/different'
    with patch.object(release, 'run', side_effect=[b'api web worker', json.dumps(rows).encode()]):
        third = release.protected_containers()
    with patch.object(release, 'protected_containers', return_value=third), pytest.raises(release.UpgradeError, match='PROTECTED_CONTAINER_CHANGED'):
        release.verify_protected_containers(first)


class FactConnection:
    def __init__(self, new_rows=0):
        self.new_rows = new_rows
    def execute(self, query):
        sql = str(query)
        if 'information_schema.tables' in sql:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ['academy_videos', 'academy_learning_records', 'knowledge_favorites', 'guild_memberships']))
        if 'FROM "guild_memberships"' in sql:
            return SimpleNamespace(scalar_one=lambda: self.new_rows)
        if 'FROM ' in sql:
            return SimpleNamespace(one=lambda: (7, 'unchanged'))
        return None


def test_existing_academy_data_is_fingerprinted_instead_of_required_empty():
    assert guard.snapshot(FactConnection()) == {name: [7, 'unchanged'] for name in ('academy_videos', 'academy_learning_records', 'knowledge_favorites')}


def test_new_guild_activity_blocks_old_application_rollback():
    with pytest.raises(AssertionError, match='NEW_GUILD_ACTIVITY'):
        guard.snapshot(FactConnection(1))


def activation_receipts(path):
    if path.name == 'backup-receipt.json':
        return json.dumps({'restore': 'PASS', 'candidate': 'a' * 40, 'backup_sha256': 'hash'}).encode()
    return json.dumps({'schema': release.TARGET_SCHEMA}).encode()


def activation_patches(app):
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(app, 'verify_base'))
    stack.enter_context(patch.object(app, 'verify_prepared'))
    stack.enter_context(patch.object(release, 'verify_protected_containers'))
    stack.enter_context(patch.object(release, 'read_file', side_effect=activation_receipts))
    stack.enter_context(patch.object(release, 'file_sha', return_value='hash'))
    stack.enter_context(patch.object(release, 'write_new'))
    stack.enter_context(patch.object(app, 'pointer'))
    stack.enter_context(patch.object(app, 'current', return_value=app.base))
    return stack


def test_migration_grants_and_protection_checks_precede_success_receipt():
    app = application()
    with activation_patches(app), patch.object(app, 'docker_api', side_effect=[b'0', release.SOURCE_SCHEMA.encode(), b'', release.TARGET_SCHEMA.encode(), b'', b'']) as api, \
         patch.object(release, 'compose'), patch.object(app, 'guard', return_value={'facts': 'same'}), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy'), patch.object(release, 'run', return_value=b'401'):
        app.activate()
        assert api.call_args_list[2].args == ('secrets/migration.env', 'alembic', 'upgrade', release.TARGET_SCHEMA)
        assert api.call_args_list[4].args == ('secrets/migration.env', 'python', '/tmp/grant_runtime.py')
        up.assert_called_once_with(app.new)


@pytest.mark.parametrize('changed', [False, True])
def test_failed_switch_only_rolls_back_when_business_and_new_guild_records_are_unchanged(changed):
    app = application()
    facts = [{'facts': 'before'}, {'facts': 'before'}, {'facts': 'new'} if changed else {'facts': 'before'}]
    with activation_patches(app), patch.object(app, 'docker_api', side_effect=[b'0', release.SOURCE_SCHEMA.encode(), b'', release.TARGET_SCHEMA.encode(), b'', b'']), \
         patch.object(release, 'compose') as compose, patch.object(app, 'guard', side_effect=facts), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy', side_effect=[RuntimeError('unhealthy'), None]), \
         pytest.raises(release.UpgradeError if changed else RuntimeError):
        app.activate()
    assert compose.call_args_list[-1].args == (app.new, 'stop', 'web', 'api')
    assert [call.args[0] for call in up.call_args_list] == [app.new, app.new if changed else app.base]


def test_workflow_binds_successful_mainline_build_and_always_closes_temporary_ingress():
    workflow = (ROOT / '.github/workflows/guild-growth-release.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert "run['head_sha']==p['candidate']" in workflow
    assert "run['status']=='completed' and run['conclusion']=='success'" in workflow
    assert "if: always() && steps.runner.outputs.cidr != ''" in workflow
    assert 'wp08_security_group close' in workflow
    assert 'deploy/guild-growth-release/package.py' in workflow
    assert 'cancel-in-progress: false' in workflow
    grants = (ROOT / 'deploy/guild-growth-release/grant_runtime.py').read_text()
    assert all('public.' + name in grants for name in release.NEW_TABLES)
    assert 'GRANT ALL' not in grants and 'ON ALL TABLES' not in grants
