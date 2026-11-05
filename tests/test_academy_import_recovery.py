"""A stopped import may reuse proved bytes, never bypass an activation boundary."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('academy_import_recovery', ROOT / 'deploy/academy-release/recover_import.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def package(tmp_path):
    folder = tmp_path / 'package'
    folder.mkdir()
    manifest = {
        'schema_version': 3, 'candidate': recovery.CANDIDATE, 'package_run_id': recovery.PACKAGE_RUN,
        'base_candidate': recovery.BASE,
        'base_release': str(recovery.ROOT / 'releases' / (recovery.BASE + '-badges-knowledge')),
        'database': 'journey_next_canary_20260901_c72fea5', 'migrations': dict(recovery.MIGRATIONS),
        'old_images': {}, 'images': {'dbrestore': recovery.DBRESTORE}, 'archives': {},
        'disk_budget': {'import': 3 * 1024**3},
    }
    for name, count in (('api', 70), ('web', 71)):
        raw = name.encode() + bytes(range(256)) * 32
        compressed = gzip.compress(raw, mtime=0)
        chunks = []
        for index in range(count):
            content = compressed[index * len(compressed) // count:(index + 1) * len(compressed) // count]
            filename = f'{name}.part{index:04}'
            (folder / filename).write_bytes(content)
            chunks.append({'file': filename, 'sha256': sha(content)})
        manifest['images'][name] = 'sha256:' + sha(name.encode())
        manifest['archives'][name] = {
            'source_reference': f'ghcr.io/muchenai/muchen-journey-vnext-{name}:{recovery.CANDIDATE}',
            'config_digest': manifest['images'][name], 'gzip_sha256': sha(compressed), 'gzip_bytes': len(compressed),
            'source_tar_sha256': sha(raw), 'source_tar_bytes': len(raw), 'chunks': chunks,
        }
    for filename in recovery.SOURCE_FILES:
        (folder / filename).write_text('# original verified source: ' + filename + '\n')
    (folder / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True))
    sums = ''.join(sha(path.read_bytes()) + '  ' + path.name + '\n' for path in sorted(folder.iterdir()))
    (folder / 'SHA256SUMS').write_text(sums)
    control = ROOT / 'deploy/academy-release'
    proof = {
        'schema_version': 1, 'source_run_id': recovery.SOURCE_RUN, 'source_attempt': 1,
        'source_package': str(recovery.SOURCE), 'operations_commit': 'f' * 40, 'manifest': manifest,
        'files': {path.name: recovery.file_info(path) for path in folder.iterdir()},
        'controls': {name: recovery.file_info(control / name) for name in recovery.CONTROL_FILES},
    }
    assert len(proof['files']) == 155
    return folder, proof


def test_proof_binds_all_original_bytes_and_only_uploads_small_controls(package, tmp_path):
    folder, proof = package
    recovery.verify_original_package(folder, proof)
    destination = tmp_path / 'controls'
    recovery.prepare_proof(folder, destination, proof['operations_commit'])
    assert {path.name for path in destination.iterdir()} == {
        'recover_import.py', 'image_transport.py', 'original-package-proof.json', 'SHA256SUMS'}
    assert sum(p.stat().st_size for p in destination.iterdir()) < 200_000
    assert json.loads((destination / 'original-package-proof.json').read_text()) == proof


@pytest.mark.parametrize('field,value,category', [
    ('candidate', 'a' * 40, 'APPLICATION_PIN'),
    ('package_run_id', '42035425028', 'APPLICATION_PIN'),
    ('base_candidate', 'a' * 40, 'BASE_PIN'),
    ('migrations', {'from': '0052_knowledge_publication', 'to': '0055_other'}, 'MIGRATION_CONTRACT'),
    ('database', 'another_database', 'DATABASE_PIN'),
    ('old_images', {'api': 'latest'}, 'ORIGINAL_IMAGES'),
])
def test_other_application_or_migration_cannot_use_recovery(package, field, value, category):
    _, proof = package
    proof['manifest'][field] = value
    with pytest.raises(recovery.RecoveryError, match=category):
        recovery.validate_proof(proof)


@pytest.mark.parametrize('name', ['activate.py', 'api.part0000', 'manifest.json', 'SHA256SUMS'])
def test_original_script_or_chunk_tampering_stops_before_execution(package, name):
    folder, proof = package
    (folder / name).write_bytes((folder / name).read_bytes() + b'changed')
    with pytest.raises(recovery.RecoveryError, match='ORIGINAL_FILE_CHANGED'):
        recovery.verify_original_package(folder, proof)


def test_an_untrusted_server_checksum_list_cannot_authorize_changed_script(package):
    folder, proof = package
    (folder / 'activate.py').write_bytes(b'changed')
    # Even updating every server-local checksum cannot change the runner proof.
    (folder / 'SHA256SUMS').write_text(''.join(
        sha(p.read_bytes()) + '  ' + p.name + '\n'
        for p in sorted(folder.iterdir()) if p.name != 'SHA256SUMS'))
    with pytest.raises(recovery.RecoveryError, match='ORIGINAL_FILE_CHANGED'):
        recovery.verify_original_package(folder, proof)


@pytest.mark.parametrize('name', ['unexpected.py', 'api.part9999'])
def test_unknown_or_missing_package_entries_are_rejected(package, name):
    folder, proof = package
    (folder / name).write_bytes(b'unknown')
    with pytest.raises(recovery.RecoveryError, match='SOURCE_FILE_SET'):
        recovery.verify_original_package(folder, proof)
    (folder / name).unlink()
    (folder / 'web.part0000').unlink()
    with pytest.raises(recovery.RecoveryError, match='SOURCE_FILE_SET'):
        recovery.verify_original_package(folder, proof)


def test_original_import_caches_are_inert_but_unknown_cached_modules_are_rejected(package):
    folder, proof = package
    cache = folder / '__pycache__'
    cache.mkdir()
    (cache / 'prepare.cpython-311.pyc').write_bytes(b'never trusted or executed')
    recovery.verify_original_package(folder, proof)
    (cache / 'other.cpython-311.pyc').write_bytes(b'unknown')
    with pytest.raises(recovery.RecoveryError, match='SOURCE_CACHE_ENTRY'):
        recovery.verify_original_package(folder, proof)


def test_assembled_archive_is_reused_without_rewriting_or_deleting(package):
    folder, proof = package
    entry = proof['manifest']['archives']['api']
    archive = recovery.ensure_archive(folder, 'api', entry)
    before = (archive.read_bytes(), archive.stat().st_mtime_ns)
    recovery.verify_original_package(folder, proof)
    assert recovery.ensure_archive(folder, 'api', entry) == archive
    assert (archive.read_bytes(), archive.stat().st_mtime_ns) == before
    assert all((folder / part['file']).exists() for part in entry['chunks'])


def test_partial_assembled_archive_is_preserved_and_stops_recovery(package):
    folder, proof = package
    archive = folder / 'api.tar.gz'
    archive.write_bytes(b'partial old archive')
    with pytest.raises(recovery.RecoveryError, match='ASSEMBLED_ARCHIVE_CHANGED'):
        recovery.ensure_archive(folder, 'api', proof['manifest']['archives']['api'])
    assert archive.read_bytes() == b'partial old archive'


def test_original_tar_digest_is_required_even_when_gzip_digest_matches(package):
    folder, proof = package
    entry = proof['manifest']['archives']['api']
    archive = recovery.ensure_archive(folder, 'api', entry)
    entry['source_tar_sha256'] = '0' * 64
    with pytest.raises(recovery.RecoveryError, match='SOURCE_TAR_CHANGED'):
        recovery.verify_archive(archive, entry)


@pytest.mark.parametrize('parent,prefix', [('releases', ''), ('backups', 'academy-')])
def test_any_existing_stage_or_backup_blocks_import_resume(tmp_path, parent, prefix):
    for name in ('releases', 'backups'):
        (tmp_path / name).mkdir()
    recovery.require_pre_stage_boundary(tmp_path)
    target = tmp_path / parent / (prefix + recovery.CANDIDATE + '-evidence')
    target.mkdir()
    with pytest.raises(recovery.RecoveryError, match='PAST_IMPORT_RECOVERY_BOUNDARY'):
        recovery.require_pre_stage_boundary(tmp_path)
    assert target.is_dir()


def fake_activation(package, tmp_path):
    folder, proof = package
    root = tmp_path / 'production'
    root.mkdir()
    (root / 'releases').mkdir()
    (root / 'backups').mkdir()
    calls = []

    class OriginalActivation:
        def __init__(self, manifest, package):
            self.manifest, self.package, self.base = manifest, package, root / 'base'
            self.images = manifest['images']
            self.old_images = {'api': 'sha256:' + 'b' * 64, 'web': 'sha256:' + 'c' * 64}

        def verify_base(self):
            calls.append('verify_base')

        def image_check(self, *args):
            calls.append(('image_check', *args))

        def verify_runtime_dependencies(self):
            calls.append('runtime_dependencies')

        def stage(self, *args):
            calls.append('original_stage')

        def backup_migrate(self, *args):
            calls.append('original_backup_restore_migrate')

        def activate(self):
            calls.append('original_activate_with_rollback')

    def run(args, **kwargs):
        calls.append(tuple(args[:3]))
        if args[:3] == ['docker', 'image', 'inspect']:
            return json.dumps([{'Id': 'sha256:' + ('d' if '-api:' in args[3] else 'e') * 64}]).encode()
        return b''

    module = SimpleNamespace(Activation=OriginalActivation, ROOT=root,
        Upgrade=SimpleNamespace(image_check=Mock()), check_space=Mock(), run=Mock(side_effect=run),
        compose=Mock(return_value=json.dumps([recovery.MIGRATIONS['from']]).encode()))
    actual_config = 'sha256:' + '7' * 64
    transport = SimpleNamespace(source_config_digest=Mock(return_value=actual_config),
        verify_loaded_image=Mock(), cleanup_verified_transports=Mock())
    kind = recovery.recovery_type(module, transport)
    app = kind(copy.deepcopy(proof['manifest']), folder)
    return app, module, transport, kind, calls


def test_only_import_is_overridden_and_actual_config_is_checked_after_load(package, tmp_path):
    app, module, transport, kind, calls = fake_activation(package, tmp_path)
    for method in ('stage', 'backup_migrate', 'activate'):
        assert getattr(kind, method) is getattr(module.Activation, method)
    app.import_images()
    assert transport.source_config_digest.call_count == 2
    assert transport.source_config_digest.call_args_list[0].args[1] == package[1]['manifest']['archives']['api']['config_digest']
    assert transport.verify_loaded_image.call_args_list[0].args == ('sha256:' + 'd' * 64, 'sha256:' + '7' * 64)
    assert transport.verify_loaded_image.call_args_list[1].args == ('sha256:' + 'e' * 64, 'sha256:' + '7' * 64)
    assert app.images['api'] == 'sha256:' + 'd' * 64
    transport.cleanup_verified_transports.assert_called_once_with(app.package, app.manifest)
    module.Upgrade.image_check.assert_called_once_with(app, 'dbrestore', recovery.DBRESTORE)
    assert 'runtime_dependencies' in calls
    assert 'original_stage' not in calls


def test_changed_live_schema_stops_before_image_loading(package, tmp_path):
    app, module, transport, _, _ = fake_activation(package, tmp_path)
    module.compose.return_value = b'["0054_academy_covers"]'
    with pytest.raises(recovery.RecoveryError, match='LIVE_SCHEMA_CHANGED'):
        app.import_images()
    module.run.assert_not_called()
    transport.cleanup_verified_transports.assert_not_called()
    assert 'SET TRANSACTION READ ONLY' in module.compose.call_args.args[-1]


def test_bad_loaded_config_preserves_transports_and_never_imports_web(package, tmp_path):
    app, module, transport, _, _ = fake_activation(package, tmp_path)
    transport.verify_loaded_image.side_effect = AssertionError('IMAGE_CONFIG_CHANGED')
    with pytest.raises(AssertionError, match='IMAGE_CONFIG_CHANGED'):
        app.import_images()
    transport.cleanup_verified_transports.assert_not_called()
    loads = [call for call in module.run.call_args_list if call.args[0][:2] == ['docker', 'load']]
    assert len(loads) == 1
    assert (app.package / 'api.tar.gz').exists()
    assert not (app.package / 'web.tar.gz').exists()


def test_recovery_workflow_has_protected_exact_pins_and_no_image_reupload():
    workflow = (ROOT / '.github/workflows/academy-import-recovery.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert "github.ref == 'refs/heads/main' && inputs.expected_commit == github.sha" in workflow
    assert 'group: wp08-volcengine-staging' in workflow and 'cancel-in-progress: false' in workflow
    assert "source['conclusion']=='failure'" in workflow and "source['run_attempt']==1" in workflow
    assert "build['conclusion']=='success'" in workflow
    assert "source['head_sha']==candidate" in workflow and "build['head_sha']==candidate" in workflow
    assert "read_run('42037456146')" in workflow and "read_run('42035425027')" in workflow
    assert 'ref: ' + recovery.CANDIDATE in workflow
    assert 'python3 original-candidate/deploy/academy-release/package.py' in workflow
    assert 'scp "${opts[@]}" "$RUNNER_TEMP/import-recovery-controls/"*' in workflow
    assert 'control_sum=' in workflow and 'sha256sum -c - && sha256sum -c SHA256SUMS' in workflow
    assert 'transfer_package.py' not in workflow and 'resume_transfer.py' not in workflow
    assert 'candidate-package' not in workflow and 'docker build' not in workflow
    assert 'if: always() && steps.runner.outputs.cidr' in workflow
