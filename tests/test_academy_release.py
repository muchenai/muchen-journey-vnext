"""The combined release preserves its predecessor and rehearses the additive migration."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace
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
    sys.modules['disk_space'] = load('disk_space', 'deploy/academy-release/disk_space.py')
    sys.modules['image_transport'] = load('image_transport', 'deploy/academy-release/image_transport.py')
    release = load('academy_release', 'deploy/academy-release/activate.py')
transport = load('academy_transport', 'deploy/academy-release/image_transport.py')
space = load('academy_disk_space', 'deploy/academy-release/disk_space.py')


def manifest():
    data = json.loads((ROOT/'deploy/academy-release/baseline.json').read_text())
    data['candidate'] = 'a'*40
    return data


def prior(path):
    if path.name == 'schema-upgrade-prepared.json':
        return json.dumps({'manifest':{'candidate':release.BASE,'images':{'api':'sha256:'+'b'*64,'web':'sha256:'+'c'*64}}}).encode()
    return json.dumps({'release':release.BASE,'status':'PASS','schema':release.SOURCE_SCHEMA}).encode()


def test_exact_predecessor_schema_and_production_approval_gate():
    with patch.object(release,'read_file',side_effect=prior):
        app = release.Activation(manifest(),Path('/package'))
    assert str(app.base).endswith(release.BASE+'-badges-knowledge')
    assert str(app.new).endswith('-academy')
    assert release.SOURCE_SCHEMA == '0052_knowledge_publication'
    assert release.TARGET_SCHEMA == '0054_academy_covers'
    assert release.NEW_TABLES == ('academy_videos', 'academy_video_chunks', 'academy_courses', 'academy_learning_records', 'academy_course_covers')
    workflow = (ROOT/'.github/workflows/academy-release.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert "run['head_sha']==p['candidate']" in workflow
    grants = (ROOT/'deploy/academy-release/grant_runtime.py').read_text()
    assert all('public.' + name in grants for name in release.NEW_TABLES)
    assert 'install_project36_medals' not in (ROOT/'deploy/academy-release/activate.py').read_text()


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


def test_disk_gate_fails_before_a_small_filesystem_can_fill(tmp_path, monkeypatch):
    budget = space.disk_budget(100, 200, 50)
    assert budget['transfer'] > budget['import'] > 2*space.GIB
    monkeypatch.setattr(space.shutil, 'disk_usage', lambda _path: SimpleNamespace(free=budget['transfer']-1))
    with pytest.raises(RuntimeError, match='INSUFFICIENT_DISK_SPACE_TRANSFER'):
        space.check_space('TRANSFER', budget['transfer'], roots=[tmp_path])
    monkeypatch.setattr(space.shutil, 'disk_usage', lambda _path: SimpleNamespace(free=budget['transfer']))
    space.check_space('TRANSFER', budget['transfer'], roots=[tmp_path])


def export_archive(config):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        for name, raw in [('config.json', config), ('manifest.json', b'[{"Config":"config.json","Layers":[]}]')]:
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    data.seek(0)
    return data


def test_streamed_image_verification_rejects_changed_config_without_export_file():
    config = b'{"rootfs":{"diff_ids":["sha256:layer"]}}'
    expected = 'sha256:' + hashlib.sha256(config).hexdigest()
    transport.verify_export(export_archive(config), expected)
    with pytest.raises(AssertionError, match='IMAGE_CONFIG_CHANGED'):
        transport.verify_export(export_archive(config+b' '), expected)


def package_transports(directory):
    manifest = {'archives': {}}
    for name in ('api', 'web'):
        content = (name+'-verified-bytes').encode()
        digest = hashlib.sha256(content).hexdigest()
        (directory/(name+'.part0000')).write_bytes(content)
        (directory/(name+'.tar.gz')).write_bytes(content)
        manifest['archives'][name] = {'gzip_sha256': digest, 'chunks': [{'file':name+'.part0000', 'sha256':digest}]}
    return manifest


def test_transport_cleanup_plan_never_includes_backups_or_unknown_files(tmp_path):
    manifest = package_transports(tmp_path)
    for name in ('manifest.json','SHA256SUMS','activate.py','unrelated.tar.gz','canary.dump.enc'):
        (tmp_path/name).write_bytes(b'keep')
    plan = transport.transport_plan(tmp_path, manifest)
    assert {row[0].name for row in plan} == {'api.part0000','api.tar.gz','web.part0000','web.tar.gz'}
    (tmp_path/'web.part0000').write_bytes(b'changed')
    with pytest.raises(AssertionError, match='TRANSPORT_CHANGED'):
        transport.transport_plan(tmp_path, manifest)
    assert all(path.exists() for path, _, _ in plan), 'Validation cannot delete any package file'


def test_transport_cleanup_rejects_paths_outside_current_package(tmp_path):
    manifest = package_transports(tmp_path)
    manifest['archives']['api']['chunks'][0]['file'] = '../canary.dump.enc'
    with pytest.raises(AssertionError):
        transport.transport_plan(tmp_path, manifest)
    with pytest.raises(AssertionError):
        transport.cleanup_verified_transports(tmp_path, package_transports(tmp_path))


def test_existing_knowledge_favorites_are_included_in_preservation_fingerprint():
    guard = load('academy_facts_guard', 'deploy/academy-release/facts_guard.py')
    class Connection:
        def execute(self, query):
            sql = str(query)
            if 'information_schema.tables' in sql:
                return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ['knowledge_favorites','academy_courses']))
            if 'FROM "knowledge_favorites"' in sql:
                return SimpleNamespace(one=lambda: (7,'existing-favorites-hash'))
            if 'FROM "academy_courses"' in sql:
                return SimpleNamespace(scalar_one=lambda: 0)
            return None
    assert guard.snapshot(Connection()) == {'knowledge_favorites':[7,'existing-favorites-hash']}


def test_restore_cleanup_cannot_silently_leave_its_temporary_volume():
    with patch.dict(sys.modules):
        sys.modules['diagnose_backup'] = load('academy_diagnose_backup', 'deploy/admin-reviewed/diagnose_backup.py')
        restore = load('academy_restore_backup', 'deploy/academy-release/restore_backup.py')
    with patch.object(restore.subprocess, 'run', side_effect=[SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)]) as command:
        assert not restore.cleanup_restore_resources('owned-restore', 'owned-network', container_created=True, network_created=True)
        assert command.call_args_list[0].args[0] == ['docker','rm','-f','-v','owned-restore']
        assert command.call_args_list[1].args[0] == ['docker','network','rm','owned-network']
        assert all(call.kwargs['timeout'] == 60 for call in command.call_args_list)
    with patch.object(restore.subprocess, 'run') as command:
        assert restore.cleanup_restore_resources('unowned', 'unowned', container_created=False, network_created=False)
        command.assert_not_called()
