"""Protect production baseline, additive migration, curriculum import and rollback boundary."""
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
    sys.modules['catalog_actor'] = load('catalog_actor', 'deploy/dynamic-exploration-release/catalog_actor.py')
    release = load('dynamic_exploration_release', 'deploy/dynamic-exploration-release/activate.py')

API_IMAGE = 'sha256:' + 'b' * 64
WEB_IMAGE = 'sha256:' + 'c' * 64


def manifest():
    result = json.loads((ROOT / 'deploy/dynamic-exploration-release/baseline.json').read_text())
    result['candidate'] = 'a' * 40
    result['package_run_id'] = '123456'
    return result


ORG = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
AUTHOR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

def baseline_files():
    files = {name: b'original-config' for name in release.COPY_FILES + release.ENV_FILES + tuple(release.SECRET_FILES.values())}
    files['.deployment.env'] = f'API_IMAGE={API_IMAGE}\nWEB_IMAGE={WEB_IMAGE}\n'.encode()
    files['secrets/api.env'] = f'APP_RELEASE={release.BASE}\nFEISHU_LEARNER_ORGANIZATION_ID={ORG}\nFEISHU_LEARNER_REVIEWER_ID={AUTHOR}\n'.encode()
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
            'schema': release.SOURCE_SCHEMA, 'previous_release': str(release.ROOT / 'releases' / release.PREVIOUS_WEB_DIRECTORY),
            'release_kind': 'learner-usability-web', 'api_container_unchanged': True, 'other_containers_unchanged': True, 'database_writes': 0,
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
    assert app.base.name == release.WEB_BASE + '-learner-usability'
    assert app.new.name == 'a' * 40 + '-dynamic-exploration'
    assert (release.SOURCE_SCHEMA, release.TARGET_SCHEMA) == ('0056_guild_halls', '0060_migrated_ai_ownership')
    assert len(release.NEW_TABLES) == 5


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


def initialization():
    return {'mode': 'apply', 'schema': release.TARGET_SCHEMA,
        'business_records_preserved': True, 'legacy_progress_rewritten': False,
        'independent_review': False, 'organization_id': ORG, 'author_id': AUTHOR,
        'inserted': [str(index) for index in range(8)], 'preserved': [], 'seed_sha256': '1' * 64}


def receipts(path):
    if path.name == 'backup-receipt.json':
        return json.dumps({'restore': 'PASS', 'candidate': 'a' * 40, 'backup_sha256': 'hash',
            'migration': release.SOURCE_SCHEMA, 'production_migration_applied': False}).encode()
    if path.name == 'migration-rehearsal.json':
        return json.dumps({'candidate': 'a' * 40, 'from': release.SOURCE_SCHEMA, 'to': release.TARGET_SCHEMA,
            'curriculum_initialized': True, 'curriculum_source_sha256': '1' * 64,
            'import_idempotent': True, 'existing_business_rows_preserved': True,
            'old_application_compatibility': 'PASS'}).encode()
    return prior(path)


def activation_patches(app):
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(app, 'verify_base'))
    stack.enter_context(patch.object(app, 'verify_prepared'))
    stack.enter_context(patch.object(app, 'verify_catalog_actor'))
    stack.enter_context(patch.object(app, 'verify_runtime_schema'))
    stack.enter_context(patch.object(release, 'verify_protected_containers'))
    stack.enter_context(patch.object(release, 'read_file', side_effect=receipts))
    stack.enter_context(patch.object(release, 'file_sha', return_value='hash'))
    stack.enter_context(patch.object(release, 'write_new'))
    stack.enter_context(patch.object(app, 'pointer'))
    stack.enter_context(patch.object(app, 'current', return_value=app.base))
    return stack


def api_response(*args, **kwargs):
    if args[1:3] == ('alembic', 'current'):
        return (release.SOURCE_SCHEMA + '\n').encode()
    return b'0'


def migration_facts():
    before = {'assignments': [4, 'original'], 'guild_memberships': [2, 'retained']}
    after = {**before, **{name: [0, 'empty'] for name in release.NEW_TABLES}}
    initialized = {**after, 'task_definitions': [8, 'new-curriculum'],
                   'exploration_catalog_tasks': [8, 'catalog']}
    return before, after, initialized


def test_migration_and_fixed_import_finish_before_candidate_containers_start():
    app = application()
    with activation_patches(app), patch.object(app, 'docker_api', side_effect=api_response) as api, \
         patch.object(app, 'catalog_initialize', return_value=initialization()), \
         patch.object(release, 'compose'), patch.object(app, 'guard', side_effect=migration_facts()), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy'), patch.object(release, 'run', return_value=b'401'):
        app.activate()
        receipt = json.loads(release.write_new.call_args.args[1])
    commands = [call.args for call in api.call_args_list]
    assert ('secrets/migration.env', 'alembic', 'upgrade', release.TARGET_SCHEMA) in commands
    assert ('secrets/migration.env', 'python', '/tmp/grant_runtime.py') in commands
    assert not any('downgrade' in call for call in commands)
    up.assert_called_once_with(app.new)
    assert receipt['schema'] == release.TARGET_SCHEMA and receipt['database_schema_changed'] is True
    assert receipt['existing_business_rows_preserved'] is True
    assert receipt['previous_web_release'] == release.WEB_BASE and receipt['previous_api_release'] == release.BASE


@pytest.mark.parametrize('changed', [False, True])
def test_failed_candidate_restores_old_application_only_before_new_business_writes(changed):
    app = application()
    before, migrated, initialized = migration_facts()
    last = {**initialized, 'exploration_work': [1, 'learner-work']} if changed else initialized
    with activation_patches(app), patch.object(app, 'docker_api', side_effect=api_response), \
         patch.object(app, 'catalog_initialize', return_value=initialization()), \
         patch.object(release, 'compose') as compose, patch.object(app, 'guard', side_effect=[before, migrated, initialized, last]), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy', side_effect=[RuntimeError('not healthy'), None]), \
         pytest.raises(release.UpgradeError if changed else RuntimeError):
        app.activate()
    assert compose.call_args_list[-1].args == (app.new, 'stop', 'web', 'api')
    assert [call.args[0] for call in up.call_args_list] == [app.new, app.new if changed else app.base]


def test_candidate_shutdown_failure_restores_candidate_availability_without_risky_rollback():
    app = application()
    with activation_patches(app), patch.object(app, 'docker_api', side_effect=api_response), \
         patch.object(app, 'catalog_initialize', return_value=initialization()), \
         patch.object(release, 'compose', side_effect=[b'', RuntimeError('shutdown timeout')]), \
         patch.object(app, 'guard', side_effect=migration_facts()), patch.object(app, 'up') as up, \
         patch.object(app, 'healthy', side_effect=RuntimeError('startup failed')), \
         pytest.raises(release.UpgradeError, match='CANDIDATE_STOP_UNCONFIRMED_FORWARD_FIX_REQUIRED'):
        app.activate()
    assert [call.args[0] for call in up.call_args_list] == [app.new, app.new]


@pytest.mark.parametrize('failure', ['migration', 'initialization', 'runtime_probe'])
def test_preswitch_failure_restarts_original_services_without_downgrading_database(failure):
    app = application()
    before, migrated, initialized = migration_facts()
    def api(*args, **kwargs):
        if failure == 'migration' and 'upgrade' in args:
            raise RuntimeError('migration stopped')
        return api_response(*args, **kwargs)
    with activation_patches(app), patch.object(app, 'docker_api', side_effect=api) as command, \
         patch.object(app, 'catalog_initialize', side_effect=RuntimeError('import rolled back') if failure == 'initialization' else None,
                      return_value=initialization()), \
         patch.object(app, 'verify_runtime_schema', side_effect=RuntimeError('probe failed') if failure == 'runtime_probe' else None), \
         patch.object(release, 'compose') as compose, patch.object(app, 'guard', side_effect=[before, migrated, initialized]), \
         patch.object(app, 'up') as up, patch.object(app, 'healthy'), pytest.raises(RuntimeError):
        app.activate()
    compose.assert_called_once_with(app.base, 'stop', 'web', 'api', timeout=90)
    up.assert_called_once_with(app.base)
    assert not any('downgrade' in call.args for call in command.call_args_list)


@pytest.mark.parametrize('field,value', [('from', 'other'), ('to', 'other'), ('candidate', 'b' * 40),
    ('curriculum_initialized', False), ('import_idempotent', False), ('old_application_compatibility', 'FAIL')])
def test_missing_rehearsal_proof_stops_before_maintenance(field, value):
    app = application()
    def changed(path):
        raw = receipts(path)
        if path.name == 'migration-rehearsal.json':
            data = json.loads(raw); data[field] = value
            return json.dumps(data).encode()
        return raw
    with activation_patches(app), patch.object(release, 'read_file', side_effect=changed), \
         patch.object(release, 'compose') as compose, pytest.raises(release.UpgradeError, match='RESTORE_SCHEMA_PROOF'):
        app.activate()
    compose.assert_not_called()


def test_catalog_identity_is_production_configuration_bound_without_name_or_role_guessing():
    app = application()
    with patch.object(release, 'read_file', side_effect=prior):
        assert app.catalog_command() == ['python', 'scripts/upgrade_exploration_catalog.py', '--organization-id', ORG,
            '--author-id', AUTHOR, '--authorization-reference', release.AUTHORIZATION]
    with patch.object(release, 'read_file', return_value=b'FEISHU_LEARNER_ORGANIZATION_ID=\nFEISHU_LEARNER_REVIEWER_ID=\n'), \
         pytest.raises(release.UpgradeError, match='CURRICULUM_IDENTITY_CONFIG'):
        app.catalog_command(apply=True)


def test_database_command_allowlist_rejects_arbitrary_write_probes_and_downgrades():
    app = application()
    with patch.object(release, 'read_file', side_effect=prior), patch.object(release, 'run') as run:
        for args in [('python', '-c', 'arbitrary database write'), ('alembic', 'downgrade', release.SOURCE_SCHEMA),
                     ('alembic', 'upgrade', 'head'), ('python', 'scripts/import_exploration_catalog.py')]:
            with pytest.raises(release.UpgradeError, match='PRODUCTION_WRITE_PROBE_FORBIDDEN'):
                app.docker_api('secrets/migration.env', *args)
        run.assert_not_called()
        app.docker_api('secrets/migration.env', 'alembic', 'upgrade', release.TARGET_SCHEMA)
        assert 'PGOPTIONS=-c default_transaction_read_only=on' not in run.call_args.args[0]
        app.verify_runtime_schema()
        assert 'PGOPTIONS=-c default_transaction_read_only=on' in run.call_args.args[0]
        assert all(name in run.call_args.args[0][-1] for name in release.NEW_TABLES)


@pytest.mark.parametrize('field,value', [('business_records_preserved', False), ('legacy_progress_rewritten', True),
    ('independent_review', True), ('schema', '0056_guild_halls'), ('organization_id', AUTHOR), ('preserved', ['extra'])])
def test_import_receipt_must_preserve_history_and_match_exact_owner_authorized_catalog(field, value):
    app = application(); result = initialization(); result[field] = value
    with patch.object(release, 'read_file', side_effect=prior), \
         patch.object(app, 'docker_api', return_value=json.dumps(result).encode()), \
         pytest.raises(release.UpgradeError, match='CURRICULUM_INITIALIZATION_PROOF'):
        app.catalog_initialize()


def test_live_baseline_health_checks_web_and_api_against_their_separate_releases():
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


def test_restore_rehearses_exact_migration_plan_import_replay_and_old_application():
    app = application()
    before, after, initialized = migration_facts()
    results = [json.dumps(before).encode(), (release.TARGET_SCHEMA + ' (head)').encode(),
        release.SOURCE_SCHEMA.encode(), b'', json.dumps(after).encode(), release.TARGET_SCHEMA.encode(),
        json.dumps({'mode': 'plan', 'inserted': [], 'business_records_preserved': True}).encode(),
        json.dumps(initialized).encode(), json.dumps(initialized).encode(), json.dumps(initialized).encode()]
    with patch.object(release, 'read_file', side_effect=lambda path: b'guard' if path.name == 'facts_guard.py' else prior(path)), \
         patch.object(release, 'run', side_effect=results) as run, \
         patch.object(app, 'catalog_initialize', return_value=initialization()) as catalog, \
         patch.object(app, 'verify_old_application_on_restore') as old, patch.object(release, 'write_new') as write:
        app.validate_restored_database('isolated-restore', Path('/restore.env'))
    assert catalog.call_count == 2
    old.assert_called_once_with('isolated-restore', Path('/restore.env'))
    assert all('isolated-restore' in call.args[0] for call in run.call_args_list)
    assert sum('upgrade' in call.args[0] for call in run.call_args_list) == 1
    receipt = json.loads(write.call_args.args[1])
    assert receipt['from'] == release.SOURCE_SCHEMA and receipt['to'] == release.TARGET_SCHEMA
    assert receipt['import_idempotent'] is True and receipt['old_application_compatibility'] == 'PASS'


def test_old_application_probe_uses_only_isolated_database_read_only_without_external_workers():
    app = application()
    with patch.object(release, 'run', return_value=b'OLD_APPLICATION_SCHEMA_COMPATIBLE\n') as run:
        app.verify_old_application_on_restore('isolated-restore', Path('/restore.env'))
    command = run.call_args.args[0]
    assert command[command.index('--network') + 1] == 'isolated-restore'
    assert 'PGOPTIONS=-c default_transaction_read_only=on' in command
    assert app.old_images['api'] in command
    assert "client.get('/health/ready')" in command[-1]
    assert 'with TestClient' not in command[-1]


def test_workflow_pins_mainline_candidate_and_closes_the_exact_temporary_ingress():
    workflow = (ROOT / '.github/workflows/dynamic-exploration-release.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert "run['head_sha']==p['candidate']" in workflow
    assert "run['status']=='completed' and run['conclusion']=='success'" in workflow
    assert "if: always() && steps.runner.outputs.cidr != ''" in workflow
    assert 'wp08_security_group close' in workflow
    assert 'deploy/dynamic-exploration-release/package.py' in workflow
    assert 'cancel-in-progress: false' in workflow
    assert workflow.index('< deploy/dynamic-exploration-release/catalog_actor.py') < workflow.index("install -d -m 0700 '$REMOTE_PACKAGE'")
    assert workflow.index('< deploy/dynamic-exploration-release/catalog_actor.py') < workflow.index('python3 deploy/exploration-release/transfer_package.py')
    source = (ROOT / 'deploy/dynamic-exploration-release/activate.py').read_text()
    assert '"alembic", "downgrade"' not in source
    assert '"APP_ENV": "local"' not in source


def actor_preflight_module():
    return load('dynamic_exploration_catalog_actor', 'deploy/dynamic-exploration-release/catalog_actor.py')


def test_transfer_preflight_checks_the_existing_immutable_container_with_read_only_sql(capsys):
    helper = actor_preflight_module()
    api = {'Id': 'old-api-container-id', 'Image': 'sha256:' + 'b' * 64,
        'Config': {'Labels': {'com.docker.compose.project': helper.PROJECT, 'com.docker.compose.service': 'api',
                             'org.opencontainers.image.revision': helper.API_BASE},
                   'Env': ['APP_RELEASE=' + helper.API_BASE, 'SENSITIVE_CONFIGURATION=must-not-print']},
        'State': {'Running': True, 'Health': {'Status': 'healthy'}}}
    base = helper.ROOT / 'releases' / (helper.WEB_BASE + '-learner-usability')
    def resolve(path, *args, **kwargs):
        return base if path == helper.ROOT / 'current' else path
    with patch.object(helper.sys, 'platform', 'linux'), patch.object(helper.os, 'geteuid', return_value=0, create=True), \
         patch.object(helper.socket, 'gethostname', return_value='journey-next-staging'), \
         patch.object(Path, 'resolve', resolve), patch.object(Path, 'is_symlink', return_value=True), \
         patch.object(helper, 'command', side_effect=[json.dumps([api]).encode(), helper.SUCCESS.encode()]) as command:
        helper.preflight()
    assert len(command.call_args_list) == 2
    first, second = [call.args[0] for call in command.call_args_list]
    assert first == ['docker', 'inspect', helper.PROJECT + '-api-1']
    assert second[:2] == ['docker', 'exec'] and 'old-api-container-id' in second
    assert 'PGOPTIONS=-c default_transaction_read_only=on' in second
    assert 'SET TRANSACTION READ ONLY' in second[-1] and "access_role == 'super_admin'" in second[-1]
    assert "RoleAssignment.role == Role.REVIEWER" in second[-1]
    assert 'FOR UPDATE' not in second[-1] and 'INSERT ' not in second[-1] and 'UPDATE ' not in second[-1]
    assert 'SENSITIVE_CONFIGURATION' not in capsys.readouterr().out


def test_shared_actor_probe_binds_production_configuration_and_exact_schema_without_role_changes():
    helper = actor_preflight_module()
    source = helper.actor_probe(ORG, AUTHOR)
    assert 'EXPECTED_ORG=' + repr(ORG) in source and 'EXPECTED_AUTHOR=' + repr(AUTHOR) in source
    assert 's.feishu_learner_organization_id' in source and 's.feishu_learner_reviewer_id' in source
    assert "s.app_env == 'production' and not s.allow_fixture_identity" in source
    assert "['0056_guild_halls']" in source
    assert 'GRANT ' not in source and 'with_for_update' not in source


def test_preflight_subprocess_failure_never_prints_stderr_or_production_values():
    helper = actor_preflight_module()
    with patch.object(helper.subprocess, 'run', return_value=SimpleNamespace(returncode=1,
            stdout=b'private configuration', stderr=b'private database URL')), \
         pytest.raises(helper.ActorPreflightError, match='^CURRICULUM_ACTOR_PREFLIGHT_COMMAND_FAILED$'):
        helper.command(['docker', 'inspect', 'container'])


def test_runtime_grant_targets_exactly_new_tables_without_schema_wide_privileges():
    grants = load('dynamic_exploration_grant', 'deploy/dynamic-exploration-release/grant_runtime.py')
    assert set(grants.TABLES) == set(release.NEW_TABLES)
    assert 'ALL TABLES' not in grants.GRANT_SQL and 'CREATE' not in grants.GRANT_SQL
    assert grants.GRANT_SQL.endswith(' TO journey_next_runtime')



@pytest.mark.parametrize('extra_change', [False, True])
@pytest.mark.skipif(sys.platform == 'win32', reason='Linux deployment preserves POSIX file permissions')
def test_stage_preserves_profile_receipt_files_and_reconciles_mixed_release_values(tmp_path, extra_change):
    app = application()
    app.base, app.new, app.package = tmp_path / 'current-web', tmp_path / 'dynamic-release', tmp_path / 'package'
    (app.base / 'secrets').mkdir(parents=True, mode=0o700)
    app.package.mkdir()
    files = baseline_files()
    files['.deployment.env'] += f'CANDIDATE_COMMIT={release.WEB_BASE}\nUNCHANGED_OPTION=keep\n'.encode()
    files['secrets/api.env'] += b'DATABASE_URL=postgresql+psycopg://runtime:fixture@db:5432/journey_next_canary_20260901_c72fea5\nALLOW_FIXTURE_IDENTITY=false\nPHONE_OTP_ENABLED=true\n'
    files['secrets/web.env'] += b'API_INTERNAL_URL=http://api:8000\n'
    files['secrets/migration.env'] = b'PREVIOUS_MAINTENANCE=preserved_in_old_release\n'
    files['secrets/extra-retained-key'] = b'fixture-nonproduction-material'
    # The last Web-only release has no runtime-grant helper in its receipt.
    for name, raw in files.items():
        (app.base / name).write_bytes(raw)
        (app.base / name).chmod(0o700 if name == 'compose.sh' else 0o600)
    app.base_hashes = {name: release.digest(raw) for name, raw in files.items()}
    (app.package / 'db_facts.py').write_bytes(b'# Read-only facts helper.\n')
    (app.package / 'grant_runtime.py').write_bytes(b'# New exact-table grants.\n')

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

    with patch.object(app, 'verify_base'), patch.object(release, 'compose', side_effect=configuration), \
         patch.object(release.os, 'chown', create=True), patch.object(release.os, 'fchmod', create=True):
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
