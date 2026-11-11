"""Protect the mixed Web/API baseline and a schema-preserving application release."""
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
    release = load('learner_refinements_release', 'deploy/learner-refinements-release/activate.py')
guard = load('learner_refinements_facts_guard', 'deploy/learner-refinements-release/facts_guard.py')

API_IMAGE = 'sha256:' + 'b' * 64
WEB_IMAGE = 'sha256:' + 'c' * 64


def manifest():
    result = json.loads((ROOT / 'deploy/learner-refinements-release/baseline.json').read_text())
    result['candidate'] = 'a' * 40
    result['package_run_id'] = '123456'
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
    assert app.base.name == release.WEB_BASE + '-profile-growth'
    assert app.new.name == 'a' * 40 + '-learner-refinements'
    assert (release.SOURCE_SCHEMA, release.TARGET_SCHEMA) == ('0056_guild_halls', '0056_guild_halls')
    assert release.RUNTIME_TABLES == ('guild_certification_requests', 'guild_memberships', 'guild_selections', 'guild_task_submissions')


@pytest.mark.parametrize('field,value', [
    ('base_release', '/wrong'), ('base_candidate', 'b' * 40),
    ('base_web_candidate', 'b' * 40), ('candidate', release.WEB_BASE),
    ('old_images', {'web': 'latest'}), ('migrations', {'from': '0054_academy_covers', 'to': '0056_guild_halls'}),
    ('package_run_id', 'invalid'), ('database', 'other_database'),
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
            return SimpleNamespace(one=lambda: (self.new_rows, 'guild-unchanged'))
        if 'FROM ' in sql:
            return SimpleNamespace(one=lambda: (7, 'unchanged'))
        return None


def test_existing_academy_and_guild_data_are_fingerprinted_instead_of_required_empty():
    expected = {name: [7, 'unchanged'] for name in ('academy_videos', 'academy_learning_records', 'knowledge_favorites')}
    expected['guild_memberships'] = [4, 'guild-unchanged']
    assert guard.snapshot(FactConnection(4)) == expected


def test_guild_changes_are_visible_to_the_rollback_fact_guard():
    assert guard.snapshot(FactConnection(4)) != guard.snapshot(FactConnection(5))


def activation_receipts(path):
    if path.name == 'backup-receipt.json':
        return json.dumps({'restore': 'PASS', 'candidate': 'a' * 40, 'backup_sha256': 'hash', 'migration': release.SOURCE_SCHEMA, 'production_migration_applied': False}).encode()
    return json.dumps({'candidate': 'a' * 40, 'schema': release.TARGET_SCHEMA, 'schema_changed': False, 'restore': 'PASS'}).encode()


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


def test_schema_is_verified_read_only_without_migrations_or_grants_before_switch():
    app = application()
    with activation_patches(app), patch.object(app, 'docker_api', return_value=b'0') as api, \
         patch.object(release, 'compose'), patch.object(app, 'guard', return_value={'facts': 'same'}), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy'), patch.object(release, 'run', return_value=b'401'):
        app.activate()
        assert all(call.kwargs.get('read_only') for call in api.call_args_list)
        assert not any('alembic' in call.args or '/tmp/grant_runtime.py' in call.args for call in api.call_args_list)
        assert sum('version_num' in str(call) for call in api.call_args_list) == 2
        up.assert_called_once_with(app.new)
        receipt = json.loads(release.write_new.call_args.args[1])
        assert receipt['schema'] == '0056_guild_halls'
        assert receipt['database_schema_changed'] is False and receipt['database_writes'] == 0
        assert receipt['previous_web_release'] == release.WEB_BASE
        assert receipt['previous_api_release'] == release.BASE


@pytest.mark.parametrize('changed', [False, True])
def test_failed_switch_only_rolls_back_when_existing_guild_records_are_unchanged(changed):
    app = application()
    facts = [{'guild_memberships': [4, 'before']}, {'guild_memberships': [4, 'before']},
             {'guild_memberships': [5, 'new']} if changed else {'guild_memberships': [4, 'before']}]
    with activation_patches(app), patch.object(app, 'docker_api', return_value=b'0'), \
         patch.object(release, 'compose') as compose, patch.object(app, 'guard', side_effect=facts), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy', side_effect=[RuntimeError('unhealthy'), None]) as healthy, \
         pytest.raises(release.UpgradeError if changed else RuntimeError):
        app.activate()
    assert compose.call_args_list[-1].args == (app.new, 'stop', 'web', 'api')
    assert [call.args[0] for call in up.call_args_list] == [app.new, app.new if changed else app.base]
    if not changed:
        assert healthy.call_args.args == (app.base, release.BASE, {'api': API_IMAGE, 'web': WEB_IMAGE})


def test_workflow_binds_successful_mainline_build_and_always_closes_temporary_ingress():
    workflow = (ROOT / '.github/workflows/learner-refinements-release.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert "run['head_sha']==p['candidate']" in workflow
    assert "run['status']=='completed' and run['conclusion']=='success'" in workflow
    assert "if: always() && steps.runner.outputs.cidr != ''" in workflow
    assert 'wp08_security_group close' in workflow
    assert 'deploy/learner-refinements-release/package.py' in workflow
    assert 'cancel-in-progress: false' in workflow
    package = (ROOT / 'deploy/learner-refinements-release/package.py').read_text()
    assert 'grant_runtime.py' not in package
    assert '"api", "web"' in package
    source = (ROOT / 'deploy/learner-refinements-release/activate.py').read_text()
    assert '"alembic", "upgrade"' not in source and '"alembic", "downgrade"' not in source
    assert 'GRANT ' not in source


def test_live_baseline_health_checks_each_service_against_its_own_release():
    app = application()
    rows = []
    for service, candidate in [('api', release.BASE), ('web', release.WEB_BASE)]:
        row = container(service, service, [])
        row['Config']['Env'] = ['APP_RELEASE=' + candidate]
        row['State'] = {'Running': True, 'Health': {'Status': 'healthy'}}
        rows.append(row)
    with patch.object(app, 'containers', return_value=rows), patch.object(release, 'run',
            return_value=json.dumps({'status': 'ready', 'release': release.WEB_BASE}).encode()):
        app.healthy(app.base, release.BASE, app.old_images)
        rows[1]['Config']['Env'] = ['APP_RELEASE=' + release.BASE]
        with pytest.raises(release.UpgradeError, match='RUNTIME_RELEASE'):
            app.healthy(app.base, release.BASE, app.old_images)


def test_restored_copy_must_match_candidate_and_existing_schema_without_writes():
    app = application()
    with patch.object(release, 'run', side_effect=[
            (release.TARGET_SCHEMA + ' (head)\n').encode(),
            json.dumps([release.TARGET_SCHEMA]).encode(),
            json.dumps({name: [3, 'existing-data'] for name in release.RUNTIME_TABLES}).encode(),
        ]) as run, patch.object(release, 'read_file', return_value=b'guard'), patch.object(release, 'write_new') as write:
        app.validate_restored_database('isolated-restore', Path('/restore.env'))
        assert all('--network' in call.args[0] and 'isolated-restore' in call.args[0] for call in run.call_args_list)
        assert all('PGOPTIONS=-c default_transaction_read_only=on' in call.args[0] for call in run.call_args_list)
        assert not any('upgrade' in call.args[0] or 'downgrade' in call.args[0] for call in run.call_args_list)
        assert json.loads(write.call_args.args[1])['schema_changed'] is False


def test_candidate_with_unreviewed_schema_head_stops_before_activation():
    app = application()
    with patch.object(release, 'run', return_value=b'0057_unreviewed (head)\n'), \
         patch.object(release, 'write_new') as write, pytest.raises(release.UpgradeError, match='CANDIDATE_SCHEMA_HEAD'):
        app.validate_restored_database('isolated-restore', Path('/restore.env'))
    write.assert_not_called()


def test_production_database_probe_cannot_omit_read_only_mode():
    app = application()
    with patch.object(release, 'run') as run:
        with pytest.raises(release.UpgradeError, match='PRODUCTION_WRITE_PROBE_FORBIDDEN'):
            app.docker_api('secrets/migration.env', 'python', '-c', 'anything')
        run.assert_not_called()
        app.verify_runtime_schema()
        command = run.call_args.args[0]
        assert 'PGOPTIONS=-c default_transaction_read_only=on' in command
        assert 'REQUIRE_READ_ONLY=true' in command
        assert all(name in command[-1] for name in release.RUNTIME_TABLES)


def test_restore_or_backup_receipt_drift_stops_before_services_are_stopped():
    app = application()
    def wrong_receipt(path):
        result = json.loads(activation_receipts(path))
        if path.name == 'schema-validation.json':
            result['schema_changed'] = True
        return json.dumps(result).encode()
    with activation_patches(app), patch.object(release, 'read_file', side_effect=wrong_receipt), \
         patch.object(release, 'compose') as compose, patch.object(app, 'up') as up, \
         pytest.raises(release.UpgradeError, match='RESTORE_SCHEMA_PROOF'):
        app.activate()
    compose.assert_not_called()
    up.assert_not_called()


def test_failure_after_public_switch_restores_the_previous_pointer_and_mixed_images():
    app = application()
    with activation_patches(app), patch.object(app, 'docker_api', return_value=b'0'), \
         patch.object(release, 'compose'), patch.object(app, 'guard', return_value={'facts': 'same'}), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy'), \
         patch.object(release, 'run', side_effect=RuntimeError('entry unavailable')), \
         patch.object(app, 'current', return_value=app.new), patch.object(app, 'pointer') as pointer, \
         pytest.raises(RuntimeError, match='entry unavailable'):
        app.activate()
    assert [call.args[0] for call in up.call_args_list] == [app.new, app.base]
    assert [call.args[0] for call in pointer.call_args_list] == [app.new, app.base]


@pytest.mark.parametrize('failure', ['runtime_probe', 'guard_unavailable', 'guard_changed'])
def test_preswitch_probe_failure_always_restarts_old_mixed_services(failure):
    app = application()
    before = {'guild_memberships': [4, 'before']}
    schemas = [None, RuntimeError('schema probe unavailable')] if failure == 'runtime_probe' else [None, None]
    facts = [before]
    if failure == 'guard_unavailable':
        facts.append(RuntimeError('fact probe unavailable'))
    elif failure == 'guard_changed':
        facts.append({'guild_memberships': [5, 'external-write']})
    error = release.UpgradeError if failure == 'guard_changed' else RuntimeError
    with activation_patches(app), patch.object(app, 'docker_api', return_value=b'0'), \
         patch.object(app, 'verify_runtime_schema', side_effect=schemas), \
         patch.object(release, 'compose') as compose, patch.object(app, 'guard', side_effect=facts) as guard, \
         patch.object(app, 'up') as up, patch.object(app, 'healthy') as healthy, \
         pytest.raises(error):
        app.activate()
    # The candidate was never started, so failed or changing probes cannot
    # justify keeping the original, otherwise healthy services stopped.
    compose.assert_called_once_with(app.base, 'stop', 'web', 'api', timeout=90)
    up.assert_called_once_with(app.base)
    healthy.assert_called_once_with(app.base, release.BASE, {'api': API_IMAGE, 'web': WEB_IMAGE})
    assert guard.call_count == (1 if failure == 'runtime_probe' else 2)


@pytest.mark.parametrize('extra_change', [False, True])
def test_stage_preserves_profile_receipt_files_and_reconciles_mixed_release_values(tmp_path, extra_change):
    app = application()
    app.base, app.new, app.package = tmp_path / 'profile-growth', tmp_path / 'refinements', tmp_path / 'package'
    (app.base / 'secrets').mkdir(parents=True, mode=0o700)
    app.package.mkdir()
    files = baseline_files()
    files['.deployment.env'] += f'CANDIDATE_COMMIT={release.WEB_BASE}\nUNCHANGED_OPTION=keep\n'.encode()
    files['secrets/api.env'] += b'DATABASE_URL=postgresql+psycopg://runtime:fixture@db:5432/journey_next_canary_20260901_c72fea5\nALLOW_FIXTURE_IDENTITY=false\nPHONE_OTP_ENABLED=true\n'
    files['secrets/web.env'] += b'API_INTERNAL_URL=http://api:8000\n'
    files['secrets/migration.env'] = b'PREVIOUS_MAINTENANCE=preserved_in_old_release\n'
    files['secrets/extra-retained-key'] = b'fixture-nonproduction-material'
    files['grant_runtime.py'] = b'# Previous historical script; never run this release.\n'
    for name, raw in files.items():
        (app.base / name).write_bytes(raw)
        (app.base / name).chmod(0o700 if name == 'compose.sh' else 0o600)
    app.base_hashes = {name: release.digest(raw) for name, raw in files.items()}
    (app.package / 'db_facts.py').write_bytes(b'# Read-only facts helper.\n')

    def configuration(path, *args):
        assert args == ('config', '--format', 'json')
        env = release.env_values((path / '.deployment.env').read_bytes())
        config = {'services': {}, 'networks': {'edge': {'external': True}}}
        for service in ('api', 'web'):
            config['services'][service] = {
                'image': env[service.upper() + '_IMAGE'],
                'environment': release.env_values((path / f'secrets/{service}.env').read_bytes()),
                'volumes': [{'type': 'bind', 'source': str(path / 'secrets/volcengine-rds-ca.pem'),
                             'target': '/run/secrets/volcengine-rds-ca.pem', 'read_only': True}],
            }
        if extra_change and path == app.new:
            config['services']['api']['environment']['PHONE_OTP_ENABLED'] = 'false'
        return json.dumps(config).encode()

    with patch.object(app, 'verify_base'), patch.object(release, 'compose', side_effect=configuration):
        if extra_change:
            with pytest.raises(release.UpgradeError, match='COMPOSE_EXTRA_CHANGE'):
                app.stage('fixture-maintenance-password')
            assert not (app.new / 'schema-upgrade-prepared.json').exists()
            return
        app.stage('fixture-maintenance-password')
    deployment = release.env_values((app.new / '.deployment.env').read_bytes())
    assert deployment == {'API_IMAGE': app.images['api'], 'WEB_IMAGE': app.images['web'],
                          'CANDIDATE_COMMIT': app.manifest['candidate'], 'UNCHANGED_OPTION': 'keep'}
    for service in ('api', 'web'):
        before = release.env_values(files[f'secrets/{service}.env'])
        assert release.env_values((app.new / f'secrets/{service}.env').read_bytes()) == {
            **before, 'APP_RELEASE': app.manifest['candidate']}
    for name, raw in files.items():
        assert (app.base / name).read_bytes() == raw
        if name not in release.ENV_FILES and name != 'secrets/migration.env':
            assert (app.new / name).read_bytes() == raw
            assert (app.new / name).stat().st_mode == (app.base / name).stat().st_mode
    state = json.loads((app.new / 'schema-upgrade-prepared.json').read_text())
    assert state['manifest']['old_images'] == {'api': API_IMAGE, 'web': WEB_IMAGE}
    assert set(files) <= state['hashes'].keys()
    app.verify_prepared()


def test_offline_import_resolves_config_then_pins_actual_loaded_ids(tmp_path):
    import gzip
    import hashlib
    app = application()
    app.package = tmp_path
    app.manifest['disk_budget'] = {'import': 1}
    app.manifest['archives'] = {}
    for name in ('api', 'web'):
        original = (name + '-source-image').encode()
        compressed = gzip.compress(original)
        (tmp_path / (name + '.part0000')).write_bytes(compressed)
        app.manifest['archives'][name] = {
            'config_digest': 'sha256:' + '1' * 64,
            'source_reference': name + ':candidate',
            'chunks': [{'file': name + '.part0000', 'sha256': hashlib.sha256(compressed).hexdigest()}],
            'gzip_sha256': hashlib.sha256(compressed).hexdigest(),
            'source_tar_sha256': hashlib.sha256(original).hexdigest(),
        }
    resolved_config = 'sha256:' + '2' * 64
    loaded = {'api': 'sha256:' + '3' * 64, 'web': 'sha256:' + '4' * 64}
    def command(args, **kwargs):
        if args[:3] == ['docker', 'image', 'inspect']:
            return json.dumps([{'Id': loaded[args[3].split(':')[0]]}]).encode()
        assert args[:2] == ['docker', 'load']
        return b''
    with patch.object(app, 'verify_base'), patch.object(release, 'check_space'), \
         patch.object(release, 'source_config_digest', return_value=resolved_config) as source, \
         patch.object(release, 'verify_loaded_image') as verify, patch.object(release, 'run', side_effect=command), \
         patch.object(app, 'image_check'), patch.object(release.Upgrade, 'image_check'), \
         patch.object(app, 'verify_runtime_dependencies'), patch.object(release, 'cleanup_verified_transports') as cleanup:
        app.import_images()
    assert app.images['api'] == loaded['api'] and app.images['web'] == loaded['web']
    assert source.call_count == 2
    assert [call.args for call in verify.call_args_list] == [(loaded['api'], resolved_config), (loaded['web'], resolved_config)]
    cleanup.assert_called_once_with(tmp_path, app.manifest)
