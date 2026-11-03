"""Only hash-verified image transport copies can be reclaimed by this recovery."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'deploy/badges-knowledge'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

with patch.dict(sys.modules):
    sys.modules['diagnose_restore'] = load('diagnose_restore')
    recovery = load('recover_disk')


def image_export(config=b'{"rootfs":{"diff_ids":["sha256:verified"]}}'):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, raw in [('config.json', config), ('manifest.json',b'[{"Config":"config.json","Layers":[]}]')]:
            member = tarfile.TarInfo(name); member.size = len(raw)
            archive.addfile(member,io.BytesIO(raw))
    output.seek(0)
    return output, 'sha256:'+hashlib.sha256(config).hexdigest()


def test_streaming_export_proves_config_without_another_disk_copy():
    stream, expected = image_export()
    recovery.verify_export(stream,expected)
    stream, _ = image_export(b'changed')
    with pytest.raises(AssertionError,match='IMAGE_CONFIG_CHANGED'):
        recovery.verify_export(stream,expected)


def manifest(tmp_path):
    result = {'archives':{}}
    for name in ('api','web'):
        data = (name+'transport').encode()
        (tmp_path/(name+'.part0000')).write_bytes(data)
        (tmp_path/(name+'.tar.gz')).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        result['archives'][name] = {'gzip_sha256':digest,'chunks':[{'file':name+'.part0000','sha256':digest}]}
    return result


def test_cleanup_plan_contains_only_exact_transport_files_and_preserves_other_files(tmp_path):
    data = manifest(tmp_path)
    for name in ('before.json','canary.dump.enc','manifest.json','secrets.env'):
        (tmp_path/name).write_bytes(b'preserve')
    plan = recovery.transport_files(tmp_path,data)
    assert {row[0].name for row in plan} == {'api.part0000','web.part0000','api.tar.gz','web.tar.gz'}
    assert all((tmp_path/name).read_bytes()==b'preserve' for name in ('before.json','canary.dump.enc','manifest.json','secrets.env'))


@pytest.mark.parametrize('change',['path','checksum','duplicate','unexpected_archive','corrupted'])
def test_unsafe_or_changed_artifacts_are_rejected(tmp_path,change):
    data = manifest(tmp_path)
    if change=='path': data['archives']['api']['chunks'][0]['file']='../before.json'
    if change=='checksum': data['archives']['api']['chunks'][0]['sha256']='0'*64
    if change=='duplicate': data['archives']['api']['chunks']*=2
    if change=='unexpected_archive': data['archives']['business']={}
    if change=='corrupted': (tmp_path/'api.tar.gz').write_bytes(b'changed')
    with pytest.raises(AssertionError):
        recovery.transport_files(tmp_path,data)


def test_already_reclaimed_transport_copies_are_not_required_or_recreated(tmp_path):
    data = manifest(tmp_path)
    for path in tmp_path.iterdir(): path.unlink()
    assert recovery.transport_files(tmp_path,data) == []


def test_recovery_keeps_original_application_and_production_approval_boundary():
    assert recovery.CANDIDATE == '2bab0cefe55447c9d64af81dd5c52f5db67db09c'
    source = (ROOT/'deploy/badges-knowledge/recover_disk.py').read_text()
    workflow = (ROOT/'.github/workflows/badges-knowledge-recover.yml').read_text()
    assert 'docker image prune' not in source and 'docker volume prune' not in source
    assert 'release.backup_migrate(' in source and 'release.activate()' in source
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert 'recover_disk.py' in workflow and 'diagnose_restore.py' in workflow
